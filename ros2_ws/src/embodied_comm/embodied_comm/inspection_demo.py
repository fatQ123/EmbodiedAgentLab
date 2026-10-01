"""生产线工件质检 Action 的命令行演示客户端."""
import argparse
import sys

from action_msgs.msg import GoalStatus
from embodied_comm.common import EXECUTE_TASK_ACTION
from embodied_interfaces.action import ExecuteTask
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.utilities import remove_ros_args


EXIT_SUCCESS = 0
EXIT_ABORTED = 2
EXIT_CANCELED = 3
EXIT_REJECTED = 4
EXIT_UNAVAILABLE = 5

STATUS_NAMES = {
    GoalStatus.STATUS_SUCCEEDED: 'SUCCEEDED',
    GoalStatus.STATUS_CANCELED: 'CANCELED',
    GoalStatus.STATUS_ABORTED: 'ABORTED',
}


class InspectionDemo(Node):
    def __init__(self):
        super().__init__('inspection_demo')
        self.action_client = ActionClient(self, ExecuteTask, EXECUTE_TASK_ACTION)
        self.goal_handle = None
        self.cancel_at = None
        self.cancel_requested = False
        self.cancel_future = None

    def request_cancel(self):
        """在目标句柄可用后发送一次取消，兼容 0% 立即取消."""
        if self.goal_handle is not None and self.cancel_future is None:
            self.cancel_future = self.goal_handle.cancel_goal_async()

    def feedback_callback(self, wrapped_feedback):
        feedback = wrapped_feedback.feedback
        self.get_logger().info(
            f'质检反馈：phase={feedback.phase}，'
            f'progress={feedback.progress_percent:.1f}%'
        )
        if (self.cancel_at is not None and not self.cancel_requested
                and feedback.progress_percent >= self.cancel_at):
            self.cancel_requested = True
            self.get_logger().warning(
                f'模拟安全联锁：进度达到 {feedback.progress_percent:.1f}%，请求取消'
            )
            self.request_cancel()

    def run(self, task_name, duration_sec, cancel_at=None, timeout_sec=5.0):
        self.cancel_at = cancel_at
        if not self.action_client.wait_for_server(timeout_sec=timeout_sec):
            self.get_logger().error(f'等待 Action Server 超时：{EXECUTE_TASK_ACTION}')
            return EXIT_UNAVAILABLE

        goal = ExecuteTask.Goal()
        goal.task_name = task_name
        goal.duration_sec = duration_sec
        send_future = self.action_client.send_goal_async(
            goal, feedback_callback=self.feedback_callback,
        )
        rclpy.spin_until_future_complete(self, send_future, timeout_sec=timeout_sec)
        if not send_future.done():
            self.get_logger().error('等待目标响应超时')
            return EXIT_UNAVAILABLE

        self.goal_handle = send_future.result()
        if not self.goal_handle.accepted:
            self.get_logger().error(f'目标被拒绝：task_name={task_name}')
            return EXIT_REJECTED
        if self.cancel_requested:
            self.request_cancel()
        self.get_logger().info(
            f'目标已接受：task_name={task_name}，duration={duration_sec:.2f} 秒'
        )

        result_future = self.goal_handle.get_result_async()
        # 合法任务最长 300 秒；额外预留响应和调度时间。
        result_timeout = max(timeout_sec, duration_sec + timeout_sec)
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=result_timeout)
        if not result_future.done():
            self.get_logger().error('等待任务结果超时')
            return EXIT_UNAVAILABLE

        wrapped_result = result_future.result()
        result = wrapped_result.result
        status_name = STATUS_NAMES.get(wrapped_result.status, str(wrapped_result.status))
        self.get_logger().info(
            f'最终状态={status_name}，success={result.success}，'
            f'sensor_seq={result.sensor_seq}，message={result.message}'
        )
        if wrapped_result.status == GoalStatus.STATUS_SUCCEEDED and result.success:
            return EXIT_SUCCESS
        if wrapped_result.status == GoalStatus.STATUS_CANCELED:
            return EXIT_CANCELED
        return EXIT_ABORTED


def parse_args(args=None):
    parser = argparse.ArgumentParser(description='运行一次模拟生产线工件质检长任务。')
    parser.add_argument('--task-name', required=True, help='工件或工序追踪名称。')
    parser.add_argument('--duration', required=True, type=float, help='模拟执行时长，单位秒。')
    parser.add_argument(
        '--cancel-at', type=float, default=None, metavar='PERCENT',
        help='达到指定百分比后发送取消请求；省略则正常完成。',
    )
    if args is None:
        cli_args = remove_ros_args()[1:]
    else:
        cli_args = remove_ros_args(args=['inspection_demo', *args])[1:]
    parsed = parser.parse_args(cli_args)
    if parsed.cancel_at is not None and not 0.0 <= parsed.cancel_at < 100.0:
        parser.error('--cancel-at 必须位于 [0, 100)')
    return parsed


def main(args=None):
    parsed = parse_args(args)
    rclpy.init(args=None if args is None else [])
    node = InspectionDemo()
    try:
        exit_code = node.run(
            parsed.task_name, parsed.duration, cancel_at=parsed.cancel_at,
        )
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    if args is None:
        raise SystemExit(exit_code)
    return exit_code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
