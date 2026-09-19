#!/usr/bin/env python3
"""复现阶段⑤，保存真实 CLI、日志与 rqt_graph 证据。需先构建并加载工作空间。"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def stop(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGINT)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=3)
            raise RuntimeError('进程未按期退出，已清理本脚本启动的进程组')


def run_case(output, name, domain, wrong):
    folder = output / name
    folder.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, ROS_DOMAIN_ID=str(domain),
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST', PYTHONUNBUFFERED='1')
    command = ['ros2', 'launch', 'embodied_comm', 'three_nodes.launch.py']
    if wrong:
        command.append('executor_sensor_topic:=/sensor_state_wrong')
    (folder / 'configuration.json').write_text(json.dumps(
        {'command': command, 'ROS_DOMAIN_ID': domain, 'case': name}, indent=2) + '\n')
    launch_log = folder / 'launch.log'

    def capture(label, args):
        for _ in range(3):
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=25)
            if result.returncode == 0:
                break
        (folder / (label + '.log')).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, f'{name}/{label}: {result.stderr}'
        return result.stdout

    with launch_log.open('w') as log:
        proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            deadline = time.monotonic() + 12
            while '收到传感器' not in launch_log.read_text() and time.monotonic() < deadline:
                assert proc.poll() is None, launch_log.read_text()
                time.sleep(0.1)
            assert '收到传感器' in launch_log.read_text()
            discovery = ['--no-daemon', '--spin-time', '5']
            nodes = capture('nodes', ['ros2', 'node', 'list', *discovery])
            assert set(nodes.split()) == {'/sensor_simulator', '/task_executor', '/status_monitor'}
            sensor = capture('sensor-topic', ['ros2', 'topic', 'info', '/sensor_state',
                                             '--verbose', *discovery])
            assert 'Publisher count: 1' in sensor
            assert f'Subscription count: {1 if wrong else 2}' in sensor
            task_topic = capture('task-topic', ['ros2', 'topic', 'info', '/task_status',
                                               '--verbose', *discovery])
            assert 'Publisher count: 1' in task_topic and 'Subscription count: 1' in task_topic
            info = capture('executor-node', ['ros2', 'node', 'info', '/task_executor', *discovery])
            expected = '/sensor_state_wrong' if wrong else '/sensor_state'
            assert f'{expected}: std_msgs/msg/String' in info
            if wrong:
                bad = capture('wrong-topic', ['ros2', 'topic', 'info', '/sensor_state_wrong',
                                              '--verbose', *discovery])
                assert 'Publisher count: 0' in bad and 'Subscription count: 1' in bad
                assert '最新传感器' not in launch_log.read_text()
            response = capture('service', ['ros2', 'service', 'call', '/execute_task',
                                           'std_srvs/srv/Trigger', '{}'])
            assert f'success={not wrong}' in response
            deadline = time.monotonic() + 5
            while '收到任务结果' not in launch_log.read_text() and time.monotonic() < deadline:
                time.sleep(0.1)
            assert '收到任务结果' in launch_log.read_text()
            # 临时订阅放在端点统计之后，避免把验收工具误计为业务节点。
            capture('sensor-message', ['ros2', 'topic', 'echo', '/sensor_state',
                                       'std_msgs/msg/String', '--once'])
            with (folder / 'frequency.log').open('w') as hz_log:
                hz = subprocess.Popen(['ros2', 'topic', 'hz', '/sensor_state'], env=env,
                                      stdout=hz_log, stderr=subprocess.STDOUT,
                                      start_new_session=True)
                try:
                    time.sleep(7)
                finally:
                    stop(hz)
            assert 'average rate:' in (folder / 'frequency.log').read_text()
            graph_args = ['/usr/bin/python3', str(ROOT / 'scripts/capture_ros2_graph.py'), str(folder)]
            if wrong:
                graph_args.append('--wrong-topic')
            result = subprocess.run(graph_args, env=dict(env, QT_QPA_PLATFORM='offscreen'),
                                    capture_output=True, text=True, timeout=30)
            (folder / 'graph-capture.log').write_text(result.stdout + result.stderr)
            assert result.returncode == 0, result.stderr
        finally:
            stop(proc)
        assert proc.returncode == 0, launch_log.read_text()
    print(f'{name}: 节点、话题、服务、频率、监控结果、rqt_graph 均已验证', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='新的证据目录；已有案例目录不会覆盖')
    parser.add_argument('--domain-start', type=int, default=186)
    args = parser.parse_args()
    if not 0 <= args.domain_start <= 230:
        parser.error('起始域必须在 0～230，连续三个域需空闲')
    for offset, (name, wrong) in enumerate([('normal', False), ('wrong', True), ('repaired', False)]):
        run_case(args.output.resolve(), name, args.domain_start + offset, wrong)


if __name__ == '__main__':
    main()
