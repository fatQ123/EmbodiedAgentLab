"""监控传感器和任务状态，并发布标准 ROS 诊断消息."""
import time

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from embodied_comm.common import (
    DIAGNOSTICS_TOPIC, parse_sensor, parse_task_status, positive_parameter,
    run_node, sensor_qos, SENSOR_TOPIC, TASK_STATUS_TOPIC,
)
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import qos_check_compatible, QoSCompatibility
from std_msgs.msg import String


class StatusMonitor(Node):
    """把传感器流状态转换为日志和 DiagnosticArray."""

    def __init__(self, **kwargs):
        super().__init__('status_monitor', **kwargs)
        try:
            self.timeout_sec = positive_parameter(self, 'timeout_sec', 3.0)
            self.diagnostic_rate = positive_parameter(self, 'diagnostic_rate', 1.0)
        except Exception:
            self.destroy_node()
            raise
        self.last_received_at = time.monotonic()
        self.timed_out = False
        self.latest_reading = None
        self.received_count = 0
        self.invalid_count = 0
        self.publisher_seen = False
        self.sensor_qos = sensor_qos('reliable')
        self.subscription = self.create_subscription(
            String, SENSOR_TOPIC, self.receive, self.sensor_qos,
        )
        self.latest_task_status = None
        self.task_status_count = 0
        self.task_subscription = self.create_subscription(
            String, TASK_STATUS_TOPIC, self.receive_task_status, 10,
        )
        self.diagnostic_publisher = self.create_publisher(
            DiagnosticArray, DIAGNOSTICS_TOPIC, 10,
        )
        self.last_diagnostic = None
        self.diagnostic_publish_count = 0

        # 使用单调时钟调度，即使 ROS /clock 暂停也会发现消息中断。
        steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.check_period = min(0.1, self.timeout_sec / 2.0)
        self.timeout_timer = self.create_timer(
            self.check_period, self.check_timeout, clock=steady_clock,
        )
        self.diagnostic_timer = self.create_timer(
            1.0 / self.diagnostic_rate,
            self.publish_diagnostics,
            clock=steady_clock,
        )
        self.publish_diagnostics()
        self.get_logger().info(
            f'监控器已启动：话题={self.subscription.topic_name}，'
            f'超时={self.timeout_sec:.2f} 秒，诊断={DIAGNOSTICS_TOPIC} '
            f'@ {self.diagnostic_rate:.2f} Hz'
        )

    def receive(self, message):
        try:
            reading = parse_sensor(message.data)
        except (ValueError, OverflowError) as exc:
            self.invalid_count += 1
            self.get_logger().warning(f'忽略非法传感器消息：{exc}')
            return
        was_waiting = self.received_count == 0
        was_timed_out = self.timed_out
        self.last_received_at = time.monotonic()
        if was_timed_out:
            self.get_logger().info('传感器消息已恢复')
        self.timed_out = False
        self.latest_reading = reading
        self.received_count += 1
        self.get_logger().info(
            f'收到传感器：seq={reading["seq"]}，value={reading["value"]:.1f}'
        )
        if was_waiting or was_timed_out:
            self.publish_diagnostics()

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
            f'收到任务结果：task_id={status["task_id"]}，'
            f'success={status["success"]}，sensor_seq={status["sensor_seq"]}，'
            f'{status["message"]}'
        )

    def check_timeout(self):
        elapsed = time.monotonic() - self.last_received_at
        if elapsed >= self.timeout_sec and not self.timed_out:
            self.timed_out = True
            self.get_logger().warning(
                f'传感器消息超时：已 {elapsed:.2f} 秒没有有效消息'
            )
            self.publish_diagnostics()

    def qos_observation(self):
        """从 ROS graph 计算发布端与本订阅端的实际 QoS 兼容性."""
        endpoints = self.get_publishers_info_by_topic(SENSOR_TOPIC)
        if endpoints:
            self.publisher_seen = True
        reliabilities = sorted({
            endpoint.qos_profile.reliability.name.lower()
            for endpoint in endpoints
        })
        results = [
            qos_check_compatible(endpoint.qos_profile, self.sensor_qos)
            for endpoint in endpoints
        ]
        incompatible = [reason for level, reason in results
                        if level == QoSCompatibility.ERROR]
        if not endpoints:
            compatibility = 'no_publisher'
        elif len(incompatible) == len(endpoints):
            compatibility = 'incompatible'
        else:
            compatibility = 'compatible'
        return {
            'publisher_reliability': ','.join(reliabilities) or 'none',
            'subscriber_reliability': self.sensor_qos.reliability.name.lower(),
            'qos_compatibility': compatibility,
            'qos_reason': ' | '.join(incompatible) or 'none',
        }

    def diagnostic_state(self, qos_values=None):
        """返回 REP-107 等级、稳定状态码和面向操作员的说明."""
        qos_values = qos_values or self.qos_observation()
        if self.timed_out:
            if qos_values['qos_compatibility'] == 'incompatible':
                return (
                    DiagnosticStatus.ERROR,
                    'qos_mismatch',
                    '传感器 Publisher 存在，但 QoS 与订阅端不兼容',
                )
            if qos_values['qos_compatibility'] == 'no_publisher':
                if self.publisher_seen:
                    return (
                        DiagnosticStatus.ERROR,
                        'publisher_lost',
                        '曾发现传感器 Publisher，但当前端点已消失',
                    )
                return (
                    DiagnosticStatus.ERROR,
                    'publisher_missing',
                    '尚未发现传感器 Publisher',
                )
            # 监控节点仍在按时发布诊断，因此这里是 ERROR，而非诊断项自身 STALE。
            return (
                DiagnosticStatus.ERROR,
                'stale',
                '传感器流已过期，测量值不可用于任务决策',
            )
        if self.received_count == 0:
            return DiagnosticStatus.WARN, 'waiting', '等待第一条合法传感器消息'
        return DiagnosticStatus.OK, 'healthy', '传感器流正常'

    def publish_diagnostics(self):
        """发布可被 rosbag 记录和诊断聚合器消费的健康快照."""
        qos_values = self.qos_observation()
        level, state, state_message = self.diagnostic_state(qos_values)
        age = max(0.0, time.monotonic() - self.last_received_at)
        latest_seq = (
            str(self.latest_reading['seq'])
            if self.latest_reading is not None else 'none'
        )
        status = DiagnosticStatus()
        status.level = level
        status.name = 'sensor_simulator: Sensor Stream'
        status.message = state_message
        status.hardware_id = 'simulated_inspection_sensor'
        values = {
            'topic': SENSOR_TOPIC,
            'state': state,
            'age_sec': f'{age:.3f}',
            'timeout_sec': f'{self.timeout_sec:.3f}',
            'received_count': str(self.received_count),
            'invalid_count': str(self.invalid_count),
            'latest_seq': latest_seq,
            'publisher_count': str(self.count_publishers(SENSOR_TOPIC)),
            'publisher_seen': str(self.publisher_seen).lower(),
            **qos_values,
        }
        status.values = [
            KeyValue(key=key, value=value) for key, value in values.items()
        ]
        diagnostic_array = DiagnosticArray()
        diagnostic_array.header.stamp = self.get_clock().now().to_msg()
        diagnostic_array.status = [status]
        self.diagnostic_publisher.publish(diagnostic_array)
        self.last_diagnostic = status
        self.diagnostic_publish_count += 1


def main(args=None):
    run_node(StatusMonitor, args)
