# 第 3 周第 3 天：健康诊断、话题停止故障与 rosbag 证据闭环

> 实现、联锁与现场定位路径见[第 3 天诊断流程图](../flowcharts/week03-day03-health-topic-stop.md)，跨天关系见[第 1～7 天总流程图](../flowcharts/week03-overall.md)。

## 1. 今天完成了什么

今天把前两天“能执行、能看见”的质检工位扩展成“数据断流时能发现、能阻断、能留证”的系统，并完成本周六类故障中的第一类：**话题停止**。

交付结果如下：

- `/status_monitor` 以 `diagnostic_msgs/msg/DiagnosticArray` 发布标准 `/diagnostics`；
- 传感器健康状态按 `waiting/WARN → healthy/OK → stale/ERROR → healthy/OK` 转换；
- `fault_stop_after_sec` 可以只停止 `/sensor_state` 消息，同时保留节点和 DDS Publisher；
- `/execute_task` Service 和 `/execute_task_long` Action 独立检查缓存新鲜度，拒绝陈旧数据；
- 故障期间 TF 坐标树和 RViz Marker 保持正常，用于区分空间链和感知链；
- rosbag 记录 `/sensor_state`、`/diagnostics` 和 `/task_status`，可以回放故障时间线；
- 安装后的 Launch、真实 DDS、Service、Action、TF 和 Marker 均有自动化回归测试。

这不是“节点消失”故障。它模拟的是工业现场更隐蔽的一类问题：驱动进程和网络端点仍在，但相机、测量仪或驱动线程卡住，不再产生新测量。

## 2. 系统原理

```text
sensor_simulator
  ├─ 正常：持续发布 /sensor_state
  └─ 故障：取消发布定时器，但节点和 Publisher 继续存活
             │
             ├──────────────► status_monitor
             │                 └─ 超时后发布 /diagnostics: ERROR/stale
             │
             └──────────────► task_executor
                               ├─ Service 请求时检查接收时间
                               └─ Action 结束前检查接收时间
                                  陈旧数据一律失败/ABORTED

workcell_visualizer ──► /tf、/tf_static、Marker（本次故障不破坏）
rosbag              ◄── /sensor_state、/diagnostics、/task_status
```

监控器和执行器都使用单调时钟判断“距离最后一条合法数据过去多久”。单调时钟不受系统时间校正影响，也不会因为仿真 `/clock` 暂停而掩盖断流。非法 JSON 不刷新接收时间。

监控器仍在按频率发布诊断，所以传感器流失效使用 `DiagnosticStatus.ERROR`；`STALE` 等级通常留给诊断项本身长期没有更新的场景。这里把稳定的业务状态字符串命名为 `stale`，便于脚本和 rosbag 检索。

诊断只负责可观察性，不作为执行器的“许可心跳”。执行器直接依据它自己收到的数据时间戳做联锁，因此即使监控节点崩溃，也不会把过期数据误判为可用。

## 3. 启动与观察

### 3.1 正常模式

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
ros2 launch embodied_comm week03_day3.launch.py \
  fault_stop_after_sec:=0.0 timeout_sec:=2.0 diagnostic_rate:=2.0
```

新终端执行：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws && source install/setup.bash
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray --once
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

实测诊断为 `level: \0`、`state: healthy`、`publisher_count: 1`；快速检查以 `success=True` 返回最新序号。

### 3.2 注入话题停止故障

```bash
ros2 launch embodied_comm week03_day3.launch.py \
  publish_rate:=5.0 \
  fault_stop_after_sec:=6.0 \
  timeout_sec:=1.5 \
  diagnostic_rate:=2.0
```

启动后可同时观察：

```bash
ros2 topic echo /sensor_state std_msgs/msg/String
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
ros2 topic info /sensor_state --verbose
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
ros2 run tf2_ros tf2_echo world tool0
```

参数均为只读启动参数。`fault_stop_after_sec:=0.0` 表示不注入故障；负数、NaN 和无穷值会在启动时被拒绝。

## 4. 七段式故障记录

### 4.1 现象

- `/sensor_state` 起初递增，约 6 秒后停在 `seq=30`；
- `sensor_simulator` 节点仍存在，`/sensor_state` 的 Publisher 数仍为 1；
- 超过 1.5 秒阈值后，`/diagnostics` 变成 `level=ERROR`、`state=stale`；
- `/execute_task` 返回失败，Action 在终态校验时会进入 `ABORTED`；
- RViz 中 `world → base_link → camera_link → tool0` 与绿色 Marker 仍正常。

### 4.2 检查命令

```bash
ros2 node list
ros2 topic info /sensor_state --verbose
ros2 topic hz /sensor_state
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
ros2 run tf2_ros tf2_echo world tool0
```

关键区别是：`topic info` 只能证明端点存在，不能证明数据仍在流动。必须结合频率、序号、年龄和诊断状态判断。QoS 不匹配也可能表现为“有端点却收不到数据”，所以后续 QoS 故障实验还要比较发布端与订阅端策略；本次根因已由注入日志明确锁定。

### 4.3 画面

本次 RViz 画面应与第 2 天的正常基线一致：TF 状态为 OK，绿色质检区域仍位于 `tool0` 前方。可对照[第 2 天正常 RViz 截图](evidence/week03-day2/rviz-normal.png)。

这不是测试遗漏，而是诊断结论：**RViz 是空间关系可视化工具，不是传感器数据健康仪表盘**。如果只盯着 RViz，操作员会错误地认为工位仍可生产；真正的异常证据在 `/diagnostics` 和数据时间线上。

### 4.4 日志

实测关键时间线：

```text
[1789916941.899904622] 故障注入：节点与 Publisher 保持存活，
                       但 /sensor_state 停止发布，最后序号=30
[1789916943.411190359] 传感器消息超时：已 1.51 秒没有有效消息
[1789916954.646852524] 任务结果：success=False，sensor_seq=None，
                       last_seq=30，age=12.24 秒，阈值=1.50 秒
```

从停止发布到报警约 `1.511` 秒，与 `timeout_sec:=1.5` 的配置一致。诊断快照仍显示 `publisher_count=1`，从而排除“发布端已经退出”这一解释。

### 4.5 根因

`sensor_simulator` 的故障定时器主动取消数据发布定时器，但不销毁节点和 Publisher。这模拟设备线程卡死或驱动不再产生帧，而 DDS 发现信息仍然存在。

执行器过去只保存“最后一个数值”；如果没有新鲜度概念，旧读数可能被无限期复用，形成危险的“假正常”。今天的根本修复是把“数值是否合法”和“数值是否足够新”设为两个独立条件。

### 4.6 修复

演示环境中，重启 Launch 并关闭故障注入：

```bash
ros2 launch embodied_comm week03_day3.launch.py \
  fault_stop_after_sec:=0.0 timeout_sec:=2.0 diagnostic_rate:=2.0
```

恢复后 `/diagnostics` 回到 `healthy/OK`，快速 Service 再次返回成功。真实产线中的修复可能是重启相机驱动、复位采集卡、修复供电或网络、替换设备；必须依据硬件日志和维护规程决定，不能让诊断节点自行猜测。

### 4.7 回归测试

自动化测试验证：

- `waiting → healthy → stale → recovered` 的完整状态机；
- 非法消息不刷新健康时间；
- 消息停止时节点和 Publisher 仍在线；
- Service 与 Action 拒绝陈旧数据；
- TF、Marker、Service 和 Action 服务器仍在；
- 安装后的 Day 3 Launch 可复现故障并干净退出；
- 第 1 天 Action、第 2 天 TF/RViz 和第 2 周功能继续通过。

最终全量实测：ROS Python 94 项、C++ 5 项全部通过；`colcon test-result` 因 CTest 包装层额外计 1 条记录，所以报告为 100 条、0 错误、0 失败、0 跳过。根项目另有 18 项通过。按独立测试用例计共 117 项。代码风格、XML 和补丁空白检查也全部通过。详细结果见[证据目录](evidence/week03-day3/README.md)。

## 5. rosbag：把“我看到过”变成可回放证据

先启动录制，再启动故障场景：

```bash
ros2 bag record -o /tmp/week03_day3_topic_stop \
  --topics /sensor_state /diagnostics /task_status
```

停止录制后检查并回放：

```bash
ros2 bag info /tmp/week03_day3_topic_stop
ros2 bag play /tmp/week03_day3_topic_stop --rate 0.5
```

本次实测包长 `24.712 s`、共 `79` 条消息：`/sensor_state` 27 条、`/diagnostics` 51 条、`/task_status` 1 条。故障后传感器消息数量冻结，但诊断继续增长并记录状态变化，因此可以离线还原“数据先停、随后超时、任务最终被联锁拒绝”的因果顺序。二进制 bag 保存在 `/tmp`，仓库只保存体积小、可审阅的元数据与结果摘要。

当前 `/sensor_state` 仍是教学用 JSON，只有序号和值，没有采集时间戳。DDS 深度 10 的队列可能让不同订阅者在高负载时稍晚清空积压数据。工业消息应改成带 `std_msgs/Header` 的强类型接口，同时分别记录采集时间、接收时间和处理时间。

## 6. 工业场景推演

把系统放到“生产线工件视觉质检”中：

```text
WP-003 到站
  → 相机驱动仍显示在线
  → 图像采集线程卡死，不再产生新帧
  → TF/RViz 仍显示相机和检查头位置正常
  → 健康监控发现数据年龄超过 1.5 秒
  → 工位诊断升级为 ERROR
  → 质检 Service/Action 拒绝使用最后一帧判断新工件
  → rosbag 保留断流、报警和任务失败时间线
  → 操作员检修并重启驱动
  → 新帧恢复，诊断回到 OK，工位重新放行
```

它防止的真实风险是“拿上一件工件的数据给下一件工件判定”。在测量、视觉、力控或定位系统中，旧数据的数值可能完全落在合法范围内，但语义上已经无效。

当前实现仍是通信和任务调度模拟：没有真实相机、缺陷识别、PLC、安全继电器、机械臂或分拣执行。ROS 软件超时和 Action cancel 不能替代经过安全认证的急停与功能安全回路。

## 7. 与工业前沿如何接轨

第三天不是在仿制一个机器人基础模型，而是在构建模型进入真实机器人前所需的确定性外壳：

```text
多模态/具身模型：看懂图像和语言，提出目标或动作
                         │
ROS 2 Action：          管任务生命周期、反馈、取消和终态
TF：                    管观测、机器人、工具和世界的时空关系
diagnostics：           管数据是否可信以及异常证据
rosbag：                管可回放的观测、动作、结果和失败样本
                         │
受约束控制与安全系统：  决定动作能否真正下发到物理设备
```

### 7.1 具身智能：Gemini Robotics 2

Google DeepMind 在 2026 年发布的 Gemini Robotics 2 把视觉、语言和机器人动作结合，并强调多步任务规划、进度/成功检测、自纠错以及必要时请求人类介入。对应到本项目，高层模型未来可以选择 `inspect_workpiece` 技能，但执行仍应落入 Action 的接受、反馈、取消和终态边界；数据过期诊断则应阻止模型在“看不见最新现场”时继续行动。

差距也很明确：当前没有图像、语言输入、学习策略、机器人动作、置信度或 OOD 检测；软件超时不是安全认证能力。参考：[Gemini Robotics 2 官方发布](https://deepmind.google/blog/gemini-robotics-2-brings-whole-body-intelligence-to-robots/)。

### 7.2 多模态机器人基础模型：NVIDIA Isaac GR00T N1.7

GR00T N1.7 接收图像/视频、语言和机器人状态并输出连续动作，官方流水线覆盖数据采集、训练、评测、导出与 Isaac ROS 部署。本项目的 `task_name`、阶段、终态、`sensor_seq`、诊断状态和 rosbag 可以演进成一次 policy rollout 的 episode 元数据，帮助判断“模型失败”还是“输入数据早已失效”。

当前还没有相机序列、关节状态、动作轨迹、示教数据、模型服务器或闭环评测。参考：[NVIDIA 官方技术文章](https://developer.nvidia.com/blog/develop-humanoid-robot-policies-end-to-end-with-nvidia-isaac-gr00t/)。

### 7.3 失败数据也有价值：Physical Intelligence π0.7

π0.7 的研究把子任务、视觉目标、控制模式、成功/失败和质量等 episode 元数据纳入训练，并使用自治执行和失败轨迹。今天形成的“故障注入→诊断→任务拒绝→恢复→回归”记录，未来若再加入真实观测和动作，就能从调试日志演进为机器人学习数据集的一部分。

当前 bag 只记录字符串传感器、诊断和任务终态，不能冒充多模态机器人数据集。参考：[Physical Intelligence π0.7 研究发布](https://www.pi.website/blog/pi07)。

### 7.4 数字孪生与仿真：Isaac Sim 和工业 AI

NVIDIA Isaac Sim 通过 ROS 2 Bridge 提供 TF、传感器、仿真时间和物理场景。下一步可以把今天的“定时停止字符串话题”升级为相机掉帧、时间戳冻结、网络延迟或传感器退化，并在数字孪生中反复运行同一验收。参考：[Isaac Sim 6.1 ROS 2/TF 教程](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/ros2_tutorials/tutorial_series/tutorial_ros2_tf.html)。

Siemens 与 NVIDIA 在 2026 年公布的工业 AI 方向也强调：在数字孪生中分析、试验和验证改变，再把验证过的结果应用到物理工厂。当前项目只有 TF/RViz 的几何骨架，还没有 CAD/USD、物理模型、PLC/MES/SCADA 或双向状态同步，因此这是架构对接方向，不是已经实现的数字孪生。参考：[Siemens–NVIDIA 官方合作公告](https://press.siemens.com/global/en/pressrelease/siemens-and-nvidia-expand-partnership-build-industrial-ai-operating-system)。

## 8. 能力边界与下一步

今天已经具备：

- 可复现“节点和端点存活、数据却停止”的故障；
- 标准、可录制、可被聚合器消费的健康输出；
- 避免 Service/Action 使用陈旧传感器缓存的独立联锁；
- 故障、日志、画面解释、修复和回归测试的完整证据链。

尚未具备：

- `/diagnostics` 尚未接入 `diagnostic_aggregator` 或工业告警平台；
- 没有设备侧时间戳、Deadline/Liveliness 事件、冗余传感器或自动恢复策略；
- 没有真实多模态输入、学习模型、运动控制或功能安全认证；
- 后续第 4～6 天已补齐其余故障与自动证据流水线；跨天关系见[第 1～7 天总流程图](../flowcharts/week03-overall.md)。

因此第三天的准确成果是：系统开始知道“自己什么时候不该相信数据”，并能把这个判断留成可回放证据。这是具身智能从实验演示走向可运维工业系统的一层必要基础。
