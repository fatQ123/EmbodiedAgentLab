# 阶段④：一个 Launch 启动三个节点

## 实现与参数

新增 `ros2_ws/src/embodied_comm/launch/three_nodes.launch.py`，启动传感器、执行器和监控器三个业务进程，日志汇总到同一终端。`setup.py` 安装 Launch 文件到包的 share 目录，`package.xml` 增加 `launch`、`launch_ros` 依赖。

| Launch 参数 | 默认值 | 作用范围 |
|---|---|---|
| `publish_rate` | `2.0` | 仅传感器，单位 Hz |
| `timeout_sec` | `3.0` | 仅监控器，单位秒 |
| `executor_sensor_topic` | `/sensor_state` | 仅执行器的传感器输入重映射 |

数值参数显式转换为浮点型后传入节点，仍由节点校验有限正数。参数在启动时生效，修改后需要重启 Launch。非法参数会导致对应节点启动失败并显示原因，当前不提供自动重启或整组故障恢复；看到某节点退出时应 Ctrl+C 关闭该次启动并修正参数。

默认执行器和监控器均订阅 `/sensor_state`。修改 `executor_sensor_topic` 不会改变传感器发布端或监控器订阅端，也不会改变 `/execute_task`、`/task_status`。

Launch 负责启动进程，不保证第一个服务请求前传感器数据已到达。等执行器日志显示“最新传感器”后调用，才应预期成功。

## 你现在的验收步骤

先 Ctrl+C 关闭此前手动运行的节点，避免同名节点或重复服务端。

终端 A 构建、加载并启动：

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
cd /home/fatbro/workspace/ros2_ws
colcon build --symlink-install --packages-select embodied_comm
source install/setup.bash
ros2 launch embodied_comm three_nodes.launch.py
```

预期同一终端同时显示三个节点启动日志，执行器和监控器持续收到传感器数据。

终端 B 加载相同环境并验收：

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
source /home/fatbro/workspace/ros2_ws/install/setup.bash
ros2 node list --no-daemon --spin-time 5
ros2 topic info /sensor_state --verbose --no-daemon --spin-time 5
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

预期：三个业务节点；传感器话题 1 发布端、2 订阅端；服务返回 `success=True`；终端 A 的监控器显示对应任务结果。端点统计前退出额外的 echo/hz 订阅。发现有延迟时，等待后再查询；本次实测首次使用 2 秒发现窗口曾返回 Unknown topic，增加到 5 秒后重新验收。

### 修改参数

终端 A 按 Ctrl+C 关闭整组节点，再启动：

```bash
ros2 launch embodied_comm three_nodes.launch.py publish_rate:=5.0 timeout_sec:=1.5
```

终端 B 核对真实节点参数并测量频率：

```bash
ros2 param get /sensor_simulator publish_rate
ros2 param get /status_monitor timeout_sec
ros2 topic hz /sensor_state
```

预期参数为 5.0、1.5，测得频率约 5 Hz。结束频率测量用 Ctrl+C；终端 A 按一次 Ctrl+C 应关闭所有三个业务节点。

列出可用启动参数：

```bash
ros2 launch embodied_comm three_nodes.launch.py --show-args
```

### 为阶段⑤准备的错误连接入口

先关闭当前 Launch，再运行：

```bash
ros2 launch embodied_comm three_nodes.launch.py executor_sensor_topic:=/sensor_state_wrong
```

预期监控器仍收到传感器消息，执行器无数据，服务返回失败。退出后使用默认命令重启即可修复。本阶段已用自动化测试确认重映射作用范围；正常、错误、修复的完整诊断与 rqt_graph 截图留在阶段⑤。

## 测试与实测记录

```bash
cd /home/fatbro/workspace/ros2_ws
colcon test --packages-select embodied_comm --event-handlers console_direct+
colcon test-result --verbose
```

2026-09-19：37 项测试通过。新增两个测试从安装后的包运行真实 Launch，读取节点参数、核对订阅端、调用服务、检查监控结果，并向 Launch 主进程发送 Ctrl+C 验证三个节点全部退出。正常配置和错误重映射分别在域 181、182 验证；默认命令另在域 185 验收。测试域不应同时用于其他实验。

本机 `ros2` 和 `colcon` 使用系统 Python 3.12.3，即使终端激活 Conda 也如此。本次在激活项目 Conda 后运行默认 Launch 成功，未绕过已安装的 `ros2 launch` 入口；无需为此阶段修改 Conda 依赖。

- [默认 Launch 日志](evidence/week02-stage4/default-launch.log)
- [三个业务节点](evidence/week02-stage4/nodes.log)
- [传感器话题端点](evidence/week02-stage4/sensor-topic.log)
- [命令行服务响应](evidence/week02-stage4/service.log)
- [自定义参数及服务验证](evidence/week02-stage4/configured-result.json)
- [仅执行器错误重映射验证](evidence/week02-stage4/remapped-result.json)
- [37 项测试结果](evidence/week02-stage4/test-result.log)

本次启动的业务节点均已关闭，尚未执行 Git 提交或版本标记。下一步：你完成上述正常启动和改参数验收后，进入阶段⑤保存正常、错误和修复的诊断证据。
