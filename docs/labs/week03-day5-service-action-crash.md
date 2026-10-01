# 第 3 周第 5 天：Service 超时、Action 取消与节点崩溃

> 实现与定位分支见[第 5 天流程图](../flowcharts/week03-day05-service-action-crash.md)，跨天关系见[第 1～7 天总流程图](../flowcharts/week03-overall.md)。

## 今天交付了什么

第 5 天完成三种任务生命周期故障，并保持第 1～4 天接口兼容：

- `task_executor` 可延迟 `/execute_task` 响应，复现服务器仍在工作但超过客户端期限；
- 新增 `service_timeout_demo`，由客户端明确设置响应截止时间，并用退出码 `6` 表示超时；
- 继续使用标准 ROS 2 Action Cancel 协议，在指定进度取消 `/execute_task_long`；
- `sensor_simulator` 可在指定时间抛出未捕获异常，以退出码 `1` 真实结束进程；
- `status_monitor` 会区分从未发现 Publisher 的 `publisher_missing` 与运行中端点消失的 `publisher_lost`；
- 三种故障的默认参数均为 `0`，正常启动不会注入故障。

## 构建与正常基线

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
ros2 launch embodied_comm week03_day5.launch.py
```

正常基线应包含五个长期运行节点：

```text
sensor_simulator
task_executor
status_monitor
workcell_visualizer
spatial_health_monitor
```

一次只启动一种故障。切换场景前先在启动终端按 `Ctrl+C`，防止不同场景共享节点名和话题。

## 故障一：Service 响应超时

启动一个故意延迟 3 秒的 Service Server。这里把传感器新鲜度阈值设为 5 秒，使实验只关注 Service 期限：

```bash
ros2 launch embodied_comm week03_day5.launch.py \
  fault_service_delay_sec:=3.0 timeout_sec:=5.0
```

另开终端，客户端只等待 1 秒：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws && source install/setup.bash
ros2 run embodied_comm service_timeout_demo --response-timeout 1.0
echo "$?"
```

### 现象

客户端在约 1 秒后报告“服务响应超时”并以退出码 `6` 结束。服务器进程仍然存在，并在 3 秒延迟结束后完成请求、写日志和发布一次 `/task_status`。

### 检查命令

```bash
ros2 service list -t
ros2 node info /task_executor
ros2 topic echo /task_status std_msgs/msg/String
ros2 topic echo /sensor_state std_msgs/msg/String --once
```

检查顺序是：服务是否被发现、Server 节点是否存在、请求最终是否在服务器端完成、传感器数据是否仍在流动。

### 画面

RViz 坐标树和绿色检查区域保持正常。Service 响应延迟属于任务接口时序问题，不会直接改变 TF 或 Marker。

### 日志

客户端日志：

```text
服务响应超时：等待 1.00 秒，客户端截止时间=1.00 秒
```

服务器稍后记录：

```text
故障注入：/execute_task 延迟 3.00 秒后响应
任务结果：task_id=...，检查通过：seq=...
```

### 根因

ROS 2 Service 是一次请求对应一次响应，但本接口没有内建“所有客户端共同使用的业务超时”。超时是本次客户端的截止时间策略；客户端停止等待，不等于服务器回调被取消。`std_srvs/srv/Trigger` 也没有请求 ID 或取消字段供服务器执行回滚。

### 修复

关闭延迟注入：

```bash
ros2 launch embodied_comm week03_day5.launch.py \
  fault_service_delay_sec:=0.0
```

真实系统应先确定接口的响应时间预算。需要反馈、取消或长时间运行的工序，应使用 Action；Service 只承担短时、幂等或能够接受重复请求的操作。客户端超时后不要盲目重试有副作用的服务，因为第一次请求可能仍会完成。

### 回归测试

再次运行 `service_timeout_demo --response-timeout 1.0`，应在截止时间内收到响应并返回退出码 `0`；确认 `/task_status` 只新增一次终态。

## 故障二：Action 在 40% 进度取消

正常启动第 5 天系统：

```bash
ros2 launch embodied_comm week03_day5.launch.py
```

另开终端发送一个 10 秒目标，并在反馈达到 40% 时请求取消：

```bash
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-DAY5-CANCEL \
  --duration 10 \
  --cancel-at 40
echo "$?"
```

### 现象

客户端先收到 `preparing` 和 `inspecting` 反馈；达到 40% 后发送 Cancel Request。Server 接受取消，目标进入 `CANCELED`，结果 `success=false`，客户端退出码为 `3`。

### 检查命令

```bash
ros2 action list -t
ros2 action info /execute_task_long
ros2 topic echo /task_status std_msgs/msg/String
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

快速 Service 在 Action 运行与取消期间仍应响应，证明多线程执行器和可重入回调组没有被长任务占死。

### 画面

当前 Action 是任务调度模拟，没有驱动 Marker 或机械臂运动，所以 RViz 不会直接显示“进度 40%”或停止动作。取消证据来自 Feedback、Action 终态、`/task_status` 和日志。

### 日志

关键顺序应为：

```text
长任务反馈：... progress=40...%
接受取消请求：task_name=inspect_workpiece_WP-DAY5-CANCEL
任务结果：... 任务已取消
最终状态=CANCELED，success=False
```

### 根因

这不是 Server 崩溃或网络断开，而是客户端通过 ROS 2 Action Cancel 协议提出业务终止。Server 的取消回调先决定是否接受，执行循环随后检查 `is_cancel_requested`，调用 `canceled()` 并返回结果。当前检查周期不超过约 0.2 秒，自动化验收要求 1 秒内进入取消终态。

### 修复

取消本身是安全控制动作，不需要“修复为成功”。Server 必须释放单工位占用，真实机器人还应停止运动、撤销执行中的控制目标并进入安全状态。

随后提交新工件验证恢复：

```bash
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-DAY5-RECOVER \
  --duration 2
```

### 回归测试

新目标应被接受并返回 `SUCCEEDED`；`/task_status` 顺序应为一次取消终态和一次成功终态。再调用快速 Service，确认它没有被取消流程影响。

## 故障三：传感器节点崩溃

启动后 6 秒让 `sensor_simulator` 抛出未捕获异常：

```bash
ros2 launch embodied_comm week03_day5.launch.py \
  fault_sensor_crash_after_sec:=6.0 timeout_sec:=1.5
```

### 现象

前 6 秒传感器正常发布；随后进程以退出码 `1` 结束，节点和 `/sensor_state` Publisher 从 ROS Graph 消失。其他四个节点继续运行。监控器超过阈值后报告 `ERROR + publisher_lost`，任务执行器拒绝使用旧缓存。

### 检查命令

```bash
ros2 node list
ros2 topic info /sensor_state --verbose
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
ros2 run tf2_ros tf2_echo world tool0
```

和“话题停止”相比，本场景的关键差异是 Publisher 数量变为 `0`，且 Launch 输出包含进程退出码。

### 画面

RViz 的 TF 树和绿色检查区域继续正常，因为崩溃的是传感器进程，空间可视化由另一个节点负责。画面正常只说明 TF 链还在，不能证明测量链健康。

### 日志

Launch 终端应出现：

```text
故障注入：sensor_simulator 即将崩溃，最后序号=...
RuntimeError: 故障注入：sensor_simulator 即将崩溃...
process has died ... exit code 1
```

诊断键值应包含：

```text
state=publisher_lost
publisher_count=0
publisher_seen=true
qos_compatibility=no_publisher
```

### 根因

故障 Timer 的回调抛出未捕获 `RuntimeError`。异常离开 rclpy Executor 后进程非正常结束，DDS Participant 被清理，其他节点经过发现延迟后看到端点消失。`publisher_lost` 的含义是“监控器曾经发现过发布端，现在没有了”；它仍可能由进程退出、网络隔离或节点被停止造成，结合 Launch 的退出日志才能确定本实验的根因是崩溃。

### 修复

关闭崩溃注入并重启：

```bash
ros2 launch embodied_comm week03_day5.launch.py \
  fault_sensor_crash_after_sec:=0.0
```

当前 Launch 不自动重启崩溃节点。工业部署通常由 systemd、容器编排器或 ROS 2 Launch 的受控 respawn 策略负责重启，同时设置重试上限和退避，避免反复崩溃形成重启风暴。

### 回归测试

确认 `sensor_simulator` 重新进入节点列表、Publisher 数量恢复为 `1`、新序号继续增长、诊断进入 `healthy`，Service 与 Action 再次成功。TF 诊断在整个过程中应保持 `healthy`。

## rosbag 留证

```bash
mkdir -p artifacts/week03-day5
ros2 bag record --storage mcap \
  -o artifacts/week03-day5/fault-run \
  /sensor_state /diagnostics /task_status /tf /tf_static \
  /inspection_target_marker
```

Service 请求/响应和 Action Goal/Cancel/Result 不会完整地以普通业务 Topic 形式出现在上述列表中，因此还要保留客户端输出与 Launch 日志。rosbag 用于对齐传感器、诊断、任务终态和 TF 时间线。

## 工业质检推演与能力边界

把三个故障放进同一条质检线：

```text
PLC/上位机请求一次即时检查
  → 超过 1 秒未返回：客户端进入未知结果处理

安全门打开或急停联锁
  → 取消正在运行的 Action
  → 工位释放后处理下一件工件

测量驱动进程异常退出
  → Publisher 消失 + 数据过期
  → 新任务被传感器新鲜度门禁阻止
```

Service 超时后的结果具有不确定性：客户端不知道服务器最终是否完成，因此真实有副作用的接口需要幂等键、任务 ID 或查询结果接口。Action 取消则有明确协议终态，适合可终止的长工序。节点崩溃属于进程级故障，需要通信诊断与进程监管两类证据共同判断。

当前系统仍是调度、通信和诊断模拟。Action 取消没有发送真实机器人停止轨迹，Service 没有接 PLC，节点恢复也没有自动重启策略。

## 自动化覆盖

`test_day5_fault_injection.py` 使用三个独立 ROS Domain 启动已安装的 Day 5 Launch，覆盖：

- 客户端 0.2 秒截止时间先于服务器 1 秒响应，退出码为 `6`；
- 客户端退出后服务器仍完成请求并只发布一次 `/task_status`；
- Action 在 40% 取消后进入 `CANCELED`，下一目标成功；
- 传感器进程以退出码 `1` 崩溃，Publisher 消失；
- 其他四个节点保持运行，诊断为 `publisher_lost`；
- 崩溃后 Service 拒绝过期缓存；
- 每个实验结束后剩余进程均可干净关闭。

完整回归：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
colcon test --packages-select embodied_interfaces embodied_comm embodied_comm_cpp \
  --event-handlers console_direct+
colcon test-result --all --verbose
```

本轮构建、测试和三个真实 Launch 场景的摘录保存在[第 5 天实测证据](evidence/week03-day5/README.md)。
