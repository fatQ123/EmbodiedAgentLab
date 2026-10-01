"""验证 Service 超时、Action 取消和节点崩溃的真实 ROS 行为."""
import json
import os
import re
import signal
import subprocess
import time
from collections import Counter

import pytest

from diagnostic_msgs.msg import DiagnosticArray
from embodied_interfaces.action import ExecuteTask
from rclpy.action import ActionClient
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


SENSOR_DIAGNOSTIC = 'sensor_simulator: Sensor Stream'
SYSTEM_PROCESSES = {
    'sensor_simulator', 'task_executor', 'status_monitor',
    'workcell_visualizer', 'spatial_health_monitor',
}


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


def shutdown_day5_launch(proc, log_path, sensor_crash_expected):
    """先核对所有节点的具名退出，再处理可能滞留的 Launch 外壳."""
    clean_expected = SYSTEM_PROCESSES - (
        {'sensor_simulator'} if sensor_crash_expected else set()
    )
    died_expected = [('sensor_simulator', 1)] if sensor_crash_expected else []
    report = {
        'expected_clean_processes': sorted(clean_expected),
        'expected_crashed_processes': died_expected,
        'node_exits_verified': False,
        'mode': 'sigint',
    }
    try:
        proc.send_signal(signal.SIGINT)
        deadline = time.monotonic() + 20.0
        while True:
            text = log_path.read_text()
            clean = Counter(re.findall(
                r'\[(\w+)-\d+\]: process has finished cleanly \[pid \d+\]',
                text,
            ))
            died = [
                (name, int(code)) for name, code in re.findall(
                    r'\[(\w+)-\d+\]: process has died '
                    r'\[pid \d+, exit code (-?\d+),', text,
                )
            ]
            if proc.poll() is not None or time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        report.update(clean_processes=dict(clean), crashed_processes=died)
        assert clean == Counter({name: 1 for name in clean_expected}), text
        assert died == died_expected, text
        report['node_exits_verified'] = True
        if proc.poll() is None:
            # 每个节点都已退出；只终止残留的本次 Launch PID，不操作进程组。
            report['mode'] = 'shell_only_sigterm'
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                report['mode'] = 'shell_only_sigkill'
                proc.kill()
                proc.wait(timeout=3.0)
        else:
            assert proc.returncode == 0, text
        report['exit_code'] = proc.returncode
    finally:
        report['exit_code'] = proc.poll()
        log_path.with_suffix('.shutdown.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )


class FakeLaunchProcess:
    """只模拟 Launch 外壳；是否允许终止由真实日志判据决定."""

    def __init__(self, exits_on_sigint=False):
        self.exits_on_sigint = exits_on_sigint
        self.returncode = None
        self.terminated = False
        self.killed = False

    def send_signal(self, signal_number):
        assert signal_number == signal.SIGINT
        if self.exits_on_sigint:
            self.returncode = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -signal.SIGTERM

    def kill(self):
        self.killed = True
        self.returncode = -signal.SIGKILL

    def wait(self, timeout):
        assert timeout > 0
        return self.returncode


def clean_process_log(names):
    """生成与 Launch 实际输出相同格式的具名进程退出记录."""
    return '\n'.join(
        f'[INFO] [{name}-{index}]: process has finished cleanly [pid {index}]'
        for index, name in enumerate(sorted(names), 1)
    ) + '\n'


def expire_shutdown_deadline(monkeypatch):
    """让首次检查即超过期限，避免模拟测试真实等待 20 秒."""
    clock = iter((0.0, 21.0))
    monkeypatch.setattr(time, 'monotonic', lambda: next(clock))


def test_day5_shutdown_accepts_all_clean_nodes(tmp_path):
    log_path = tmp_path / 'normal.log'
    log_path.write_text(clean_process_log(SYSTEM_PROCESSES), encoding='utf-8')
    process = FakeLaunchProcess(exits_on_sigint=True)
    shutdown_day5_launch(process, log_path, sensor_crash_expected=False)
    report = json.loads(log_path.with_suffix('.shutdown.json').read_text())
    assert report['node_exits_verified'] is True
    assert report['mode'] == 'sigint'
    assert report['exit_code'] == 0
    assert not process.terminated and not process.killed


def test_day5_shutdown_rejects_missing_node_before_termination(
        tmp_path, monkeypatch):
    log_path = tmp_path / 'missing-node.log'
    log_path.write_text(
        clean_process_log(SYSTEM_PROCESSES - {'spatial_health_monitor'}),
        encoding='utf-8',
    )
    process = FakeLaunchProcess()
    expire_shutdown_deadline(monkeypatch)
    with pytest.raises(AssertionError):
        shutdown_day5_launch(process, log_path, sensor_crash_expected=False)
    report = json.loads(log_path.with_suffix('.shutdown.json').read_text())
    assert report['node_exits_verified'] is False
    assert not process.terminated and not process.killed


def test_day5_shutdown_allows_verified_shell_only_cleanup(
        tmp_path, monkeypatch):
    log_path = tmp_path / 'crashed-sensor.log'
    log_path.write_text(
        clean_process_log(SYSTEM_PROCESSES - {'sensor_simulator'})
        + '[ERROR] [sensor_simulator-1]: process has died '
        "[pid 99, exit code 1, cmd 'sensor_simulator']\n",
        encoding='utf-8',
    )
    process = FakeLaunchProcess()
    expire_shutdown_deadline(monkeypatch)
    shutdown_day5_launch(process, log_path, sensor_crash_expected=True)
    report = json.loads(log_path.with_suffix('.shutdown.json').read_text())
    assert report['node_exits_verified'] is True
    assert report['crashed_processes'] == [['sensor_simulator', 1]]
    assert report['mode'] == 'shell_only_sigterm'
    assert report['exit_code'] == -signal.SIGTERM
    assert process.terminated and not process.killed


def run_day5_launch(tmp_path, domain, extra_args, scenario):
    env = dict(
        os.environ,
        ROS_DOMAIN_ID=str(domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
    )
    parameters = {
        'use_rviz': 'false', 'publish_rate': '20.0',
        'timeout_sec': '2.0', 'tf_timeout_sec': '0.4',
        'diagnostic_rate': '20.0', 'frame_publish_rate': '20.0',
    }
    parameters.update(item.split(':=', 1) for item in extra_args)
    args = [
        'ros2', 'launch', 'embodied_comm', 'week03_day5.launch.py',
        *(f'{name}:={value}' for name, value in parameters.items()),
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
            spin_until(
                executor,
                lambda: launch_alive() and SYSTEM_PROCESSES <= set(
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

            shutdown_day5_launch(
                proc, log_path,
                float(parameters.get('fault_sensor_crash_after_sec', '0')) > 0,
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
