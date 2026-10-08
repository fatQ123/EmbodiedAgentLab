# EmbodiedAgentLab（具身智能体实验室）

一个以项目驱动方式学习并构建“机器人大小脑”的长期工程：用 **ROS 2（机器人操作系统第二代）**、**RViz（机器人可视化工具）**、Gazebo（物理仿真器）、MoveIt 2（机械臂运动规划框架）、ros2_control（机器人控制框架）、视觉感知、LLM Agent（大语言模型智能体）与机器人学习，完成可诊断、可恢复、可评测的机械臂系统。第 1.0 版采用仿真优先路线，不要求真实机器人硬件。

**当前阶段：v0.4 两关节机械臂与交互式 CLI 已实现，构建及无界面功能检查已完成，CLI 的 RViz / 滑块入口待人工验收。** v0.3 已通过干净终端发布验收，六类故障均可隔离复现、定位、录包和回归。Gazebo、运动控制、视觉与智能体能力属于后续版本计划。

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

通用 Python 工具使用项目环境；以下环境准备命令由用户按需执行：

```bash
# 根据配置创建 Conda（环境与包管理器）环境
conda env create -f environment.yml

# 激活项目环境
conda activate embodied-agent-lab

# 以可编辑方式安装项目；修改源码后无需重复安装
python -m pip install --editable .

# 运行环境诊断命令
embodiedlab doctor

# 运行已有自动化测试
python -m unittest discover -s tests
```

ROS 实验使用 Ubuntu 24.04、ROS 2 Jazzy、系统 Python 3.12、colcon 和 C++ 工具链。请在未激活 Conda 的 ROS 终端中构建与运行，避免混用 Python 与系统原生 ROS 库。ROS 依赖通过系统包管理器准备，不用 pip 安装 `rclpy`；各包的依赖声明见 `package.xml`。

## v0.2：三节点模拟系统

传感器持续发布 `/sensor_state`，执行器按请求检查缓存读数并发布 `/task_status`，监控器显示结果和传感器超时。支持 Python / C++ 发布订阅对照。默认读数有效范围为 0～100；`publish_rate` 范围为 0.1～100 Hz。无数据时服务返回失败，v0.3 增加数据新鲜度联锁后，旧缓存也不能通过任务检查。

主要系统依赖包括 `ros-jazzy-rclpy`、`ros-jazzy-rclcpp`、`ros-jazzy-std-msgs`、`ros-jazzy-std-srvs`、`ros-jazzy-launch-ros`、`ros-jazzy-ros2launch`、`ros-jazzy-ament-cmake-gtest`、`python3-pytest`、`libjsoncpp-dev`；截图实验另需 `ros-jazzy-rqt-graph` 和 Graphviz。

在仓库根目录打开 ROS 终端：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --packages-up-to embodied_comm embodied_comm_cpp \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
source install/local_setup.bash
ros2 launch embodied_comm three_nodes.launch.py
```

另一个终端加载相同环境和工作空间，等执行器显示最新读数后调用：

```bash
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

已有包测试入口（在 `ros2_ws` 中，先加载构建产物）：

```bash
colcon test --packages-select embodied_comm embodied_comm_cpp
colcon test-result --verbose
```

完整的 [v0.2 验收与复现记录](docs/labs/week02-stage6.md)包含阶段证据、双语言对照、限制和版本信息。

## v0.3：可取消任务、工位可视化与故障诊断

v0.3 在三节点系统上形成完整的工位实验：执行长任务、观察坐标与状态、注入故障、诊断恢复，并保存可回放的证据。

| 能力 | 实现与用途 |
|---|---|
| 可取消长任务 | `/execute_task_long` Action 模拟工件质检，反馈 `preparing → inspecting → validating → completed`；同一工位一次接受一个长任务，支持取消后继续处理下一件工件 |
| 工位坐标与 RViz | 发布 `world → base_link → camera_link → tool0` 坐标树，在末端前方显示绿色合成质检区域 |
| 健康诊断 | `/diagnostics` 区分等待、正常、数据陈旧、发布者丢失与 QoS 不匹配；执行器独立检查数据新鲜度 |
| 空间诊断 | `spatial_health_monitor` 区分完整 TF 链从未形成与动态 TF 停止刷新 |
| 六类故障 | QoS 不匹配、话题停止、TF 缺失/过期、Service 超时、Action 取消和节点崩溃；TF 分为两个场景，共七场实验 |
| 留证与回归 | 既有工具保存 MCAP rosbag、日志、ROS Graph、诊断快照、JSON 结果和中文故障记录 |

### 构建与启动

在 v0.2 依赖外，需要 ROS 接口生成、Action、诊断、TF、Marker、RViz 和 rosbag2 / MCAP 相关包。已配置 ROS apt 源的主机，可由用户在仓库根目录执行以下命令补齐声明依赖：

```bash
rosdep install --from-paths ros2_ws/src --ignore-src --rosdistro jazzy -y
```

在仓库根目录打开 ROS 终端，构建并启动集成工位。沿用现有 launch 文件名：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --packages-up-to embodied_comm embodied_comm_cpp \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
source install/local_setup.bash
ros2 launch embodied_comm week03_day5.launch.py
```

默认打开 RViz，显示坐标树和绿色质检区域；只观察终端时添加 `use_rviz:=false`。另一个已加载相同环境的终端可执行：

```bash
# 正常质检
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-001 --duration 5

# 模拟安全门打开：首次收到达到或超过 40% 的反馈时请求取消
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-002 --duration 10 --cancel-at 40

# 取消后处理下一件工件，检查资源是否释放
ros2 run embodied_comm inspection_demo \
  --task-name inspect_workpiece_WP-003 --duration 2

# 观察完整坐标链与健康诊断；观察命令按 Ctrl-C 结束
ros2 run tf2_ros tf2_echo world tool0
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
```

Action 客户端退出码：成功为 `0`，任务失败为 `2`，预期取消为 `3`，目标拒绝为 `4`，接口不可用为 `5`。反馈阈值不保证精确停在 40%；取消验证任务协议和资源释放，不替代硬件急停或安全联锁。

### 故障复现与恢复

先停止正常工位，再使用同一入口选择故障参数；一次只运行一种场景，便于隔离根因。

| 场景 | 添加到 `week03_day5.launch.py` 后的参数或客户端操作 |
|---|---|
| QoS 不匹配 | `publisher_reliability:=best_effort timeout_sec:=1.5` |
| 话题停止 | `fault_stop_after_sec:=6.0 timeout_sec:=1.5` |
| TF 缺失 | `tf_fault_mode:=missing tf_timeout_sec:=1.0` |
| TF 过期 | `tf_fault_mode:=stale tf_fault_after_sec:=6.0 tf_timeout_sec:=1.0` |
| Service 超时 | `fault_service_delay_sec:=3.0 timeout_sec:=5.0`，随后运行 `ros2 run embodied_comm service_timeout_demo --response-timeout 1.0` |
| Action 取消 | 正常工位中运行带 `--cancel-at 40` 的质检客户端，再运行下一件工件 |
| 节点崩溃 | `fault_sensor_crash_after_sec:=6.0 timeout_sec:=1.5` |

话题停止时节点与 DDS Publisher 仍在线；进程崩溃后诊断进入 `publisher_lost`。QoS 不匹配和陈旧传感器数据会阻止执行器接收有效任务。Service 客户端超时不会自动取消服务器回调。

绿色方块是合成检查区域，不是真实视觉检测结果。TF 故障由空间诊断报警，目前尚未接入 Action 门禁；传感器故障也不一定改变 RViz 画面，应结合诊断、端点、服务结果和 rosbag 判断。

### 证据采集与发布复现

已有 `week03_day6_evidence` 工具把六类故障展开为七个独立 ROS Domain 场景，单场失败后继续采集，最终退出码可供 CI 使用。在已加载工作空间的 ROS 终端运行：

```bash
# 七个场景 + ROS 包回归 + 仓库回归
ros2 run embodied_comm week03_day6_evidence

# 只采集一个场景
ros2 run embodied_comm week03_day6_evidence \
  --scenario tf_missing --skip-regression
```

结果默认写入被 Git 忽略的 `artifacts/week03-day6/run-时间戳/`。`summary.json` 供程序读取，`故障记录.md` 供操作员阅读，大型 MCAP 不提交到仓库。

v0.3 历史发布验收结果：三个 ROS 包干净构建通过，179 项独立测试全部通过，七场 MCAP 共记录 7,426 条消息，Python / C++ 四组通信组合全部通过。正常质检期间的快速查询约 3.2 毫秒，取消进入终态约 0.202 秒；这些是当轮实测值，不是硬实时保证。完整结果见[发布证据索引](docs/labs/evidence/week03-day7/README.md)。

在仓库根目录，使用既有脚本复现固定发布标签；`OUTPUT` 必须是尚不存在的新目录：

```bash
# 例如将 OUTPUT 替换为 /tmp/embodiedagentlab-v0.3-replay
bash scripts/verify_ros2_release.sh OUTPUT refs/tags/v0.3
```

发布代码以 annotated tag `v0.3` 为准，显式使用 `refs/tags/v0.3` 避免同名分支歧义。流程、能力边界与历史记录见 [v0.3 发布说明](docs/labs/week03-day7-release.md)、[故障采集说明](docs/labs/week03-day6-automated-evidence.md)和[集成总流程图](docs/flowcharts/week03-overall.md)；详细学习过程保留在[流程图目录](docs/flowcharts/README.md)。

## v0.4：两关节机械臂与交互式 CLI

v0.4 从工位通信进入机械臂运动学可视化：用 Xacro / URDF 描述两关节机械臂，C++ 节点发布合成关节状态，`robot_state_publisher` 生成 TF，RViz 展示姿态。常驻终端 CLI 提供中文编号菜单和 `/` 命令，操作完成后返回提示符。

| 能力 | 实现与用途 |
|---|---|
| 两关节模型 | `joint1、joint2` 固定顺序，包含连杆、关节限位、惯性与 RViz 配置 |
| 固定 / 正弦演示 | C++ 发布 `/joint_states`；支持固定角度或按中心、振幅和频率摆动 |
| 运行时调姿 | 通过原子参数服务整体更新两个关节，非法值被拒绝且保留上一合法设置 |
| 关节滑块 | 用户选择后启动 GUI 状态源，与 C++ 状态源二选一 |
| 状态观察 | CLI 显示发布者、关节状态与对应时间戳的末端 TF |
| 演示管理 | 启动、切换、停止、查看日志和退出清理；发现已有机械臂状态源时拒绝启动 |

### 构建与启动

在已有 Jazzy 和工具链基础上，需要 Xacro、URDF、`robot_state_publisher`、`sensor_msgs`、TF、`joint_state_publisher_gui` 与 RViz 等包，完整声明见两个机械臂包的 `package.xml`。CLI 使用 Python 标准库及现有 ROS 依赖，无需额外安装 Python CLI 框架，也无需激活 Conda。

在仓库根目录打开 ROS 终端，统一构建当前五个包：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --base-paths src --executor sequential \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 -DBUILD_TESTING=OFF
cd ..

# 启动中文交互菜单
bash scripts/arm_cli.sh
```

已有当前构建产物时，直接运行脚本即可。脚本仅在自身进程环境中加载 Jazzy 和 **`ros2_ws/install`**；该目录是项目编译产物，不是系统依赖安装位置。构建中间文件、安装产物和构建日志分别统一放在 `ros2_ws/build`、`ros2_ws/install`、`ros2_ws/log`，均不提交 Git。

```bash
# 显式选择独立 Domain，或使用另一份构建
bash scripts/arm_cli.sh --domain-id 222 --install-dir ros2_ws/install
bash scripts/arm_cli.sh --help
```

Domain 按“显式参数 → 已有 `ROS_DOMAIN_ID` → 222”选择。启动页显示安装目录、Domain、当前模式与日志位置；缺少环境或构建产物时给出手动处理提示。

### 菜单与命令

| 编号 | 命令 | 功能 |
|---|---|---|
| 1 | `/start static` | 固定姿态演示，默认两关节零位 |
| 2 | `/start sine` | 设置运动中心、振幅、频率及发布频率 |
| 3 | `/start gui` | 使用关节滑块调姿 |
| 4 | `/pose 0.5 -0.3` | 调整两个关节；不填参数时逐项询问 |
| 5 | `/zero` | 固定模式归零；正弦模式中心归零 |
| 6 | `/status` | 查看关节状态、发布者与对应 TF |
| 7 | `/logs` | 查看最近 40 行日志及完整日志路径 |
| 8 | `/stop` | 停止本次演示，保留菜单 |
| 0 | `/quit` | 清理本次进程并退出 |
| — | `/help` | 查看帮助；配置过程中用 `/cancel` 取消 |

角度单位为 rad，速度单位为 rad/s。启动演示时会询问是否打开 RViz，默认否；输入 `y` 后启用。GUI 模式使用滑块，禁用 CLI 调姿与归零。正弦模式下 `/pose` 和 `/zero` 改变运动中心，机械臂继续摆动。

固定调姿直接更新状态，不提供平滑运动轨迹。这一版使用合成状态，不是传感器反馈或物理控制；Gazebo、控制器、规划与模型推理尚未引入。工位与机械臂使用部分相同坐标名称，应分开运行或使用不同 Domain。

每次 CLI 会话的日志位于 `artifacts/week04/cli/`。模式切换先停止旧演示；`/quit`、EOF 和 Ctrl-C 清理本次启动的进程。原有 launch 与调姿客户端仍可直接使用，具体命令、参数、检查结果和已知限制见 [v0.4 集成说明](docs/labs/week04-integration.md)，模型尺寸、关节方向和运动学见[两关节模型说明](docs/labs/week04-stage1-description.md)。

当前已完成构建与无界面指令检查；新版 CLI 的 RViz / 滑块实际画面仍待人工验收，不将状态或 TF 检查视为图形验收通过。

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

`echo` 用于输出文本或变量值；$? 是上一条命令的退出码，因此不要在诊断与该命令之间执行其他命令。

| 退出码 | 含义 |
|---|---|
| 0 | 检查没有失败；可以包含可选能力缺失的警告。帮助命令也返回 0。 |
| 1 | 至少一个检查结果为“失败”。 |
| 2 | 命令用法错误，例如缺少子命令、未知子命令或未知选项。 |

JSON 顶层固定包含 schema_version（当前为整数 1）、checks（检查列表）、summary（正常、警告、失败的数量）和 exit_code（诊断退出码）。每个检查包含 check_id（稳定标识）、name（中文名称）、status（正常/警告/失败）、detail（检查证据）和 suggestion（处理建议，可为空）。JSON 模式不混入标题或日志；参数用法错误写入标准错误流，不生成 JSON 报告。

### 检查范围与边界

| 检查项 | 实际验证内容 | 异常处理 |
|---|---|---|
| 操作系统、Python | 报告系统、解释器路径及版本；最低 Python 版本为 3.10 | Python 不满足最低要求为失败；Jazzy 实验另外要求 Python 3.12 |
| Git | 实际运行 git --version，记录命令路径和版本输出 | 必要开发工具，缺失、超时或执行失败返回失败 |
| Conda | 当前环境变量 | 未激活仅警告；本工具也可在普通 Python 虚拟环境运行 |
| ROS 发行版 | ROS_DISTRO 是否为本实验的 Jazzy | 未加载或发行版不符为警告，不冒充安装检测 |
| ROS 命令行 | 实际运行 ros2 --help | 异常为警告；不创建节点，不依赖 ROS daemon |
| ROS Python | 用启动本工具的解释器导入 rclpy、std_msgs.msg.String，并加载原生消息类型支持 | 异常为警告；不能代替节点构建和通信验证 |
| NVIDIA 显卡、驱动 | 用 nvidia-smi 查询 GPU 名称和驱动版本 | 缺失或异常仅警告；不检测其他品牌 GPU |
| CUDA 工具链 | 用 nvcc --version 查看当前 PATH 中的 Toolkit 编译器 | 缺失仅警告；不等同于没有 CUDA 运行时，也不验证 PyTorch GPU 运算 |
| 串口 | 枚举 /dev/ttyUSB*、/dev/ttyACM* 并检查当前用户读写权限 | 缺失、权限不足仅警告；不打开设备，不验证真实通信 |
| 网络 | 向 https://pypi.org/simple/ 发出 HTTPS HEAD 请求，遵循系统代理设置 | 失败只说明该目标检查未通过，不代表整个网络断开；可用 --skip-network 跳过 |

`nvidia-smi` 的驱动版本、它可能显示的 CUDA 兼容版本，以及 nvcc 报告的已安装 Toolkit 版本是不同概念；本工具分别报告 GPU/驱动和 Toolkit，不推断框架运行时是否可用。

每个外部命令的执行等待上限为 5 秒；网络请求还设置了 3 秒连接/读取超时，并在子进程中执行，使 DNS 等阻塞也受到外层 5 秒限制。命令缺失、权限错误、非零退出、超时或空输出都会形成单项结果，后续检查继续运行。所有检查均只读，不安装依赖或修改系统。网络跳过状态记为警告，明确区分“未验证”和“验证成功”。

自动化测试模拟命令、设备和网络结果，不要求 ROS、NVIDIA 显卡、串口或外网。覆盖正常、缺失、权限不足、非零退出、超时、空输出、离线选项、JSON 协议与实际进程退出码。

以后配置发生变化时，执行以下命令同步环境：

```bash
# 更新已有环境，并移除配置文件中不再需要的依赖
conda env update --name embodied-agent-lab --file environment.yml --prune
```

也可以由用户执行 `./scripts/setup.sh`（自动创建或更新 Conda 环境并安装项目的脚本） 完成环境准备。

## 当前目录

```text
EmbodiedAgentLab/                    # 具身智能体实验室仓库
├── docs/                            # 设计与学习文档
│   ├── architecture.md              # 系统架构说明
│   ├── flowcharts/                  # 实现 / 调试流程图与集成总图
│   ├── labs/                        # 各版本实验、运行说明与精简证据
│   └── roadmap.md                   # 16 周学习与交付路线
├── scripts/                         # 运行入口与已有辅助工具
│   ├── setup.sh                     # 本地环境安装脚本，由用户执行
│   └── arm_cli.sh                   # v0.4 机械臂交互式 CLI 入口
├── src/embodied_agent_lab/           # Python 用户工具
│   ├── __init__.py                  # 软件包入口与版本
│   ├── doctor.py                    # 环境诊断命令行工具
│   └── arm_cli.py                   # 机械臂菜单、进程管理与状态观察
├── ros2_ws/                         # 唯一 ROS 2 工作空间
│   ├── src/
│   │   ├── embodied_interfaces/     # ExecuteTask Action 接口生成
│   │   ├── embodied_comm/           # Python 工位、Action、诊断与故障采集
│   │   ├── embodied_comm_cpp/       # C++ 发布订阅对照与 GoogleTest
│   │   ├── embodied_arm_description/ # 两关节模型、RViz 配置与模型测试
│   │   └── embodied_arm_cpp/        # C++ 合成状态、统一 launch 与调姿入口
│   ├── build/                      # 编译中间文件，Git 忽略
│   ├── install/                    # 编译后的 ROS 包，CLI 默认加载
│   └── log/                        # colcon 构建日志，Git 忽略
├── tests/                           # 已有 Python 测试
├── artifacts/                       # 运行日志、录包与截图，Git 忽略
├── LICENSE                          # MIT（宽松开源许可）文本
├── environment.yml                  # Conda 环境配置
└── pyproject.toml                   # Python 项目配置，当前版本 0.4.0
```

仓库会随真实功能逐周生长，不预先创建没有代码的目录。源码统一维护在项目源目录中，构建产物与实验日志分开保存。

## 路线与验收

完整计划见 [16 周路线](docs/roadmap.md)，无硬件情况下的逐周工具与验收见[仿真与机器人可视化路线](docs/simulation-first-track.md)。开源项目的通用学习方法见[开源学习指南](docs/open-source-study.md)，第一次完整实战见 [ROS 2 官方示例实验](docs/labs/week02-ros2-examples.md)。三节点系统的开发前检查与文件计划见[实施清单](docs/labs/week02-three-node-system.md)，系统边界与演进方式见[架构说明](docs/architecture.md)。

| 版本 | 使用说明与验收记录 |
|---|---|
| v0.2：三节点通信 | [通信系统发布记录](docs/labs/week02-stage6.md) |
| v0.3：任务与诊断 | [集成发布记录](docs/labs/week03-day7-release.md)、[总流程图](docs/flowcharts/week03-overall.md) |
| v0.4：机械臂与 CLI | [集成说明与提交清单](docs/labs/week04-integration.md)、[模型说明](docs/labs/week04-stage1-description.md) |

## 工作方式

每个功能遵循 Issue（任务单）→ Branch（分支）→ Commit（提交）→ Pull Request（合并请求）→ Review（审查）→ Merge（合并）。提交信息采用“英文类型 + 中文说明”，例如：

```text
feat: 增加 ROS 2 心跳监控节点
test: 增加规划失败恢复测试
docs: 记录陈旧 TF 坐标变换故障
```

Git 写操作、依赖安装和图形验收由用户手动执行；助手在获准范围内完成代码、文档、构建及必要的无界面检查。

## 许可证

本项目使用 [MIT License（MIT 宽松开源许可证）](LICENSE)。
