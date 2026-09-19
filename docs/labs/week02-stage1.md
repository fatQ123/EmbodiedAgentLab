# 阶段①：独立传感器发布与监控订阅

## 实现范围

包位于 `ros2_ws/src/embodied_comm`，包含两个独立节点及共享格式校验。仅实现 `/sensor_state` 通信；执行器、服务、任务状态与 Launch 留给后续阶段。

- `sensor_simulator` 默认 2 Hz 发布 `std_msgs/msg/String`，文本为 `{"seq": 1, "value": 0.0}`。序号从 1 递增；模拟读数按 0～100 循环，重启后重新计数。
- `status_monitor` 解析并记录最新合法消息，忽略非法 JSON、错误字段类型与非有限读数。越界但格式合法的值保留给后续执行器判断。
- `publish_rate` 与 `timeout_sec`（默认 3 秒）为启动时的有限正数参数，设为只读，运行中修改会明确失败。
- 监控使用单调时钟，从启动或最近一次合法消息接收时刻计时。首次超时报警一次，恢复提示一次；超时检查周期不超过 0.1 秒。因此正常调度下报警发生在阈值之后约一个检查周期内，并非硬实时保证。
- 默认双方使用深度 10 的可靠、易失 QoS；监控启动前的消息不会补发。

## 构建与运行

在主项目根目录执行：

```bash
source /home/fatbro/software/miniforge3/etc/profile.d/conda.sh
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
cd /home/fatbro/workspace
./scripts/check_ros2_lab.sh
cd ros2_ws
colcon build --symlink-install --packages-select embodied_comm
source install/setup.bash
ros2 pkg executables embodied_comm
```

分别在两个终端激活同一 Conda 环境，加载系统与工作空间：

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
source /home/fatbro/workspace/ros2_ws/install/setup.bash
```

终端 A：

```bash
ros2 run embodied_comm status_monitor --ros-args -p timeout_sec:=3.0
```

终端 B：

```bash
ros2 run embodied_comm sensor_simulator --ros-args -p publish_rate:=2.0
```

观察终端也加载上述环境，依次执行：

```bash
ros2 topic info /sensor_state --verbose --no-daemon --spin-time 2
ros2 topic echo /sensor_state std_msgs/msg/String --once
ros2 topic hz /sensor_state
```

频率观察结束后按 Ctrl+C。在传感器终端按 Ctrl+C，监控器应在最后一条合法消息约 3 秒后报警。再以 `publish_rate:=5.0` 启动传感器，应看到恢复提示；再次测量频率。结束时分别 Ctrl+C 关闭两个节点。

参数写成 `2.0` 而不是整数 `2`，与声明的浮点类型保持一致。`publish_rate:=0.0` 或 `timeout_sec:=-1.0` 应启动失败，错误说明参数必须为有限正数。

## 自动化测试

在已加载系统与工作空间的终端：

```bash
cd /home/fatbro/workspace/ros2_ws
colcon test --packages-select embodied_comm --event-handlers console_direct+
colcon test-result --verbose
```

测试使用独立 ROS Context 和域 172，覆盖真实 DDS 通信、序号更新、无数据超时、中断与恢复、非法消息，以及零、负数、NaN、正负无穷参数。运行时不要在域 172 启动其他实验节点。

本机 `colcon` 的解释器为系统 Python 3.12.3。额外用 Conda Python 3.12.14 验证时：

```bash
cd /home/fatbro/workspace
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest ros2_ws/src/embodied_comm/test -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests -q
```

关闭自动插件加载仅针对上述测试进程：本机 Conda 环境缺少 ROS `launch_testing` 插件间接需要的 `lark`，直接运行 pytest 会在收集前失败。本阶段未使用 Launch 测试，故无需加载该插件；标准 `colcon test` 已正常运行。后续 Launch 阶段需重新检查相应运行环境。

## 实测证据（2026-09-19）

首先仅实现发布订阅并运行，确认序号 1～6 持续递增后，再加入超时检测。日志位于 [证据目录](evidence/week02-stage1/)。

CLI 首次查询曾在节点正常收发时报告 `Unknown topic`；改用 `--no-daemon --spin-time 2` 直接等待发现后查询成功。`echo` 自动推断类型也曾失败，显式提供 `std_msgs/msg/String` 后成功。查询缓存/发现时机与节点实际通信应分开检查。

本轮独立进程验收使用域 175、仅本机发现，结束后关闭了本次启动的业务进程。话题端点检查在运行 `echo`、`hz` 之前进行，避免临时订阅影响数量。

接口及包安装结构参考 [ROS 2 Jazzy 包安装文档](https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Launch/Launch-system.html)；节点业务逻辑在本项目独立实现。

| 验收项 | 本次结果 | 原始证据 |
|---|---|---|
| 包构建与入口 | 构建成功，注册两个可执行程序 | `ros2 pkg executables embodied_comm` 可复查 |
| 持续递增消息 | 初次联调收到 seq=1～6 | [初次监控日志](evidence/week02-stage1/initial-status_monitor.log) |
| 话题端点 | String；1 发布端、1 订阅端 | [端点信息](evidence/week02-stage1/topic-info.log) |
| 消息内容 | 收到 seq=14、value=13.0 的 JSON 文本 | [单条消息](evidence/week02-stage1/topic-echo.log) |
| 默认频率 | 平均 2.000 Hz | [2 Hz 日志](evidence/week02-stage1/frequency-2hz.log) |
| 修改频率 | 平均 5.000 Hz；局部接收间隔有调度抖动，非硬实时 | [5 Hz 日志](evidence/week02-stage1/frequency-5hz.log) |
| 停止与恢复 | 阈值 1 秒；两次停止分别在 1.07、1.00 秒报警，中间恢复时有提示 | [超时恢复日志](evidence/week02-stage1/monitor-timeout-recovery.log) |
| ROS 自动化测试 | colcon：21 通过，0 失败；Conda：相同 21 项通过 | [colcon 结果](evidence/week02-stage1/test-result.log) |
| 原项目回归 | 18 项通过，17 个子测试通过 | 本次 Conda pytest 运行结果 |

阶段①已完成。本轮不提交 Git、不标记 v0.2；服务、Launch、C++ 对照和完整系统验收仍未完成。
