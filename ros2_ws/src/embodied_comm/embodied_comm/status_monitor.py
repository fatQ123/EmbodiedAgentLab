"""订阅传感器状态，并用单调时钟检测数据中断。"""
import time
from rclpy.node import Node
from rclpy.clock import Clock, ClockType
from std_msgs.msg import String

from embodied_comm.common import (
    SENSOR_TOPIC, TASK_STATUS_TOPIC, parse_sensor, parse_task_status,
    positive_parameter, run_node,
)


class StatusMonitor(Node):
    def __init__(self, **kwargs):
        super().__init__('status_monitor', **kwargs)
        try:
            self.timeout_sec = positive_parameter(self, 'timeout_sec', 3.0)
        except Exception:
            self.destroy_node()
            raise
        self.last_received_at = time.monotonic()
        self.timed_out = False
        self.latest_reading = None
        self.received_count = 0
        self.subscription = self.create_subscription(String, SENSOR_TOPIC, self.receive, 10)
        self.latest_task_status = None
        self.task_status_count = 0
        self.task_subscription = self.create_subscription(
            String, TASK_STATUS_TOPIC, self.receive_task_status, 10,
        )
        # 不依赖仿真时钟；即使 /clock 暂停也能发现消息中断。
        self.check_period = min(0.1, self.timeout_sec / 2.0)
        self.timeout_timer = self.create_timer(
            self.check_period, self.check_timeout,
            clock=Clock(clock_type=ClockType.STEADY_TIME),
        )
        self.get_logger().info(
            f'监控器已启动：话题={self.subscription.topic_name}，超时={self.timeout_sec:.2f} 秒'
        )

    def receive(self, message):
        try:
            reading = parse_sensor(message.data)
        except (ValueError, OverflowError) as exc:
            self.get_logger().warning(f'忽略非法传感器消息：{exc}')
            return
        self.last_received_at = time.monotonic()
        if self.timed_out:
            self.get_logger().info('传感器消息已恢复')
        self.timed_out = False
        self.latest_reading = reading
        self.received_count += 1
        self.get_logger().info(f'收到传感器：seq={reading["seq"]}，value={reading["value"]:.1f}')

    def receive_task_status(self, message):
        try:
            status = parse_task_status(message.data)
        except ValueError as exc:
            self.get_logger().warning(f'忽略非法任务状态：{exc}')
            return
        self.latest_task_status = status
        self.task_status_count += 1
        # 任务按请求发生，不重置传感器超时计时，也不为任务话题设置超时。
        self.get_logger().info(
            f'收到任务结果：task_id={status["task_id"]}，success={status["success"]}，'
            f'sensor_seq={status["sensor_seq"]}，{status["message"]}'
        )

    def check_timeout(self):
        elapsed = time.monotonic() - self.last_received_at
        if elapsed >= self.timeout_sec and not self.timed_out:
            self.timed_out = True
            self.get_logger().warning(f'传感器消息超时：已 {elapsed:.2f} 秒没有有效消息')


def main(args=None):
    run_node(StatusMonitor, args)
