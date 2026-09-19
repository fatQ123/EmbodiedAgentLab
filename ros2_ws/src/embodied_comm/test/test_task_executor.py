"""验证执行器缓存语义及三节点实际通信。"""
import time

from rclpy.executors import SingleThreadedExecutor
from rclpy.parameter import Parameter
from std_msgs.msg import String

from embodied_comm.sensor_simulator import SensorSimulator
from embodied_comm.status_monitor import StatusMonitor
from embodied_comm.task_executor import TaskExecutor


def test_cache_preserves_last_valid_reading(ros_context):
    node = TaskExecutor(context=ros_context)
    try:
        assert node.latest_reading is None
        assert node.last_received_at is None
        assert node.received_count == 0
        node.receive(String(data='bad JSON'))
        assert node.latest_reading is None
        assert node.last_received_at is None
        node.receive(String(data='{"seq": 7, "value": 42.0}'))
        received_at = node.last_received_at
        assert received_at is not None
        node.receive(String(data='{"seq": 8, "value": NaN}'))
        assert node.latest_reading == {'seq': 7, 'value': 42.0}
        assert node.last_received_at == received_at
        assert node.received_count == 1
        # 传感器重启后序号可回到 1，越界读数仍是格式合法数据。
        node.receive(String(data='{"seq": 1, "value": 101.0}'))
        assert node.latest_reading == {'seq': 1, 'value': 101.0}
        assert node.last_received_at >= received_at
        assert node.received_count == 2
    finally:
        node.destroy_node()


def test_sensor_reaches_both_subscribers(ros_context):
    sensor = SensorSimulator(context=ros_context, parameter_overrides=[
        Parameter('publish_rate', value=20.0),
    ])
    task = TaskExecutor(context=ros_context)
    monitor = StatusMonitor(context=ros_context)
    executor = SingleThreadedExecutor(context=ros_context)
    for node in (sensor, task, monitor):
        executor.add_node(node)
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.02)
            if (sensor.publisher.get_subscription_count() == 2
                    and task.received_count >= 4 and monitor.received_count >= 4):
                break
        assert sensor.publisher.get_subscription_count() == 2
        assert task.received_count >= 4
        assert monitor.received_count >= 4
        previous_seq = task.latest_reading['seq']
        previous_time = task.last_received_at
        deadline = time.monotonic() + 2.0
        while task.latest_reading['seq'] <= previous_seq and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.02)
        assert task.latest_reading['seq'] > previous_seq
        assert task.last_received_at > previous_time
    finally:
        executor.shutdown()
        for node in (sensor, task, monitor):
            node.destroy_node()
