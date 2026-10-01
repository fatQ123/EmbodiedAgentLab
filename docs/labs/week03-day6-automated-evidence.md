# 第 3 周第 6 天：自动 rosbag、日志与回归证据

> 自动化分支见[第 6 天流程图](../flowcharts/week03-day06-automated-evidence.md)，跨天关系见[第 1～7 天总流程图](../flowcharts/week03-overall.md)。

## 今天交付了什么

新增 `week03_day6_evidence` 证据编排器。它把六类需求展开为七个互相隔离的真实 ROS 2 场景：QoS 不匹配、话题停止、TF 缺失、TF 过期、Service 超时、Action 取消、节点崩溃。每个场景使用独立 `ROS_DOMAIN_ID`，自动完成：

1. 在故障前启动 MCAP Recorder 和常驻诊断观察器；
2. 启动第 5 天完整系统并执行故障驱动命令；
3. 保存 Launch、客户端、节点、端点、接口、诊断和 TF 日志；
4. 干净停止 Recorder，再用 `ros2 bag info` 验证消息数；
5. 即使单场失败也继续运行矩阵，最后生成 `summary.json` 与 `故障记录.md`；
6. 执行三个 ROS 包和仓库级 Python 回归并保存结果。

## 一键运行

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to \
  embodied_comm embodied_comm_cpp \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash

ros2 run embodied_comm week03_day6_evidence
echo "$?"
```

默认输出到 `artifacts/week03-day6/run-时间戳/`。退出码 `0` 表示所有场景与回归通过，`1` 表示已生成证据但有验收失败，`2` 表示参数或输出目录错误。为防止覆盖事故证据，显式 `--output-dir` 必须指向尚不存在的目录。

开发时可以只运行一个场景：

```bash
ros2 run embodied_comm week03_day6_evidence \
  --scenario tf_stale --skip-regression

ros2 run embodied_comm week03_day6_evidence --list-scenarios
```

## 证据目录

```text
run-时间戳/
├── qos_mismatch/ ... node_crash/   # 七个隔离场景
│   ├── rosbag/                     # metadata.yaml + MCAP
│   ├── launch.log                  # 节点日志、异常栈、退出码
│   ├── diagnostics-live.log        # 故障前启动的健康状态转换
│   ├── *-client.log                # Service/Action 退出码与终态
│   ├── nodes.log                   # ROS Graph 快照
│   ├── sensor-topic.log            # 端点与实际 QoS
│   ├── diagnostics-snapshot.log
│   ├── tf-snapshot.log
│   ├── bag-info.log
│   └── result.json                 # 单场判据
├── colcon-test.log
├── colcon-test-result.log
├── repository-tests.log
├── summary.json                    # 机器可读总结果
└── 故障记录.md                     # 本次运行的中文报告
```

rosbag 记录 `/sensor_state`、`/diagnostics`、`/task_status`、`/tf`、`/tf_static`、Marker、Action Feedback/Status 和 `/rosout`。Service 超时、Action 客户端退出码以及进程退出不能只靠业务 Topic 完整表达，因此文件日志是必要的第二条证据链。

回放示例：

```bash
ros2 bag info artifacts/week03-day6/run-时间戳/topic_stop/rosbag
ros2 bag play artifacts/week03-day6/run-时间戳/topic_stop/rosbag
```

## 六类中文故障记录

以下是稳定的排障知识；每次自动运行还会把实际通过/失败、bag 消息数和目录写入新的 `故障记录.md`。

### 1. QoS 不匹配

- 现象：Publisher 存在，但 RELIABLE 业务订阅收不到 BEST_EFFORT 数据，诊断 `qos_mismatch`，任务失败。
- 检查命令：`ros2 topic info /sensor_state --verbose`、查看 `/diagnostics`、调用 `/execute_task`。
- 画面：RViz 坐标树正常；画面正常而测量任务失败，应转查通信链。
- 日志：核对发布端 `best_effort`、订阅端 `reliable`、兼容性 `incompatible`。
- 根因：DDS Requested/Offered 可靠性不兼容；发现端点不代表建立数据连接。
- 修复：按数据丢失预算统一 QoS；本项目恢复发布端 `reliable`。
- 回归测试：序号持续增长，诊断 `healthy`，Service 与 Action 成功。

### 2. 话题停止

- 现象：节点和 Publisher 在线，但序号停止，超时后诊断 `stale`，任务被新鲜度门禁拒绝。
- 检查命令：组合 `node list`、`topic info`、`topic hz`、诊断和 Service 结果。
- 画面：TF 与 Marker 正常，不能据此证明传感器仍在采样。
- 日志：出现“停止发布”和“消息超时”，同时 `publisher_count=1`。
- 根因：数据 Timer 停止，模拟驱动在线但采集线程冻结。
- 修复：关闭停止注入并重启；只在新数据到达后解除联锁。
- 回归测试：新序号增长、诊断回到 `healthy`、任务恢复。

### 3. TF 缺失或过期

- 现象：缺失时完整链从未形成；过期时链先正常，随后动态时间戳停止并进入 `stale`。
- 检查命令：`tf2_echo world tool0`、`topic info /tf --verbose`，并比较 `age_sec` 与阈值。
- 画面：缺失时 RViz 出现两棵子树，tool0 Marker 不显示；过期时目标消失或出现 old data/extrapolation。
- 日志：分别包含“坐标链缺失”或“停止刷新”，诊断为 `missing/stale`。
- 根因：关键动态边未发布，或最后时间戳超过新鲜度限制。
- 修复：恢复唯一、连续且时钟正确的 TF 发布源，使用 `normal` 模式。
- 回归测试：完整链持续输出、时间戳增长、空间诊断 `healthy`、Marker 可见。

### 4. Service 超时

- 现象：客户端先达到截止时间；Server 仍完成请求并发布终态。
- 检查命令：查看 Service、Server 节点、客户端退出码和 `/task_status`。
- 画面：RViz 正常；这是接口时序问题，不是空间故障。
- 日志：客户端“服务响应超时”，Server 稍后记录“延迟 1.00 秒后响应”。
- 根因：客户端期限短于回调耗时；客户端停止等待不会取消 Server 回调。
- 修复：关闭延迟；长工序用 Action，有副作用的 Service 使用幂等键。
- 回归测试：正常请求在期限内返回，每次请求只产生一个任务终态。

### 5. Action 取消

- 现象：客户端收到首个达到或超过 40% 阈值的反馈后请求取消，目标进入 `CANCELED`，下一个目标进入 `SUCCEEDED`。反馈采样和调度可能使进度跨过阈值，不保证精确停在 40%。
- 检查命令：查看 Action 类型、Feedback、Cancel/Result 和 `/task_status`。
- 画面：当前 Marker 不由 Action 驱动，终止证据来自协议状态，不来自机械臂动画。
- 日志：依次出现取消请求、`CANCELED`、资源释放、恢复目标 `SUCCEEDED`。
- 根因：客户端主动发送标准 Cancel Request，Server 在执行循环内协作终止。
- 修复：取消本身是安全动作；保证响应时限并在 `finally` 释放工位。
- 回归测试：取消后立即提交下一件工件，确认不死锁、不误拒绝且成功。

### 6. 节点崩溃

- 现象：传感器进程退出码为 1，Node 和 Publisher 消失，诊断为 `publisher_lost`，其余节点继续运行。
- 检查命令：组合 `node list`、`topic info`、诊断、Launch 退出日志和 Service 结果。
- 画面：独立 TF/Marker 保持正常，说明空间链与测量进程隔离。
- 日志：必须同时出现“即将崩溃”、异常栈、`process has died` 与 `exit code 1`。
- 根因：Timer 抛出未捕获异常，进程退出后 DDS 清理端点。
- 修复：关闭注入并重启；生产环境增加有限重试、退避和升级报警。
- 回归测试：节点和 Publisher 恢复、诊断 `healthy`、新数据任务成功。

## 画面与自动化边界

流水线固定 `use_rviz:=false`，适合无人值守与 CI；`tf-snapshot.log` 和空间诊断是机器判据，“画面”字段记录操作员在 RViz 应观察到的差异。需要视觉验收时，按第 4 天文档手动启动对应场景与 RViz。当前 rosbag 也不等于安全认证审计：工业项目还需统一时钟、工件 ID、软件版本、参数快照、不可篡改存储和保留策略。
