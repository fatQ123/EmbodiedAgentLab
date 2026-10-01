"""发布质检工位 TF/Marker，并可控注入 TF 缺失或过期故障."""
import math

from embodied_comm.common import (
    choice_parameter, period_seconds, positive_parameter, run_node,
)
from geometry_msgs.msg import TransformStamped
from rclpy.clock import Clock, ClockType
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
from visualization_msgs.msg import Marker


WORLD_FRAME = 'world'
BASE_FRAME = 'base_link'
CAMERA_FRAME = 'camera_link'
TOOL_FRAME = 'tool0'
MARKER_TOPIC = '/inspection_target_marker'


def quaternion_from_euler(roll, pitch, yaw):
    """把固定工位的欧拉角转换为四元数."""
    cr = math.cos(roll / 2.0)
    sr = math.sin(roll / 2.0)
    cp = math.cos(pitch / 2.0)
    sp = math.sin(pitch / 2.0)
    cy = math.cos(yaw / 2.0)
    sy = math.sin(yaw / 2.0)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


class WorkcellVisualizer(Node):
    """用无硬件的坐标和标记表达一个工业质检工位."""

    def __init__(self, **kwargs):
        super().__init__('workcell_visualizer', **kwargs)
        try:
            self.publish_rate = positive_parameter(self, 'publish_rate', 10.0)
            self.publish_period = period_seconds(self.publish_rate)
            self.tf_fault_mode = choice_parameter(
                self, 'tf_fault_mode', 'normal',
                ('normal', 'missing', 'stale'),
            )
            self.tf_fault_after_sec = positive_parameter(
                self, 'tf_fault_after_sec', 5.0,
            )
            self.static_broadcaster = StaticTransformBroadcaster(self)
            self.dynamic_broadcaster = TransformBroadcaster(self)
            marker_qos = QoSProfile(
                depth=1,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                reliability=ReliabilityPolicy.RELIABLE,
            )
            self.marker_publisher = self.create_publisher(
                Marker, MARKER_TOPIC, marker_qos,
            )
            static_stamp = self.get_clock().now().to_msg()
            self.static_broadcaster.sendTransform([
                self.world_to_base(static_stamp),
                self.camera_to_tool(static_stamp),
            ])
            self.tf_fault_injected = self.tf_fault_mode == 'missing'
            self.tf_fault_timer = None
            self.timer = self.create_timer(self.publish_period, self.publish_scene)
            if self.tf_fault_mode == 'stale':
                self.tf_fault_timer = self.create_timer(
                    self.tf_fault_after_sec,
                    self.inject_stale_tf,
                    clock=Clock(clock_type=ClockType.STEADY_TIME),
                )
            # 不必等待第一个定时周期，启动后立即提供动态 TF 和 Marker。
            self.publish_scene()
        except Exception:
            self.destroy_node()
            raise
        self.get_logger().info(
            f'质检工位可视化已启动：{WORLD_FRAME} → {BASE_FRAME} → '
            f'{CAMERA_FRAME} → {TOOL_FRAME}，频率={self.publish_rate:.2f} Hz，'
            f'Marker={MARKER_TOPIC}，TF 故障模式={self.tf_fault_mode}'
        )
        if self.tf_fault_mode == 'missing':
            self.get_logger().warning(
                f'故障注入：不发布 {BASE_FRAME} → {CAMERA_FRAME}，'
                f'{WORLD_FRAME} → {TOOL_FRAME} 坐标链缺失'
            )

    def make_transform(self, parent, child, translation, rotation, stamp=None):
        transform = TransformStamped()
        transform.header.stamp = stamp or self.get_clock().now().to_msg()
        transform.header.frame_id = parent
        transform.child_frame_id = child
        transform.transform.translation.x = float(translation[0])
        transform.transform.translation.y = float(translation[1])
        transform.transform.translation.z = float(translation[2])
        transform.transform.rotation.x = float(rotation[0])
        transform.transform.rotation.y = float(rotation[1])
        transform.transform.rotation.z = float(rotation[2])
        transform.transform.rotation.w = float(rotation[3])
        return transform

    def world_to_base(self, stamp=None):
        # 工位底座相对车间标定原点有可见偏移，RViz 中不会与 world 轴重叠。
        return self.make_transform(
            WORLD_FRAME, BASE_FRAME, (0.20, -0.20, 0.10),
            (0.0, 0.0, 0.0, 1.0), stamp,
        )

    def base_to_camera(self, stamp):
        # 相机位于工位上方，并略微朝向传送带中心。
        rotation = quaternion_from_euler(
            roll=0.0, pitch=math.radians(-20.0), yaw=math.radians(10.0),
        )
        return self.make_transform(
            BASE_FRAME, CAMERA_FRAME, (0.45, 0.0, 0.85), rotation, stamp,
        )

    def camera_to_tool(self, stamp):
        # tool0 是与相机刚性安装的检查头，因此属于不会老化的静态外参。
        return self.make_transform(
            CAMERA_FRAME, TOOL_FRAME, (0.35, 0.0, -0.25),
            (0.0, 0.0, 0.0, 1.0), stamp,
        )

    def inspection_marker(self, stamp):
        marker = Marker()
        marker.header.stamp = stamp
        marker.header.frame_id = TOOL_FRAME
        marker.ns = 'inspection_target'
        marker.id = 0
        marker.type = Marker.CUBE
        marker.action = Marker.ADD
        marker.pose.position.x = 0.25
        marker.pose.position.y = 0.0
        marker.pose.position.z = 0.0
        marker.pose.orientation.w = 1.0
        marker.scale.x = 0.20
        marker.scale.y = 0.14
        marker.scale.z = 0.06
        marker.color.r = 0.10
        marker.color.g = 0.85
        marker.color.b = 0.25
        marker.color.a = 0.95
        marker.frame_locked = True
        if self.tf_fault_mode == 'stale':
            # 动态 TF 停止后让旧 Marker 自动消失，避免 RViz 保留永久残影。
            marker.lifetime = Duration(
                seconds=max(0.5, self.publish_period * 3.0),
            ).to_msg()
        return marker

    def publish_scene(self):
        stamp = self.get_clock().now().to_msg()
        if not self.tf_fault_injected:
            self.dynamic_broadcaster.sendTransform(self.base_to_camera(stamp))
        self.marker_publisher.publish(self.inspection_marker(stamp))

    def inject_stale_tf(self):
        """停止刷新动态 TF，但继续发布带当前时间戳和有限寿命的 Marker."""
        if self.tf_fault_injected:
            return
        self.tf_fault_injected = True
        if self.tf_fault_timer is not None:
            self.tf_fault_timer.cancel()
        self.get_logger().warning(
            f'故障注入：停止刷新 {BASE_FRAME} → {CAMERA_FRAME} 动态 TF；'
            f'节点、TF Publisher 和 Marker Publisher 保持存活'
        )


def main(args=None):
    run_node(WorkcellVisualizer, args)
