# 第 3 周第 6 天验收证据

最终一键验收于 2026-09-29 12:15:34～12:19:00（Asia/Shanghai）执行：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
source install/setup.bash
ros2 run embodied_comm week03_day6_evidence
```

结果为 `passed`：七个隔离场景覆盖六类故障，七个 MCAP 共记录 6,876 条消息；ROS 回归汇总 148 条记录零失败，仓库级测试 18 项通过。精简结果见 [`acceptance.log`](acceptance.log)。

本机完整证据目录：

```text
artifacts/week03-day6/run-20260929-121534-600895/
```

该目录包含每场 rosbag、Launch/客户端/Graph/诊断/TF 日志、`result.json`、`summary.json`、三份回归日志和自动生成的 `故障记录.md`。`artifacts/` 被 Git 忽略，因为 MCAP 属于大型运行产物；仓库只保留这份可审查的验收摘要和生成/复现方法。

关键约束：rosbag 证明消息时间线，不单独证明 Service 客户端超时或进程崩溃的根因。定位这两类故障时必须同时查看客户端、Launch、节点与端点日志。

