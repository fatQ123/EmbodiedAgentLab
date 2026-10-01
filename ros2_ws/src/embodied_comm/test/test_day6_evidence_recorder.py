"""验证第 6 天证据编排器的场景、录包主题和中文报告契约."""
import json
import os
import subprocess
import sys

from embodied_comm import evidence_recorder
from embodied_comm.evidence_recorder import (
    DIAGNOSTIC_ECHO, FAULT_RECORDS, RECORDED_TOPICS, SCENARIOS, bag_message_count,
    evidence_environment, render_chinese_report, run_captured, run_regression,
    scenario_launch_arguments, selected_scenarios,
)


def fake_result(scenario, status='passed'):
    """构造不启动 ROS 进程的最小场景结果."""
    return {
        'key': scenario.key,
        'category': scenario.category,
        'title': scenario.title,
        'status': status,
        'failures': [] if status == 'passed' else ['模拟失败'],
        'rosbag': {'message_count': 12},
    }


def test_six_fault_categories_are_covered_by_seven_isolated_scenarios():
    """六类需求应展开为 TF 双场景在内的七次隔离运行."""
    assert len(SCENARIOS) == 7
    assert len({scenario.category for scenario in SCENARIOS}) == 6
    assert {scenario.category for scenario in SCENARIOS} == set(FAULT_RECORDS)
    assert {scenario.key for scenario in SCENARIOS} == {
        'qos_mismatch', 'topic_stop', 'tf_missing', 'tf_stale',
        'service_timeout', 'action_cancel', 'node_crash',
    }
    assert len({scenario.domain_offset for scenario in SCENARIOS}) == 7


def test_rosbag_topics_cover_runtime_evidence_and_action_state():
    """录包主题必须横跨传感、诊断、任务、空间和日志证据."""
    assert {
        '/sensor_state', '/diagnostics', '/task_status', '/tf', '/tf_static',
        '/inspection_target_marker', '/execute_task_long/_action/feedback',
        '/execute_task_long/_action/status', '/rosout',
    } == set(RECORDED_TOPICS)


def test_diagnostic_observer_waits_for_a_publisher_with_explicit_type():
    """发布者还未启动时观察器必须等待，不能因无法推断类型而退出。"""
    code, output = run_captured(
        list(DIAGNOSTIC_ECHO), evidence_environment(217), timeout_sec=1.5,
    )
    assert code == 124, output
    assert 'Could not determine the type' not in output


def test_launch_arguments_are_unique_and_scenario_overrides_common_value():
    """场景覆盖公共参数后不应把同一 Launch 参数传入两次."""
    service = next(item for item in SCENARIOS if item.key == 'service_timeout')
    arguments = scenario_launch_arguments(service)
    names = [item.split(':=', 1)[0] for item in arguments]
    assert len(names) == len(set(names))
    assert 'timeout_sec:=5.0' in arguments
    assert 'timeout_sec:=0.6' not in arguments
    assert 'use_rviz:=false' in arguments


def test_selected_scenarios_keep_matrix_order_and_remove_duplicates():
    """部分运行仍按固定矩阵顺序，保证报告可稳定比较."""
    selected = selected_scenarios(['node_crash', 'qos_mismatch', 'node_crash'])
    assert [item.key for item in selected] == ['qos_mismatch', 'node_crash']


def test_bag_message_count_parses_jazzy_info_output():
    """消息数解析应兼容 Jazzy 输出中的对齐空格."""
    info = 'Files: x.mcap\nMessages:             123\n'
    assert bag_message_count(info) == 123
    assert bag_message_count('Messages: 0\n') == 0
    assert bag_message_count('missing') == 0


def test_chinese_report_contains_all_seven_fields_for_six_categories():
    """生成报告必须为每类故障保留完整七段式字段."""
    summary = {
        'started_at': '2026-01-01T00:00:00+08:00',
        'finished_at': '2026-01-01T00:01:00+08:00',
        'status': 'passed',
        'output_dir': '/tmp/evidence',
        'scenarios': [fake_result(item) for item in SCENARIOS],
        'regression': [{
            'passed': True,
            'command': 'colcon test',
            'log': 'colcon-test.log',
        }],
    }
    report = render_chinese_report(summary)
    assert report.count('\n## ') == 8  # 六类故障、回归、回放入口
    for record in FAULT_RECORDS.values():
        assert record.title in report
    for field in ('现象', '检查命令', '画面', '日志', '根因', '修复', '回归测试'):
        assert report.count(f'- {field}：') == 6


def test_scenario_result_shape_is_json_serializable():
    """场景结果必须可以无损写入 UTF-8 JSON 汇总."""
    payload = [fake_result(item) for item in SCENARIOS]
    assert json.loads(json.dumps(payload, ensure_ascii=False))[0][
        'key'
    ] == 'qos_mismatch'


def timeout_command():
    """输出一条证据后等待中断，以真实管道触发超时重试."""
    return [
        sys.executable, '-u', '-c',
        'import time\n'
        'print("unique-timeout-evidence", flush=True)\n'
        'try:\n'
        '    time.sleep(30)\n'
        'except KeyboardInterrupt:\n'
        '    pass\n',
    ]


def test_captured_timeout_preserves_output_once_and_returns_124():
    """重试 communicate 后完整输出应保留一次，并标记超时."""
    code, output = run_captured(timeout_command(), dict(os.environ), 0.5)
    assert code == 124
    assert output.splitlines().count('unique-timeout-evidence') == 1


def test_regression_timeout_logs_preserve_output_once(tmp_path, monkeypatch):
    """三个回归入口超时均应写唯一证据，并返回失败而非通过."""
    real_popen = subprocess.Popen

    def short_timeout_process(_argv, **kwargs):
        # 保留真实进程、管道和 SIGINT；仅替换重命令及首次等待时限。
        process = real_popen(timeout_command(), **kwargs)
        real_communicate = process.communicate
        first_wait = True

        def communicate(*args, **wait_kwargs):
            nonlocal first_wait
            if first_wait:
                first_wait = False
                wait_kwargs['timeout'] = 0.5
            return real_communicate(*args, **wait_kwargs)

        process.communicate = communicate
        return process

    monkeypatch.setattr(
        evidence_recorder.subprocess, 'Popen', short_timeout_process,
    )
    results = run_regression(tmp_path, tmp_path, dict(os.environ))
    assert len(results) == 3
    for result in results:
        assert result['exit_code'] == 124
        assert result['passed'] is False
        output = (tmp_path / result['log']).read_text(encoding='utf-8')
        assert 'exit_code=124' in output
        assert output.splitlines().count('unique-timeout-evidence') == 1
