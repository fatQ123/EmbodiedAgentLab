# EmbodiedAgentLab（具身智能体实验室）

一个以项目驱动方式学习并构建“机器人大小脑”的长期工程：用 `ROS 2（机器人操作系统第二代）`、`RViz（机器人可视化工具）`、`Gazebo（物理仿真器）`、`MoveIt 2（机械臂运动规划框架）`、`ros2_control（机器人控制框架）`、视觉感知、`LLM Agent（大语言模型智能体）` 与机器人学习，完成可诊断、可恢复、可评测的机械臂系统。第 1.0 版采用仿真优先路线，不要求真实机器人硬件。

> 当前阶段：第三周功能已实现，正在完成 `v0.3` 干净终端发布验收。第 3 周要求的六类故障均可隔离复现、定位、录包和回归。

## 项目目标

最终演示不是“机械臂偶尔成功一次”，而是一个可复现的闭环：

```text
自然语言任务
  → 智能体规划
  → 技能库调用
  → ROS 2 执行
  → 结果验证
  → 失败诊断与恢复
  → 自动评测与报告
```

## 当前可运行内容

```bash
# 根据配置创建 Conda（环境与包管理器）环境
conda env create -f environment.yml

# 激活项目环境
conda activate embodied-agent-lab

# 以可编辑方式安装项目；修改源码后无需重复安装
python -m pip install --editable .

# 运行环境诊断命令
embodiedlab doctor

# 运行自动化测试
python -m unittest discover -s tests
```

## v0.2：三节点模拟系统

需要 Ubuntu 24.04、ROS 2 Jazzy、colcon 和 C++ 工具链。系统依赖包括 `ros-jazzy-rclpy`、`ros-jazzy-rclcpp`、`ros-jazzy-std-msgs`、`ros-jazzy-std-srvs`、`ros-jazzy-launch-ros`、`ros-jazzy-ros2launch`、`ros-jazzy-ament-cmake-gtest`、`python3-pytest`、`libjsoncpp-dev`；截图实验另需 `ros-jazzy-rqt-graph` 和 Graphviz。ROS 依赖通过系统包管理器准备，不用 pip 安装 rclpy。

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --packages-up-to embodied_comm embodied_comm_cpp \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash
ros2 launch embodied_comm three_nodes.launch.py
```

另一个终端加载相同环境和工作空间，等执行器显示最新读数后调用：

```bash
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

传感器持续发布 `/sensor_state`，执行器按请求检查缓存读数并发布 `/task_status`，监控器显示结果和传感器超时。默认读数有效范围为 0～100；`publish_rate` 范围为 0.1～100 Hz。无数据时服务返回失败。第 3 周第 3 天已在此基础上增加数据新鲜度联锁，旧缓存不再能够通过任务检查。

```bash
# 运行两个包的测试（先加载 install/setup.bash）
colcon test --packages-select embodied_comm embodied_comm_cpp
colcon test-result --verbose
```

[完整 v0.2 验收与复现记录](docs/labs/week02-stage6.md)包含阶段①～⑤证据、双语言对照、限制和版本信息。

## v0.3 第 1 天：可取消的工业长任务

第三周在上述依赖外还需要 `ros-jazzy-rosidl-default-generators`、`ros-jazzy-rosidl-default-runtime`、`ros-jazzy-action-msgs`、`ros-jazzy-diagnostic-msgs`、`ros-jazzy-tf2-ros`、`ros-jazzy-tf2-ros-py`、`ros-jazzy-tf2-tools`、`ros-jazzy-visualization-msgs`、`ros-jazzy-rviz2`、`ros-jazzy-ros2bag`、`ros-jazzy-rosbag2-transport`、`ros-jazzy-rosbag2-storage-mcap`。使用系统 Python 3.12 的 ROS 终端，避免 Conda 的 Python 与系统原生 ROS 库混用；所有构建命令可追加 `--cmake-args -DPython3_EXECUTABLE=/usr/bin/python3`。已配置 ROS apt 源的主机可用 `rosdep install --from-paths ros2_ws/src --ignore-src --rosdistro jazzy -y` 补齐声明依赖。

`/execute_task` 继续承担立即返回的传感器检查；新增的 `/execute_task_long` Action 模拟生产线工件质检，持续反馈 `preparing → inspecting → validating → completed`，并支持任务取消。同一工位一次只接受一个长任务。

构建并启动三节点：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
ros2 launch embodied_comm three_nodes.launch.py
```

在另一个已加载相同环境的终端运行正常质检：

```bash
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-001 \
  --duration 5
```

模拟安全门打开，收到首次达到或超过 40% 阈值的反馈后请求取消任务：

```bash
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-002 \
  --duration 10 \
  --cancel-at 40
```

取消属于预期业务结果，客户端以退出码 `3` 标识；成功、任务失败、目标拒绝和接口不可用分别使用 `0`、`2`、`4`、`5`。反馈阈值不保证精确停在 40%，当前取消验证任务协议和资源释放，不替代硬件急停或安全联锁。完整的工业场景解释、并发规则、复现步骤和能力边界见[第 3 周第 1 天记录](docs/labs/week03-day1-action.md)。

## v0.3 第 2 天：正常坐标树与 RViz 工位画面

新的 `workcell_visualizer` 节点发布 `world → base_link → camera_link → tool0` 坐标树，并在 `tool0` 前方显示一个绿色质检区域。启动命令会同时运行第 2 周三节点、第 1 天 Action、坐标发布器和 RViz：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
ros2 launch embodied_comm week03_day2.launch.py
```

新终端加载相同环境后，可验证完整坐标链并运行一件工件的长任务：

```bash
ros2 run tf2_ros tf2_echo world tool0
ros2 topic echo /inspection_target_marker visualization_msgs/msg/Marker \
  --qos-durability transient_local --qos-reliability reliable --once
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-DAY2 --duration 5
```

绿色方块目前是合成的检查区域，不是真实视觉检测结果；Action 与 TF 已能在同一工位场景中运行，但 Action 尚未依赖 TF 做任务判定。坐标含义、RViz 读图方式、工业推演、验证命令和实测证据见[第 3 周第 2 天记录](docs/labs/week03-day2-tf-rviz.md)。

## v0.3 第 3 天：健康诊断、话题停止与 rosbag 留证

`status_monitor` 现在把传感器流发布为标准 `/diagnostics`：启动时为 `waiting/WARN`，收到合法数据后为 `healthy/OK`，超过阈值没有新数据时为 `stale/ERROR`，恢复数据后重新回到 `healthy/OK`。执行器独立检查数据接收时间，避免监控节点或诊断话题本身成为安全联锁的单点依赖。

下面的命令在 6 秒后停止 `/sensor_state` 数据，但故意保留节点和 DDS Publisher，用于区分“设备进程崩溃”和“设备还在线但数据卡死”：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
ros2 launch embodied_comm week03_day3.launch.py \
  fault_stop_after_sec:=6.0 timeout_sec:=1.5
```

在新终端观察诊断、端点和陈旧数据联锁：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws && source install/setup.bash
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
ros2 topic info /sensor_state --verbose
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

RViz 中的 TF 树和绿色质检区域会保持正常，因为本次只破坏传感器数据流；故障证据应从 `/diagnostics`、消息序号、服务结果和 rosbag 判断。复现、恢复、录包回放、七段式故障记录、工业推演与具身智能/多模态前沿对照见[第 3 周第 3 天记录](docs/labs/week03-day3-health-topic-stop.md)。

## v0.3 第 4 天：QoS、话题停止与 TF 缺失/过期

统一入口 `week03_day4.launch.py` 在前三天系统上增加独立的 `spatial_health_monitor`。传感器诊断能区分 DDS QoS 不兼容与运行期断流；空间诊断能区分完整坐标链从未形成与动态 TF 时间戳停止更新。默认启动仍是无故障基线：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash
ros2 launch embodied_comm week03_day4.launch.py
```

一次只运行一种故障，便于隔离根因：

```bash
# Publisher 存在，但 BEST_EFFORT 无法满足业务订阅端的 RELIABLE 请求
ros2 launch embodied_comm week03_day4.launch.py \
  publisher_reliability:=best_effort timeout_sec:=1.5

# 节点与 Publisher 在线，但 6 秒后停止产生新数据
ros2 launch embodied_comm week03_day4.launch.py \
  fault_stop_after_sec:=6.0 timeout_sec:=1.5

# 中间 TF 边从未发布
ros2 launch embodied_comm week03_day4.launch.py \
  tf_fault_mode:=missing tf_timeout_sec:=1.0

# TF 先正常，6 秒后停止刷新并逐渐过期
ros2 launch embodied_comm week03_day4.launch.py \
  tf_fault_mode:=stale tf_fault_after_sec:=6.0 tf_timeout_sec:=1.0
```

另开终端观察 `/diagnostics`、端点和完整 TF 链：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws && source install/setup.bash
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
ros2 topic info /sensor_state --verbose
ros2 run tf2_ros tf2_echo world tool0
```

QoS 不匹配和话题停止会被执行器的传感器新鲜度门禁阻止；TF 缺失/过期目前由独立空间诊断报警，尚未接入 Action 门禁。四类故障的七段式中文记录、RViz 画面差异、修复与回归命令见[第 3 周第 4 天记录](docs/labs/week03-day4-qos-tf-faults.md)。

## v0.3 第 5 天：Service 超时、Action 取消与节点崩溃

第 5 天统一入口继续包含前四天系统，并增加服务器延迟和传感器进程崩溃参数。Action 取消使用标准 Cancel 协议和现有 `inspection_demo` 客户端：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to embodied_comm embodied_comm_cpp
source install/setup.bash

# 正常基线
ros2 launch embodied_comm week03_day5.launch.py

# /execute_task 延迟 3 秒；客户端可以使用更短截止时间
ros2 launch embodied_comm week03_day5.launch.py \
  fault_service_delay_sec:=3.0 timeout_sec:=5.0

# 传感器节点在 6 秒后抛出未捕获异常并以退出码 1 结束
ros2 launch embodied_comm week03_day5.launch.py \
  fault_sensor_crash_after_sec:=6.0 timeout_sec:=1.5
```

Service 超时客户端：

```bash
ros2 run embodied_comm service_timeout_demo --response-timeout 1.0
```

Action 在反馈达到 40% 阈值后请求取消，并验证下一件工件能够恢复：

```bash
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-DAY5-CANCEL \
  --duration 10 --cancel-at 40

ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-DAY5-RECOVER \
  --duration 2
```

Service 客户端超时不会自动取消服务器回调；传感器进程崩溃后，其他节点继续运行，诊断进入 `publisher_lost`，执行器会因缓存过期拒绝新任务。三类故障的七段式记录、工业推演、能力边界和验收命令见[第 3 周第 5 天记录](docs/labs/week03-day5-service-action-crash.md)。

## v0.3 第 6 天：自动证据与中文故障报告

`week03_day6_evidence` 把六类故障展开为七个独立 ROS Domain 场景，自动保存 MCAP rosbag、Launch/客户端日志、ROS Graph 与诊断快照、单场 JSON、完整回归结果和七段式中文报告。单场失败不会阻断后续采集，最终退出码可直接供 CI 使用。

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to \
  embodied_comm embodied_comm_cpp \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash

# 七个场景 + ROS 包回归 + 仓库回归
ros2 run embodied_comm week03_day6_evidence

# 开发时只采集一个场景
ros2 run embodied_comm week03_day6_evidence \
  --scenario tf_missing --skip-regression
```

结果默认写入被 Git 忽略的 `artifacts/week03-day6/run-时间戳/`，避免把大型 MCAP 提交到仓库。每次运行的 `summary.json` 供程序读取，`故障记录.md` 供操作员阅读。设计、目录、回放方式、六类中文记录和自动化边界见[第 3 周第 6 天记录](docs/labs/week03-day6-automated-evidence.md)。

## v0.3 第 7 天：干净终端完整验收

当前候选仍在发布验收中，`v0.3` 尚未发布。验收脚本固定一个已提交 ref，将源码导出到新目录，再以 `env -i` 和无终端配置的 shell 构建三个 ROS 包，运行正常质检、取消恢复、七场故障采集、全部测试及 Python/C++ 四组通信组合。

在仓库根目录运行；输出目录必须尚不存在。当前候选可省略 ref 使用 `HEAD`；发布标签创建后，完整复现入口为：

```bash
# OUTPUT 为新的验收目录，例如 /tmp/embodiedagentlab-v0.3-replay
bash scripts/verify_ros2_release.sh OUTPUT refs/tags/v0.3
```

发布代码以 annotated tag `v0.3` 为准。同名 branch 不代表发布标签；命令中使用 `refs/tags/v0.3`，避免 Git 将 `v0.3` 解析成同名分支。脚本保存实际源码 SHA、安装前缀、演示与测试结果、MCAP 和中文故障记录。验收条件、修复记录与工业交付推演见[第 3 周第 7 天记录](docs/labs/week03-day7-release.md)。

## 第 3 周实现与调试流程图

当前已为第 1～7 天分别绘制实现/调试流程图，并维护一张随每日进度扩展的总图：

- [第 1 天：长任务 Action、取消与恢复](docs/flowcharts/week03-day01-action.md)
- [第 2 天：TF 坐标树与 RViz 工位](docs/flowcharts/week03-day02-tf-rviz.md)
- [第 3 天：健康诊断、话题停止与 rosbag](docs/flowcharts/week03-day03-health-topic-stop.md)
- [第 4 天：QoS、话题停止与 TF 缺失/过期](docs/flowcharts/week03-day04-qos-tf-faults.md)
- [第 5 天：Service 超时、Action 取消与节点崩溃](docs/flowcharts/week03-day05-service-action-crash.md)
- [第 6 天：自动 rosbag、日志与回归证据](docs/flowcharts/week03-day06-automated-evidence.md)
- [第 7 天：干净终端演练、回归与发布](docs/flowcharts/week03-day07-release.md)
- [第 1～7 天集成总流程图](docs/flowcharts/week03-overall.md)

以后每完成一天，就新增当天流程图并把已实现能力接入总图；入口和读图约定见[流程图目录](docs/flowcharts/README.md)。

## 诊断命令与输出协议

```bash
# 查看可用子命令，不执行环境检查
embodiedlab --help

# 查看诊断子命令的选项
embodiedlab doctor --help

# 显示供人阅读的检查结果、处理建议和汇总
embodiedlab doctor

# 仅向标准输出写入 JSON 报告，便于其他程序解析
embodiedlab doctor --json

# 离线运行诊断，不访问外部网络；报告明确记录网络检查已跳过
embodiedlab doctor --skip-network

# 在诊断命令结束后立即查看它的退出码
echo "$?"
```

`echo` 用于输出文本或变量值；`$?` 是上一条命令的退出码，因此不要在诊断与该命令之间执行其他命令。

| 退出码 | 含义 |
|---|---|
| `0` | 检查没有失败；可以包含可选能力缺失的警告。帮助命令也返回 0。 |
| `1` | 至少一个检查结果为“失败”。 |
| `2` | 命令用法错误，例如缺少子命令、未知子命令或未知选项。 |

JSON 顶层固定包含 `schema_version`（当前为整数 1）、`checks`（检查列表）、`summary`（正常、警告、失败的数量）和 `exit_code`（诊断退出码）。每个检查包含 `check_id`（稳定标识）、`name`（中文名称）、`status`（正常/警告/失败）、`detail`（检查证据）和 `suggestion`（处理建议，可为空）。JSON 模式不混入标题或日志；参数用法错误写入标准错误流，不生成 JSON 报告。

### 检查范围与边界

| 检查项 | 实际验证内容 | 异常处理 |
|---|---|---|
| 操作系统、Python | 报告系统、解释器路径及版本；最低 Python 版本为 3.10 | Python 不满足最低要求为失败；Jazzy 实验另外要求 Python 3.12 |
| Git | 实际运行 `git --version`，记录命令路径和版本输出 | 必要开发工具，缺失、超时或执行失败返回失败 |
| Conda | 当前环境变量 | 未激活仅警告；本工具也可在普通 Python 虚拟环境运行 |
| ROS 发行版 | `ROS_DISTRO` 是否为本实验的 Jazzy | 未加载或发行版不符为警告，不冒充安装检测 |
| ROS 命令行 | 实际运行 `ros2 --help` | 异常为警告；不创建节点，不依赖 ROS daemon |
| ROS Python | 用启动本工具的解释器导入 `rclpy`、`std_msgs.msg.String`，并加载原生消息类型支持 | 异常为警告；不能代替节点构建和通信验证 |
| NVIDIA 显卡、驱动 | 用 `nvidia-smi` 查询 GPU 名称和驱动版本 | 缺失或异常仅警告；不检测其他品牌 GPU |
| CUDA 工具链 | 用 `nvcc --version` 查看当前 PATH 中的 Toolkit 编译器 | 缺失仅警告；不等同于没有 CUDA 运行时，也不验证 PyTorch GPU 运算 |
| 串口 | 枚举 `/dev/ttyUSB*`、`/dev/ttyACM*` 并检查当前用户读写权限 | 缺失、权限不足仅警告；不打开设备，不验证真实通信 |
| 网络 | 向 `https://pypi.org/simple/` 发出 HTTPS HEAD 请求，遵循系统代理设置 | 失败只说明该目标检查未通过，不代表整个网络断开；可用 `--skip-network` 跳过 |

`nvidia-smi` 的驱动版本、它可能显示的 CUDA 兼容版本，以及 `nvcc` 报告的已安装 Toolkit 版本是不同概念；本工具分别报告 GPU/驱动和 Toolkit，不推断框架运行时是否可用。

每个外部命令的执行等待上限为 5 秒；网络请求还设置了 3 秒连接/读取超时，并在子进程中执行，使 DNS 等阻塞也受到外层 5 秒限制。命令缺失、权限错误、非零退出、超时或空输出都会形成单项结果，后续检查继续运行。所有检查均只读，不安装依赖或修改系统。网络跳过状态记为警告，明确区分“未验证”和“验证成功”。

自动化测试模拟命令、设备和网络结果，不要求 ROS、NVIDIA 显卡、串口或外网。覆盖正常、缺失、权限不足、非零退出、超时、空输出、离线选项、JSON 协议与实际进程退出码。

以后配置发生变化时，执行以下命令同步环境：

```bash
# 更新已有环境，并移除配置文件中不再需要的依赖
conda env update --name embodied-agent-lab --file environment.yml --prune
```

也可以执行 `./scripts/setup.sh（自动创建或更新 Conda 环境并安装项目的脚本）` 完成环境准备。

## 当前目录

```text
EmbodiedAgentLab/                 # 具身智能体实验室仓库
├── docs/                         # 设计与学习文档
│   ├── architecture.md           # 系统架构说明
│   ├── flowcharts/               # 每日实现/调试流程图与累计总图
│   └── roadmap.md                # 16 周学习与交付路线
├── scripts/                      # 自动化脚本
│   └── setup.sh                  # 本地环境安装脚本
├── src/embodied_agent_lab/       # Python（编程语言）源代码
│   ├── __init__.py               # 软件包入口
│   └── doctor.py                 # 环境诊断命令行工具
├── ros2_ws/src/                  # ROS 2 独立源码
│   ├── embodied_interfaces/      # ExecuteTask Action 接口生成
│   ├── embodied_comm/            # Python 工位、Action、诊断、故障采集与测试
│   └── embodied_comm_cpp/        # C++ 发布订阅对照与 GoogleTest
├── tests/                        # 环境诊断自动化测试
├── LICENSE                       # MIT（宽松开源许可）文本
├── environment.yml               # Conda（环境与包管理器）环境配置
└── pyproject.toml                # Python（编程语言）项目配置
```

仓库会随真实功能逐周生长，不预先创建没有代码的目录。

## 路线与验收

完整计划见 [docs/roadmap.md](docs/roadmap.md)，无硬件情况下的逐周工具与验收见 [仿真与机器人可视化路线](docs/simulation-first-track.md)。开源项目的通用学习方法见 [docs/open-source-study.md](docs/open-source-study.md)，第一次完整实战见 [第 2 周 ROS 2 官方示例实验](docs/labs/week02-ros2-examples.md)。主项目第 2 周的开发前检查与文件计划见 [三节点系统实施清单](docs/labs/week02-three-node-system.md)。系统边界与演进方式见 [docs/architecture.md](docs/architecture.md)。

## 工作方式

每个功能遵循 `Issue（任务单）→ Branch（分支）→ Commit（提交）→ Pull Request（合并请求）→ Review（审查）→ Merge（合并）`。提交信息采用“英文类型 + 中文说明”，例如：

```text
feat: 增加 ROS 2 心跳监控节点
test: 增加规划失败恢复测试
docs: 记录陈旧 TF 坐标变换故障
```

## 许可证

本项目使用 `MIT License（MIT 宽松开源许可证）`。
