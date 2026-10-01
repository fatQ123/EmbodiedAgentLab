# 第 3 周第 3 天实测证据

本目录保存“标准健康诊断 + 话题停止故障 + 陈旧数据联锁 + rosbag 留证”的可审阅文本证据。二进制 rosbag 位于实验机 `/tmp/week03_day3_topic_stop`，未提交到仓库。

| 文件 | 内容 |
|---|---|
| [`build-test.log`](build-test.log) | 全量构建、ROS 测试、根项目测试与静态检查摘要 |
| [`normal-diagnostics.log`](normal-diagnostics.log) | 正常数据流的 `healthy/OK` 快照与成功 Service |
| [`topic-stop-diagnostics.log`](topic-stop-diagnostics.log) | 消息停止后的 `stale/ERROR` 快照 |
| [`topic-info.log`](topic-info.log) | 故障时 Publisher 和订阅端点仍存在 |
| [`service-stale.log`](service-stale.log) | 执行器拒绝陈旧缓存 |
| [`launch-transition.log`](launch-transition.log) | 故障注入、超时报警和任务拒绝时间线 |
| [`recovery.log`](recovery.log) | 关闭故障注入后恢复正常 |
| [`bag-info.log`](bag-info.log) | MCAP 时长、消息总数和逐话题计数 |

## 复现配置

故障录包使用：

```text
publish_rate=5.0 Hz
fault_stop_after_sec=6.0 s
timeout_sec=1.5 s
diagnostic_rate=2.0 Hz
RViz/TF 保持正常
```

另一次人工观察使用 12 秒后停、2 秒超时，用于检查长时间 `stale` 状态和端点信息。

完整解释、七段式故障记录和工业前沿对照见 [`../../week03-day3-health-topic-stop.md`](../../week03-day3-health-topic-stop.md)。
