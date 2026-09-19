"""按指定频率发布可重复的模拟读数。"""
from rclpy.node import Node
from std_msgs.msg import String

from embodied_comm.common import (
    SENSOR_TOPIC, period_seconds, positive_parameter, run_node, sensor_text,
)


class SensorSimulator(Node):
    def __init__(self, **kwargs):
        super().__init__('sensor_simulator', **kwargs)
        try:
            self.publish_rate = positive_parameter(self, 'publish_rate', 2.0)
            self.publisher = self.create_publisher(String, SENSOR_TOPIC, 10)
            self.seq = 0
            self.timer = self.create_timer(period_seconds(self.publish_rate), self.publish_reading)
        except Exception:
            self.destroy_node()
            raise
        self.get_logger().info(
            f'传感器已启动：话题={self.publisher.topic_name}，频率={self.publish_rate:.2f} Hz'
        )

    def publish_reading(self):
        self.seq += 1
        # 固定规律便于复现，读数始终在 0～100 范围内。
        text = sensor_text(self.seq)
        self.publisher.publish(String(data=text))
        self.get_logger().info(f'发布：{text}')


def main(args=None):
    run_node(SensorSimulator, args)
