"""验证 Service 超时、Action 取消和节点崩溃的真实 ROS 行为."""
import json
import os
import signal
import subprocess
import time

from diagnostic_msgs.msg import DiagnosticArray
from embodied_interfaces.action import ExecuteTask
from rclpy.action import ActionClient
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


SENSOR_DIAGNOSTIC = 'sensor_simulator: Sensor Stream'


def spin_until(executor, predicate, timeout=8.0, message='等待 Day 5 状态超时'):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.02)
    assert predicate(), message


def diagnostic_states(messages):
    return [
        next(
            (item.value for item in status.values if item.key == 'state'),
            None,
        )
        for message in messages
        for status in message.status
        if status.name == SENSOR_DIAGNOSTIC
    ]


def run_day5_launch(tmp_path, domain, extra_args, scenario):
    env = dict(
        os.environ,
        ROS_DOMAIN_ID=str(domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
    )
    args = [
        'ros2', 'launch', 'embodied_comm', 'week03_day5.launch.py',
        'use_rviz:=false', 'publish_rate:=20.0',
        'timeout_sec:=2.0', 'tf_timeout_sec:=0.4',
        'diagnostic_rate:=20.0', 'frame_publish_rate:=20.0',
        *extra_args,
    ]
    log_path = tmp_path / f'day5-{domain}.log'
    context = Context()
    context.init(args=[], domain_id=domain)
    probe = Node(f'day5_fault_probe_{domain}', context=context)
    diagnostics = []
    sensor_messages = []
    task_statuses = []
    probe.create_subscription(
        DiagnosticArray, '/diagnostics', diagnostics.append, 10,
    )
    probe.create_subscription(
        String, '/sensor_state', sensor_messages.append, 10,
    )
    probe.create_subscription(
        String, '/task_status',
        lambda message: task_statuses.append(json.loads(message.data)), 10,
    )
    service = probe.create_client(Trigger, '/execute_task')
    action = ActionClient(probe, ExecuteTask, '/execute_task_long')
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
                lambda: launch_alive() and expected <= set(
                    probe.get_node_names()
                ),
                timeout=12.0,
                message=log_path.read_text(),
            )
            spin_until(
                executor,
                lambda: launch_alive()
                and 'healthy' in diagnostic_states(diagnostics)
                and bool(sensor_messages),
                message=log_path.read_text(),
            )
            assert service.wait_for_service(timeout_sec=5.0)
            assert action.wait_for_server(timeout_sec=5.0)
            scenario(
                env, proc, probe, executor, service, diagnostics,
                sensor_messages, task_statuses, log_path,
            )

            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=20)
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
        executor.shutdown()
        probe.destroy_node()
        context.try_shutdown()


def test_installed_service_timeout_keeps_server_alive(tmp_path):
    def scenario(
            env, proc, probe, executor, service, diagnostics,
            sensor_messages, task_statuses, log_path):
        result = subprocess.run(
            [
                'ros2', 'run', 'embodied_comm', 'service_timeout_demo',
                '--response-timeout', '0.2',
            ],
            env=env, capture_output=True, text=True, timeout=8,
        )
        assert result.returncode == 6, result.stdout + result.stderr
        assert '服务响应超时' in result.stdout + result.stderr
        spin_until(
            executor,
            lambda: len(task_statuses) == 1,
            timeout=3.0,
            message=log_path.read_text(),
        )
        assert task_statuses[0]['success'] is True
        assert '延迟 1.00 秒后响应' in log_path.read_text()
        assert proc.poll() is None
        assert 'task_executor' in probe.get_node_names()

    run_day5_launch(
        tmp_path, 189,
        [
            'fault_service_delay_sec:=1.0',
            # 本用例只验证客户端期限，不把传感器 freshness 混入根因。
            'timeout_sec:=10.0',
        ],
        scenario,
    )


def test_installed_action_cancel_and_recovery(tmp_path):
    def scenario(
            env, proc, probe, executor, service, diagnostics,
            sensor_messages, task_statuses, log_path):
        canceled = subprocess.run(
            [
                'ros2', 'run', 'embodied_comm', 'inspection_demo',
                '--task-name', 'inspect_workpiece_WP-DAY5-CANCEL',
                '--duration', '2.0', '--cancel-at', '40',
            ],
            env=env, capture_output=True, text=True, timeout=10,
        )
        assert canceled.returncode == 3, canceled.stdout + canceled.stderr
        assert '最终状态=CANCELED' in canceled.stdout + canceled.stderr

        recovered = subprocess.run(
            [
                'ros2', 'run', 'embodied_comm', 'inspection_demo',
                '--task-name', 'inspect_workpiece_WP-DAY5-RECOVER',
                '--duration', '0.2',
            ],
            env=env, capture_output=True, text=True, timeout=8,
        )
        assert recovered.returncode == 0, recovered.stdout + recovered.stderr
        assert '最终状态=SUCCEEDED' in recovered.stdout + recovered.stderr
        spin_until(
            executor, lambda: len(task_statuses) == 2,
            message=log_path.read_text(),
        )
        assert [item['success'] for item in task_statuses] == [False, True]
        assert '接受取消请求' in log_path.read_text()
        assert proc.poll() is None

    run_day5_launch(tmp_path, 190, [], scenario)


def test_installed_sensor_node_crash_is_diagnosed(tmp_path):
    def scenario(
            env, proc, probe, executor, service, diagnostics,
            sensor_messages, task_statuses, log_path):
        spin_until(
            executor,
            lambda: proc.poll() is None
            and 'sensor_simulator' not in probe.get_node_names()
            and 'publisher_lost' in diagnostic_states(diagnostics),
            timeout=8.0,
            message=log_path.read_text(),
        )
        remaining = {
            'task_executor', 'status_monitor', 'workcell_visualizer',
            'spatial_health_monitor',
        }
        assert remaining <= set(probe.get_node_names())
        assert probe.count_publishers('/sensor_state') == 0
        stopped_count = len(sensor_messages)
        # Publisher 消失时，执行器的 RELIABLE Subscription 里仍可能留有
        # depth=10 的在途样本。等待队列排空并明确越过 0.4 秒新鲜度门限，
        # 避免把机器负载导致的晚到样本误判为联锁失效。
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.02)
        assert len(sensor_messages) == stopped_count

        future = service.call_async(Trigger.Request())
        spin_until(executor, future.done, message=log_path.read_text())
        assert not future.result().success
        assert '数据已过期' in future.result().message
        spin_until(executor, lambda: len(task_statuses) == 1)
        log_text = log_path.read_text()
        assert '即将崩溃' in log_text
        assert 'process has died' in log_text
        assert 'exit code 1' in log_text

    run_day5_launch(
        tmp_path, 191,
        ['fault_sensor_crash_after_sec:=4.0', 'timeout_sec:=0.4'],
        scenario,
    )
