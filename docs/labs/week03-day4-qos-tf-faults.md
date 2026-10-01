# 第 3 周第 4 天：QoS、话题停止与 TF 缺失/过期故障注入

> 实现和定位分支见[第 4 天故障注入流程图](../flowcharts/week03-day04-qos-tf-faults.md)，跨天关系见[第 1～7 天总流程图](../flowcharts/week03-overall.md)。

## 今天交付了什么

第 4 天把同一质检工位变成一个可控的通信与空间故障实验台：

- `/sensor_state` 发布端可切换 `RELIABLE` 或 `BEST_EFFORT`，订阅端固定请求 `RELIABLE`，可以制造真实 DDS QoS 不兼容；
- 传感器可以停止数据定时器，同时保留节点和 Publisher，复现“设备在线但数据卡死”；
- `workcell_visualizer` 可以从启动起不发布 `base_link → camera_link`，复现 TF 缺失；
- 它也可以先正常刷新动态 TF，再停止刷新，复现 TF 过期；
- 新增 `spatial_health_monitor`，用独立 TF Buffer 诊断 `waiting / healthy / missing / stale`；
- 传感器与 TF 诊断共同发布到 `/diagnostics`，通过 `status.name` 区分；
- 默认参数全部为正常模式，不传故障参数时不会改变前三天的行为。

## 构建与正常基线

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
ros2 launch embodied_comm week03_day4.launch.py
```

正常时 RViz 的 Fixed Frame 为 `world`，可以看到：

```text
world → base_link → camera_link → tool0 → 绿色质检区域
```

另开终端检查两个诊断项：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws && source install/setup.bash
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
```

正常基线应同时出现：

- `sensor_simulator: Sensor Stream`：`level=OK`、`state=healthy`；
- `workcell_visualizer: TF Chain`：`level=OK`、`state=healthy`。

一次只启动下面一种故障。切换场景前先在启动终端按 `Ctrl+C`，避免旧节点与新节点重名并同时占用相同话题。

## 故障一：QoS 不匹配

启动：

```bash
ros2 launch embodied_comm week03_day4.launch.py \
  publisher_reliability:=best_effort timeout_sec:=1.5
```

### 现象

`sensor_simulator` 节点和 `/sensor_state` Publisher 都存在，但固定请求 `RELIABLE` 的 `status_monitor` 与 `task_executor` 收不到任何测量值。约 1.5 秒后，传感器诊断变为 `ERROR + qos_mismatch`；快速 Service 返回失败，长任务在结束检查时会 `ABORTED`。

### 检查命令

```bash
ros2 topic info /sensor_state --verbose
ros2 topic echo /sensor_state std_msgs/msg/String
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

定位重点是把端点 QoS 放在一起比较：Publisher 是 `BEST_EFFORT`，两个业务订阅端是 `RELIABLE`。`topic echo` 使用默认 QoS 时是否能收到数据不是业务链健康的充分证据，应以业务订阅端的实际 QoS 和 `/diagnostics` 为准。

### 画面

RViz 中坐标树与绿色质检区域保持正常，因为故障只发生在传感器 DDS 匹配阶段。画面正常但任务失败，正是提示操作员转向通信 QoS，而不是继续排查 TF。

### 日志

启动日志包含 `可靠性=best_effort`。诊断键值包含：

```text
state=qos_mismatch
publisher_count=1
publisher_reliability=best_effort
subscriber_reliability=reliable
qos_compatibility=incompatible
qos_reason=...
```

### 根因

DDS 的 Requested/Offered 规则要求 Publisher 提供的可靠性至少满足 Subscription 的请求。`BEST_EFFORT` 不能满足 `RELIABLE`，因此端点能被发现，但不会建立兼容的数据连接。这不是话题名错误，也不是节点崩溃。

### 修复

恢复发布端可靠性并重启场景：

```bash
ros2 launch embodied_comm week03_day4.launch.py \
  publisher_reliability:=reliable timeout_sec:=1.5
```

真实项目也可以把订阅端改为 `BEST_EFFORT`，但必须依据数据允许丢失与否统一设计，而不是为了消除报警随意降低可靠性。

### 回归测试

确认 `/sensor_state` 序号持续增长，诊断回到 `healthy`，快速 Service 成功；再运行一次 `inspection_demo`，确认 Action 能成功完成。

## 故障二：话题停止

启动：

```bash
ros2 launch embodied_comm week03_day4.launch.py \
  fault_stop_after_sec:=6.0 timeout_sec:=1.5
```

### 现象

启动后的前 6 秒数据和任务正常；之后消息序号停止增长，但节点和 Publisher 仍然存在。再过 1.5 秒，诊断变为 `ERROR + stale`，Service 与 Action 都会被执行器自身的新鲜度检查拒绝。

### 检查命令

```bash
ros2 node list
ros2 topic info /sensor_state --verbose
ros2 topic hz /sensor_state
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

`node list` 和 `topic info` 只能证明进程与端点存在；必须再看 `topic hz`、最新序号和 `age_sec` 才能证明数据仍在流动。

### 画面

RViz 的 TF 树与绿色质检区域继续正常。这个画面对“测量值是否新鲜”没有证明力，故障证据来自诊断和消息时间线。

### 日志

注入时会记录：

```text
故障注入：节点与 Publisher 保持存活，但 /sensor_state 停止发布，最后序号=...
传感器消息超时：已 ... 秒没有有效消息
```

诊断显示 `publisher_count=1`、`qos_compatibility=compatible`、`state=stale`，这组证据把断流与 QoS 不匹配区分开。

### 根因

模拟传感器的数据 Timer 被取消，但 Node 与 DDS Publisher 未销毁。这对应工业设备线程卡死、驱动停止采样或上游采集链冻结，而非网络端点消失。

### 修复

用 `fault_stop_after_sec:=0.0` 重启。真实系统应先安全停机，再恢复驱动/设备并等待新的、序号继续增长的数据；不能直接把旧缓存标为健康。

### 回归测试

确认新消息到达后诊断从 `waiting` 进入 `healthy`，Service 和 Action 恢复；同时复跑 QoS 不匹配用例，避免“修复断流”掩盖 QoS 配置错误。

## 故障三：TF 缺失

启动：

```bash
ros2 launch embodied_comm week03_day4.launch.py \
  tf_fault_mode:=missing tf_timeout_sec:=1.0
```

### 现象

静态边 `world → base_link` 与 `camera_link → tool0` 仍发布，但中间的动态边 `base_link → camera_link` 从未发布，因此无法合成 `world → tool0`。空间诊断先短暂为 `waiting`，超过阈值后变为 `ERROR + missing`。

### 检查命令

```bash
ros2 run tf2_ros tf2_echo world tool0
ros2 run tf2_ros tf2_echo world base_link
ros2 run tf2_ros tf2_echo camera_link tool0
ros2 topic info /tf --verbose
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
```

先查完整链，再查两段局部链，可以把问题快速收敛到缺失的 `base_link → camera_link`，而不是笼统地判断“TF 全坏了”。

### 画面

RViz 的 TF 显示中会出现两个不连通的子树：`world/base_link` 与 `camera_link/tool0`。Fixed Frame 为 `world` 时，绑定到 `tool0` 的绿色质检区域无法变换到世界坐标，因此不显示并出现 Transform 错误。

### 日志

发布器明确记录：

```text
故障注入：不发布 base_link → camera_link，world → tool0 坐标链缺失
```

空间诊断包含 `state=missing`、`source_frame=world`、`target_frame=tool0`、`age_sec=none` 与 TF 查询异常。

### 根因

动态 TF 边从未进入 Buffer。工业现场常见原因是相机驱动未启动、frame_id 拼写不一致、标定发布器未部署或父子帧接反。

### 修复

用 `tf_fault_mode:=normal` 重启；真实系统应修正并恢复唯一的权威 TF 发布源，避免为了“补齐树”临时发布重复或冲突变换。

### 回归测试

确认 `tf2_echo world tool0` 连续输出、空间诊断为 `healthy`、RViz 四帧重新连通且绿色区域出现。传感器诊断应始终保持 `healthy`，证明修复没有扰动通信链。

## 故障四：TF 过期

启动：

```bash
ros2 launch embodied_comm week03_day4.launch.py \
  tf_fault_mode:=stale tf_fault_after_sec:=6.0 tf_timeout_sec:=1.0
```

### 现象

最初 `world → tool0` 正常且诊断为 `healthy`。6 秒后停止刷新 `base_link → camera_link`，节点和两个 Publisher 均保持存活；再过约 1 秒空间诊断变为 `ERROR + stale`。TF Buffer 仍可能返回最后一次缓存，所以“能查到”不等于“足够新”。

### 检查命令

```bash
ros2 run tf2_ros tf2_echo world tool0
ros2 topic hz /tf
ros2 topic info /tf --verbose
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
```

观察 `tf2_echo` 的时间戳是否停止增长，并将诊断里的 `age_sec` 与 `tf_timeout_sec` 比较。只看 Publisher 数量或只做一次 latest-time 查询会漏报过期故障。

### 画面

启动时四帧与绿色质检区域正常。故障注入后，Marker 继续发布但使用有限寿命；由于新 Marker 无法用最新 TF 正确变换，原有绿色区域会消失或 RViz 报 extrapolation/old data。不同 RViz 缓存时序可能短暂保留最后姿态，因此诊断中的时间戳年龄是权威判断。

### 日志

注入时记录：

```text
故障注入：停止刷新 base_link → camera_link 动态 TF；节点、TF Publisher 和 Marker Publisher 保持存活
```

空间诊断持续给出 `state=stale` 和递增的 `age_sec`，同时 Publisher 计数仍非零。

### 根因

动态 TF 的最后时间戳超过允许的新鲜度。工业现场可能是定位线程卡死、时钟异常、网络阻塞或驱动仍存活但不再更新位姿。

### 修复

用 `tf_fault_mode:=normal` 重启；真实系统还要校准 ROS Time/设备时钟，并确认动态变换频率满足控制周期。

### 回归测试

确认 TF 时间戳持续增长、`age_sec < tf_timeout_sec`、空间诊断恢复 `healthy`，并检查 RViz 目标不会再因 Marker 到期而消失。

## rosbag 留证

在启动故障场景前另开终端：

```bash
mkdir -p artifacts/week03-day4
ros2 bag record --storage mcap \
  -o artifacts/week03-day4/fault-run \
  /sensor_state /diagnostics /task_status /tf /tf_static \
  /inspection_target_marker
```

完成后按 `Ctrl+C`，检查并回放：

```bash
ros2 bag info artifacts/week03-day4/fault-run
ros2 bag play artifacts/week03-day4/fault-run
```

QoS 不匹配场景中 rosbag 可能仍录到 `/sensor_state`，因为 Recorder 自己协商了兼容 QoS；这不推翻业务订阅端不兼容的事实。定位时必须同时保存端点 QoS 与业务诊断。

## 工业质检推演与能力边界

将当前节点映射到一条相机质检线：

```text
相机/测量设备
  → DDS 数据链（QoS 与连续性）
  → 质检任务 Service / Action（新鲜度联锁）

标定与定位发布器
  → TF 空间链（完整性与时间戳）
  → RViz / 数字孪生画面（空间可观测性）
```

四种故障对应不同现场问题：QoS 不匹配是系统集成配置错误；话题停止是运行期数据源冻结；TF 缺失是空间拓扑不完整；TF 过期是定位链停止更新。它们可能具有相似的“任务或画面异常”，但根因和修复完全不同。

当前安全边界必须说清楚：`task_executor` 已独立对传感器数据做新鲜度联锁，所以 QoS 不匹配和话题停止会阻止 Service/Action 使用旧数据；第 4 天的 TF 监控还是独立报警链，Action 尚未订阅空间健康状态，因此 TF 缺失/过期不会自动中止任务。这是后续把多模态感知、位姿置信度和动作规划纳入统一任务门禁的接口位置，不应把今天的诊断演示描述成真实视觉检测、机器人定位或安全 PLC。

## 自动化覆盖

`test_day4_fault_injection.py` 同时覆盖节点内逻辑与已安装 Launch 的四场景矩阵：

- 实际 QoS 不兼容时端点存在但业务订阅无数据；
- 话题停止后数据计数不再增长；
- TF 缺失时完整链不可合成；
- TF 过期时最后时间戳停止刷新并触发 `stale`；
- 正常传感器场景 Service 成功，QoS/断流场景 Service 失败；
- 四个故障均产生稳定的诊断状态码与注入日志；
- 结束 Launch 后所有进程干净退出。

完整回归命令：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
colcon test --packages-select embodied_interfaces embodied_comm embodied_comm_cpp \
  --event-handlers console_direct+
colcon test-result --all --verbose
```
