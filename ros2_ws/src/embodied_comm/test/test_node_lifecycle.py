"""关闭 Context 的 RCL 竞态可清理；真实运行错误绝不能被吞掉。"""
from embodied_comm import common, task_executor
import pytest


@pytest.mark.parametrize('entrypoint', ['single', 'multi'])
@pytest.mark.parametrize('context_alive,error_type,expected_type', [
    (False, common.RCLError, None),
    (True, common.RCLError, common.RCLError),
    (False, RuntimeError, RuntimeError),
])
def test_shutdown_race_does_not_mask_runtime_failures(
        monkeypatch, entrypoint, context_alive, error_type, expected_type):
    """两个执行器入口都按上下文状态区别 shutdown 与实际故障。"""
    calls = {'destroy': 0, 'shutdown': 0, 'executor_shutdown': 0}

    class FakeNode:
        def destroy_node(self):
            calls['destroy'] += 1

    def spin(_node=None):
        raise error_type('模拟 RCL 等待集或节点错误')

    class FakeExecutor:
        def __init__(self, **kwargs):
            pass

        def add_node(self, node):
            pass

        def spin(self):
            spin()

        def shutdown(self):
            calls['executor_shutdown'] += 1

    def shutdown():
        calls['shutdown'] += 1

    monkeypatch.setattr(common.rclpy, 'init', lambda **kwargs: None)
    monkeypatch.setattr(common.rclpy, 'ok', lambda: context_alive)
    monkeypatch.setattr(common.rclpy, 'spin', spin)
    monkeypatch.setattr(common.rclpy, 'try_shutdown', shutdown)
    monkeypatch.setattr(task_executor, 'TaskExecutor', FakeNode)
    monkeypatch.setattr(task_executor, 'MultiThreadedExecutor', FakeExecutor)

    def run():
        if entrypoint == 'single':
            common.run_node(FakeNode)
        else:
            task_executor.main()

    if expected_type is None:
        run()
    else:
        with pytest.raises(expected_type):
            run()
    assert calls['destroy'] == 1
    assert calls['shutdown'] == 1
    assert calls['executor_shutdown'] == (entrypoint == 'multi')
