# 第 3 周第 1 天实测证据

验证环境：Ubuntu 24.04、ROS 2 Jazzy、Python 3.12。测试使用独立 `ROS_DOMAIN_ID` 和本机发现范围。

| 证据 | 结论 |
|---|---|
| [`build-test.log`](build-test.log) | 三个 ROS 包构建成功，ROS 71 项及根项目 18 项测试全部通过 |
| [`normal-inspection.log`](normal-inspection.log) | `WP-001` 持续反馈并成功；执行期间快速 Service 正常响应 |
| [`cancel-recovery.log`](cancel-recovery.log) | `WP-002` 在 40.2% 取消，`WP-003` 随后成功 |

这些日志是 2026-09-20 的实际本机运行结果摘录。为避免把大量重复传感器输出加入仓库，只保留能够证明接口、并发、取消和恢复行为的行。
