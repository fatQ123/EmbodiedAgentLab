"""从已安装的 Launch 启动进程，验证参数、服务和重映射作用域。"""
import json
import os
import signal
import subprocess
import time

import pytest
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter_client import AsyncParameterClient
from std_srvs.srv import Trigger


@pytest.mark.parametrize('wrong_topic,domain', [(False, 181), (True, 182)])
def test_installed_launch(tmp_path, wrong_topic, domain):
    env = dict(os.environ, ROS_DOMAIN_ID=str(domain),
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    args = ['ros2', 'launch', 'embodied_comm', 'three_nodes.launch.py',
            'publish_rate:=5.0', 'timeout_sec:=1.5']
    if wrong_topic:
        args.append('executor_sensor_topic:=/sensor_state_wrong')
    log_path = tmp_path / 'launch.log'
    context = Context()
    context.init(args=[], domain_id=domain)
    probe = Node('launch_acceptance_probe', context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(probe)
    proc = None

    def wait_for(predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            assert proc.poll() is None, log_path.read_text()
            executor.spin_once(timeout_sec=0.05)
        assert predicate(), log_path.read_text()

    try:
        with log_path.open('w') as log:
            proc = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            expected = {'sensor_simulator', 'task_executor', 'status_monitor'}
            wait_for(lambda: expected <= set(probe.get_node_names()))
            parameters = {}
            for name, parameter, value in [('sensor_simulator', 'publish_rate', 5.0),
                                            ('status_monitor', 'timeout_sec', 1.5)]:
                client = AsyncParameterClient(probe, name)
                assert client.wait_for_services(timeout_sec=5)
                future = client.get_parameters([parameter])
                wait_for(future.done)
                actual = future.result().values[0].double_value
                assert actual == value
                parameters[parameter] = actual
            expected_subscribers = {'status_monitor'} if wrong_topic else {
                'status_monitor', 'task_executor'}
            wait_for(lambda: {e.node_name for e in probe.get_subscriptions_info_by_topic(
                '/sensor_state')} == expected_subscribers)
            if wrong_topic:
                wait_for(lambda: {e.node_name for e in probe.get_subscriptions_info_by_topic(
                    '/sensor_state_wrong')} == {'task_executor'})
            wait_for(lambda: '收到传感器' in log_path.read_text())
            if not wrong_topic:
                wait_for(lambda: '最新传感器' in log_path.read_text())
            wait_for(lambda: {e.node_name for e in probe.get_subscriptions_info_by_topic(
                '/task_status')} == {'status_monitor'})
            client = probe.create_client(Trigger, '/execute_task')
            assert client.wait_for_service(timeout_sec=5)
            future = client.call_async(Trigger.Request())
            wait_for(future.done)
            response = future.result()
            assert response.success is (not wrong_topic)
            if wrong_topic:
                assert '没有有效传感器数据' in response.message
            wait_for(lambda: '收到任务结果：task_id=1' in log_path.read_text())
            (tmp_path / 'result.json').write_text(json.dumps({
                'launch_args': args, 'parameters': parameters,
                'sensor_subscribers': sorted(expected_subscribers),
                'service_success': response.success, 'service_message': response.message,
                'monitor_received_task': True,
            }, ensure_ascii=False, indent=2) + '\n')
            # 只给 Launch 主进程发 Ctrl+C，验证它能关闭所有子节点。
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=12)
            assert proc.returncode == 0, log_path.read_text()
            deadline = time.monotonic() + 5
            while expected & set(probe.get_node_names()) and time.monotonic() < deadline:
                executor.spin_once(timeout_sec=0.05)
            assert not expected & set(probe.get_node_names())
    finally:
        if proc is not None:
            # 清理仅限本测试创建的进程组，包括测试失败时残留的子进程。
            try:
                os.killpg(proc.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)
        executor.shutdown()
        probe.destroy_node()
        context.try_shutdown()
