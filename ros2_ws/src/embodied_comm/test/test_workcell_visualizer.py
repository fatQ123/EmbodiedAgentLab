"""验证正常质检工位的 TF 链、Marker 和安装后 Launch."""
import os
from pathlib import Path
import signal
import subprocess
import time

from embodied_comm.workcell_visualizer import (
    BASE_FRAME, CAMERA_FRAME, MARKER_TOPIC, TOOL_FRAME, WorkcellVisualizer,
    WORLD_FRAME,
)
from embodied_interfaces.action import ExecuteTask
from geometry_msgs.msg import TransformStamped
from rclpy.action import ActionClient
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, ReliabilityPolicy
from rclpy.time import Time
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener
from visualization_msgs.msg import Marker


def spin_until(executor, predicate, timeout=5.0, message='等待 TF 或 Marker 超时'):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.02)
    assert predicate(), message


def stamp_nanoseconds(transform):
    stamp = transform.header.stamp
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def assert_normal_tree(buffer):
    assert buffer.can_transform(WORLD_FRAME, TOOL_FRAME, Time())
    world_to_base = buffer.lookup_transform(WORLD_FRAME, BASE_FRAME, Time())
    base_to_camera = buffer.lookup_transform(BASE_FRAME, CAMERA_FRAME, Time())
    camera_to_tool = buffer.lookup_transform(CAMERA_FRAME, TOOL_FRAME, Time())
    assert isinstance(world_to_base, TransformStamped)
    assert world_to_base.transform.translation.x == 0.20
    assert world_to_base.transform.translation.y == -0.20
    assert world_to_base.transform.translation.z == 0.10
    assert world_to_base.transform.rotation.w == 1.0
    assert base_to_camera.transform.translation.x == 0.45
    assert base_to_camera.transform.translation.z == 0.85
    assert camera_to_tool.transform.translation.x == 0.35
    assert camera_to_tool.transform.translation.z == -0.25
    quaternion = base_to_camera.transform.rotation
    norm = sum(value * value for value in (
        quaternion.x, quaternion.y, quaternion.z, quaternion.w,
    ))
    assert abs(norm - 1.0) < 1e-6
    return base_to_camera


def assert_inspection_marker(marker):
    assert marker.header.frame_id == TOOL_FRAME
    assert marker.ns == 'inspection_target'
    assert marker.id == 0
    assert marker.type == Marker.CUBE
    assert marker.action == Marker.ADD
    assert marker.pose.position.x == 0.25
    assert marker.pose.orientation.w == 1.0
    assert marker.scale.x == 0.20
    assert marker.scale.y == 0.14
    assert marker.scale.z == 0.06
    assert abs(marker.color.g - 0.85) < 1e-6
    assert abs(marker.color.a - 0.95) < 1e-6
    assert marker.frame_locked
    assert marker.lifetime.sec == 0
    assert marker.lifetime.nanosec == 0


def test_tf_tree_marker_and_dynamic_timestamp(ros_context):
    visualizer = WorkcellVisualizer(context=ros_context)
    probe = Node('workcell_visualizer_test', context=ros_context)
    buffer = Buffer(node=probe)
    listener = TransformListener(buffer, probe, spin_thread=False)
    markers = []
    probe.create_subscription(Marker, MARKER_TOPIC, markers.append, 10)
    executor = SingleThreadedExecutor(context=ros_context)
    executor.add_node(visualizer)
    executor.add_node(probe)
    try:
        spin_until(executor, lambda: buffer.can_transform(WORLD_FRAME, TOOL_FRAME, Time()))
        first = assert_normal_tree(buffer)
        static_tool_stamp = stamp_nanoseconds(buffer.lookup_transform(
            CAMERA_FRAME, TOOL_FRAME, Time(),
        ))
        spin_until(executor, lambda: bool(markers))
        assert_inspection_marker(markers[-1])
        endpoint = probe.get_publishers_info_by_topic(MARKER_TOPIC)[0]
        assert endpoint.qos_profile.durability == DurabilityPolicy.TRANSIENT_LOCAL
        assert endpoint.qos_profile.reliability == ReliabilityPolicy.RELIABLE

        first_stamp = stamp_nanoseconds(first)
        spin_until(
            executor,
            lambda: stamp_nanoseconds(buffer.lookup_transform(
                BASE_FRAME, CAMERA_FRAME, Time(),
            )) > first_stamp,
        )
        assert stamp_nanoseconds(buffer.lookup_transform(
            CAMERA_FRAME, TOOL_FRAME, Time(),
        )) == static_tool_stamp
    finally:
        listener.unregister()
        executor.shutdown()
        visualizer.destroy_node()
        probe.destroy_node()


def test_installed_day2_launch_without_rviz(tmp_path):
    domain = 183
    env = dict(
        os.environ,
        ROS_DOMAIN_ID=str(domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
    )
    args = [
        'ros2', 'launch', 'embodied_comm', 'week03_day2.launch.py',
        'use_rviz:=false', 'frame_publish_rate:=20.0',
    ]
    log_path = tmp_path / 'day2-launch.log'
    context = Context()
    context.init(args=[], domain_id=domain)
    probe = Node('day2_launch_probe', context=context)
    buffer = Buffer(node=probe)
    listener = TransformListener(buffer, probe, spin_thread=False)
    markers = []
    sensor_messages = []
    probe.create_subscription(Marker, MARKER_TOPIC, markers.append, 10)
    probe.create_subscription(String, '/sensor_state', sensor_messages.append, 10)
    service_client = probe.create_client(Trigger, '/execute_task')
    action_client = ActionClient(probe, ExecuteTask, '/execute_task_long')
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(probe)
    proc = None

    def launch_alive():
        assert proc.poll() is None, log_path.read_text()
        return True

    try:
        with log_path.open('w') as log:
            proc = subprocess.Popen(
                args, env=env, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            expected = {
                'sensor_simulator', 'task_executor', 'status_monitor',
                'workcell_visualizer',
            }
            spin_until(
                executor,
                lambda: launch_alive() and expected <= set(probe.get_node_names()),
                timeout=12.0,
                message=log_path.read_text(),
            )
            assert 'rviz2' not in probe.get_node_names()
            spin_until(
                executor,
                lambda: launch_alive()
                and buffer.can_transform(WORLD_FRAME, TOOL_FRAME, Time()),
                timeout=8.0,
                message=log_path.read_text(),
            )
            assert_normal_tree(buffer)
            spin_until(
                executor, lambda: launch_alive() and bool(markers),
                timeout=5.0, message=log_path.read_text(),
            )
            assert_inspection_marker(markers[-1])
            spin_until(
                executor, lambda: launch_alive() and bool(sensor_messages),
                timeout=5.0, message=log_path.read_text(),
            )
            assert service_client.wait_for_service(timeout_sec=5.0)
            service_future = service_client.call_async(Trigger.Request())
            spin_until(
                executor, service_future.done, timeout=5.0,
                message=log_path.read_text(),
            )
            assert service_future.result().success
            assert action_client.wait_for_server(timeout_sec=5.0)

            prefix = Path(subprocess.check_output(
                ['ros2', 'pkg', 'prefix', 'embodied_comm'], env=env, text=True,
            ).strip())
            rviz_config = prefix / 'share/embodied_comm/config/week03_workcell.rviz'
            config_text = rviz_config.read_text()
            assert 'Fixed Frame: world' in config_text
            assert 'Value: /inspection_target_marker' in config_text

            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=12)
            assert proc.returncode == 0, log_path.read_text()
            spin_until(
                executor,
                lambda: not expected & set(probe.get_node_names()),
                timeout=5.0,
                message=log_path.read_text(),
            )
    finally:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)
        listener.unregister()
        executor.shutdown()
        probe.destroy_node()
        context.try_shutdown()
