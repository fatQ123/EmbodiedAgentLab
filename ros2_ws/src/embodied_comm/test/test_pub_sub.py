"""真实 DDS 收发测试，不用 mock 替代 ROS 通信。"""
import time

import pytest
from rclpy.executors import SingleThreadedExecutor
from rclpy.parameter import Parameter
from std_msgs.msg import String

from embodied_comm.common import parse_sensor
from embodied_comm.sensor_simulator import SensorSimulator
from embodied_comm.status_monitor import StatusMonitor


def spin_until(executor, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.02)
    assert predicate(), '等待 ROS 通信或状态变化超时'


def test_communication_timeout_and_recovery(ros_context):
    monitor = StatusMonitor(context=ros_context, parameter_overrides=[
        Parameter('timeout_sec', value=0.3),
    ])
    sensor = SensorSimulator(context=ros_context, parameter_overrides=[
        Parameter('publish_rate', value=20.0),
    ])
    executor = SingleThreadedExecutor(context=ros_context)
    executor.add_node(monitor)
    try:
        # 启动后一直没有数据也必须报警。
        spin_until(executor, lambda: monitor.timed_out)
        executor.add_node(sensor)
        spin_until(executor, lambda: monitor.received_count >= 4)
        assert not monitor.timed_out
        first_seq = monitor.latest_reading['seq']
        spin_until(executor, lambda: monitor.latest_reading['seq'] > first_seq)
        assert 0 <= monitor.latest_reading['value'] <= 100
        sensor.timer.cancel()
        spin_until(executor, lambda: monitor.timed_out)
        last_reading = monitor.latest_reading.copy()
        before_count = monitor.received_count
        sensor.publisher.publish(String(data='not JSON'))
        for _ in range(10):
            executor.spin_once(timeout_sec=0.02)
        assert monitor.timed_out
        assert monitor.latest_reading == last_reading
        assert monitor.received_count == before_count
        sensor.timer.reset()
        spin_until(executor, lambda: not monitor.timed_out)
        assert monitor.received_count > before_count
    finally:
        executor.shutdown()
        sensor.destroy_node()
        monitor.destroy_node()


@pytest.mark.parametrize('text', [
    'not JSON', '[]', '{}', '{"seq":true,"value":1}',
    '{"seq":0,"value":1}', '{"seq":1,"value":NaN}',
    '{"seq":1,"value":true}', '{"seq":1,"value":"50"}',
])
def test_invalid_messages(text):
    with pytest.raises(ValueError):
        parse_sensor(text)
