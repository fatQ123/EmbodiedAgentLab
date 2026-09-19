# 阶段②：执行器订阅并保存最新传感器状态

## 本阶段新增内容

- `embodied_comm/task_executor.py`：节点名 `task_executor`，订阅 `/sensor_state`，类型为 `std_msgs/msg/String`，队列深度 10。
- `setup.py`：注册 `task_executor` 可执行入口。沿用现有依赖，无新增依赖。
- `test/test_task_executor.py`：验证缓存更新、非法消息不覆盖缓存、重启后的序号与越界读数处理，以及真实传感器到两个订阅者的通信。

节点内部保存 `latest_reading`、`last_received_at`（本进程单调时钟接收时间）和 `received_count`。启动时前两项为 `None`、计数为 0；收到格式合法的数据才更新这三项。越界但格式合法的读数也保存，业务有效范围判断留给阶段③。收到非法消息会警告，并保留原有缓存和接收时间；传感器重启后 seq 从 1 开始也正常接收。

日志每次显示最新序号、读数和累计接收次数。阶段②尚无 `/execute_task` 服务或 `/task_status` 发布。

## 你现在的手动验收步骤

先关闭之前手动启动的同名节点，避免重复进程干扰端点计数。重新构建以安装新增入口：

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
cd /home/fatbro/workspace/ros2_ws
colcon build --symlink-install --packages-select embodied_comm
source install/setup.bash
ros2 pkg executables embodied_comm
```

预期列出 `sensor_simulator`、`task_executor`、`status_monitor` 三个入口。

每个新终端先执行：

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
source /home/fatbro/workspace/ros2_ws/install/setup.bash
```

终端 A：

```bash
ros2 run embodied_comm task_executor
```

此时只显示等待数据，不应伪造最新读数。

终端 B：

```bash
ros2 run embodied_comm status_monitor
```

终端 C：

```bash
ros2 run embodied_comm sensor_simulator --ros-args -p publish_rate:=2.0
```

预期 A 持续显示 `最新传感器：seq=…，value=…，累计接收=…`，B 也收到递增序号。订阅者启动较晚时，第一条序号不一定为 1。

终端 D（先退出其他终端的 echo/hz 命令）：

```bash
ros2 node list --no-daemon --spin-time 2
ros2 topic info /sensor_state --verbose --no-daemon --spin-time 2
```

预期三个业务节点均在；`/sensor_state` 类型为 `std_msgs/msg/String`，发布端为 `sensor_simulator`，两个订阅端分别为 `task_executor` 和 `status_monitor`。如果第一次发现不完整，稍后重新查询。

验收完毕，在 A、B、C 分别 Ctrl+C 退出。下一步是阶段③：加入 Trigger 服务，验证无数据失败、有数据成功和任务结果到监控器的通信。

## 自动化验证与证据

```bash
cd /home/fatbro/workspace/ros2_ws
colcon test --packages-select embodied_comm --event-handlers console_direct+
colcon test-result --verbose
```

2026-09-19 构建成功，23 项测试通过（含阶段①的 21 项）。独立进程验收使用域 176、仅本机发现，与用户默认域中的运行互不干扰；验收完成后关闭本次启动的节点。

- [三个节点](evidence/week02-stage2/nodes.log)
- [传感器话题端点：1 发布端、2 订阅端](evidence/week02-stage2/topic-info.log)
- [执行器接收日志](evidence/week02-stage2/task_executor.log)
- [监控器接收日志](evidence/week02-stage2/status_monitor.log)
- [可执行入口](evidence/week02-stage2/entries.log)
- [测试结果](evidence/week02-stage2/test-result.log)

没有执行 Git 提交或标记版本；完整 v0.2 仍待后续阶段验收。
