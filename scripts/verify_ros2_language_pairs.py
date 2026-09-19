#!/usr/bin/env python3
"""实测四组语言组合；主项目另验证话题错连与修复。需加载待验收工作空间。"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String


def check_pair(output, publisher_lang, subscriber_lang, domain, official):
    folder = output / f'{publisher_lang}-to-{subscriber_lang}'
    folder.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, ROS_DOMAIN_ID=str(domain), ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    env.setdefault('ROS_LOG_DIR', str(output / 'ros-logs'))
    topic = '/topic' if official else '/sensor_state'
    if official:
        pub_package = f'examples_{publisher_lang}_minimal_publisher'
        sub_package = f'examples_{subscriber_lang}_minimal_subscriber'
        pub_executable, sub_executable = 'publisher_member_function', 'subscriber_member_function'
    else:
        pub_package = 'embodied_comm_cpp' if publisher_lang == 'rclcpp' else 'embodied_comm'
        sub_package = 'embodied_comm_cpp' if subscriber_lang == 'rclcpp' else 'embodied_comm'
        pub_executable, sub_executable = 'sensor_simulator', 'status_monitor'
    context = Context()
    context.init(args=[], domain_id=domain)
    probe = Node('language_pair_probe', context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(probe)
    processes = []

    def start(label, package, executable, extra=()):
        stream = (folder / f'{label}.log').open('w')
        command = ['ros2', 'run', package, executable, *extra]
        proc = subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True)
        record = (proc, stream)
        processes.append(record)
        return record

    def stop(record):
        proc, stream = record
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)
        stream.close()
        processes.remove(record)
        upstream_interrupt = (official and proc.returncode == 254
                              and 'KeyboardInterrupt' in Path(stream.name).read_text())
        assert proc.returncode == 0 or upstream_interrupt, f'{folder}: exit={proc.returncode}'
        report['process_exits'].append({'log': Path(stream.name).name,
                                        'code': proc.returncode,
                                        'upstream_keyboard_interrupt': upstream_interrupt})

    def wait(predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=.05)
        assert predicate(), f'{folder}: 等待通信超时'

    def endpoint_count(name):
        return len(probe.get_subscriptions_info_by_topic(name))

    report = {'domain': domain, 'topic': topic, 'type': 'std_msgs/msg/String', 'cases': [], 'process_exits': []}
    try:
        start('publisher', pub_package, pub_executable,
              [] if official else ['--ros-args', '-p', 'publish_rate:=5.0'])
        for phase in (['normal'] if official else ['normal', 'wrong', 'repaired']):
            sub_topic = '/sensor_state_wrong' if phase == 'wrong' else topic
            extra = ['--ros-args', '-r', f'{topic}:={sub_topic}'] if phase == 'wrong' else []
            subscriber = start(phase + '-subscriber', sub_package, sub_executable, extra)
            wait(lambda: len(probe.get_publishers_info_by_topic(topic)) == 1
                 and endpoint_count(sub_topic) == 1)
            sub_log = folder / f'{phase}-subscriber.log'
            samples = []
            times = []

            def receive(message):
                samples.append(message.data)
                times.append(time.monotonic())

            observation = probe.create_subscription(String, topic, receive, 10)
            try:
                wait(lambda: len(samples) >= 10)
            finally:
                probe.destroy_subscription(observation)
            seqs = ([int(re.search(r'(\d+)\D*$', text).group(1)) for text in samples]
                    if official else [json.loads(text)['seq'] for text in samples])
            assert all(b > a for a, b in zip(seqs, seqs[1:])), samples
            hz = (len(times) - 1) / (times[-1] - times[0])
            expected_hz = 2.0 if official else 5.0
            assert expected_hz * .7 < hz < expected_hz * 1.3, hz
            if phase == 'wrong':
                assert len(probe.get_publishers_info_by_topic(sub_topic)) == 0
                assert '收到传感器' not in sub_log.read_text()
            else:
                marker = 'I heard' if official else '收到传感器'
                wait(lambda: marker in sub_log.read_text())
            report['cases'].append({'phase': phase, 'subscriber_topic': sub_topic,
                                    'publisher_count': 1,
                                    'subscriber_count_before_probe': 1,
                                    'received_samples_at_probe': samples,
                                    'measured_hz': round(hz, 3),
                                    'subscriber_received': phase != 'wrong'})
            stop(subscriber)
            wait(lambda: endpoint_count(sub_topic) == 0)
    finally:
        try:
            for record in list(processes):
                stop(record)
        finally:
            executor.shutdown()
            probe.destroy_node()
            context.try_shutdown()
    (folder / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'{publisher_lang} → {subscriber_lang}: 通过', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--domain-start', default=194, type=int)
    parser.add_argument('--official', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.domain_start <= 229:
        parser.error('连续四个域必须位于 0～232')
    for index, (pub, sub) in enumerate([('rclpy', 'rclpy'), ('rclcpp', 'rclcpp'),
                                       ('rclpy', 'rclcpp'), ('rclcpp', 'rclpy')]):
        check_pair(args.output.resolve(), pub, sub, args.domain_start + index, args.official)


if __name__ == '__main__':
    main()
