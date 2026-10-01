"""验证 QoS 不匹配以及 TF 缺失/过期故障的真实 ROS 行为."""
import os
import re
import signal
import subprocess
import time

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from embodied_comm.sensor_simulator import SensorSimulator
from embodied_comm.spatial_health_monitor import SpatialHealthMonitor
from embodied_comm.status_monitor import StatusMonitor
from embodied_comm.task_executor import TaskExecutor
from embodied_comm.workcell_visualizer import (
    BASE_FRAME, CAMERA_FRAME, MARKER_TOPIC, TOOL_FRAME, WorkcellVisualizer,
    WORLD_FRAME,
)
import pytest
from rclpy.context import Context
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import ReliabilityPolicy
from rclpy.time import Time
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener
from visualization_msgs.msg import Marker


SENSOR_DIAGNOSTIC = 'sensor_simulator: Sensor Stream'
TF_DIAGNOSTIC = 'workcell_visualizer: TF Chain'


def spin_until(executor, predicate, timeout=5.0, message='等待 Day 4 状态超时'):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.02)
    assert predicate(), message


def status_values(status):
    return {item.key: item.value for item in status.values}


def diagnostic_states(messages, name):
    return [
        status_values(status).get('state')
        for message in messages
        for status in message.status
        if status.name == name
    ]


def latest_status(messages, name, state=None):
    matches = [
        status
        for message in messages
        for status in message.status
        if status.name == name
        and (state is None or status_values(status).get('state') == state)
    ]
    return matches[-1] if matches else None


def transform_stamp_ns(buffer, parent, child):
    stamp = buffer.lookup_transform(parent, child, Time()).header.stamp
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def test_real_qos_mismatch_blocks_sensor_delivery(ros_context):
    sensor = SensorSimulator(
        context=ros_context,
        parameter_overrides=[
            Parameter('publish_rate', value=20.0),
            Parameter('publisher_reliability', value='best_effort'),
        ],
    )
    monitor = StatusMonitor(
        context=ros_context,
        parameter_overrides=[
            Parameter('timeout_sec', value=0.25),
            Parameter('diagnostic_rate', value=20.0),
        ],
    )
    task = TaskExecutor(
        context=ros_context,
        parameter_overrides=[Parameter('sensor_timeout_sec', value=0.25)],
    )
    probe = Node('qos_mismatch_probe', context=ros_context)
    diagnostics = []
    probe.create_subscription(
        DiagnosticArray, '/diagnostics', diagnostics.append, 10,
    )
    service = probe.create_client(Trigger, '/execute_task')
    executor = MultiThreadedExecutor(num_threads=4, context=ros_context)
    for node in (sensor, monitor, task, probe):
        executor.add_node(node)
    try:
        assert service.wait_for_service(timeout_sec=5.0)
        spin_until(executor, lambda: sensor.seq >= 3)
        spin_until(
            executor,
            lambda: latest_status(
                diagnostics, SENSOR_DIAGNOSTIC, 'qos_mismatch',
            ) is not None,
            timeout=3.0,
        )
        assert monitor.received_count == 0
        assert task.received_count == 0
        status = latest_status(
            diagnostics, SENSOR_DIAGNOSTIC, 'qos_mismatch',
        )
        values = status_values(status)
        assert status.level == DiagnosticStatus.ERROR
        assert values['publisher_count'] == '1'
        assert values['publisher_reliability'] == 'best_effort'
        assert values['subscriber_reliability'] == 'reliable'
        assert values['qos_compatibility'] == 'incompatible'
        endpoint = probe.get_publishers_info_by_topic('/sensor_state')[0]
        assert endpoint.qos_profile.reliability == ReliabilityPolicy.BEST_EFFORT

        future = service.call_async(Trigger.Request())
        spin_until(executor, future.done)
        assert not future.result().success
        assert '尚未收到' in future.result().message
    finally:
        executor.shutdown()
        for node in (sensor, monitor, task, probe):
            node.destroy_node()


def test_missing_tf_is_reported_and_chain_is_broken(ros_context):
    visualizer = WorkcellVisualizer(
        context=ros_context,
        parameter_overrides=[
            Parameter('publish_rate', value=20.0),
            Parameter('tf_fault_mode', value='missing'),
        ],
    )
    monitor = SpatialHealthMonitor(
        context=ros_context,
        parameter_overrides=[
            Parameter('tf_timeout_sec', value=0.2),
            Parameter('diagnostic_rate', value=20.0),
        ],
    )
    probe = Node('missing_tf_probe', context=ros_context)
    diagnostics = []
    markers = []
    probe.create_subscription(
        DiagnosticArray, '/diagnostics', diagnostics.append, 10,
    )
    probe.create_subscription(Marker, MARKER_TOPIC, markers.append, 10)
    buffer = Buffer(node=probe)
    listener = TransformListener(buffer, probe, spin_thread=False)
    executor = SingleThreadedExecutor(context=ros_context)
    for node in (visualizer, monitor, probe):
        executor.add_node(node)
    try:
        spin_until(executor, lambda: bool(markers))
        spin_until(
            executor,
            lambda: latest_status(
                diagnostics, TF_DIAGNOSTIC, 'missing',
            ) is not None,
            timeout=3.0,
        )
        status = latest_status(diagnostics, TF_DIAGNOSTIC, 'missing')
        assert status.level == DiagnosticStatus.ERROR
        assert not buffer.can_transform(WORLD_FRAME, TOOL_FRAME, Time())
        assert buffer.can_transform(WORLD_FRAME, BASE_FRAME, Time())
        assert buffer.can_transform(CAMERA_FRAME, TOOL_FRAME, Time())
        assert visualizer.tf_fault_injected
    finally:
        listener.unregister()
        executor.shutdown()
        for node in (visualizer, monitor, probe):
            node.destroy_node()


def test_stale_tf_stops_timestamp_and_expires_marker(ros_context):
    visualizer = WorkcellVisualizer(
        context=ros_context,
        parameter_overrides=[
            Parameter('publish_rate', value=20.0),
            Parameter('tf_fault_mode', value='stale'),
            Parameter('tf_fault_after_sec', value=0.5),
        ],
    )
    monitor = SpatialHealthMonitor(
        context=ros_context,
        parameter_overrides=[
            Parameter('tf_timeout_sec', value=0.2),
            Parameter('diagnostic_rate', value=20.0),
        ],
    )
    probe = Node('stale_tf_probe', context=ros_context)
    diagnostics = []
    markers = []
    probe.create_subscription(
        DiagnosticArray, '/diagnostics', diagnostics.append, 10,
    )
    probe.create_subscription(Marker, MARKER_TOPIC, markers.append, 10)
    buffer = Buffer(node=probe)
    listener = TransformListener(buffer, probe, spin_thread=False)
    executor = SingleThreadedExecutor(context=ros_context)
    for node in (visualizer, monitor, probe):
        executor.add_node(node)
    try:
        spin_until(
            executor,
            lambda: buffer.can_transform(WORLD_FRAME, TOOL_FRAME, Time())
            and latest_status(
                diagnostics, TF_DIAGNOSTIC, 'healthy',
            ) is not None,
        )
        spin_until(executor, lambda: bool(markers))
        assert markers[-1].lifetime.sec or markers[-1].lifetime.nanosec
        spin_until(
            executor,
            lambda: visualizer.tf_fault_injected
            and latest_status(
                diagnostics, TF_DIAGNOSTIC, 'stale',
            ) is not None,
            timeout=3.0,
        )
        stopped_stamp = transform_stamp_ns(buffer, BASE_FRAME, CAMERA_FRAME)
        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.02)
        assert transform_stamp_ns(buffer, BASE_FRAME, CAMERA_FRAME) == stopped_stamp
        status = latest_status(diagnostics, TF_DIAGNOSTIC, 'stale')
        assert status.level == DiagnosticStatus.ERROR
        assert float(status_values(status)['age_sec']) >= 0.2
    finally:
        listener.unregister()
        executor.shutdown()
        for node in (visualizer, monitor, probe):
            node.destroy_node()


@pytest.mark.parametrize(
    'domain,extra_args,sensor_state,tf_state',
    [
        (185, ['publisher_reliability:=best_effort'], 'qos_mismatch', 'healthy'),
        (186, ['fault_stop_after_sec:=2.0'], 'stale', 'healthy'),
        (187, ['tf_fault_mode:=missing'], 'healthy', 'missing'),
        (
            188,
            ['tf_fault_mode:=stale', 'tf_fault_after_sec:=4.0'],
            'healthy',
            'stale',
        ),
    ],
)
def test_installed_day4_fault_matrix(
        tmp_path, domain, extra_args, sensor_state, tf_state):
    env = dict(
        os.environ,
        ROS_DOMAIN_ID=str(domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
    )
    args = [
        'ros2', 'launch', 'embodied_comm', 'week03_day4.launch.py',
        'use_rviz:=false', 'publish_rate:=20.0',
        'timeout_sec:=0.4', 'tf_timeout_sec:=0.4',
        'diagnostic_rate:=20.0', 'frame_publish_rate:=20.0',
        *extra_args,
    ]
    log_path = tmp_path / f'day4-{domain}.log'
    context = Context()
    context.init(args=[], domain_id=domain)
    probe = Node(f'day4_fault_probe_{domain}', context=context)
    diagnostics = []
    sensor_messages = []
    probe.create_subscription(
        DiagnosticArray, '/diagnostics', diagnostics.append, 10,
    )
    probe.create_subscription(
        String, '/sensor_state', sensor_messages.append, 10,
    )
    service = probe.create_client(Trigger, '/execute_task')
    buffer = Buffer(node=probe)
    listener = TransformListener(buffer, probe, spin_thread=False)
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
                'workcell_visualizer', 'spatial_health_monitor',
            }
            spin_until(
                executor,
                lambda: launch_alive() and expected <= set(probe.get_node_names()),
                timeout=12.0,
                message=log_path.read_text(),
            )
            spin_until(
                executor,
                lambda: launch_alive()
                and diagnostic_states(diagnostics, SENSOR_DIAGNOSTIC)[-1:]
                == [sensor_state]
                and diagnostic_states(diagnostics, TF_DIAGNOSTIC)[-1:]
                == [tf_state],
                timeout=8.0,
                message=log_path.read_text(),
            )
            assert service.wait_for_service(timeout_sec=5.0)

            if sensor_state == 'qos_mismatch':
                assert not sensor_messages
                assert probe.count_publishers('/sensor_state') == 1
            elif sensor_state == 'stale':
                # 监控器与执行器有独立的 DDS 接收队列。先证明注入确已
                # 停止、执行器已消费最终样本，再越过其接收时间门限；
                # 历史诊断 stale 或观察器断流不能证明执行器队列已排空。
                spin_until(
                    executor,
                    lambda: re.search(
                        r'停止发布，最后序号=(\d+)', log_path.read_text(),
                    ) is not None,
                    timeout=5.0,
                    message='等待停止注入记录超时',
                )
                final_seq = re.search(
                    r'停止发布，最后序号=(\d+)', log_path.read_text(),
                ).group(1)
                spin_until(
                    executor,
                    lambda: f'最新传感器：seq={final_seq}，'
                    in log_path.read_text(),
                    timeout=8.0,
                    message='执行器未在时限内消费最终传感器样本',
                )
                stopped_count = len(sensor_messages)
                deadline = time.monotonic() + 0.8
                while time.monotonic() < deadline:
                    executor.spin_once(timeout_sec=0.02)
                assert len(sensor_messages) == stopped_count
            else:
                spin_until(
                    executor,
                    lambda: launch_alive() and bool(sensor_messages),
                    timeout=2.0,
                    message=log_path.read_text(),
                )

            if tf_state == 'missing':
                assert not buffer.can_transform(
                    WORLD_FRAME, TOOL_FRAME, Time(),
                )
            elif tf_state == 'stale':
                spin_until(
                    executor,
                    lambda: buffer.can_transform(
                        WORLD_FRAME, TOOL_FRAME, Time(),
                    ),
                    timeout=2.0,
                    message=log_path.read_text(),
                )
            else:
                spin_until(
                    executor,
                    lambda: buffer.can_transform(
                        WORLD_FRAME, TOOL_FRAME, Time(),
                    ),
                    timeout=2.0,
                    message=log_path.read_text(),
                )

            future = service.call_async(Trigger.Request())
            spin_until(
                executor, future.done, timeout=5.0,
                message=log_path.read_text(),
            )
            if sensor_state in ('qos_mismatch', 'stale'):
                assert not future.result().success
                if sensor_state == 'stale':
                    assert '数据已过期' in future.result().message
            else:
                assert future.result().success

            log_text = log_path.read_text()
            if sensor_state == 'qos_mismatch':
                assert 'best_effort' in log_text
            if sensor_state == 'stale':
                assert '停止发布' in log_text
            if tf_state == 'missing':
                assert '坐标链缺失' in log_text
            if tf_state == 'stale':
                assert '停止刷新' in log_text

            proc.send_signal(signal.SIGINT)
            # DDS participant teardown can occasionally outlive all five child
            # processes for several seconds on a busy full-suite run. Jazzy 的
            # launch 外壳还可能在五个子进程都退出后停留；先验证子进程，
            # 再终止仅剩的外壳，避免把 Launch 工具竞态误报为节点泄漏。
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                log_text = log_path.read_text()
                assert log_text.count('process has finished cleanly') >= 5
                proc.terminate()
                proc.wait(timeout=5)
            else:
                assert proc.returncode == 0, log_path.read_text()
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
