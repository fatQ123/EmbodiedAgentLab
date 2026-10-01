# 第 3 周第 6 天自动故障记录

- 开始时间：`2026-10-01T16:04:35+08:00`
- 结束时间：`2026-10-01T16:08:32+08:00`
- 总体结果：`passed`
- 输出目录：`/home/fatbro/workspace/artifacts/week03-day7/clean-candidate-20261001-g/faults`

> rosbag 保存消息时间线；CLI/Launch 文件日志保存超时、退出码和进程事件。

## 1. QoS 不匹配

- 本次自动验收：**通过**；证据：`qos_mismatch/`（passed，bag=817 条）
- 现象：Publisher 存在，但 RELIABLE 业务订阅收不到 BEST_EFFORT 数据，诊断为 `qos_mismatch`，任务检查失败。
- 检查命令：`ros2 topic info /sensor_state --verbose`；`ros2 topic echo /diagnostics`；调用 `/execute_task`。
- 画面：RViz 坐标树正常；画面正常而测量任务失败。
- 日志：核对 `publisher_reliability=best_effort`、`subscriber_reliability=reliable` 和 `qos_compatibility=incompatible`。
- 根因：DDS Requested/Offered 可靠性策略不兼容，端点发现不等于可传输。
- 修复：统一发布端与业务订阅端的 QoS；本项目恢复 `reliable`。
- 回归测试：确认消息序号增长、诊断 `healthy`、Service 与 Action 成功。

## 2. 话题停止

- 本次自动验收：**通过**；证据：`topic_stop/`（passed，bag=887 条）
- 现象：节点和 Publisher 保持在线，但序号停止增长，超时后诊断为 `stale`，任务被新鲜度门禁拒绝。
- 检查命令：`ros2 node list`；`ros2 topic info /sensor_state --verbose`；`ros2 topic hz /sensor_state`；调用 `/execute_task`。
- 画面：RViz 的 TF 与 Marker 仍正常，不能据此证明测量链健康。
- 日志：出现“停止发布”和“传感器消息超时”，Publisher 数量仍为 1。
- 根因：数据定时器停止，模拟驱动在线但采集线程冻结。
- 修复：关闭停止注入并重启，等待新数据到达后再解除任务联锁。
- 回归测试：确认新序号持续增长、诊断恢复 `healthy`、任务恢复。

## 3. TF 缺失或过期

- 本次自动验收：**通过**；证据：`tf_missing/`（passed，bag=851 条）；`tf_stale/`（passed，bag=1301 条）
- 现象：缺失时 `world → tool0` 从未连通；过期时链先正常，随后动态 TF 时间戳停止并进入 `stale`。
- 检查命令：`ros2 run tf2_ros tf2_echo world tool0`；`ros2 topic info /tf --verbose`；查看 TF 诊断。
- 画面：缺失时 RViz 出现两棵子树且 tool0 Marker 不显示；过期时目标会消失或出现 old data/extrapolation，具体瞬态受 RViz 缓存影响。
- 日志：分别查找“坐标链缺失”或“停止刷新”，并核对诊断的 `state=missing/stale` 与 `age_sec`。
- 根因：关键动态边从未发布，或其时间戳超过允许的新鲜度。
- 修复：恢复唯一、连续且时钟正确的 TF 发布源，使用 `normal` 模式重启。
- 回归测试：确认完整链持续输出、时间戳增长、空间诊断 `healthy`、Marker 可见。

## 4. Service 超时

- 本次自动验收：**通过**；证据：`service_timeout/`（passed，bag=1091 条）
- 现象：客户端先达到响应期限并退出，但 Server 仍会完成原请求并发布终态。
- 检查命令：`ros2 service list -t`；`ros2 node info /task_executor`；查看 `/task_status` 和超时客户端退出码。
- 画面：RViz 保持正常；该故障属于接口时序而非空间链。
- 日志：客户端出现“服务响应超时”，Server 稍后记录“延迟 1.00 秒后响应”。
- 根因：客户端截止时间短于 Server 执行时间；客户端超时不会取消回调。
- 修复：关闭延迟；长任务改用 Action，有副作用的 Service 增加幂等键。
- 回归测试：短截止时间内收到正常响应，且 `/task_status` 每次请求只发布一次。

## 5. Action 取消

- 本次自动验收：**通过**；证据：`action_cancel/`（passed，bag=1588 条）
- 现象：目标在 40% 请求取消并进入 `CANCELED`，随后新目标可进入 `SUCCEEDED`。
- 检查命令：`ros2 action list -t`；`ros2 action info /execute_task_long`；查看 Feedback、Result 与 `/task_status`。
- 画面：当前 Marker 不受 Action 驱动，取消证据来自协议终态而非 RViz 动作。
- 日志：依次出现取消请求、`CANCELED`、工位释放和恢复目标 `SUCCEEDED`。
- 根因：客户端主动发出标准 Action Cancel Request，Server 协作停止。
- 修复：取消是安全动作；确保执行循环响应取消并在 `finally` 释放工位。
- 回归测试：取消后立即提交下一目标，确认不拒绝、不死锁且成功完成。

## 6. 节点崩溃

- 本次自动验收：**通过**；证据：`node_crash/`（passed，bag=891 条）
- 现象：`sensor_simulator` 以退出码 1 消失，Publisher 数量变为 0，其他节点继续运行并诊断 `publisher_lost`。
- 检查命令：`ros2 node list`；`ros2 topic info /sensor_state --verbose`；查看 `/diagnostics`、Launch 退出日志并调用 `/execute_task`。
- 画面：独立 TF/Marker 画面保持正常，说明空间链与测量进程相互隔离。
- 日志：组合“即将崩溃”、异常栈、`process has died`、`exit code 1`。
- 根因：故障 Timer 抛出未捕获异常，进程退出后 DDS 端点被清理。
- 修复：关闭注入并重启；生产部署增加有退避和上限的进程监管策略。
- 回归测试：确认节点和 Publisher 恢复、诊断 `healthy`、新数据任务成功。

## 回归结果

- **通过**：`colcon test --packages-select embodied_interfaces embodied_comm embodied_comm_cpp --event-handlers console_direct+`；日志 `colcon-test.log`
- **通过**：`colcon test-result --all --verbose`；日志 `colcon-test-result.log`
- **通过**：`/usr/bin/python3 -m pytest -q /home/fatbro/workspace/artifacts/week03-day7/clean-candidate-20261001-g/source/tests`；日志 `repository-tests.log`

## 回放入口

进入本报告所在目录后，对任一场景执行：

```bash
ros2 bag info <scenario>/rosbag
ros2 bag play <scenario>/rosbag
```

Service 超时和进程崩溃不能只靠话题回放下结论；必须同时查看该场景的
`launch.log`、客户端日志、`nodes.log` 和 `sensor-topic.log`。
