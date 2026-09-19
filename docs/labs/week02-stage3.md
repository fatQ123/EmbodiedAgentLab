# 阶段③：一次请求、一次响应与任务结果通知

## 新增行为

`task_executor` 提供 `/execute_task`，类型 `std_srvs/srv/Trigger`，请求为空。每次请求立即检查缓存中的最新合法传感器读数，返回 `success` 和 `message`；回调没有休眠或长任务。

| 输入状态 | 响应 |
|---|---|
| 尚无格式合法的传感器消息 | `success=false`，说明没有有效传感器数据 |
| 最新合法读数在闭区间 `[0, 100]` | `success=true`，说明检查通过，附序号与读数 |
| 最新合法读数小于 0 或大于 100 | `success=false`，说明读数不在有效范围 |

每次请求都向 `/task_status` 发布一条 `std_msgs/msg/String`，文本为 JSON：

```json
{"task_id": 1, "success": false, "message": "没有有效传感器数据：尚未收到格式合法的读数", "sensor_seq": null}
```

任务编号从 1 递增，执行器重启后重新计数。`sensor_seq` 指向本次检查的读数序号，无数据时为 `null`。成功与失败均通知监控器，消息中的结果说明与服务响应一致。

`status_monitor` 增加任务状态订阅、格式校验和结果日志。任务消息不会重置传感器超时，也不会因没有新任务而报警。任务话题使用可靠、易失 QoS（深度 10），应先启动监控器再调用服务；后来启动的订阅者不补收历史任务。

服务目前只检查缓存读数的格式和数值范围，不检查其新鲜度。停止传感器会触发监控报警，但执行器仍可能用上次合法读数返回成功；验证“无数据失败”必须在没有传感器运行时重新启动执行器。非法消息不覆盖此前合法缓存。

## 文件变更

- `embodied_comm/task_executor.py`：服务回调、任务计数和结果发布。
- `embodied_comm/status_monitor.py`：任务结果订阅与日志。
- `embodied_comm/common.py`：接口名称常量、任务结果格式校验。
- `package.xml`：声明实际使用的 `std_srvs` 依赖。
- `test/test_execute_task.py`：真实服务调用和话题传输测试。

## 你现在的手动验收

先关闭阶段②启动的三个业务节点，尤其确认传感器已停止，再构建：

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
cd /home/fatbro/workspace/ros2_ws
colcon build --symlink-install --packages-select embodied_comm
source install/setup.bash
```

每个新终端都加载：

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
source /home/fatbro/workspace/ros2_ws/install/setup.bash
```

### 1. 先验收无数据失败

终端 A：

```bash
ros2 run embodied_comm task_executor
```

终端 B：

```bash
ros2 run embodied_comm status_monitor
```

暂不启动传感器。终端 C 先确认任务话题有 1 个发布端和 1 个订阅端，再调用：

```bash
ros2 topic info /task_status --verbose --no-daemon --spin-time 2
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

预期 C 返回 `success=False` 和“没有有效传感器数据”；B 显示 `task_id=1`、`success=False`、`sensor_seq=None`。此时监控器可能同时提示传感器超时，这是预期行为。

### 2. 再验收有数据成功

终端 D：

```bash
ros2 run embodied_comm sensor_simulator
```

等终端 A 显示最新传感器读数，再在终端 C 调用：

```bash
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

预期 C 返回 `success=True` 和“检查通过”；B 显示 `task_id=2`、`success=True` 和对应传感器序号。重复调用，任务编号应继续递增。

服务响应与任务话题是两条通信链路，必须分别观察。不要仅用节点关系图证明服务成功。若需要直接观察 JSON，另开终端加载环境后运行以下命令，再发起一次服务调用：

```bash
ros2 topic echo /task_status std_msgs/msg/String
```

验收完成后 Ctrl+C 关闭各业务节点与 echo。下一阶段④将用一个 Launch 文件启动三个节点并集中传入参数。

## 自动化测试和实测证据

```bash
cd /home/fatbro/workspace/ros2_ws
colcon test --packages-select embodied_comm --event-handlers console_direct+
colcon test-result --verbose
```

2026-09-19：构建成功，35 项测试全部通过。新增测试覆盖无数据失败、真实传感器输入成功、0/100 边界通过、负数/超过 100 失败、任务编号递增、响应与监控消息一致，以及任务消息不重置传感器超时。保留阶段①②全部回归测试。

实现顺序：先运行真实服务调用，确认无数据失败、有数据成功，再增加任务结果话题并验证整条链路。最终独立进程验收使用域 178、仅本机发现；结束后关闭本次启动的业务节点。

- [无数据服务响应](evidence/week02-stage3/service-no-data.log)
- [有数据服务响应](evidence/week02-stage3/service-success.log)
- [监控器收到两次任务结果](evidence/week02-stage3/status_monitor.log)
- [任务话题端点](evidence/week02-stage3/task-topic-info.log)
- [执行器日志](evidence/week02-stage3/task_executor.log)
- [测试结果](evidence/week02-stage3/test-result.log)

尚未实现 Launch，也未执行 Git 提交或版本标记。
