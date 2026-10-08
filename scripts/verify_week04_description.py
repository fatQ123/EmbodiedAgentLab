#!/usr/bin/env python3
"""Observe an already running headless week-04 display launch; never start nodes/GUI.

Exit codes: 0 passed, 1 failed/timed out, 2 environment blocked or observer error,
130 interrupted. --output is a new JSON file and is never overwritten.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET


JOINT_TOL = 1e-12
TF_TOL = 1e-9
MIN_SAMPLES = 10
MIN_WINDOW = 2.0
HZ_RANGE = (15.0, 25.0)
MAX_AGE = 1.0
EXPECTED_EDGES = {
    ('base_link', 'link1'): [0.0, 0.0, 0.0],
    ('link1', 'link2'): [0.4, 0.0, 0.0],
    ('link2', 'tool0'): [0.3, 0.0, 0.0],
    ('base_link', 'tool0'): [0.7, 0.0, 0.0],
}


def joint_errors(sample):
    errors = []
    names, positions = sample['names'], sample['positions']
    if len(names) != 2 or set(names) != {'joint1', 'joint2'}:
        errors.append('joint names must contain joint1 and joint2 exactly once')
    if len(positions) != len(names):
        errors.append('joint name/position lengths differ')
    if any(not math.isfinite(value) or abs(value) > JOINT_TOL for value in positions):
        errors.append('joint positions are not finite zero values')
    return errors


def transform_errors(translation, quaternion, expected):
    if not all(math.isfinite(value) for value in translation + quaternion):
        return ['non-finite TF']
    errors = []
    if any(abs(value-wanted) > TF_TOL for value, wanted in zip(translation, expected)):
        errors.append(f'TF translation differs from {expected}')
    if abs(sum(value*value for value in quaternion)-1) > TF_TOL:
        errors.append('TF quaternion is not unit length')
    if any(abs(value) > TF_TOL for value in quaternion[:3]) or abs(abs(quaternion[3])-1) > TF_TOL:
        errors.append('zero-pose TF orientation is not identity')
    return errors


def description_errors(text):
    try:
        root = ET.fromstring(text)
        links = root.findall('link')
        joints = root.findall('joint')
        if root.tag != 'robot' or len(links) != 4 or len(joints) != 3:
            return ['description does not have four links and three joints']
        if {item.attrib['name'] for item in links} != {'base_link', 'link1', 'link2', 'tool0'}:
            return ['description link names differ']
        edges = {(item.find('parent').attrib['link'], item.find('child').attrib['link'])
                 for item in joints}
        if edges != set(EXPECTED_EDGES) - {('base_link', 'tool0')}:
            return ['description parent/child chain differs']
    except (ET.ParseError, AttributeError, KeyError) as error:
        return [f'invalid robot_description: {error}']
    return []


def publisher_snapshot(node, topic):
    return [{'node_name': info.node_name, 'node_namespace': info.node_namespace,
             'topic_type': info.topic_type, 'endpoint_gid': list(info.endpoint_gid)}
            for info in node.get_publishers_info_by_topic(topic)]


def publisher_errors(publishers, expected_name, expected_type):
    if len(publishers) != 1:
        return [f'expected one publisher from {expected_name}, received {len(publishers)}']
    endpoint = publishers[0]
    if (endpoint['node_name'], endpoint['node_namespace'], endpoint['topic_type']) != (
            expected_name, '/', expected_type):
        return [f'unexpected publisher endpoint: {endpoint}']
    return []


def observe(args, report):
    # Imports are delayed so --help and pure validator tests do not need ROS.
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from rclpy.time import Time
    from sensor_msgs.msg import JointState
    from std_msgs.msg import String
    from tf2_ros import Buffer, TransformException, TransformListener

    rclpy.init(args=[])
    node = None
    try:
        node = rclpy.create_node(f'week04_description_observer_{os.getpid()}')
        report['observer_node'] = node.get_fully_qualified_name()
        try:
            from ament_index_python.packages import get_package_share_directory
            report['package_versions'] = {}
            for package in ('rclpy', 'tf2_ros', 'robot_state_publisher', 'joint_state_publisher'):
                root = ET.parse(Path(get_package_share_directory(package)) / 'package.xml').getroot()
                report['package_versions'][package] = root.findtext('version')
        except (ImportError, LookupError, OSError, ET.ParseError) as error:
            report['package_version_error'] = str(error)

        buffer = Buffer()
        listener = TransformListener(buffer, node, spin_thread=False)
        samples, descriptions, invalid_samples = [], [], []
        started = time.monotonic()
        deadline = started + args.timeout

        def on_joint(message):
            sample = {'received_monotonic_s': time.monotonic(),
                      'stamp_ns': message.header.stamp.sec * 10**9 + message.header.stamp.nanosec,
                      'names': list(message.name), 'positions': list(message.position),
                      'velocities': list(message.velocity), 'efforts': list(message.effort)}
            errors = joint_errors(sample)
            if errors:
                invalid_samples.append({'index': len(samples), 'errors': errors})
            samples.append(sample)

        def on_description(message):
            descriptions.append({'received_monotonic_s': time.monotonic(),
                                 'sha256': hashlib.sha256(message.data.encode()).hexdigest(),
                                 'xml': message.data, 'errors': description_errors(message.data)})

        node.create_subscription(JointState, '/joint_states', on_joint, 100)
        node.create_subscription(String, '/robot_description', on_description,
                                 QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                                            reliability=ReliabilityPolicy.RELIABLE,
                                            durability=DurabilityPolicy.TRANSIENT_LOCAL))

        def assess():
            errors, transforms = [], []
            graph = {topic: publisher_snapshot(node, topic)
                     for topic in ('/joint_states', '/robot_description', '/tf', '/tf_static')}
            for topic, name, topic_type in (
                    ('/joint_states', 'joint_state_publisher', 'sensor_msgs/msg/JointState'),
                    ('/robot_description', 'robot_state_publisher', 'std_msgs/msg/String'),
                    ('/tf', 'robot_state_publisher', 'tf2_msgs/msg/TFMessage'),
                    ('/tf_static', 'robot_state_publisher', 'tf2_msgs/msg/TFMessage')):
                errors.extend(f'{topic}: {error}' for error in publisher_errors(graph[topic], name, topic_type))
            nodes = [{'name': name, 'namespace': namespace}
                     for name, namespace in node.get_node_names_and_namespaces()]
            identities = [(item['name'], item['namespace']) for item in nodes]
            for name in ('robot_state_publisher', 'joint_state_publisher'):
                if identities.count((name, '/')) != 1:
                    errors.append(f'expected exactly one root namespace {name} node')
            if any('joint_state_publisher_gui' == item['name'] or item['name'].startswith('rviz')
                   for item in nodes):
                errors.append('GUI node detected in headless acceptance graph')
            if not descriptions:
                errors.append('no transient-local robot_description received')
            else:
                errors.extend(error for item in descriptions for error in item['errors'])
                if len({item['sha256'] for item in descriptions}) != 1:
                    errors.append('robot_description changed during observation')
            rate = None
            window = samples[-1]['received_monotonic_s']-samples[0]['received_monotonic_s'] if len(samples) > 1 else 0
            if len(samples) < MIN_SAMPLES or window < MIN_WINDOW:
                errors.append(f'insufficient stable window: {len(samples)} samples over {window:.3f}s')
            if window > 0:
                rate = (len(samples)-1) / window
                if not HZ_RANGE[0] <= rate <= HZ_RANGE[1]:
                    errors.append(f'JointState rate {rate:.3f}Hz outside {HZ_RANGE}')
            if invalid_samples:
                errors.append(f'{len(invalid_samples)} malformed/nonzero joint samples')
            stamps = [sample['stamp_ns'] for sample in samples]
            if any(stamp <= 0 for stamp in stamps) or any(b <= a for a, b in zip(stamps, stamps[1:])):
                errors.append('JointState stamps are zero or not strictly increasing')
            now_ns = node.get_clock().now().nanoseconds
            if samples and not -0.1 <= (now_ns-stamps[-1])/1e9 <= MAX_AGE:
                errors.append('latest JointState timestamp is stale or in the future')
            for (parent, child), expected in EXPECTED_EDGES.items():
                try:
                    value = buffer.lookup_transform(parent, child, Time())
                    translation = [value.transform.translation.x, value.transform.translation.y,
                                   value.transform.translation.z]
                    quaternion = [value.transform.rotation.x, value.transform.rotation.y,
                                  value.transform.rotation.z, value.transform.rotation.w]
                    stamp = value.header.stamp.sec * 10**9 + value.header.stamp.nanosec
                    transform_record = {'parent': parent, 'child': child, 'translation': translation,
                                        'quaternion_xyzw': quaternion, 'stamp_ns': stamp}
                    if (parent, child) != ('link2', 'tool0'):
                        transform_record['age_s'] = (now_ns-stamp)/1e9
                        if stamp <= 0 or not -0.1 <= transform_record['age_s'] <= MAX_AGE:
                            errors.append(f'{parent}->{child}: stale/zero/future dynamic TF stamp')
                    transforms.append(transform_record)
                    errors.extend(f'{parent}->{child}: {error}'
                                  for error in transform_errors(translation, quaternion, expected))
                except TransformException as error:
                    errors.append(f'{parent}->{child}: unavailable TF: {error}')
            return {'errors': errors, 'publishers': graph, 'nodes': nodes, 'transforms': transforms,
                    'joint_rate_hz': rate, 'sample_window_s': window}

        assessment = None
        try:
            while time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=min(0.1, max(0.0, deadline-time.monotonic())))
                # Graph/TF checks are bounded and run only after enough data or at deadline.
                if len(samples) >= MIN_SAMPLES and time.monotonic()-started >= MIN_WINDOW:
                    assessment = assess()
                    if not assessment['errors']:
                        report['status'] = 'passed'
                        break
            if report['status'] != 'passed':
                report['status'] = 'failed'
                report['failure_reason'] = 'observation deadline expired before every criterion passed'
                assessment = assess()
        except ExternalShutdownException as error:
            # ROS signal handlers can shut down the context before spin returns.
            # Preserve the same interrupted outcome as Python's SIGINT handler.
            raise KeyboardInterrupt('ROS context shut down during observation') from error
        finally:
            report.update({'joint_samples': samples, 'invalid_joint_samples': invalid_samples,
                           'robot_descriptions': descriptions, 'assessment': assessment,
                           'elapsed_s': time.monotonic()-started})
            listener.unregister()
    finally:
        if node is not None:
            node.destroy_node()
        # SIGINT may already have closed this context; cleanup must be idempotent
        # and must not replace KeyboardInterrupt with an RCLError.
        rclpy.try_shutdown()


def json_safe(value):
    """Keep invalid numeric evidence without emitting nonstandard JSON NaN tokens."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new JSON evidence file')
    parser.add_argument('--timeout', type=float, default=15.0, help='wall-time observation deadline, 3..120 s')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 3 <= args.timeout <= 120:
        parser.error('--timeout must be finite and in [3,120] seconds')
    if args.output.exists():
        parser.error('--output already exists; preserve earlier evidence and choose a new file')
    report = {'status': 'not_run', 'started_utc': datetime.now(timezone.utc).isoformat(),
              'command': [sys.executable, str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)],
              'python': sys.version, 'environment': {key: os.environ.get(key) for key in (
                  'ROS_DOMAIN_ID', 'ROS_DISTRO', 'ROS_AUTOMATIC_DISCOVERY_RANGE', 'ROS_LOG_DIR', 'RMW_IMPLEMENTATION')},
              'criteria': {'minimum_samples': MIN_SAMPLES, 'minimum_window_s': MIN_WINDOW,
                           'joint_zero_tolerance_rad': JOINT_TOL, 'tf_tolerance': TF_TOL,
                           'joint_frequency_hz_range': HZ_RANGE, 'maximum_dynamic_age_s': MAX_AGE},
              'manual_rviz_acceptance': 'pending_manual_acceptance'}
    exit_code = 2
    try:
        observe(args, report)
        exit_code = 0 if report['status'] == 'passed' else 1
    except ImportError as error:
        report.update(status='environment_blocked', error=f'{type(error).__name__}: {error}')
    except KeyboardInterrupt:
        report.update(status='interrupted', error='observer interrupted; target launch was not stopped')
        exit_code = 130
    except Exception as error:
        report.update(status='observer_error', error=f'{type(error).__name__}: {error}')
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    report['exit_code'] = exit_code
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(json_safe(report), stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(f"{report['status']}: {args.output.resolve()}")
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
