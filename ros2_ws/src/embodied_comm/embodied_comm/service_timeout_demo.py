"""用客户端截止时间演示 ROS 2 Service 响应超时."""
import argparse
import math
import sys
import time

from embodied_comm.common import EXECUTE_TASK_SERVICE
import rclpy
from rclpy.node import Node
from rclpy.utilities import remove_ros_args
from std_srvs.srv import Trigger


EXIT_SUCCESS = 0
EXIT_SERVICE_FAILED = 2
EXIT_UNAVAILABLE = 5
EXIT_TIMEOUT = 6


def positive_float(text):
    """把命令行文本解析成有限正数."""
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('必须是数值') from exc
    if not math.isfinite(value) or value <= 0.0:
        raise argparse.ArgumentTypeError('必须是有限正数')
    return value


class ServiceTimeoutDemo(Node):
    """调用快速服务，并由客户端决定最长等待时间."""

    def __init__(self, **kwargs):
        super().__init__('service_timeout_demo', **kwargs)
        self.client = self.create_client(Trigger, EXECUTE_TASK_SERVICE)

    def run(self, response_timeout, discovery_timeout=5.0):
        if not self.client.wait_for_service(timeout_sec=discovery_timeout):
            self.get_logger().error(
                f'服务发现超时：{EXECUTE_TASK_SERVICE}'
            )
            return EXIT_UNAVAILABLE

        started_at = time.monotonic()
        future = self.client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(
            self, future, timeout_sec=response_timeout,
        )
        elapsed = time.monotonic() - started_at
        if not future.done():
            self.client.remove_pending_request(future)
            self.get_logger().error(
                f'服务响应超时：等待 {elapsed:.2f} 秒，'
                f'客户端截止时间={response_timeout:.2f} 秒'
            )
            return EXIT_TIMEOUT

        response = future.result()
        self.get_logger().info(
            f'服务响应：elapsed={elapsed:.2f} 秒，'
            f'success={response.success}，message={response.message}'
        )
        return EXIT_SUCCESS if response.success else EXIT_SERVICE_FAILED


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description='调用 /execute_task 并在客户端截止时间到达后退出。',
    )
    parser.add_argument(
        '--response-timeout', type=positive_float, default=1.0,
        help='服务请求发出后等待响应的最长秒数，默认 1.0。',
    )
    parser.add_argument(
        '--discovery-timeout', type=positive_float, default=5.0,
        help='等待服务端被发现的最长秒数，默认 5.0。',
    )
    if args is None:
        cli_args = remove_ros_args()[1:]
    else:
        cli_args = remove_ros_args(
            args=['service_timeout_demo', *args],
        )[1:]
    return parser.parse_args(cli_args)


def main(args=None):
    parsed = parse_args(args)
    rclpy.init(args=None if args is None else [])
    node = ServiceTimeoutDemo()
    try:
        exit_code = node.run(
            parsed.response_timeout,
            discovery_timeout=parsed.discovery_timeout,
        )
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    if args is None:
        raise SystemExit(exit_code)
    return exit_code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
