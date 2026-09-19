# EmbodiedAgentLab（具身智能体实验室）

一个以项目驱动方式学习并构建“机器人大小脑”的长期工程：用 `ROS 2（机器人操作系统第二代）`、`RViz（机器人可视化工具）`、`Gazebo（物理仿真器）`、`MoveIt 2（机械臂运动规划框架）`、`ros2_control（机器人控制框架）`、视觉感知、`LLM Agent（大语言模型智能体）` 与机器人学习，完成可诊断、可恢复、可评测的机械臂系统。第 1.0 版采用仿真优先路线，不要求真实机器人硬件。

> 当前阶段：`v0.2` 三节点模拟系统、Trigger 服务、一键启动，以及 Python/C++ 发布订阅对照。

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
colcon build --packages-select embodied_comm embodied_comm_cpp \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash
ros2 launch embodied_comm three_nodes.launch.py
```

另一个终端加载相同环境和工作空间，等执行器显示最新读数后调用：

```bash
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

传感器持续发布 `/sensor_state`，执行器按请求检查缓存读数并发布 `/task_status`，监控器显示结果和传感器超时。默认读数有效范围为 0～100；`publish_rate` 范围为 0.1～100 Hz。无数据时服务返回失败。尚未检查数据新鲜度，停止传感器后旧缓存仍可能通过任务检查。

```bash
# 运行两个包的测试（先加载 install/setup.bash）
colcon test --packages-select embodied_comm embodied_comm_cpp
colcon test-result --verbose
```

[完整 v0.2 验收与复现记录](docs/labs/week02-stage6.md)包含阶段①～⑤证据、双语言对照、限制和版本信息。

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
│   └── roadmap.md                # 16 周学习与交付路线
├── scripts/                      # 自动化脚本
│   └── setup.sh                  # 本地环境安装脚本
├── src/embodied_agent_lab/       # Python（编程语言）源代码
│   ├── __init__.py               # 软件包入口
│   └── doctor.py                 # 环境诊断命令行工具
├── ros2_ws/src/                  # ROS 2 独立源码
│   ├── embodied_comm/            # Python 三节点、服务、Launch 与测试
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
