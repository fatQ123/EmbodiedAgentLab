# EmbodiedAgentLab（具身智能体实验室）

一个以项目驱动方式学习并构建“机器人大小脑”的长期工程：用 `ROS 2（机器人操作系统第二代）`、`RViz（机器人可视化工具）`、`Gazebo（物理仿真器）`、`MoveIt 2（机械臂运动规划框架）`、`ros2_control（机器人控制框架）`、视觉感知、`LLM Agent（大语言模型智能体）` 与机器人学习，完成可诊断、可恢复、可评测的机械臂系统。第 1.0 版采用仿真优先路线，不要求真实机器人硬件。

> 当前阶段：`v0.1（第 0.1 版）` 工程骨架与环境诊断工具。

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

当前检查项仍为基础版本：操作系统、Python、Git 路径、Conda 环境、ROS 发行版环境变量和常见串口。现有收集器只产生“正常”或“警告”；退出码 1 的分支已用模拟失败结果测试，后续必要检查可使用。当前版本尚不验证 Git 版本、ROS 库可用性、显卡、CUDA 或网络，也不自动安装软件或修改系统。

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
├── tests/                        # 自动化测试
├── LICENSE                       # MIT（宽松开源许可）文本
├── environment.yml               # Conda（环境与包管理器）环境配置
└── pyproject.toml                # Python（编程语言）项目配置
```

仓库会随真实功能逐周生长，不预先创建没有代码的目录。

## 路线与验收

完整计划见 [docs/roadmap.md](docs/roadmap.md)，无硬件情况下的逐周工具与验收见 [仿真与机器人可视化路线](docs/simulation-first-track.md)。开源项目的通用学习方法见 [docs/open-source-study.md](docs/open-source-study.md)，第一次完整实战见 [第 2 周 ROS 2 官方示例实验](docs/labs/week02-ros2-examples.md)。系统边界与演进方式见 [docs/architecture.md](docs/architecture.md)。

## 工作方式

每个功能遵循 `Issue（任务单）→ Branch（分支）→ Commit（提交）→ Pull Request（合并请求）→ Review（审查）→ Merge（合并）`。提交信息采用“英文类型 + 中文说明”，例如：

```text
feat: 增加 ROS 2 心跳监控节点
test: 增加规划失败恢复测试
docs: 记录陈旧 TF 坐标变换故障
```

## 许可证

本项目使用 `MIT License（MIT 宽松开源许可证）`。
