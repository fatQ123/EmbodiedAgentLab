# 第 3 周第 4 天实测证据

本目录保存“QoS 不匹配 + 话题停止 + TF 缺失/过期 + 双链诊断”的可审阅文本证据。四个场景由已安装的 `week03_day4.launch.py` 在独立 ROS Domain 中实际启动，不用 mock 替代 DDS 或 TF 通信。

| 文件 | 内容 |
|---|---|
| [`build-test.log`](build-test.log) | 全量构建、ROS 测试、根项目测试和静态检查摘要 |
| [`fault-matrix.log`](fault-matrix.log) | 四个故障场景的诊断、端点、TF 和 Service 判定 |
| [`launch-events.log`](launch-events.log) | 四次真实 Launch 的关键启动、注入、联锁与退出日志 |

## 自动化复现配置

```text
publish_rate=20.0 Hz
diagnostic_rate=20.0 Hz
frame_publish_rate=20.0 Hz
sensor timeout=0.4 s
TF timeout=0.4 s
RViz=false（无图形自动化；人工验收默认 true）
```

完整解释、七段式故障记录、人工 RViz 观察步骤和工业能力边界见 [`../../week03-day4-qos-tf-faults.md`](../../week03-day4-qos-tf-faults.md)。
