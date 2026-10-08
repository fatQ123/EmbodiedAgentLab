"""常驻中文菜单：管理第四周合成机械臂演示并显示 ROS 观察值。"""

from __future__ import annotations

import argparse
import codecs
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
from pathlib import Path
import select
import shlex
import signal
import subprocess
import sys
import time
from typing import BinaryIO


HELP = """
两关节机械臂菜单（角度单位 rad；合成状态与运动学观察）
  1  static 固定姿态       /start static
  2  sine 正弦运动         /start sine
  3  gui 手动关节滑块      /start gui
  4  pose 设置角度/中心    /pose Q1 Q2（省略参数则逐项输入）
  5  zero 归零             /zero（sine 模式仅将中心归零）
  6  status 查看状态       /status
  7  logs 查看日志         /logs
  8  stop 停止当前演示     /stop
  0  quit 退出并清理       /quit
                          /help 显示菜单
GUI 模式使用滑块调姿；RViz 默认关闭，仅在明确选择时启动。
输入问题时可用 /cancel 取消本次操作，/quit 退出。
""".strip()

CRITICAL_NODES = {
    'synthetic_joint_publisher', 'robot_state_publisher',
    'joint_state_publisher', 'joint_state_publisher_gui',
}
START_TIMEOUT = 15.0
POSE_TIMEOUT = 5.0
# The existing client has separate service, response and observation deadlines.
POSE_PROCESS_TIMEOUT = 3 * POSE_TIMEOUT + 3.0


def installed_joint_limits():
    """Read the same installed Xacro used by demo.launch.py, without ROS nodes."""
    from ament_index_python.packages import get_package_share_directory
    import xacro

    model = Path(get_package_share_directory('embodied_arm_description')) / 'urdf' / 'two_link_arm.urdf.xacro'
    document = xacro.process_file(str(model))
    joints = {joint.getAttribute('name'): joint for joint in document.getElementsByTagName('joint')}
    limits = {}
    for name in ('joint1', 'joint2'):
        joint = joints.get(name)
        if joint is None or joint.getAttribute('type') != 'revolute':
            raise RuntimeError(f'安装模型缺少 revolute 关节 {name}')
        tags = joint.getElementsByTagName('limit')
        if len(tags) != 1:
            raise RuntimeError(f'安装模型的 {name} 缺少唯一 limit')
        lower, upper, velocity = (float(tags[0].getAttribute(key))
                                  for key in ('lower', 'upper', 'velocity'))
        if (not all(math.isfinite(value) for value in (lower, upper, velocity))
                or lower > upper or velocity < 0):
            raise RuntimeError(f'安装模型的 {name} 限位或速度无效')
        limits[name] = (lower, upper, velocity)
    return limits


def center_bounds(limit, amplitude):
    lower, upper, _ = limit
    minimum, maximum = lower + amplitude, upper - amplitude
    if amplitude > 0 and minimum < maximum:
        minimum = math.nextafter(minimum, math.inf)
        maximum = math.nextafter(maximum, -math.inf)
    # Match the C++ q-A / q+A operations at floating-point boundaries.
    while minimum <= maximum and minimum - amplitude < lower:
        minimum = math.nextafter(minimum, math.inf)
    while maximum >= minimum and maximum + amplitude > upper:
        maximum = math.nextafter(maximum, -math.inf)
    return minimum, maximum


class QuitRequested(Exception):
    pass


class OperationCancelled(Exception):
    pass


@contextmanager
def uninterrupted_cleanup():
    """Keep a second Ctrl-C/SIGTERM from interrupting bounded cleanup."""
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


@contextmanager
def defer_interrupts():
    """Register a newly spawned group before delivering a pending interrupt."""
    received = []
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for sig in previous:
            # A callable disposition becomes SIG_DFL at exec, unlike SIG_IGN.
            signal.signal(sig, lambda signum, frame: received.append(signum))
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if received:
        raise KeyboardInterrupt


@dataclass
class OwnedProcess:
    process: subprocess.Popen
    output: BinaryIO
    log: Path
    kind: str

    @property
    def pgid(self):
        # start_new_session makes the child the leader of its own process group.
        return self.process.pid


def group_is_alive(owned: OwnedProcess) -> bool:
    owned.process.poll()  # Reap the leader before checking its descendants.
    try:
        os.killpg(owned.pgid, 0)
    except ProcessLookupError:
        return False
    # ROS runs on Linux here. Orphan zombies cannot execute or receive signals;
    # do not mistake them for live children when the host init reaps slowly.
    proc = Path('/proc')
    if not proc.is_dir():
        return True
    try:
        for entry in proc.iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(fields[2]) == owned.pgid and fields[0] not in {'Z', 'X'}:
                    return True
            except (FileNotFoundError, ProcessLookupError):
                continue
            except (OSError, ValueError, IndexError):
                # Access errors cannot prove that an owned group has exited.
                continue
        return False
    except OSError:
        return True


class RosObserver:
    """Single-threaded, read-only observation; ROS imports follow --help parsing."""

    def __init__(self):
        import rclpy
        from rclpy.parameter_client import AsyncParameterClient
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from rclpy.signals import SignalHandlerOptions
        from rclpy.time import Time
        from sensor_msgs.msg import JointState
        from tf2_ros import Buffer, TransformException, TransformListener

        self.rclpy = rclpy
        self.Time = Time
        self.TransformException = TransformException
        self.latest = None
        self.received_at = 0.0
        # Keep several in-flight samples: TF may start after the first state,
        # or arrive after a newer state. Neither frame should lock the wait.
        self.recent = deque(maxlen=64)
        self.node = None
        self.listener = None
        rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
        try:
            self.node = rclpy.create_node(f'arm_cli_{os.getpid()}')
            self.buffer = Buffer()
            self.listener = TransformListener(self.buffer, self.node)
            qos = QoSProfile(
                depth=10, reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            self.subscription = self.node.create_subscription(
                JointState, '/joint_states', self._receive, qos,
            )
            self.clients = {
                'cpp': AsyncParameterClient(self.node, '/synthetic_joint_publisher'),
                'gui': AsyncParameterClient(self.node, '/joint_state_publisher_gui'),
            }
        except BaseException:
            self.close()
            raise

    def _receive(self, msg):
        self.latest = msg
        self.received_at = time.monotonic()
        self.recent.append((msg, self.received_at))

    def spin(self, timeout=0.05):
        self.rclpy.spin_once(self.node, timeout_sec=timeout)

    def publishers(self):
        return self.node.get_publishers_info_by_topic('/joint_states')

    def nodes(self):
        return [
            (namespace.rstrip('/') + '/' + name)
            for name, namespace in self.node.get_node_names_and_namespaces()
        ]

    def stamp_ns(self, msg):
        return self.Time.from_msg(msg.header.stamp).nanoseconds

    def transform(self, msg):
        try:
            return self.buffer.lookup_transform(
                'base_link', 'tool0', self.Time.from_msg(msg.header.stamp),
            )
        except self.TransformException:
            return None

    def close(self):
        if self.listener is not None:
            self.listener.unregister()
        if self.node is not None:
            self.node.destroy_node()
            self.node = None
        if self.rclpy.ok():
            self.rclpy.shutdown()


class ArmCli:
    def __init__(self, args, observer):
        self.observer = observer
        self.args = args
        session = datetime.now().strftime('%Y%m%d-%H%M%S-%f') + f'-{os.getpid()}'
        self.session_dir = args.project_root / 'artifacts' / 'week04' / 'cli' / session
        self.session_dir.mkdir(parents=True, exist_ok=False)
        self.environment = os.environ.copy()
        self.environment['ROS_LOG_DIR'] = str(self.session_dir / 'ros')
        self.environment['ROS_DOMAIN_ID'] = str(args.domain_id)
        self.environment['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
        self.event_log = self.session_dir / 'cli.log'
        self.events = self.event_log.open('a', encoding='utf-8')
        self.log_files = []
        self.owned = []
        self.demo = None
        self.mode = None
        self.publisher_gid = None
        self.rate = 20.0
        self.joint_limits = None
        self.amplitudes = None
        self.sequence = 0
        self.input_buffer = ''
        self.input_eof = False
        self.decoder = codecs.getincrementaldecoder(sys.stdin.encoding or 'utf-8')(
            errors='replace',
        )

    def say(self, text):
        print(text, flush=True)
        self.events.write(f'{datetime.now().isoformat(timespec="seconds")} {text}\n')
        self.events.flush()

    def _spawn(self, command, kind):
        self.sequence += 1
        log = self.session_dir / f'{kind}-{self.sequence:03d}.log'
        self.log_files.append(log)
        output = log.open('wb')
        output.write(('# ' + shlex.join(command) + '\n').encode('utf-8'))
        output.flush()
        try:
            with defer_interrupts():
                process = subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=output,
                    stderr=subprocess.STDOUT, start_new_session=True,
                    cwd=self.args.project_root, env=self.environment,
                )
                owned = OwnedProcess(process, output, log, kind)
                self.owned.append(owned)
        except BaseException:
            # An interrupt may arrive after registration. Leave that group's
            # output open for the final cleanup; close only an unowned file.
            if not any(item.output is output for item in self.owned):
                output.close()
            raise
        self.say(f'已创建自有进程组 {owned.pgid}，日志：{log}')
        return owned

    def _stop_group(self, owned):
        with uninterrupted_cleanup():
            for sig, wait in ((signal.SIGINT, 2.0), (signal.SIGTERM, 2.0),
                              (signal.SIGKILL, 1.0)):
                if not group_is_alive(owned):
                    break
                try:
                    os.killpg(owned.pgid, sig)
                except ProcessLookupError:
                    break
                deadline = time.monotonic() + wait
                while group_is_alive(owned) and time.monotonic() < deadline:
                    time.sleep(0.05)
            stopped = not group_is_alive(owned)
            if stopped:
                owned.output.close()
                if owned in self.owned:
                    self.owned.remove(owned)
            else:
                self.say(f'进程组 {owned.pgid} 仍未确认退出；保留记录并禁止再次启动。')
            return stopped

    def stop(self, quiet=False):
        success = True
        with uninterrupted_cleanup():
            for owned in list(self.owned):
                success = self._stop_group(owned) and success
            if success:
                had_demo = self.demo is not None
                self.demo = None
                self.mode = None
                self.publisher_gid = None
                self.joint_limits = None
                self.amplitudes = None
                if not quiet:
                    self.say('当前自有演示已停止。' if had_demo else '没有运行中的自有演示。')
        return success

    def _monitor(self):
        if self.demo is not None and self.demo.process.poll() is not None:
            demo = self.demo
            self.say(f'\n演示意外退出（退出码 {demo.process.returncode}）；日志：{demo.log}')
            self._stop_group(demo)
            # Unconfirmed groups remain in self.owned and prevent a new start.
            self.demo = None
            self.mode = None
            self.publisher_gid = None
            self.joint_limits = None
            self.amplitudes = None
            return True
        return False

    def readline(self, prompt):
        print(prompt, end='', flush=True)
        while True:
            if self._monitor():
                print(prompt, end='', flush=True)
            self.observer.spin(0.02)
            if '\n' in self.input_buffer:
                line, self.input_buffer = self.input_buffer.split('\n', 1)
                return line.rstrip('\r')
            if self.input_eof:
                if self.input_buffer:
                    line, self.input_buffer = self.input_buffer, ''
                    return line
                raise QuitRequested
            readable, _, _ = select.select([sys.stdin.fileno()], [], [], 0.15)
            if readable:
                data = os.read(sys.stdin.fileno(), 4096)
                self.input_buffer += self.decoder.decode(data, final=not data)
                self.input_eof = not data

    def answer(self, prompt):
        value = self.readline(prompt).strip()
        if value == '/quit':
            raise QuitRequested
        if value == '/cancel':
            raise OperationCancelled
        return value

    def number(self, prompt, default=None, *, lower=None, upper=None, positive=False, valid=None):
        interval = ''
        if lower is not None and upper is not None:
            interval = f' 范围{"(" if positive else "["}{lower!r}, {upper!r}]'
        suffix = f' [{default!r}]' if default is not None else ''
        while True:
            value = self.answer(prompt + interval + suffix + '：')
            try:
                result = default if value == '' and default is not None else float(value)
                if not math.isfinite(result):
                    raise ValueError
                if ((lower is None or result >= lower)
                        and (upper is None or result <= upper)
                        and (not positive or result > 0)
                        and (valid is None or valid(result))):
                    return result
                self.say('数值超出当前可用范围或耦合约束，请重新输入。')
            except ValueError:
                self.say('请输入有限数字；不要使用 NaN、inf 或非数字文本。')

    def _configuration(self, mode):
        values = {}
        limits = None
        if mode != 'gui':
            try:
                limits = installed_joint_limits()
            except Exception as error:
                self.say(f'无法读取所选安装模型的关节范围：{error}；请修复模型后重试。')
                raise OperationCancelled from error
            label = '固定角度' if mode == 'static' else '正弦中心'
            if mode == 'sine':
                self.say('正弦中心可选关节全限位；需同时满足 L ≤ 中心−振幅、中心+振幅 ≤ U。')
                for name, limit in limits.items():
                    low, high = center_bounds(limit, 0.5)
                    if low <= high:
                        self.say(f'{name} 使用默认振幅 0.5 rad 时，中心范围为 [{low!r}, {high!r}]。')
                    else:
                        self.say(f'{name} 的模型限位不支持振幅 0.5 rad，稍后需选择更小振幅。')
                self.say('中心靠近限位时，稍后显示更小的合法振幅默认值。')
            for name, (lower, upper, _) in limits.items():
                values[name] = self.number(
                    f'{name} {label}（rad）', min(upper, max(lower, 0.0)),
                    lower=lower, upper=upper,
                )
            values['rate'] = self.number('发布频率（Hz）', 20.0, lower=0.1, upper=100.0)
            if mode == 'sine':
                amplitudes = []
                for index, (name, (lower, upper, velocity)) in enumerate(limits.items(), 1):
                    center = values[name]
                    maximum = max(0.0, min(center - lower, upper - center))
                    if maximum > 0:
                        maximum = math.nextafter(maximum, 0.0)
                    if velocity == 0:
                        maximum = 0.0
                    while maximum > 0 and (center-maximum < lower or center+maximum > upper):
                        maximum = math.nextafter(maximum, 0.0)
                    amplitude = self.number(
                        f'{name} 振幅（rad，依当前中心限制）', min(0.5, maximum),
                        lower=0.0, upper=maximum,
                        valid=lambda a, q=center, lo=lower, hi=upper: lo <= q-a and q+a <= hi,
                    )
                    values[f'amplitude{index}'] = amplitude
                    amplitudes.append(amplitude)
                rate = values['rate']
                velocities = [limit[2] for limit in limits.values()]
                maximum = min([rate / 10.0] + [
                    velocity / (2.0 * math.pi * amplitude)
                    for velocity, amplitude in zip(velocities, amplitudes) if amplitude > 0
                ])
                maximum = math.nextafter(maximum, 0.0)
                def frequency_valid(frequency):
                    return (rate >= 10.0 * frequency
                            and all(a * (2.0 * math.pi * frequency) <= v
                                    for a, v in zip(amplitudes, velocities)))
                while maximum > 0 and not frequency_valid(maximum):
                    maximum = math.nextafter(maximum, 0.0)
                if maximum <= 0:
                    self.say('当前参数没有可用的正频率；请重新配置中心、振幅和发布频率。')
                    raise OperationCancelled
                self.say('正弦频率需满足 rate ≥ 10×frequency，且 2π×振幅×frequency ≤ 模型速度上限。')
                values['frequency'] = self.number(
                    '正弦频率（Hz）', min(0.1, maximum), lower=0.0, upper=maximum,
                    positive=True, valid=frequency_valid,
                )
        while True:
            rviz = self.answer('启动 RViz？[y/N]：').lower()
            if rviz in {'', 'n', 'no', '否'}:
                return values, False, limits
            if rviz in {'y', 'yes', '是'}:
                return values, True, limits
            self.say('请输入 y 或 n；默认 n。')

    def _graph_conflicts(self):
        publishers = self.observer.publishers()
        nodes = [name for name in self.observer.nodes()
                 if name.rsplit('/', 1)[-1] in CRITICAL_NODES]
        return publishers, nodes

    def _discovery_clear(self):
        self.say(f'在 Domain {self.args.domain_id} 进行 2 秒有界发现……')
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            self.observer.spin()
            publishers, nodes = self._graph_conflicts()
            if publishers or nodes:
                names = [p.node_namespace.rstrip('/') + '/' + p.node_name for p in publishers]
                self.say(f'拒绝启动：发现 /joint_states 发布者 {names} 或机械臂节点 {nodes}。')
                self.say('请停止外部实验或退出后指定其他 Domain；CLI 不接管外部节点。')
                return False
        self.say('发现窗口内未见冲突；此检查无法排除随后由外部并发启动的节点。')
        return True

    def _valid_sample(self, sample):
        return (sample is not None and list(sample.name) == ['joint1', 'joint2']
                and len(sample.position) == 2
                and all(math.isfinite(value) for value in sample.position))

    def _matching_observation(self, after_received=0.0, after_stamp=0):
        # Search newest to oldest, retaining earlier candidates until their TF
        # arrives. This avoids both a permanent first-frame wait and repeatedly
        # chasing the latest state before its asynchronous TF has arrived.
        for sample, received in reversed(self.observer.recent):
            if not self._valid_sample(sample) or received < after_received:
                continue
            stamp = self.observer.stamp_ns(sample)
            # tf2 treats Time(0) as latest; it is not a timestamp match.
            if stamp <= 0 or stamp < after_stamp:
                continue
            transform = self.observer.transform(sample)
            if transform is not None:
                return sample, received, transform
        return None

    def start(self, mode):
        values, use_rviz, limits = self._configuration(mode)
        # Configuration can be cancelled without disrupting the current demo.
        if not self.stop(quiet=True):
            return
        if not self._discovery_clear():
            return
        source = 'gui' if mode == 'gui' else 'cpp'
        command = [
            'ros2', 'launch', 'embodied_arm_cpp', 'demo.launch.py',
            f'state_source:={source}', f'mode:={mode if source == "cpp" else "static"}',
            f'use_rviz:={str(use_rviz).lower()}',
            *[f'{key}:={value!r}' for key, value in values.items()],
        ]
        self.observer.latest = None
        self.observer.recent.clear()
        self.observer.buffer.clear()
        started_at = time.monotonic()
        started_stamp = self.observer.node.get_clock().now().nanoseconds
        demo = self._spawn(command, f'demo-{mode}')
        self.demo = demo
        self.mode = mode
        self.rate = values.get('rate', 20.0)
        self.joint_limits = limits
        self.amplitudes = (values.get('amplitude1', 0.0), values.get('amplitude2', 0.0))
        expected = 'joint_state_publisher_gui' if mode == 'gui' else 'synthetic_joint_publisher'
        deadline = time.monotonic() + START_TIMEOUT
        failure = '未在期限内同时观察到新鲜 JointState、对应时戳 TF 和参数服务。'
        while time.monotonic() < deadline:
            if demo.process.poll() is not None:
                failure = f'Launch 已退出（退出码 {demo.process.returncode}）。'
                break
            self.observer.spin()
            publishers = self.observer.publishers()
            nodes = self.observer.nodes()
            if len(publishers) > 1:
                failure = '启动期间发现多个 /joint_states 发布者。'
                break
            if nodes.count('/robot_state_publisher') > 1:
                failure = '启动期间发现重复 /robot_state_publisher。'
                break
            if (len(publishers) == 1
                    and publishers[0].node_name == expected
                    and publishers[0].node_namespace == '/'
                    and nodes.count('/' + expected) == 1
                    and nodes.count('/robot_state_publisher') == 1
                    and self.observer.clients[source].services_are_ready()
                    and self._matching_observation(started_at, started_stamp) is not None):
                if demo.process.poll() is not None:
                    failure = '链路观察期间 Launch 已退出。'
                    break
                self.publisher_gid = tuple(publishers[0].endpoint_gid)
                self.say(f'{mode} 演示运行中；已观察到新鲜状态、对应时戳 TF 与参数服务。')
                self.say('这些是合成状态与运动学观察，仍需用户进行图形检查。')
                return
        self.say('启动失败：' + failure)
        self.stop(quiet=True)
        self.say(f'失败日志已保留：{demo.log}；可用 /logs 查看。')

    def _pose_allowed(self):
        self._monitor()
        if self.demo is None:
            self.say('请先启动本 CLI 的 static 或 sine 演示，才能设置位置。')
            return False
        if self.mode == 'gui':
            self.say('GUI 模式请用关节滑块；/pose 和 /zero 不可用。')
            return False
        if any(owned is not self.demo for owned in self.owned):
            self.say('拒绝调姿：仍有未确认退出的自有客户端；请先 /stop 清理。')
            return False
        publishers = self.observer.publishers()
        nodes = self.observer.nodes()
        if (len(publishers) != 1 or self.publisher_gid is None
                or tuple(publishers[0].endpoint_gid) != self.publisher_gid
                or nodes.count('/synthetic_joint_publisher') != 1
                or nodes.count('/robot_state_publisher') != 1):
            self.say('拒绝调姿：状态源已变化或发现冲突；请 /status 排查并 /stop。')
            return False
        if not self.observer.clients['cpp'].services_are_ready():
            self.say('调姿服务尚未就绪；未发送设置请求。')
            return False
        return True

    def pose(self, positions=None, zero=False):
        if not self._pose_allowed():
            return
        if positions is None:
            positions = []
            limits, amplitudes, mode = self.joint_limits, self.amplitudes, self.mode
            for index, name in enumerate(('joint1', 'joint2')):
                limit = limits[name]
                amplitude = amplitudes[index] if mode == 'sine' else 0.0
                lower, upper = center_bounds(limit, amplitude)
                label = (f'正弦中心（rad，当前振幅 {amplitude!r}）'
                         if mode == 'sine' else '固定角度（rad）')
                positions.append(self.number(
                    f'{name} {label}', lower=lower, upper=upper,
                    valid=lambda q, a=amplitude, lo=limit[0], hi=limit[1]: lo <= q-a and q+a <= hi,
                ))
        if not self._pose_allowed():
            return
        if self.mode == 'sine':
            self.say('正弦中心归零；振幅、频率不变，关节仍在运动。' if zero else
                     '本次设置正弦中心；关节仍按原振幅、频率运动。')
        command = [
            'ros2', 'run', 'embodied_arm_cpp', 'set_arm_positions.py',
            '--timeout', str(POSE_TIMEOUT), '--', *[repr(value) for value in positions],
        ]
        client = self._spawn(command, 'pose')
        deadline = time.monotonic() + POSE_PROCESS_TIMEOUT
        timed_out = False
        demo_exited = False
        while client.process.poll() is None:
            self.observer.spin()
            if self._monitor():
                demo_exited = True
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
        self._stop_group(client)
        records, other = self._client_output(client.log)
        accepted = next((record for record in records if 'accepted' in record), None)
        observation = next((record for record in records if record.get('observation_only')), None)
        if accepted is not None and accepted.get('accepted') is False:
            self.say('请求被 C++ 拒绝：' + str(accepted.get('reason', '无原因说明')))
        elif accepted is not None and accepted.get('accepted') is True:
            if observation is not None:
                self.say('参数已接收；以下为客户端首帧原始观察：')
                self.say('首帧 TF 可能跨姿态更新插值；未验证它与请求角度一致。')
                self.say(json.dumps(observation, ensure_ascii=False, indent=2))
            else:
                self.say('参数已接收，但新鲜状态/对应时戳 TF 观察未完成；不能据此确认当前姿态。')
            self._followup_observation()
        elif any('parameter services unavailable:' in line for line in other):
            self.say('参数服务不可用；客户端未发送设置请求。')
        else:
            self.say('未获得明确响应；请求应用结果未知，请用 /status 观察后决定是否重试。')
        if timed_out:
            self.say(f'调姿客户端超过整体 {POSE_PROCESS_TIMEOUT:g} 秒期限，已执行自有进程组清理。')
        if demo_exited:
            self.say('调姿期间演示退出，已停止本次客户端。')
        if other:
            self.say('客户端提示：\n' + '\n'.join(other[-5:]))
        self.say(f'调姿日志：{client.log}')

    def _followup_observation(self):
        after_received = time.monotonic()
        after_stamp = self.observer.node.get_clock().now().nanoseconds
        deadline = after_received + 2.0
        while time.monotonic() < deadline:
            self.observer.spin()
            self._monitor()
            if self.demo is None:
                self.say('参数已接收，但演示已退出；客户端结束后的后续观察未完成。')
                return
            publishers = self.observer.publishers()
            if (len(publishers) != 1 or self.publisher_gid is None
                    or tuple(publishers[0].endpoint_gid) != self.publisher_gid
                    or self.observer.nodes().count('/robot_state_publisher') != 1):
                self.say('参数已接收，但状态源或 TF 节点存在冲突；后续观察未完成。')
                return
            matching = self._matching_observation(after_received, after_stamp)
            if matching is not None:
                sample, _, transform = matching
                xyz = transform.transform.translation
                q = transform.transform.rotation
                self.say('客户端结束后的后续观察（仍仅为合成状态与 TF 观察）：')
                self.say(f'时戳={sample.header.stamp.sec}.{sample.header.stamp.nanosec:09d}；'
                         f'names={list(sample.name)}；positions(rad)={list(sample.position)}')
                self.say(f'base_link → tool0：xyz=({xyz.x:g}, {xyz.y:g}, {xyz.z:g})；'
                         f'xyzw=({q.x:g}, {q.y:g}, {q.z:g}, {q.w:g})')
                return
        self.say('参数已接收；客户端结束后 2 秒内未取得新鲜状态及对应时戳 TF。'
                 '后续观察未完成，低发布频率时可稍后使用 /status 查看。')

    @staticmethod
    def _client_output(log):
        records, other = [], []
        for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
            if line.startswith('# ') or not line.strip():
                continue
            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    records.append(record)
                else:
                    other.append(line)
            except json.JSONDecodeError:
                other.append(line)
        return records, other

    def status(self):
        self._monitor()
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            self.observer.spin()
        self.say(f'Domain：{self.args.domain_id}；自有模式：{self.mode or "无"}')
        self.say(f'产物目录：{self.session_dir}')
        publishers = self.observer.publishers()
        self.say(f'/joint_states 发布者数量：{len(publishers)}')
        for publisher in publishers:
            name = publisher.node_namespace.rstrip('/') + '/' + publisher.node_name
            self.say(f'  {name}；GID={bytes(publisher.endpoint_gid).hex()}')
        _, nodes = self._graph_conflicts()
        self.say('机械臂节点：' + (', '.join(nodes) or '未发现'))
        self.say('C++ 参数服务：' + ('就绪' if self.observer.clients['cpp'].services_are_ready()
                                  else '未就绪'))
        sample = self.observer.latest
        if sample is None:
            self.say('尚未收到 JointState；以上仅是 ROS 图发现信息。')
            return
        received = self.observer.received_at
        matching = self._matching_observation()
        deadline = time.monotonic() + 0.5
        while matching is None and time.monotonic() < deadline:
            self.observer.spin()
            matching = self._matching_observation()
        transform = None
        if matching is not None:
            sample, received, transform = matching
            if sample is not self.observer.latest:
                self.say('最新帧 TF 尚未到达；以下显示最近具有对应时戳 TF 的状态帧。')
        else:
            sample = self.observer.latest
            received = self.observer.received_at
        age = time.monotonic() - received
        freshness = max(2.0, 2.0 / self.rate) if self.demo is not None and self.rate > 0 else 2.0
        self.say(f'最近消息：{sample.header.stamp.sec}.{sample.header.stamp.nanosec:09d}；'
                 f'收到后 {age:.2f} 秒' + ('（已陈旧）' if age > freshness else ''))
        self.say(f'names={list(sample.name)}；positions(rad)={list(sample.position)}；'
                 f'velocity={list(sample.velocity)}；effort={list(sample.effort)}')
        if transform is None:
            self.say('此消息时戳的 base_link → tool0 TF 尚不可用。')
        else:
            xyz = transform.transform.translation
            q = transform.transform.rotation
            self.say(f'对应时戳 base_link → tool0：xyz=({xyz.x:g}, {xyz.y:g}, {xyz.z:g})；'
                     f'xyzw=({q.x:g}, {q.y:g}, {q.z:g}, {q.w:g})')
        self.say('以上为观察值；不代表真实控制、执行成功或图形验收通过。')

    def logs(self):
        self.say(f'会话目录：{self.session_dir}；CLI 记录：{self.event_log}')
        for path in self.log_files:
            print('  ' + str(path), flush=True)
        path = self.log_files[-1] if self.log_files else self.event_log
        self.say(f'最近日志的最后 40 行：{path}')
        with path.open(encoding='utf-8', errors='replace') as stream:
            print(''.join(deque(stream, maxlen=40)), end='', flush=True)

    def dispatch(self, line):
        aliases = {
            '1': '/start static', '2': '/start sine', '3': '/start gui',
            '4': '/pose', '5': '/zero', '6': '/status', '7': '/logs',
            '8': '/stop', '0': '/quit',
        }
        line = aliases.get(line.strip(), line.strip())
        if not line:
            return
        try:
            words = shlex.split(line)
        except ValueError as error:
            self.say(f'命令格式错误：{error}')
            return
        if not words:
            return
        command, params = words[0], words[1:]
        if command == '/start' and params in [['static'], ['sine'], ['gui']]:
            self.start(params[0])
        elif command == '/pose' and len(params) in {0, 2}:
            positions = None
            if params:
                try:
                    positions = [float(value) for value in params]
                    if not all(math.isfinite(value) for value in positions):
                        raise ValueError
                except ValueError:
                    self.say('/pose 需要两个有限数字，单位 rad。')
                    return
            self.pose(positions)
        elif params:
            self.say('参数不正确；输入 /help 查看命令格式。')
        elif command == '/zero':
            self.pose([0.0, 0.0], zero=True)
        elif command == '/status':
            self.status()
        elif command == '/logs':
            self.logs()
        elif command == '/stop':
            self.stop()
        elif command == '/help':
            self.say(HELP)
        elif command == '/quit':
            raise QuitRequested
        else:
            self.say('未知命令；输入菜单编号或 /help。')

    def run(self):
        self.say(HELP)
        self.say(f'安装目录：{self.args.install_dir}；Domain：{self.args.domain_id}；模式：未启动')
        self.say(f'日志：{self.session_dir}')
        while True:
            try:
                self.dispatch(self.readline('机械臂> '))
            except OperationCancelled:
                self.say('本次操作已取消。')
            except (OSError, RuntimeError) as error:
                self.say(f'操作失败：{error}；输入 /logs 查看日志，菜单继续可用。')

    def close(self):
        stopped = self.stop(quiet=True)
        self.say('已清理全部自有进程组，退出 CLI。' if stopped else
                 '退出 CLI；部分自有进程组未确认退出，请根据以上 PID 检查。')
        self.events.close()
        return stopped


def check_install(install_dir):
    from ament_index_python.packages import get_package_prefix, get_package_share_directory

    if not (install_dir / 'setup.bash').is_file():
        raise RuntimeError(f'指定 install 缺少 setup.bash：{install_dir}')
    paths = {}
    for name in ('embodied_arm_cpp', 'embodied_arm_description'):
        prefix = Path(get_package_prefix(name)).resolve()
        if not prefix.is_relative_to(install_dir):
            raise RuntimeError(f'{name} 来自指定 install 以外：{prefix}；拒绝回退到其他构建。')
        paths[name] = (prefix, Path(get_package_share_directory(name)))
    cpp_prefix, cpp_share = paths['embodied_arm_cpp']
    _, description_share = paths['embodied_arm_description']
    required = [
        cpp_share / 'launch' / 'demo.launch.py',
        cpp_prefix / 'lib' / 'embodied_arm_cpp' / 'synthetic_joint_publisher',
        cpp_prefix / 'lib' / 'embodied_arm_cpp' / 'set_arm_positions.py',
        description_share / 'urdf' / 'two_link_arm.urdf.xacro',
    ]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f'指定构建产物缺失：{path}；请由用户完成第四周构建。')
    for path in required[1:3]:
        if not os.access(path, os.X_OK):
            raise RuntimeError(f'构建入口不可执行：{path}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='第四周两关节合成机械臂常驻中文 CLI')
    parser.add_argument('--project-root', required=True, type=Path, help='项目根目录绝对路径')
    parser.add_argument('--install-dir', required=True, type=Path, help='第四周 install 绝对路径')
    parser.add_argument('--domain-id', required=True, type=int, help='独立 ROS Domain，0..232')
    args = parser.parse_args(argv)
    if not args.project_root.is_absolute() or not args.install_dir.is_absolute():
        parser.error('项目根目录与 install 必须使用绝对路径')
    if not 0 <= args.domain_id <= 232:
        parser.error('--domain-id 必须在 0..232 范围内')
    args.project_root = args.project_root.resolve()
    args.install_dir = args.install_dir.resolve()
    if not args.project_root.is_dir():
        parser.error('项目根目录不存在')
    # The wrapper sources only the requested overlay. Recheck here before ROS init.
    try:
        check_install(args.install_dir)
    except (ImportError, LookupError, RuntimeError) as error:
        print(f'CLI 启动预检失败：{error}\n请用 scripts/arm_cli.sh 加载已构建的第四周 install。',
              file=sys.stderr)
        return 2
    os.environ['ROS_DOMAIN_ID'] = str(args.domain_id)
    os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    observer = None
    cli = None
    result = 0
    try:
        cli = ArmCli(args, None)
        os.environ['ROS_LOG_DIR'] = cli.environment['ROS_LOG_DIR']
        observer = RosObserver()
        cli.observer = observer
        cli.run()
    except (QuitRequested, KeyboardInterrupt):
        print('\n正在退出并清理自有进程……', flush=True)
    except Exception as error:
        print(f'CLI 错误：{error}', file=sys.stderr, flush=True)
        result = 2
    finally:
        with uninterrupted_cleanup():
            if cli is not None and not cli.close():
                result = 2
            if observer is not None:
                observer.close()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
