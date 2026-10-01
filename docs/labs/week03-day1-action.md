# 第 3 周第 1 天：长任务 Action 与生产线质检推演

> 实现路径与故障分支见[第 1 天 Action 流程图](../flowcharts/week03-day01-action.md)，跨天关系见[第 1～7 天总流程图](../flowcharts/week03-overall.md)。

## 1. 今天完成了什么

系统保留第 2 周的 `/execute_task` 快速服务，并增加 `/execute_task_long` Action。两者读取同一个 `task_executor` 传感器缓存，但解决的问题不同：

| 接口 | 工业语义 | 调用特点 |
|---|---|---|
| `/execute_task` Service | 操作员立即查询测量信号是否可用 | 一次请求、一次响应，不报告过程 |
| `/execute_task_long` Action | 工位执行定位、扫描和结果验证 | 持续反馈，可取消，有明确终态 |

这不是把 Service 换成 Action。真实工厂中，毫秒或秒级查询与几十秒甚至数分钟的工序会同时存在；长任务运行时，快速查询、传感器更新和安全取消都不能被阻塞。

## 2. Action 契约

类型为 `embodied_interfaces/action/ExecuteTask`：

```text
string task_name
float32 duration_sec
---
bool success
string message
uint64 sensor_seq
---
float32 progress_percent
string phase
```

- `task_name` 用于追踪工件或工序，不得为空。
- `duration_sec` 是本阶段用于稳定复现实验的模拟时长，范围为 0.1～300 秒。
- `sensor_seq=0` 表示结束时没有合法传感器数据。
- 进度范围为 0～100，阶段依次为 `preparing`、`inspecting`、`validating` 和 `completed`。
- 单个工位一次只执行一个目标；已有目标时，新目标会被拒绝，不会偷偷终止正在加工的工件。
- 成功、失败和取消各向 `/task_status` 发布一次终态。

## 3. 构建与启动

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
ros2 launch embodied_comm three_nodes.launch.py
```

新终端必须再次加载 ROS 和工作空间：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
source install/setup.bash
ros2 action list -t
ros2 action info /execute_task_long
```

应看到 `/execute_task_long [embodied_interfaces/action/ExecuteTask]`，服务端节点为 `/task_executor`。

## 4. 推演一：正常质检和并行查询

生产线上的 `WP-001` 到达质检工位。Action 的四个阶段在未来可以分别连接夹具定位、相机扫描、算法判定和结果归档；今天先用时间和模拟传感器验证通信契约。

终端 A 执行：

```bash
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-001 \
  --duration 5
```

Action 仍在运行时，终端 B 执行即时查询：

```bash
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

预期结果：

- Action 连续输出准备、检查、验证和完成进度；
- Service 不需要等待 Action 结束即可返回；
- 最终状态为 `SUCCEEDED`，并包含任务结束时使用的传感器序号；
- `status_monitor` 收到一次成功终态。

这说明目前系统能够让一个长工序持续运行，同时接受操作员或上层控制器的快速状态查询。

## 5. 推演二：安全取消和恢复生产

`WP-002` 检查期间模拟安全门打开或联锁触发：

```bash
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-002 \
  --duration 10 \
  --cancel-at 40
echo "$?"
```

预期最终状态为 `CANCELED`，退出码为 `3`。这不是程序崩溃，而是客户端明确区分的一种业务终态。随后执行：

```bash
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-003 \
  --duration 2
```

`WP-003` 应被接受并成功完成，证明取消已释放工位，没有留下永久占用或僵死任务。

客户端退出码：

| 退出码 | 含义 |
|---|---|
| `0` | 任务成功 |
| `2` | 任务执行后失败或中止 |
| `3` | 任务按请求取消 |
| `4` | 目标在执行前被拒绝 |
| `5` | Action Server 不可用或等待超时 |

## 6. 自动化验证

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
source install/setup.bash
colcon test --packages-select embodied_interfaces embodied_comm embodied_comm_cpp
colcon test-result --all --verbose
```

测试覆盖非法目标、成功反馈、无数据失败、越界数据失败、并发目标拒绝、取消延迟、取消后恢复、Action 运行时快速 Service 响应，以及第 2 周全部回归用例。本次实测为 ROS 工作空间 71 项通过、根项目 18 项通过、0 项失败。

## 7. 现在真正能做什么

已经具备：

- 为长工序建立目标、反馈、取消和终态协议；
- 让即时查询与长工序并行处理；
- 限制单工位并发，避免两个工件同时占用同一执行资源；
- 取消后释放资源并继续处理下一件工件；
- 用稳定任务名、传感器序号、状态话题和日志追踪一次执行。

尚未具备：

- 当前传感器是规律生成的数值，不是相机、测量仪或 PLC 的真实输入；
- `duration_sec` 驱动的是可重复的时间模拟，不是实际扫描设备；
- 目前只校验测量数据格式和范围，不能判断真实产品缺陷；
- 尚未连接安全 PLC、机械臂、传送带、分拣机构、RViz 或 Gazebo；
- 取消只验证软件任务停止，不构成经过安全认证的急停回路。

因此，第一天交付的是工业任务的通信与生命周期骨架。后续加入 TF、诊断、故障注入、视觉和机械臂时，可以复用同一个 Action 契约，而不必重新发明长任务如何开始、汇报和停止。

## 8. 实测证据

构建、测试和三件工件推演的留档位于 [`evidence/week03-day1`](evidence/week03-day1/README.md)。
