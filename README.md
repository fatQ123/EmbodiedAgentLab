# EmbodiedAgentLab（具身智能体实验室）

一个以项目驱动方式学习并构建“机器人大小脑”的长期工程：用 `ROS 2（机器人操作系统第二代）`、`MoveIt 2（机械臂运动规划框架）`、`ros2_control（机器人控制框架）`、视觉感知、`LLM Agent（大语言模型智能体）` 与机器人学习，完成可诊断、可恢复、可评测的机械臂系统。

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

完整计划见 [docs/roadmap.md](docs/roadmap.md)。开源项目的通用学习方法见 [docs/open-source-study.md](docs/open-source-study.md)，第一次完整实战见 [第 2 周 ROS 2 官方示例实验](docs/labs/week02-ros2-examples.md)。系统边界与演进方式见 [docs/architecture.md](docs/architecture.md)。

## 工作方式

每个功能遵循 `Issue（任务单）→ Branch（分支）→ Commit（提交）→ Pull Request（合并请求）→ Review（审查）→ Merge（合并）`。提交信息采用“英文类型 + 中文说明”，例如：

```text
feat: 增加 ROS 2 心跳监控节点
test: 增加规划失败恢复测试
docs: 记录陈旧 TF 坐标变换故障
```

## 许可证

本项目使用 `MIT License（MIT 宽松开源许可证）`。
