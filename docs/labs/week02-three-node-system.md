# 第 2 周：三节点系统开发前检查与实施清单

## 检查结果（2026-09-19）

本次检查主项目 `/home/fatbro/workspace`，当前分支为 `ros2-v0.2`，检查开始时工作区干净。

| 检查项 | 实际结果 | 处理决定 |
|---|---|---|
| `ros2_ws/src/embodied_comm` | `ros2_ws` 目录尚不存在，Git 中也没有该目录下的文件 | 从阶段①创建独立包，不复制官方示例 |
| 三个业务节点 | 主项目没有对应实现 | 按阶段新增，逐条验证通信 |
| 包与入口配置 | 没有 ROS 包的 `package.xml`、`setup.py`、`setup.cfg` | 创建包时补齐 |
| 现有 Python 工程 | `src/embodied_agent_lab` 实现环境诊断；`pyproject.toml` 注册 `embodiedlab` | 保留现有工具，ROS 包独立安装 |
| Launch 与 ROS 测试 | 尚无对应实现；根目录测试针对环境诊断 | ROS 测试放在包内，Launch 在阶段④增加 |
| 构建产物忽略规则 | `.gitignore` 已忽略 `ros2_ws/build`、`install`、`log` | 直接沿用 |
| 实验文档 | `week02-ros2-examples.md` 已规划 Python/C++ 两个发布订阅包 | 保留对照实验，在 Python 包中逐步扩展第三节点和服务 |
| 本机环境目录 | `/opt/ros/jazzy` 与外部官方示例仓库存在 | 目录存在不等于运行验收通过，首次开发前再运行环境检查 |

外部参考仓库 `/home/fatbro/open-source-labs/ros2-examples` 当前在 `lab/jazzy-pub-sub` 分支，有 Python/C++ 示例修改及未跟踪构建产物。这些属于已有学习现场，不覆盖、不清理，也不视为主项目已经实现。

以上为开发前快照。后续阶段①已实现，构建、运行与测试记录见 [阶段①验收记录](week02-stage1.md)；阶段②的执行器订阅也已实现，见 [阶段②验收记录](week02-stage2.md)；阶段③的服务和任务状态发布已实现，见 [阶段③验收记录](week02-stage3.md)；阶段④的一键启动已实现，见 [阶段④验收记录](week02-stage4.md)；阶段⑤的正常、错误、修复实验和实时图证据见 [阶段⑤验收记录](week02-stage5.md)；最终发布验收仍待阶段⑥完成。

## 三个节点的职责与接口

| 节点 | 职责 | ROS 接口 | 参数 |
|---|---|---|---|
| `sensor_simulator` | 定时生成模拟读数，序号持续递增 | 发布 `/sensor_state`，类型 `std_msgs/msg/String` | `publish_rate`，默认 2.0 Hz |
| `task_executor` | 保存最新读数，收到一次请求后快速检查并返回结果 | 订阅 `/sensor_state`；提供 `/execute_task`，类型 `std_srvs/srv/Trigger`；发布 `/task_status`，类型 `std_msgs/msg/String` | 本阶段不增加额外参数 |
| `status_monitor` | 显示传感器与任务状态，发现传感器消息中断 | 订阅 `/sensor_state` 和 `/task_status` | `timeout_sec`，默认 3.0 秒 |

Topic 用于持续或事件式发布，Service 用于一次请求对应一次响应。命令行服务客户端临时运行，不是第四个长期业务节点。服务回调不休眠模拟长任务。

传感器消息统一为 JSON 文本，例如 `{"seq": 1, "value": 50.0}`。`seq` 从 1 递增，`value` 为有限数值，任务检查通过范围为闭区间 0～100。格式错误的消息应明确记录且不覆盖最新合法数据；格式合法但越界的读数应保存，并在任务检查中返回失败。

任务消息例如 `{"task_id": 1, "success": true, "message": "检查通过", "sensor_seq": 12}`。每次服务请求都发布一次结果；没有合法传感器数据时返回失败，`sensor_seq` 为 `null`。

参数在启动时生效，必须为有限正数；运行时动态调参留待后续实现。监控器从启动或最近一次接收传感器消息开始计时，超过阈值报警，恢复时提示，持续故障避免刷屏。任务状态按需产生，不因没有任务请求而报警。最小版本的执行器检查最新合法读数，不承诺拒绝陈旧数据。

## 按阶段补充文件

以下均为计划文件，不表示已经创建。包根目录为 `ros2_ws/src/embodied_comm/`。

| 阶段 | 新增或修改文件（相对包根目录） | 完成后才进入下一阶段的证据 |
|---|---|---|
| ① 独立发布订阅 | 新增 `package.xml`、`setup.py`、`setup.cfg`、`resource/embodied_comm`、`embodied_comm/__init__.py`；新增 `embodied_comm/sensor_simulator.py`、`embodied_comm/status_monitor.py`；新增 `test/test_parameters.py`、`test/test_pub_sub.py` | 构建成功；监控收到递增序号；参数改变发布频率；停止传感器后报警 |
| ② 加入执行器订阅 | 新增 `embodied_comm/task_executor.py`，在 `setup.py` 注册入口 | 执行器日志显示最新读数；传感器话题为 1 发布端、2 订阅端 |
| ③ 服务与任务状态 | 扩展执行器与监控器；补充服务依赖；新增 `test/test_execute_task.py` | 无数据失败、有数据成功、越界失败；监控收到任务结果 |
| ④ 一键启动 | 新增 `launch/three_nodes.launch.py`；在 `setup.py` 安装 Launch 文件，补充依赖 | 一个 Launch 启动三个节点，可传入参数并只重映射执行器的传感器输入 |
| ⑤ 故障定位 | 在本目录下增加实际实验记录与筛选后的截图 | 正常、错误、修复三种关系证据；服务响应另行保存 |
| ⑥ 测试与复现 | 完善包内测试及运行说明；按原实验文档新增 `embodied_comm_cpp` | 自动化测试、从提交源码复现、双语言对照完成，再进入合并和版本标记 |

`package.xml` 随实现声明实际依赖：Python 节点使用 `rclpy`、`std_msgs`，服务阶段增加 `std_srvs`，Launch 阶段增加 `launch`、`launch_ros`；构建类型为 `ament_python`，测试依赖随测试工具补充。`setup.py` 最终注册三个节点入口，`setup.cfg` 指定 ROS 可执行脚本安装位置，资源标记和包清单也需安装。

根目录 `pyproject.toml` 当前只发现 `src` 中的 Python 包，pytest 默认只运行根目录 `tests`。因此以后不能用根目录测试通过代替 ROS 包测试通过，需单独构建并运行包内测试。

## 每阶段的实际操作顺序

1. 首次实现前激活项目 Conda 环境，加载 ROS Jazzy，运行已有 `scripts/check_ros2_lab.sh`。本次未执行该脚本，不宣称环境验收通过。
2. 阶段①只创建传感器与监控器，构建并分别启动；通过 `ros2 topic echo /sensor_state`、`ros2 topic hz /sensor_state` 与节点日志验证。
3. 阶段②只增加执行器订阅，确认缓存更新，再检查端点数量。统计时退出 `echo` 和 `hz`，避免额外订阅影响计数。
4. 阶段③先单独启动执行器，调用 `ros2 service call /execute_task std_srvs/srv/Trigger "{}"` 保存无数据失败响应；随后启动传感器再次调用，保存成功响应和监控日志。
5. 阶段④再加入 Launch，重复已通过的通信检查。
6. 阶段⑤以错误重映射重新启动执行器，使其订阅 `/sensor_state_wrong`，避免已有缓存干扰实验；确认监控仍正常、服务失败。恢复配置后重新启动并复验。
7. 阶段⑥汇总参数、服务分支、实际通信链路与超时测试，补全 C++ 对照。截图用于证明话题连接，服务调用成功必须另有响应证据。

## 与原文档的关系

[官方示例实验](week02-ros2-examples.md) 的第 9 节是双语言发布订阅对照，不是完整 v0.2 三节点系统。其两个 Python 入口在阶段②扩展成三个，C++ 保持一对发布订阅节点。跨语言测试使用相同 JSON 消息格式，原文的 `sensor_count=0` 只是格式示例。

本次 v0.2 服务以 `/execute_task` 为准，路线图中的旧 `/reset_robot` 约定同步替换。第 3 周的长任务 Action 属于后续设计，不在本次提前实现。
