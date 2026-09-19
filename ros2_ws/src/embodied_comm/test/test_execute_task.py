"""通过真实 ROS 服务和话题验证请求、响应、结果通知。"""
import json
import time

import pytest
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String
from std_srvs.srv import Trigger

from embodied_comm.common import parse_task_status
from embodied_comm.task_executor import TaskExecutor
from embodied_comm.status_monitor import StatusMonitor
from embodied_comm.sensor_simulator import SensorSimulator


def spin_until(executor, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.02)
    assert predicate(), '等待服务响应或话题消息超时'


@pytest.fixture
def system(ros_context):
    task = TaskExecutor(context=ros_context)
    monitor = StatusMonitor(context=ros_context)
    probe = Node('service_test_client', context=ros_context)
    executor = SingleThreadedExecutor(context=ros_context)
    for node in (task, monitor, probe):
        executor.add_node(node)
    client = probe.create_client(Trigger, '/execute_task')
    publisher = probe.create_publisher(String, '/sensor_state', 10)
    try:
        assert client.wait_for_service(timeout_sec=5.0)
        spin_until(executor, lambda: task.status_publisher.get_subscription_count() == 1
                   and publisher.get_subscription_count() == 2)
        yield task, monitor, executor, client, publisher
    finally:
        executor.shutdown()
        for node in (task, monitor, probe):
            node.destroy_node()


def call_and_check(system, task_id, success, sensor_seq):
    task, monitor, executor, client, _ = system
    count = monitor.task_status_count
    future = client.call_async(Trigger.Request())
    spin_until(executor, future.done)
    response = future.result()
    assert response.success is success
    spin_until(executor, lambda: monitor.task_status_count > count)
    assert monitor.task_status_count == count + 1
    assert monitor.latest_task_status == {
        'task_id': task_id, 'success': success,
        'message': response.message, 'sensor_seq': sensor_seq,
    }
    assert task.task_id == task_id
    return response


def test_no_data_failure_and_sensor_success(system, ros_context):
    response = call_and_check(system, 1, False, None)
    assert '没有有效传感器数据' in response.message
    task, monitor, executor, _, _ = system
    # 失败任务通知不能把传感器输入从无数据变成正常。
    assert monitor.latest_reading is None
    sensor = SensorSimulator(context=ros_context)
    executor.add_node(sensor)
    try:
        spin_until(executor, lambda: task.latest_reading is not None)
        sensor.timer.cancel()
        seq = task.latest_reading['seq']
        response = call_and_check(system, 2, True, seq)
        assert '检查通过' in response.message
    finally:
        executor.remove_node(sensor)
        sensor.destroy_node()


@pytest.mark.parametrize('value,success', [(-0.1, False), (0.0, True),
                                          (100.0, True), (100.1, False)])
def test_value_boundaries(system, value, success):
    task, _, executor, _, publisher = system
    publisher.publish(String(data=json.dumps({'seq': 42, 'value': value})))
    spin_until(executor, lambda: task.latest_reading is not None)
    response = call_and_check(system, 1, success, 42)
    assert ('检查通过' if success else '不在有效范围') in response.message


def test_task_messages_do_not_reset_sensor_timeout(system):
    _, monitor, _, _, _ = system
    received_at = monitor.last_received_at
    monitor.timed_out = True
    call_and_check(system, 1, False, None)
    assert monitor.last_received_at == received_at
    assert monitor.timed_out
    previous = monitor.latest_task_status.copy()
    monitor.receive_task_status(String(data='{}'))
    assert monitor.latest_task_status == previous
    assert monitor.task_status_count == 1


@pytest.mark.parametrize('text', ['[]', '{}', '{"task_id": true}',
    '{"task_id":1,"success":"true","message":"ok","sensor_seq":1}',
    '{"task_id":1,"success":true,"message":"ok","sensor_seq":null}',
    '{"task_id":1,"success":false,"message":"bad","sensor_seq":0}',
])
def test_reject_invalid_task_status(text):
    with pytest.raises(ValueError):
        parse_task_status(text)
