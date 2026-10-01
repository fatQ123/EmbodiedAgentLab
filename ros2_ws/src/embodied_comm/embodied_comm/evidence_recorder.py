"""第 3 周第 6 天：自动运行故障矩阵并保存可回放证据."""
import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


RECORDED_TOPICS = (
    '/sensor_state',
    '/diagnostics',
    '/task_status',
    '/tf',
    '/tf_static',
    '/inspection_target_marker',
    '/execute_task_long/_action/feedback',
    '/execute_task_long/_action/status',
    '/rosout',
)

EXPECTED_NODES = {
    'sensor_simulator',
    'task_executor',
    'status_monitor',
    'workcell_visualizer',
    'spatial_health_monitor',
}

# 观察器早于 Publisher 启动时必须给出类型，否则 ros2 echo 可能直接退出。
DIAGNOSTIC_ECHO = (
    'ros2', 'topic', 'echo', '/diagnostics',
    'diagnostic_msgs/msg/DiagnosticArray',
)


@dataclass(frozen=True)
class DriverCommand:
    """一个场景内必须执行并核对退出码的命令."""

    label: str
    argv: tuple[str, ...]
    expected_codes: tuple[int, ...] = (0,)
    timeout_sec: float = 10.0


@dataclass(frozen=True)
class Scenario:
    """一次互相隔离的故障注入与采集任务."""

    key: str
    category: str
    title: str
    domain_offset: int
    launch_overrides: tuple[tuple[str, str], ...]
    settle_sec: float
    checks: tuple[str, ...]
    drivers: tuple[DriverCommand, ...] = ()
    after_drivers_sec: float = 0.2


@dataclass(frozen=True)
class FaultRecord:
    """生成中文七段式故障记录所需的知识模板."""

    title: str
    phenomenon: str
    commands: str
    picture: str
    logs: str
    root_cause: str
    fix: str
    regression: str


def _service_call(label='service-result'):
    return DriverCommand(
        label=label,
        argv=(
            'ros2', 'service', 'call', '/execute_task',
            'std_srvs/srv/Trigger', '{}',
        ),
    )


SCENARIOS = (
    Scenario(
        key='qos_mismatch',
        category='qos_mismatch',
        title='QoS 不匹配',
        domain_offset=0,
        launch_overrides=(('publisher_reliability', 'best_effort'),),
        settle_sec=1.4,
        checks=('可靠性=best_effort', 'qos_mismatch'),
        drivers=(_service_call(),),
    ),
    Scenario(
        key='topic_stop',
        category='topic_stop',
        title='话题停止',
        domain_offset=1,
        launch_overrides=(('fault_stop_after_sec', '6.0'),),
        settle_sec=6.8,
        checks=('停止发布', 'value: stale'),
        drivers=(_service_call(),),
    ),
    Scenario(
        key='tf_missing',
        category='tf_fault',
        title='TF 缺失',
        domain_offset=2,
        launch_overrides=(('tf_fault_mode', 'missing'),),
        settle_sec=1.4,
        checks=('坐标链缺失', 'value: missing'),
        drivers=(_service_call(),),
    ),
    Scenario(
        key='tf_stale',
        category='tf_fault',
        title='TF 过期',
        domain_offset=3,
        launch_overrides=(
            ('tf_fault_mode', 'stale'),
            ('tf_fault_after_sec', '6.0'),
        ),
        settle_sec=6.8,
        checks=('停止刷新', 'value: stale'),
        drivers=(_service_call(),),
    ),
    Scenario(
        key='service_timeout',
        category='service_timeout',
        title='Service 超时',
        domain_offset=4,
        launch_overrides=(
            ('fault_service_delay_sec', '1.0'),
            ('timeout_sec', '5.0'),
        ),
        settle_sec=0.2,
        checks=('服务响应超时', '延迟 1.00 秒后响应'),
        drivers=(
            DriverCommand(
                label='service-timeout-client',
                argv=(
                    'ros2', 'run', 'embodied_comm',
                    'service_timeout_demo', '--response-timeout', '0.2',
                ),
                expected_codes=(6,),
            ),
        ),
        after_drivers_sec=1.1,
    ),
    Scenario(
        key='action_cancel',
        category='action_cancel',
        title='Action 取消与恢复',
        domain_offset=5,
        launch_overrides=(('timeout_sec', '3.0'),),
        settle_sec=0.2,
        checks=(
            '最终状态=CANCELED',
            '接受取消请求',
            '最终状态=SUCCEEDED',
        ),
        drivers=(
            DriverCommand(
                label='action-cancel-client',
                argv=(
                    'ros2', 'run', 'embodied_comm', 'inspection_demo',
                    '--task-name', 'inspect_workpiece_WP-DAY6-CANCEL',
                    '--duration', '2.0', '--cancel-at', '40',
                ),
                expected_codes=(3,),
            ),
            DriverCommand(
                label='action-recovery-client',
                argv=(
                    'ros2', 'run', 'embodied_comm', 'inspection_demo',
                    '--task-name', 'inspect_workpiece_WP-DAY6-RECOVER',
                    '--duration', '0.3',
                ),
            ),
        ),
    ),
    Scenario(
        key='node_crash',
        category='node_crash',
        title='节点崩溃',
        domain_offset=6,
        launch_overrides=(('fault_sensor_crash_after_sec', '6.0'),),
        settle_sec=6.8,
        checks=('即将崩溃', 'process has died', 'exit code 1',
                'publisher_lost'),
        drivers=(_service_call(),),
    ),
)


FAULT_RECORDS = {
    'qos_mismatch': FaultRecord(
        title='QoS 不匹配',
        phenomenon=(
            'Publisher 存在，但 RELIABLE 业务订阅收不到 BEST_EFFORT 数据，'
            '诊断为 `qos_mismatch`，任务检查失败。'
        ),
        commands=(
            '`ros2 topic info /sensor_state --verbose`；'
            '`ros2 topic echo /diagnostics`；调用 `/execute_task`。'
        ),
        picture='RViz 坐标树正常；画面正常而测量任务失败。',
        logs=(
            '核对 `publisher_reliability=best_effort`、'
            '`subscriber_reliability=reliable` 和 '
            '`qos_compatibility=incompatible`。'
        ),
        root_cause='DDS Requested/Offered 可靠性策略不兼容，端点发现不等于可传输。',
        fix='统一发布端与业务订阅端的 QoS；本项目恢复 `reliable`。',
        regression='确认消息序号增长、诊断 `healthy`、Service 与 Action 成功。',
    ),
    'topic_stop': FaultRecord(
        title='话题停止',
        phenomenon=(
            '节点和 Publisher 保持在线，但序号停止增长，超时后诊断为 `stale`，'
            '任务被新鲜度门禁拒绝。'
        ),
        commands=(
            '`ros2 node list`；`ros2 topic info /sensor_state --verbose`；'
            '`ros2 topic hz /sensor_state`；调用 `/execute_task`。'
        ),
        picture='RViz 的 TF 与 Marker 仍正常，不能据此证明测量链健康。',
        logs='出现“停止发布”和“传感器消息超时”，Publisher 数量仍为 1。',
        root_cause='数据定时器停止，模拟驱动在线但采集线程冻结。',
        fix='关闭停止注入并重启，等待新数据到达后再解除任务联锁。',
        regression='确认新序号持续增长、诊断恢复 `healthy`、任务恢复。',
    ),
    'tf_fault': FaultRecord(
        title='TF 缺失或过期',
        phenomenon=(
            '缺失时 `world → tool0` 从未连通；过期时链先正常，随后动态 TF '
            '时间戳停止并进入 `stale`。'
        ),
        commands=(
            '`ros2 run tf2_ros tf2_echo world tool0`；'
            '`ros2 topic info /tf --verbose`；查看 TF 诊断。'
        ),
        picture=(
            '缺失时 RViz 出现两棵子树且 tool0 Marker 不显示；过期时目标会消失'
            '或出现 old data/extrapolation，具体瞬态受 RViz 缓存影响。'
        ),
        logs=(
            '分别查找“坐标链缺失”或“停止刷新”，并核对诊断的 '
            '`state=missing/stale` 与 `age_sec`。'
        ),
        root_cause='关键动态边从未发布，或其时间戳超过允许的新鲜度。',
        fix='恢复唯一、连续且时钟正确的 TF 发布源，使用 `normal` 模式重启。',
        regression='确认完整链持续输出、时间戳增长、空间诊断 `healthy`、Marker 可见。',
    ),
    'service_timeout': FaultRecord(
        title='Service 超时',
        phenomenon=(
            '客户端先达到响应期限并退出，但 Server 仍会完成原请求并发布终态。'
        ),
        commands=(
            '`ros2 service list -t`；`ros2 node info /task_executor`；'
            '查看 `/task_status` 和超时客户端退出码。'
        ),
        picture='RViz 保持正常；该故障属于接口时序而非空间链。',
        logs='客户端出现“服务响应超时”，Server 稍后记录“延迟 1.00 秒后响应”。',
        root_cause='客户端截止时间短于 Server 执行时间；客户端超时不会取消回调。',
        fix='关闭延迟；长任务改用 Action，有副作用的 Service 增加幂等键。',
        regression='短截止时间内收到正常响应，且 `/task_status` 每次请求只发布一次。',
    ),
    'action_cancel': FaultRecord(
        title='Action 取消',
        phenomenon=(
            '目标在 40% 请求取消并进入 `CANCELED`，随后新目标可进入 '
            '`SUCCEEDED`。'
        ),
        commands=(
            '`ros2 action list -t`；`ros2 action info /execute_task_long`；'
            '查看 Feedback、Result 与 `/task_status`。'
        ),
        picture='当前 Marker 不受 Action 驱动，取消证据来自协议终态而非 RViz 动作。',
        logs='依次出现取消请求、`CANCELED`、工位释放和恢复目标 `SUCCEEDED`。',
        root_cause='客户端主动发出标准 Action Cancel Request，Server 协作停止。',
        fix='取消是安全动作；确保执行循环响应取消并在 `finally` 释放工位。',
        regression='取消后立即提交下一目标，确认不拒绝、不死锁且成功完成。',
    ),
    'node_crash': FaultRecord(
        title='节点崩溃',
        phenomenon=(
            '`sensor_simulator` 以退出码 1 消失，Publisher 数量变为 0，'
            '其他节点继续运行并诊断 `publisher_lost`。'
        ),
        commands=(
            '`ros2 node list`；`ros2 topic info /sensor_state --verbose`；'
            '查看 `/diagnostics`、Launch 退出日志并调用 `/execute_task`。'
        ),
        picture='独立 TF/Marker 画面保持正常，说明空间链与测量进程相互隔离。',
        logs='组合“即将崩溃”、异常栈、`process has died`、`exit code 1`。',
        root_cause='故障 Timer 抛出未捕获异常，进程退出后 DDS 端点被清理。',
        fix='关闭注入并重启；生产部署增加有退避和上限的进程监管策略。',
        regression='确认节点和 Publisher 恢复、诊断 `healthy`、新数据任务成功。',
    ),
}


COMMON_LAUNCH_ARGUMENTS = {
    'use_rviz': 'false',
    'publish_rate': '10.0',
    'timeout_sec': '0.6',
    'diagnostic_rate': '10.0',
    'frame_publish_rate': '10.0',
    'tf_timeout_sec': '0.6',
}


def scenario_launch_arguments(scenario):
    """合并公共参数与场景覆盖，保证每个参数只出现一次."""
    values = dict(COMMON_LAUNCH_ARGUMENTS)
    values.update(dict(scenario.launch_overrides))
    return [f'{name}:={value}' for name, value in values.items()]


def evidence_environment(domain_id):
    """创建独立 DDS Domain，并绕开可能缓存旧 Domain 的 ros2 daemon."""
    return dict(
        os.environ,
        ROS_DOMAIN_ID=str(domain_id),
        ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
        ROS2CLI_DISABLE_DAEMON='1',
    )


def write_command_log(path, argv, returncode, output):
    """把命令、退出码和合并输出写进同一个文本日志."""
    path.write_text(
        f'$ {shlex.join(argv)}\nexit_code={returncode}\n\n{output}',
        encoding='utf-8',
    )


def run_captured(argv, env, timeout_sec):
    """执行有时限的命令；超时用 124 表示并回收整个进程组."""
    process = subprocess.Popen(
        argv,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout_sec)
        return process.returncode, output
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or ''
        if isinstance(partial, bytes):
            partial = partial.decode(errors='replace')
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            tail, _ = process.communicate(timeout=3.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            tail, _ = process.communicate()
        # communicate() 重试返回完整已缓存输出；拼接 partial 会重复日志。
        return 124, tail if tail is not None else partial


def stop_process(process, interrupt_timeout=15.0, signal_group=True):
    """先请求干净退出，超时后逐级终止，返回退出码与终止方式."""
    if process is None:
        return None, 'not_started'
    if process.poll() is not None:
        return process.returncode, 'already_finished'
    try:
        if signal_group:
            os.killpg(process.pid, signal.SIGINT)
        else:
            process.send_signal(signal.SIGINT)
    except ProcessLookupError:
        return process.poll(), 'already_finished'
    try:
        process.wait(timeout=interrupt_timeout)
        return process.returncode, 'sigint'
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return process.poll(), 'sigint'
    try:
        process.wait(timeout=5.0)
        return process.returncode, 'sigterm'
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3.0)
        return process.returncode, 'sigkill'


def wait_for_nodes(env, launch_process, timeout_sec=12.0):
    """等五个节点都进入 ROS Graph，并保留最后一次 Graph 快照."""
    deadline = time.monotonic() + timeout_sec
    last_code = 1
    last_output = ''
    while time.monotonic() < deadline:
        if launch_process.poll() is not None:
            return False, (
                f'Launch 提前退出：exit_code={launch_process.returncode}\n'
                f'{last_output}'
            )
        last_code, last_output = run_captured(
            ['ros2', 'node', 'list'], env, timeout_sec=3.0,
        )
        names = {line.strip().lstrip('/') for line in last_output.splitlines()}
        if last_code == 0 and EXPECTED_NODES <= names:
            return True, last_output
        time.sleep(0.25)
    missing = sorted(EXPECTED_NODES - {
        line.strip().lstrip('/') for line in last_output.splitlines()
    })
    return False, (
        f'等待节点超时，last_exit_code={last_code}，missing={missing}\n'
        f'{last_output}'
    )


def start_logged_process(argv, env, log_path):
    """启动长期进程并把标准输出和错误流定向到同一日志."""
    stream = log_path.open('w', encoding='utf-8')
    process = subprocess.Popen(
        argv,
        env=env,
        stdout=stream,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return process, stream


def run_and_log(command, scenario_dir, env):
    """执行一个声明式命令并返回可序列化的验收结果."""
    code, output = run_captured(
        list(command.argv), env, timeout_sec=command.timeout_sec,
    )
    write_command_log(
        scenario_dir / f'{command.label}.log',
        list(command.argv), code, output,
    )
    return {
        'label': command.label,
        'command': shlex.join(command.argv),
        'exit_code': code,
        'expected_codes': list(command.expected_codes),
        'passed': code in command.expected_codes,
    }


def collect_snapshots(scenario_dir, env):
    """采集图、端点、接口和诊断快照；连续命令以预期超时结束."""
    probes = (
        DriverCommand('nodes', ('ros2', 'node', 'list')),
        DriverCommand(
            'sensor-topic',
            ('ros2', 'topic', 'info', '/sensor_state', '--verbose'),
        ),
        DriverCommand(
            'service-list', ('ros2', 'service', 'list', '-t'),
        ),
        DriverCommand(
            'action-list', ('ros2', 'action', 'list', '-t'),
        ),
        DriverCommand(
            'diagnostics-snapshot',
            DIAGNOSTIC_ECHO,
            expected_codes=(124,), timeout_sec=3.0,
        ),
        DriverCommand(
            'tf-snapshot',
            ('ros2', 'run', 'tf2_ros', 'tf2_echo', 'world', 'tool0'),
            expected_codes=(124,), timeout_sec=1.2,
        ),
    )
    return [run_and_log(probe, scenario_dir, env) for probe in probes]


def combined_logs(scenario_dir):
    """读取场景根目录的所有文本日志用于关键证据匹配."""
    parts = []
    for path in sorted(scenario_dir.glob('*.log')):
        try:
            parts.append(path.read_text(encoding='utf-8', errors='replace'))
        except OSError:
            continue
    return '\n'.join(parts)


def bag_message_count(info_text):
    """从 ros2 bag info 的稳定 Messages 字段提取消息数."""
    match = re.search(r'^\s*Messages:\s*(\d+)\s*$', info_text, re.MULTILINE)
    return int(match.group(1)) if match else 0


def run_scenario(scenario, output_dir, base_domain):
    """运行一个场景；任何失败都转成结果记录，让矩阵继续执行."""
    scenario_dir = output_dir / scenario.key
    scenario_dir.mkdir(parents=True)
    domain_id = base_domain + scenario.domain_offset
    env = evidence_environment(domain_id)
    failures = []
    commands = []
    launch_process = None
    launch_stream = None
    bag_process = None
    bag_stream = None
    diagnostic_process = None
    diagnostic_stream = None
    bag_dir = scenario_dir / 'rosbag'

    launch_argv = [
        'ros2', 'launch', 'embodied_comm', 'week03_day5.launch.py',
        *scenario_launch_arguments(scenario),
    ]
    bag_argv = [
        'ros2', 'bag', 'record', '--storage', 'mcap',
        '--output', str(bag_dir), '--disable-keyboard-controls',
        '--include-hidden-topics', '--polling-interval', '100',
        '--node-name', f'week03_day6_recorder_{scenario.key}',
        '--custom-data', f'scenario={scenario.key}',
        f'category={scenario.category}',
        '--topics', *RECORDED_TOPICS,
    ]
    write_command_log(
        scenario_dir / 'scenario-command.log', launch_argv, -1,
        f'ROS_DOMAIN_ID={domain_id}\n',
    )
    try:
        # Recorder 先启动，避免短故障发生后才开始 DDS 发现而丢失前态。
        bag_process, bag_stream = start_logged_process(
            bag_argv, env, scenario_dir / 'rosbag-record.log',
        )
        time.sleep(0.8)
        if bag_process.poll() is not None:
            failures.append(
                f'rosbag Recorder 提前退出：exit_code={bag_process.returncode}'
            )

        # 观察器与 Recorder 均先于系统启动，保留发现和健康前态。
        diagnostic_process, diagnostic_stream = start_logged_process(
            list(DIAGNOSTIC_ECHO),
            env, scenario_dir / 'diagnostics-live.log',
        )
        launch_process, launch_stream = start_logged_process(
            launch_argv, env, scenario_dir / 'launch.log',
        )
        ready, readiness_output = wait_for_nodes(env, launch_process)
        (scenario_dir / 'readiness.log').write_text(
            readiness_output, encoding='utf-8',
        )
        if not ready:
            failures.append('五个系统节点未在时限内全部就绪')

        # 给 Recorder 和观察器一个发现所有已上线 Topic 的窗口。
        time.sleep(0.8)
        if diagnostic_process.poll() is not None:
            failures.append(
                '诊断观察器提前退出：'
                f'exit_code={diagnostic_process.returncode}'
            )
        time.sleep(scenario.settle_sec)
        for driver in scenario.drivers:
            result = run_and_log(driver, scenario_dir, env)
            commands.append(result)
            if not result['passed']:
                failures.append(
                    f'{driver.label} 退出码 {result["exit_code"]}，'
                    f'期望 {result["expected_codes"]}'
                )
        time.sleep(scenario.after_drivers_sec)
        snapshots = collect_snapshots(scenario_dir, env)
        commands.extend(snapshots)
        for result in snapshots:
            if not result['passed']:
                failures.append(
                    f'{result["label"]} 退出码 {result["exit_code"]}，'
                    f'期望 {result["expected_codes"]}'
                )
    except Exception as exc:  # 保留其他场景，最终统一报告失败。
        failures.append(f'场景执行异常：{type(exc).__name__}: {exc}')
    finally:
        diagnostic_code, diagnostic_stop = stop_process(diagnostic_process)
        if diagnostic_stream is not None:
            diagnostic_stream.close()
        bag_code, bag_stop = stop_process(bag_process)
        if bag_stream is not None:
            bag_stream.close()
        launch_code, launch_stop = stop_process(
            launch_process, signal_group=False,
        )
        if launch_stream is not None:
            launch_stream.close()

    if bag_code != 0 or bag_stop != 'sigint':
        failures.append(
            f'Recorder 未干净退出：exit_code={bag_code}，stop={bag_stop}'
        )
    if launch_code != 0 or launch_stop != 'sigint':
        failures.append(
            f'Launch 未干净退出：exit_code={launch_code}，stop={launch_stop}'
        )

    info_code = None
    info_text = ''
    message_count = 0
    if bag_dir.exists():
        info_argv = ['ros2', 'bag', 'info', str(bag_dir)]
        info_code, info_text = run_captured(info_argv, env, timeout_sec=15.0)
        write_command_log(
            scenario_dir / 'bag-info.log', info_argv, info_code, info_text,
        )
        message_count = bag_message_count(info_text)
        if info_code != 0:
            failures.append(f'ros2 bag info 失败：exit_code={info_code}')
        if message_count <= 0:
            failures.append('rosbag 中没有消息')
    else:
        failures.append('rosbag 输出目录不存在')

    all_text = combined_logs(scenario_dir)
    check_results = []
    for needle in scenario.checks:
        found = needle in all_text
        check_results.append({'needle': needle, 'found': found})
        if not found:
            failures.append(f'证据中缺少关键文本：{needle}')

    result = {
        'key': scenario.key,
        'category': scenario.category,
        'title': scenario.title,
        'domain_id': domain_id,
        'status': 'passed' if not failures else 'failed',
        'failures': failures,
        'checks': check_results,
        'commands': commands,
        'rosbag': {
            'path': str(bag_dir.relative_to(output_dir)),
            'record_exit_code': bag_code,
            'record_stop': bag_stop,
            'info_exit_code': info_code,
            'message_count': message_count,
            'topics': list(RECORDED_TOPICS),
        },
        'launch': {
            'command': shlex.join(launch_argv),
            'exit_code': launch_code,
            'stop': launch_stop,
        },
        'diagnostic_observer': {
            'exit_code': diagnostic_code,
            'stop': diagnostic_stop,
            'log': 'diagnostics-live.log',
        },
    }
    (scenario_dir / 'result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    return result


def run_regression(workspace, output_dir, env):
    """执行 ROS 包测试、结果汇总和仓库级 Python 测试."""
    specifications = (
        (
            'colcon-test.log',
            [
                'colcon', 'test', '--packages-select',
                'embodied_interfaces', 'embodied_comm', 'embodied_comm_cpp',
                '--event-handlers', 'console_direct+',
            ],
            600.0,
        ),
        (
            'colcon-test-result.log',
            ['colcon', 'test-result', '--all', '--verbose'],
            60.0,
        ),
        (
            'repository-tests.log',
            [
                sys.executable, '-m', 'pytest', '-q',
                str(workspace.parent / 'tests'),
            ],
            120.0,
        ),
    )
    results = []
    for filename, argv, timeout_sec in specifications:
        command_env = env
        if filename == 'repository-tests.log':
            command_env = dict(env)
            root_source = str(workspace.parent / 'src')
            old_python_path = command_env.get('PYTHONPATH', '')
            command_env['PYTHONPATH'] = os.pathsep.join(
                item for item in (root_source, old_python_path) if item
            )
        process = subprocess.Popen(
            argv,
            cwd=workspace,
            env=command_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            output, _ = process.communicate(timeout=timeout_sec)
            code = process.returncode
        except subprocess.TimeoutExpired as exc:
            partial = exc.output or ''
            if isinstance(partial, bytes):
                partial = partial.decode(errors='replace')
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                tail, _ = process.communicate(timeout=5.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                tail, _ = process.communicate()
            output = tail if tail is not None else partial
            code = 124
        write_command_log(output_dir / filename, argv, code, output)
        results.append({
            'command': shlex.join(argv),
            'log': filename,
            'exit_code': code,
            'passed': code == 0,
        })
    return results


def render_chinese_report(summary):
    """把本次实际结果与固定排障知识合并为七段式中文报告."""
    by_category = {}
    for result in summary['scenarios']:
        by_category.setdefault(result['category'], []).append(result)
    lines = [
        '# 第 3 周第 6 天自动故障记录',
        '',
        f'- 开始时间：`{summary["started_at"]}`',
        f'- 结束时间：`{summary["finished_at"]}`',
        f'- 总体结果：`{summary["status"]}`',
        f'- 输出目录：`{summary["output_dir"]}`',
        '',
        '> rosbag 保存消息时间线；CLI/Launch 文件日志保存超时、退出码和进程事件。',
        '',
    ]
    for index, (category, record) in enumerate(FAULT_RECORDS.items(), 1):
        results = by_category.get(category, [])
        verdict = '未运行'
        if results:
            verdict = (
                '通过' if all(item['status'] == 'passed' for item in results)
                else '失败'
            )
        scenario_links = '；'.join(
            f'`{item["key"]}/`（{item["status"]}，'
            f'bag={item["rosbag"]["message_count"]} 条）'
            for item in results
        ) or '无'
        failures = [
            failure for item in results for failure in item.get('failures', [])
        ]
        lines.extend([
            f'## {index}. {record.title}',
            '',
            f'- 本次自动验收：**{verdict}**；证据：{scenario_links}',
            f'- 现象：{record.phenomenon}',
            f'- 检查命令：{record.commands}',
            f'- 画面：{record.picture}',
            f'- 日志：{record.logs}',
            f'- 根因：{record.root_cause}',
            f'- 修复：{record.fix}',
            f'- 回归测试：{record.regression}',
        ])
        if failures:
            lines.append(f'- 本次失败明细：{"；".join(failures)}')
        lines.append('')
    lines.extend([
        '## 回归结果',
        '',
    ])
    if summary['regression']:
        for result in summary['regression']:
            state = '通过' if result['passed'] else '失败'
            lines.append(
                f'- **{state}**：`{result["command"]}`；日志 `{result["log"]}`'
            )
    else:
        lines.append('- 本次使用 `--skip-regression`，未执行回归。')
    lines.extend([
        '',
        '## 回放入口',
        '',
        '进入本报告所在目录后，对任一场景执行：',
        '',
        '```bash',
        'ros2 bag info <scenario>/rosbag',
        'ros2 bag play <scenario>/rosbag',
        '```',
        '',
        'Service 超时和进程崩溃不能只靠话题回放下结论；必须同时查看该场景的',
        '`launch.log`、客户端日志、`nodes.log` 和 `sensor-topic.log`。',
        '',
    ])
    return '\n'.join(lines)


def build_parser():
    """构造命令行解析器，场景名直接取自唯一场景矩阵."""
    parser = argparse.ArgumentParser(
        description='自动运行第 3 周六类故障并保存 rosbag、日志和回归结果。',
    )
    parser.add_argument(
        '--workspace', type=Path, default=Path.cwd(),
        help='ROS 2 工作空间；默认当前目录。',
    )
    parser.add_argument(
        '--output-dir', type=Path,
        help='新的证据目录；默认 artifacts/week03-day6/run-时间戳。',
    )
    parser.add_argument(
        '--scenario', action='append',
        choices=[item.key for item in SCENARIOS],
        help='只运行指定场景；可重复。默认运行全部七个场景。',
    )
    parser.add_argument(
        '--base-domain', type=int, default=210,
        help='场景使用的起始 ROS_DOMAIN_ID，默认 210。',
    )
    parser.add_argument(
        '--skip-regression', action='store_true',
        help='只采集故障证据，不运行最后的完整回归。',
    )
    parser.add_argument(
        '--list-scenarios', action='store_true',
        help='列出场景后退出，不启动 ROS 进程。',
    )
    return parser


def selected_scenarios(keys):
    """按声明顺序返回选中的场景，忽略重复的命令行选择."""
    if not keys:
        return list(SCENARIOS)
    selected = set(keys)
    return [scenario for scenario in SCENARIOS if scenario.key in selected]


def validate_arguments(args, scenarios):
    """检查工作空间与 DDS Domain 范围，避免运行到错误目录."""
    workspace = args.workspace.resolve()
    if not (workspace / 'src' / 'embodied_comm').is_dir():
        raise ValueError(
            f'{workspace} 不是本项目 ros2_ws；请在 ros2_ws 下运行或指定 --workspace'
        )
    domains = [args.base_domain + item.domain_offset for item in scenarios]
    if not domains or min(domains) < 0 or max(domains) > 232:
        raise ValueError('ROS_DOMAIN_ID 必须全部处于 0～232')
    return workspace


def main(argv=None):
    """执行证据矩阵，始终生成 JSON 汇总和中文报告."""
    args = build_parser().parse_args(argv)
    if args.list_scenarios:
        for scenario in SCENARIOS:
            print(
                f'{scenario.key:16} domain+{scenario.domain_offset} '
                f'{scenario.title}'
            )
        return 0

    scenarios = selected_scenarios(args.scenario)
    try:
        workspace = validate_arguments(args, scenarios)
    except ValueError as exc:
        print(f'参数错误：{exc}', file=sys.stderr)
        return 2

    started = datetime.now().astimezone()
    if args.output_dir is None:
        stamp = started.strftime('%Y%m%d-%H%M%S-%f')
        output_dir = (
            workspace.parent / 'artifacts' / 'week03-day6' / f'run-{stamp}'
        )
    else:
        output_dir = args.output_dir.resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(f'输出目录已存在，为避免覆盖已停止：{output_dir}', file=sys.stderr)
        return 2

    print(f'证据输出目录：{output_dir}', flush=True)
    results = []
    for index, scenario in enumerate(scenarios, 1):
        print(
            f'[{index}/{len(scenarios)}] 运行 {scenario.title} '
            f'({scenario.key})...',
            flush=True,
        )
        result = run_scenario(
            scenario, output_dir, args.base_domain,
        )
        results.append(result)
        print(
            f'  -> {result["status"]}，'
            f'rosbag={result["rosbag"]["message_count"]} 条',
            flush=True,
        )

    regression = []
    if not args.skip_regression:
        print('运行完整回归...', flush=True)
        regression = run_regression(
            workspace, output_dir,
            evidence_environment(args.base_domain),
        )

    scenario_ok = all(item['status'] == 'passed' for item in results)
    regression_ok = all(item['passed'] for item in regression)
    finished = datetime.now().astimezone()
    summary = {
        'schema_version': 1,
        'started_at': started.isoformat(timespec='seconds'),
        'finished_at': finished.isoformat(timespec='seconds'),
        'output_dir': str(output_dir),
        'workspace': str(workspace),
        'status': 'passed' if scenario_ok and regression_ok else 'failed',
        'scenario_count': len(results),
        'fault_category_count': len({item['category'] for item in results}),
        'scenarios': results,
        'regression': regression,
    }
    (output_dir / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    (output_dir / '故障记录.md').write_text(
        render_chinese_report(summary), encoding='utf-8',
    )
    print(f'总体结果：{summary["status"]}', flush=True)
    print(f'中文报告：{output_dir / "故障记录.md"}', flush=True)
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
