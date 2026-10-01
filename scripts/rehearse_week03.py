#!/usr/bin/env python3
"""从已安装的第三周工位验证正常质检、运行中查询和取消恢复。"""
import argparse
import json
import time
from pathlib import Path

from action_msgs.msg import GoalStatus
from diagnostic_msgs.msg import DiagnosticArray
from embodied_comm.evidence_recorder import (
    EXPECTED_NODES, evidence_environment, start_logged_process, stop_process,
)
from embodied_interfaces.action import ExecuteTask
from rclpy.action import ActionClient
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


def spin_until(executor, predicate, timeout=12.0):
    """按条件而非固定睡眠等待 ROS 回调，超时立即失败。"""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(f'等待 ROS 条件超时（{timeout} 秒）')
        executor.spin_once(timeout_sec=0.02)


def rehearse(output, domain=202):
    """在独立 DDS 域中执行可重复的工业工位协议验收。"""
    output.mkdir(parents=True, exist_ok=False)
    environment = evidence_environment(domain)
    context = Context()
    context.init(args=[], domain_id=domain)
    probe = Node('day7_acceptance_probe', context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(probe)
    diagnostics = {}
    terminal_records = []

    def on_diagnostics(message):
        for item in message.status:
            values = {entry.key: entry.value for entry in item.values}
            diagnostics[item.name] = values.get('state')

    probe.create_subscription(DiagnosticArray, '/diagnostics', on_diagnostics, 10)
    probe.create_subscription(
        String, '/task_status',
        lambda message: terminal_records.append(json.loads(message.data)), 10,
    )
    buffer = Buffer(node=probe)
    listener = TransformListener(buffer, probe)
    service = probe.create_client(Trigger, '/execute_task')
    action = ActionClient(probe, ExecuteTask, '/execute_task_long')
    report = {'domain_id': domain, 'status': 'running', 'workpieces': []}
    launch = None
    stream = None
    try:
        launch, stream = start_logged_process(
            ('ros2', 'launch', 'embodied_comm', 'week03_day5.launch.py',
             'use_rviz:=false', 'publish_rate:=10.0',
             'diagnostic_rate:=10.0', 'timeout_sec:=3.0'),
            environment, output / 'launch.log',
        )
        spin_until(executor, lambda: (
            EXPECTED_NODES.issubset(set(probe.get_node_names()))
            and len(diagnostics) == 2
            and set(diagnostics.values()) == {'healthy'}
            and buffer.can_transform('world', 'tool0', Time())
        ))
        assert service.wait_for_service(timeout_sec=5.0)
        assert action.wait_for_server(timeout_sec=5.0)
        for name, duration, cancel in (
            ('inspect_workpiece_WP-001', 2.0, False),
            ('inspect_workpiece_WP-002', 3.0, True),
            ('inspect_workpiece_WP-003', 0.5, False),
        ):
            progress = []
            phases = []

            def on_feedback(message):
                progress.append(message.feedback.progress_percent)
                phases.append(message.feedback.phase)

            future = action.send_goal_async(
                ExecuteTask.Goal(task_name=name, duration_sec=duration),
                feedback_callback=on_feedback,
            )
            spin_until(executor, future.done)
            handle = future.result()
            assert handle.accepted, name
            print(f'{name}: 目标接受', flush=True)
            result_future = handle.get_result_async()
            item = {'task_name': name, 'accepted': True}
            if name.endswith('001'):
                spin_until(executor, lambda: 'inspecting' in phases)
                assert not result_future.done()
                started = time.monotonic()
                query = service.call_async(Trigger.Request())
                spin_until(executor, query.done, 1.0)
                item['service_latency_sec'] = time.monotonic() - started
                assert query.result().success and not result_future.done()
                print('长任务运行中：快速 Service 查询成功', flush=True)
            if cancel:
                spin_until(executor, lambda: progress and progress[-1] >= 40.0)
                started = time.monotonic()
                cancellation = handle.cancel_goal_async()
                spin_until(executor, cancellation.done, 1.0)
                assert cancellation.result().goals_canceling
                spin_until(executor, result_future.done, 1.0)
                item['cancel_latency_sec'] = time.monotonic() - started
                assert item['cancel_latency_sec'] < 1.0
            else:
                spin_until(executor, result_future.done, duration + 5.0)
            result = result_future.result()
            expected = GoalStatus.STATUS_CANCELED if cancel else GoalStatus.STATUS_SUCCEEDED
            assert result.status == expected
            assert result.result.success == (not cancel)
            assert progress and progress == sorted(progress)
            assert all(0.0 <= value <= 100.0 for value in progress)
            if not cancel:
                assert progress[-1] == 100.0
                assert list(dict.fromkeys(phases)) == [
                    'preparing', 'inspecting', 'validating', 'completed',
                ]
                assert result.result.sensor_seq > 0
            item.update({
                'status': 'CANCELED' if cancel else 'SUCCEEDED',
                'sensor_seq': result.result.sensor_seq,
                'progress': progress,
                'phases': list(dict.fromkeys(phases)),
            })
            report['workpieces'].append(item)
            print(f"{name}: {item['status']}，阶段={item['phases']}，进度={progress}",
                  flush=True)
        spin_until(executor, lambda: len(terminal_records) >= 4)
        quiet_deadline = time.monotonic() + 0.3
        while time.monotonic() < quiet_deadline:
            executor.spin_once(timeout_sec=0.02)
        assert len(terminal_records) == 4  # 一次 Service + 三个 Action
        assert len({item['task_id'] for item in terminal_records}) == 4
        assert sum(not item['success'] for item in terminal_records) == 1
        canceled = next(item for item in terminal_records if not item['success'])
        assert canceled['sensor_seq'] is None
        report.update({
            'terminal_records': terminal_records,
            'diagnostics': diagnostics,
            'status': 'passed',
        })
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        if launch is not None:
            code, mode = stop_process(launch, signal_group=False)
            report['launch_shutdown'] = {'exit_code': code, 'mode': mode}
            if report['status'] == 'passed' and (code != 0 or mode != 'sigint'):
                report.update(status='failed', error='Launch 未正常退出')
        if stream is not None:
            stream.close()
        action.destroy()
        listener.unregister()
        executor.shutdown()
        probe.destroy_node()
        context.shutdown()
        (output / 'normal-demo.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8',
        )
    assert report['status'] == 'passed', report


def main():
    """提供干净演练脚本的可执行入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--domain', type=int, default=202)
    args = parser.parse_args()
    if not 0 <= args.domain <= 232:
        parser.error('--domain 必须在 0～232 内')
    rehearse(args.output.resolve(), args.domain)


if __name__ == '__main__':
    main()
