#!/usr/bin/env python3
"""Set one synthetic pose and display observed state; not an acceptance runner."""

import argparse
import json
import math
import time

import rclpy
from rclpy.parameter import Parameter
from rclpy.parameter_client import AsyncParameterClient
from rclpy.time import Time
from sensor_msgs.msg import JointState
from tf2_ros import Buffer, TransformException, TransformListener


def main():
    parser = argparse.ArgumentParser(description='设置 C++ 合成姿态并显示实际状态/TF')
    parser.add_argument('positions', nargs=2, type=float, metavar='RAD')
    parser.add_argument('--node', default='/synthetic_joint_publisher')
    parser.add_argument('--timeout', type=float, default=5.0)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout must be positive and finite')

    rclpy.init()
    node = rclpy.create_node('arm_pose_client')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    samples = []
    subscription = node.create_subscription(
        JointState, '/joint_states', lambda msg: samples.append(msg), 10,
    )
    try:
        client = AsyncParameterClient(node, args.node)
        if not client.wait_for_services(timeout_sec=args.timeout):
            raise RuntimeError(f'parameter services unavailable: {args.node}')
        future = client.set_parameters_atomically([
            Parameter('positions', Parameter.Type.DOUBLE_ARRAY, args.positions),
        ])
        rclpy.spin_until_future_complete(node, future, timeout_sec=args.timeout)
        if not future.done():
            raise RuntimeError('parameter response timed out; application status unknown')
        result = future.result().result
        print(json.dumps({
            'accepted': result.successful, 'reason': result.reason,
        }, ensure_ascii=False), flush=True)
        if not result.successful:
            return 1

        # Display a newly received sample and the TF at that sample's timestamp.
        # No analytical expected values, tolerance checks, or pass report here.
        samples.clear()
        observed_after = node.get_clock().now().nanoseconds
        deadline = time.monotonic() + args.timeout
        sample = None
        transform = None
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            if sample is None and samples:
                latest = samples[-1]
                if Time.from_msg(latest.header.stamp).nanoseconds >= observed_after:
                    sample = latest
            samples.clear()
            if sample is not None:
                try:
                    transform = buffer.lookup_transform(
                        'base_link', 'tool0', Time.from_msg(sample.header.stamp),
                    )
                    break
                except TransformException:
                    pass
        if sample is None or transform is None:
            raise RuntimeError('pose accepted, but fresh JointState/TF observation timed out')
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        print(json.dumps({
            'observation_only': True,
            'stamp': {'sec': sample.header.stamp.sec, 'nanosec': sample.header.stamp.nanosec},
            'names': list(sample.name), 'positions': list(sample.position),
            'velocity': list(sample.velocity), 'effort': list(sample.effort),
            'base_link_to_tool0': {
                'xyz': [translation.x, translation.y, translation.z],
                'xyzw': [rotation.x, rotation.y, rotation.z, rotation.w],
            },
        }, ensure_ascii=False), flush=True)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(str(error), flush=True)
        return 2
    finally:
        node.destroy_subscription(subscription)
        listener.unregister()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
