"""通过真实 ROS Action 通信验证长任务、取消、并发和服务响应."""
import json
import time

from action_msgs.msg import GoalStatus
from embodied_comm.task_executor import TaskExecutor
from embodied_interfaces.action import ExecuteTask
import pytest
from rclpy.action import ActionClient, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


def spin_until(executor, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.02)
    assert predicate(), '等待 Action、Service 或话题状态超时'


@pytest.fixture
def action_system(ros_context):
    task = TaskExecutor(context=ros_context)
    probe = Node('action_test_client', context=ros_context)
    client = ActionClient(probe, ExecuteTask, '/execute_task_long')
    service_client = probe.create_client(Trigger, '/execute_task')
    publisher = probe.create_publisher(String, '/sensor_state', 10)
    statuses = []
    subscription = probe.create_subscription(
        String, '/task_status', lambda message: statuses.append(json.loads(message.data)), 10,
    )
    executor = MultiThreadedExecutor(num_threads=4, context=ros_context)
    executor.add_node(task)
    executor.add_node(probe)
    try:
        assert client.wait_for_server(timeout_sec=5.0)
        assert service_client.wait_for_service(timeout_sec=5.0)
        spin_until(
            executor,
            lambda: publisher.get_subscription_count() == 1
            and task.status_publisher.get_subscription_count() == 1,
        )
        yield task, probe, executor, client, service_client, publisher, statuses
    finally:
        probe.destroy_subscription(subscription)
        executor.shutdown()
        task.destroy_node()
        probe.destroy_node()


def publish_reading(system, seq=1, value=50.0):
    task, _, executor, _, _, publisher, _ = system
    publisher.publish(String(data=json.dumps({'seq': seq, 'value': value})))
    spin_until(executor, lambda: task.latest_reading is not None)


def send_goal(system, task_name, duration, feedback=None):
    _, _, executor, client, _, _, _ = system
    goal = ExecuteTask.Goal()
    goal.task_name = task_name
    goal.duration_sec = duration
    future = client.send_goal_async(goal, feedback_callback=feedback)
    spin_until(executor, future.done)
    return future.result()


def get_result(system, goal_handle, timeout=5.0):
    executor = system[2]
    future = goal_handle.get_result_async()
    spin_until(executor, future.done, timeout=timeout)
    return future.result()


@pytest.mark.parametrize('task_name,duration', [
    ('', 1.0), ('   ', 1.0), ('task', 0.09), ('task', 300.1),
    ('task', float('nan')), ('task', float('inf')), ('task', -float('inf')),
])
def test_reject_invalid_goal(ros_context, task_name, duration):
    task = TaskExecutor(context=ros_context)
    goal = ExecuteTask.Goal()
    goal.task_name = task_name
    goal.duration_sec = duration
    try:
        assert task.goal_callback(goal) == GoalResponse.REJECT
        assert not task._goal_reserved
    finally:
        task.destroy_node()


def test_success_feedback_and_single_terminal_status(action_system):
    publish_reading(action_system, seq=42, value=63.0)
    feedback = []

    def collect(message):
        value = message.feedback
        feedback.append((value.progress_percent, value.phase))

    goal_handle = send_goal(action_system, 'inspect_workpiece_WP-001', 0.45, collect)
    assert goal_handle.accepted
    wrapped = get_result(action_system, goal_handle)
    statuses = action_system[-1]
    spin_until(action_system[2], lambda: len(statuses) == 1)

    assert wrapped.status == GoalStatus.STATUS_SUCCEEDED
    assert wrapped.result.success
    assert wrapped.result.sensor_seq == 42
    assert [item[0] for item in feedback] == sorted(item[0] for item in feedback)
    assert feedback[0][1] == 'preparing'
    assert 'inspecting' in {item[1] for item in feedback}
    assert 'validating' in {item[1] for item in feedback}
    assert feedback[-1][0] == pytest.approx(100.0)
    assert feedback[-1][1] == 'completed'
    assert statuses[0]['success'] is True
    assert statuses[0]['sensor_seq'] == 42


@pytest.mark.parametrize('reading,status_seq', [(None, None), ((7, 101.0), 7)])
def test_abort_without_usable_sensor_data(action_system, reading, status_seq):
    if reading is not None:
        publish_reading(action_system, seq=reading[0], value=reading[1])
    goal_handle = send_goal(action_system, 'inspect_bad_input', 0.1)
    assert goal_handle.accepted
    wrapped = get_result(action_system, goal_handle)
    spin_until(action_system[2], lambda: len(action_system[-1]) == 1)
    assert wrapped.status == GoalStatus.STATUS_ABORTED
    assert not wrapped.result.success
    assert wrapped.result.sensor_seq == 0
    assert action_system[-1][0]['success'] is False
    assert action_system[-1][0]['sensor_seq'] == status_seq


def test_cancel_reject_concurrent_goal_and_recover(action_system):
    publish_reading(action_system, seq=8, value=40.0)
    feedback = []
    first = send_goal(
        action_system, 'inspect_workpiece_WP-002', 2.0,
        lambda message: feedback.append(message.feedback.progress_percent),
    )
    assert first.accepted
    spin_until(action_system[2], lambda: feedback and feedback[-1] >= 10.0)

    second = send_goal(action_system, 'inspect_concurrent', 0.1)
    assert not second.accepted

    cancel_started = time.monotonic()
    cancel_future = first.cancel_goal_async()
    spin_until(action_system[2], cancel_future.done)
    assert len(cancel_future.result().goals_canceling) == 1
    canceled = get_result(action_system, first)
    assert time.monotonic() - cancel_started < 1.0
    assert canceled.status == GoalStatus.STATUS_CANCELED
    assert not canceled.result.success
    spin_until(action_system[2], lambda: len(action_system[-1]) == 1)

    recovered = send_goal(action_system, 'inspect_workpiece_WP-003', 0.1)
    assert recovered.accepted
    recovered_result = get_result(action_system, recovered)
    assert recovered_result.status == GoalStatus.STATUS_SUCCEEDED
    spin_until(action_system[2], lambda: len(action_system[-1]) == 2)
    assert [status['success'] for status in action_system[-1]] == [False, True]


def test_quick_service_responds_while_action_runs(action_system):
    publish_reading(action_system, seq=9, value=55.0)
    goal_handle = send_goal(action_system, 'inspect_with_operator_query', 2.0)
    assert goal_handle.accepted

    service_started = time.monotonic()
    service_future = action_system[4].call_async(Trigger.Request())
    spin_until(action_system[2], service_future.done, timeout=1.0)
    assert time.monotonic() - service_started < 1.0
    assert service_future.result().success

    cancel_future = goal_handle.cancel_goal_async()
    spin_until(action_system[2], cancel_future.done)
    wrapped = get_result(action_system, goal_handle)
    assert wrapped.status == GoalStatus.STATUS_CANCELED
    spin_until(action_system[2], lambda: len(action_system[-1]) == 2)
    assert action_system[-1][0]['success'] is True
    assert action_system[-1][1]['success'] is False
