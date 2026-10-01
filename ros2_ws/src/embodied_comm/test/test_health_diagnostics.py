"""验证标准健康诊断、话题停止故障和陈旧数据联锁."""
import json
import os
import signal
import subprocess
import time

from action_msgs.msg import GoalStatus
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from embodied_comm.sensor_simulator import SensorSimulator
from embodied_comm.status_monitor import StatusMonitor
from embodied_comm.task_executor import TaskExecutor
from embodied_comm.workcell_visualizer import MARKER_TOPIC, TOOL_FRAME, WORLD_FRAME
from embodied_interfaces.action import ExecuteTask
from rclpy.action import ActionClient
from rclpy.context import Context
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.time import Time
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener
from visualization_msgs.msg import Marker


def spin_until(executor, predicate, timeout=5.0, message='等待健康状态超时'):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.02)
    assert predicate(), message


def status_values(status):
    return {item.key: item.value for item in status.values}


def latest_state(messages):
    if not messages or not messages[-1].status:
        return None
    return status_values(messages[-1].status[0]).get('state')


def observed_state(messages, expected):
    return any(
        message.status
        and status_values(message.status[0]).get('state') == expected
        for message in messages
    )


def test_waiting_healthy_stale_and_recovered_diagnostics(ros_context):
    monitor = StatusMonitor(
        context=ros_context,
        parameter_overrides=[
            Parameter('timeout_sec', value=0.25),
            Parameter('diagnostic_rate', value=20.0),
        ],
    )
    probe = Node('health_state_probe', context=ros_context)
    diagnostics = []
    probe.create_subscription(DiagnosticArray, '/diagnostics', diagnostics.append, 10)
    invalid_publisher = probe.create_publisher(String, '/sensor_state', 10)
    executor = SingleThreadedExecutor(context=ros_context)
    executor.add_node(monitor)
    executor.add_node(probe)
    sensor = None
    try:
        spin_until(executor, lambda: latest_state(diagnostics) == 'waiting')
        invalid_publisher.publish(String(data='not-json'))
        spin_until(executor, lambda: monitor.invalid_count == 1)
        assert monitor.received_count == 0
        probe.destroy_publisher(invalid_publisher)

        sensor = SensorSimulator(
            context=ros_context,
            parameter_overrides=[
                Parameter('publish_rate', value=20.0),
                Parameter('fault_stop_after_sec', value=0.35),
            ],
        )
        executor.add_node(sensor)
        spin_until(
            executor,
            lambda: latest_state(diagnostics) == 'healthy' and sensor.seq >= 2,
        )
        healthy = diagnostics[-1].status[0]
        assert healthy.level == DiagnosticStatus.OK
        assert healthy.name == 'sensor_simulator: Sensor Stream'
        assert healthy.hardware_id == 'simulated_inspection_sensor'
        assert status_values(healthy)['invalid_count'] == '1'

        spin_until(
            executor,
            lambda: sensor.fault_injected
            and monitor.timed_out
            and latest_state(diagnostics) == 'stale',
            timeout=2.0,
        )
        stale = diagnostics[-1].status[0]
        values = status_values(stale)
        assert stale.level == DiagnosticStatus.ERROR
        assert values['publisher_count'] == '1'
        assert values['latest_seq'] == str(sensor.seq)
        assert float(values['age_sec']) >= 0.25
        assert probe.count_publishers('/sensor_state') == 1
        stopped_seq = sensor.seq
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.02)
        assert sensor.seq == stopped_seq

        sensor.timer.reset()
        spin_until(
            executor,
            lambda: sensor.seq > stopped_seq
            and not monitor.timed_out
            and latest_state(diagnostics) == 'healthy',
        )
        assert diagnostics[-1].status[0].level == DiagnosticStatus.OK
    finally:
        if sensor is not None:
            executor.remove_node(sensor)
            sensor.destroy_node()
        executor.shutdown()
        monitor.destroy_node()
        probe.destroy_node()


def test_service_and_action_reject_stale_cache(ros_context):
    task = TaskExecutor(
        context=ros_context,
        parameter_overrides=[Parameter('sensor_timeout_sec', value=0.15)],
    )
    probe = Node('freshness_interlock_probe', context=ros_context)
    publisher = probe.create_publisher(String, '/sensor_state', 10)
    service = probe.create_client(Trigger, '/execute_task')
    action = ActionClient(probe, ExecuteTask, '/execute_task_long')
    statuses = []
    probe.create_subscription(
        String, '/task_status',
        lambda message: statuses.append(json.loads(message.data)), 10,
    )
    executor = MultiThreadedExecutor(num_threads=4, context=ros_context)
    executor.add_node(task)
    executor.add_node(probe)
    try:
        assert service.wait_for_service(timeout_sec=5.0)
        assert action.wait_for_server(timeout_sec=5.0)
        spin_until(executor, lambda: publisher.get_subscription_count() == 1)
        publisher.publish(String(data='{"seq": 7, "value": 42.0}'))
        spin_until(executor, lambda: task.latest_reading is not None)

        deadline = time.monotonic() + 0.18
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.02)
        service_future = service.call_async(Trigger.Request())
        spin_until(executor, service_future.done)
        assert not service_future.result().success
        assert '数据已过期' in service_future.result().message
        spin_until(executor, lambda: len(statuses) == 1)
        assert statuses[0]['sensor_seq'] is None

        publisher.publish(String(data='{"seq": 8, "value": 43.0}'))
        spin_until(executor, lambda: task.latest_reading['seq'] == 8)
        fresh_future = service.call_async(Trigger.Request())
        spin_until(executor, fresh_future.done)
        assert fresh_future.result().success

        deadline = time.monotonic() + 0.18
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.02)
        goal = ExecuteTask.Goal(task_name='inspect_stale_sensor', duration_sec=0.1)
        goal_future = action.send_goal_async(goal)
        spin_until(executor, goal_future.done)
        goal_handle = goal_future.result()
        assert goal_handle.accepted
        result_future = goal_handle.get_result_async()
        spin_until(executor, result_future.done)
        wrapped = result_future.result()
        assert wrapped.status == GoalStatus.STATUS_ABORTED
        assert not wrapped.result.success
        assert wrapped.result.sensor_seq == 0
        spin_until(executor, lambda: len(statuses) == 3)
        assert statuses[-1]['sensor_seq'] is None
    finally:
        action.destroy()
        executor.shutdown()
        task.destroy_node()
        probe.destroy_node()


def test_installed_day3_topic_stop_launch(tmp_path):
    domain = 184
    env = dict(
        os.environ,
        ROS_DOMAIN_ID=str(domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
    )
    args = [
        'ros2', 'launch', 'embodied_comm', 'week03_day3.launch.py',
        'use_rviz:=false', 'publish_rate:=20.0',
        'fault_stop_after_sec:=4.0', 'timeout_sec:=0.4',
        'diagnostic_rate:=20.0', 'frame_publish_rate:=20.0',
    ]
    log_path = tmp_path / 'day3-launch.log'
    context = Context()
    context.init(args=[], domain_id=domain)
    probe = Node('day3_launch_probe', context=context)
    diagnostics = []
    sensor_messages = []
    markers = []
    probe.create_subscription(DiagnosticArray, '/diagnostics', diagnostics.append, 10)
    probe.create_subscription(String, '/sensor_state', sensor_messages.append, 10)
    probe.create_subscription(Marker, MARKER_TOPIC, markers.append, 10)
    service = probe.create_client(Trigger, '/execute_task')
    action = ActionClient(probe, ExecuteTask, '/execute_task_long')
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
                'workcell_visualizer',
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
                and observed_state(diagnostics, 'healthy'),
                timeout=8.0,
                message=log_path.read_text(),
            )
            spin_until(
                executor,
                lambda: launch_alive() and len(sensor_messages) >= 2,
                timeout=5.0,
                message=log_path.read_text(),
            )
            spin_until(
                executor,
                lambda: launch_alive()
                and bool(markers)
                and buffer.can_transform(WORLD_FRAME, TOOL_FRAME, Time()),
                timeout=5.0,
                message=log_path.read_text(),
            )
            assert service.wait_for_service(timeout_sec=5.0)
            assert action.wait_for_server(timeout_sec=5.0)
            spin_until(
                executor,
                lambda: launch_alive() and latest_state(diagnostics) == 'stale',
                timeout=5.0,
                message=log_path.read_text(),
            )
            assert expected <= set(probe.get_node_names())
            assert probe.count_publishers('/sensor_state') == 1
            stopped_count = len(sensor_messages)
            # 给执行器留出清空 DDS depth=10 队列并超过自身 freshness 阈值的时间。
            # 全量回归负载下，task_executor 的独立 Subscription 可能比
            # probe 更晚清空 depth=10 的在途样本；从外部断流确认后继续
            # 等待，确保它自己的最后接收时间也越过 freshness 门限。
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                launch_alive()
                executor.spin_once(timeout_sec=0.02)
            assert len(sensor_messages) == stopped_count
            assert buffer.can_transform(WORLD_FRAME, TOOL_FRAME, Time())

            service_future = service.call_async(Trigger.Request())
            spin_until(
                executor, service_future.done, timeout=5.0,
                message=log_path.read_text(),
            )
            assert not service_future.result().success
            assert '数据已过期' in service_future.result().message
            assert '故障注入：节点与 Publisher 保持存活' in log_path.read_text()

            proc.send_signal(signal.SIGINT)
            # 忙碌的全量回归中 DDS Participant 清理可能晚于四个子进程。
            # 先验证子进程都已干净结束，再回收仅剩的 Launch 外壳。
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                log_text = log_path.read_text()
                assert log_text.count('process has finished cleanly') >= 4
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
        action.destroy()
        listener.unregister()
        executor.shutdown()
        probe.destroy_node()
        context.try_shutdown()
