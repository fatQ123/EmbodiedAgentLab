"""按指定频率发布可重复的模拟读数."""
from embodied_comm.common import (
    choice_parameter, nonnegative_parameter, period_seconds,
    positive_parameter, run_node, sensor_qos, sensor_text, SENSOR_TOPIC,
)
from rclpy.node import Node
from std_msgs.msg import String


class SensorSimulator(Node):
    def __init__(self, **kwargs):
        super().__init__('sensor_simulator', **kwargs)
        try:
            self.publish_rate = positive_parameter(self, 'publish_rate', 2.0)
            self.fault_stop_after_sec = nonnegative_parameter(
                self, 'fault_stop_after_sec', 0.0,
            )
            self.fault_crash_after_sec = nonnegative_parameter(
                self, 'fault_crash_after_sec', 0.0,
            )
            self.publisher_reliability = choice_parameter(
                self,
                'publisher_reliability',
                'reliable',
                ('reliable', 'best_effort'),
            )
            self.publisher_qos = sensor_qos(self.publisher_reliability)
            self.publisher = self.create_publisher(
                String, SENSOR_TOPIC, self.publisher_qos,
            )
            self.seq = 0
            self.fault_injected = False
            self.timer = self.create_timer(period_seconds(self.publish_rate), self.publish_reading)
            self.fault_timer = None
            if self.fault_stop_after_sec > 0.0:
                self.fault_timer = self.create_timer(
                    self.fault_stop_after_sec, self.inject_topic_stop,
                )
            self.crash_timer = None
            if self.fault_crash_after_sec > 0.0:
                self.crash_timer = self.create_timer(
                    self.fault_crash_after_sec, self.inject_node_crash,
                )
        except Exception:
            self.destroy_node()
            raise
        self.get_logger().info(
            f'传感器已启动：话题={self.publisher.topic_name}，'
            f'频率={self.publish_rate:.2f} Hz，'
            f'可靠性={self.publisher_reliability}，'
            f'停止故障={self.fault_stop_after_sec:.2f} 秒，'
            f'崩溃故障={self.fault_crash_after_sec:.2f} 秒'
        )

    def publish_reading(self):
        self.seq += 1
        # 固定规律便于复现，读数始终在 0～100 范围内。
        text = sensor_text(self.seq)
        self.publisher.publish(String(data=text))
        self.get_logger().info(f'发布：{text}')

    def inject_topic_stop(self):
        """停止数据定时器，但保留节点和 DDS Publisher 以模拟设备卡住."""
        if self.fault_injected:
            return
        self.fault_injected = True
        self.timer.cancel()
        if self.fault_timer is not None:
            self.fault_timer.cancel()
        self.get_logger().warning(
            f'故障注入：节点与 Publisher 保持存活，但 {SENSOR_TOPIC} '
            f'停止发布，最后序号={self.seq}'
        )

    def inject_node_crash(self):
        """抛出未捕获异常，使传感器进程以非零状态真实退出."""
        if self.crash_timer is not None:
            self.crash_timer.cancel()
        message = (
            f'故障注入：sensor_simulator 即将崩溃，最后序号={self.seq}'
        )
        self.get_logger().fatal(message)
        raise RuntimeError(message)


def main(args=None):
    run_node(SensorSimulator, args)
