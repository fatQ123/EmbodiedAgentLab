"""独立查询 TF Buffer，诊断坐标链缺失与时间戳过期."""
import time

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from embodied_comm.common import DIAGNOSTICS_TOPIC, positive_parameter, run_node
from embodied_comm.workcell_visualizer import TOOL_FRAME, WORLD_FRAME
from rclpy.clock import Clock, ClockType
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformException, TransformListener


class SpatialHealthMonitor(Node):
    """以独立观察者身份判断完整坐标链是否存在且足够新."""

    def __init__(self, **kwargs):
        super().__init__('spatial_health_monitor', **kwargs)
        try:
            self.tf_timeout_sec = positive_parameter(
                self, 'tf_timeout_sec', 1.0,
            )
            self.diagnostic_rate = positive_parameter(
                self, 'diagnostic_rate', 1.0,
            )
            cache_seconds = max(10.0, self.tf_timeout_sec * 4.0)
            self.tf_buffer = Buffer(
                cache_time=Duration(seconds=cache_seconds), node=self,
            )
            self.tf_listener = TransformListener(
                self.tf_buffer, self, spin_thread=False,
            )
            self.diagnostic_publisher = self.create_publisher(
                DiagnosticArray, DIAGNOSTICS_TOPIC, 10,
            )
            self.started_at = time.monotonic()
            self.last_diagnostic = None
            self.diagnostic_publish_count = 0
            self.timer = self.create_timer(
                1.0 / self.diagnostic_rate,
                self.publish_diagnostics,
                clock=Clock(clock_type=ClockType.STEADY_TIME),
            )
            self.publish_diagnostics()
        except Exception:
            self.destroy_node()
            raise
        self.get_logger().info(
            f'空间健康监控已启动：{WORLD_FRAME} → {TOOL_FRAME}，'
            f'TF 新鲜度={self.tf_timeout_sec:.2f} 秒，'
            f'诊断频率={self.diagnostic_rate:.2f} Hz'
        )

    def observe_transform(self):
        """返回等级、状态、说明、年龄和最近的查询异常."""
        try:
            transform = self.tf_buffer.lookup_transform(
                WORLD_FRAME, TOOL_FRAME, Time(),
            )
        except TransformException as exc:
            elapsed = time.monotonic() - self.started_at
            if elapsed < self.tf_timeout_sec:
                return (
                    DiagnosticStatus.WARN,
                    'waiting',
                    '等待完整坐标链进入 TF Buffer',
                    None,
                    str(exc),
                )
            return (
                DiagnosticStatus.ERROR,
                'missing',
                f'缺少 {WORLD_FRAME} → {TOOL_FRAME} 完整坐标链',
                None,
                str(exc),
            )

        transform_stamp = Time.from_msg(transform.header.stamp)
        age = max(
            0.0,
            (self.get_clock().now() - transform_stamp).nanoseconds / 1e9,
        )
        if age >= self.tf_timeout_sec:
            return (
                DiagnosticStatus.ERROR,
                'stale',
                f'{WORLD_FRAME} → {TOOL_FRAME} 坐标变换已过期',
                age,
                'none',
            )
        return (
            DiagnosticStatus.OK,
            'healthy',
            f'{WORLD_FRAME} → {TOOL_FRAME} 坐标链正常',
            age,
            'none',
        )

    def publish_diagnostics(self):
        level, state, message, age, error = self.observe_transform()
        status = DiagnosticStatus()
        status.level = level
        status.name = 'workcell_visualizer: TF Chain'
        status.message = message
        status.hardware_id = 'simulated_inspection_workcell'
        values = {
            'source_frame': WORLD_FRAME,
            'target_frame': TOOL_FRAME,
            'state': state,
            'age_sec': 'none' if age is None else f'{age:.3f}',
            'timeout_sec': f'{self.tf_timeout_sec:.3f}',
            'tf_publisher_count': str(self.count_publishers('/tf')),
            'tf_static_publisher_count': str(self.count_publishers('/tf_static')),
            'last_error': error,
        }
        status.values = [
            KeyValue(key=key, value=value) for key, value in values.items()
        ]
        message_array = DiagnosticArray()
        message_array.header.stamp = self.get_clock().now().to_msg()
        message_array.status = [status]
        self.diagnostic_publisher.publish(message_array)
        self.last_diagnostic = status
        self.diagnostic_publish_count += 1

    def destroy_node(self):
        listener = getattr(self, 'tf_listener', None)
        if listener is not None:
            listener.unregister()
            self.tf_listener = None
        return super().destroy_node()


def main(args=None):
    run_node(SpatialHealthMonitor, args)
