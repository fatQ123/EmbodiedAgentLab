# 第 3 周第 5 天实测证据

本目录保存“Service 超时 + Action 取消恢复 + 传感器节点崩溃”的可审阅文本证据。三个场景都通过已安装的 `week03_day5.launch.py` 在独立 ROS Domain 中运行，真实经过 DDS、Service、Action 和 ROS Graph，不以 mock 替代通信链路。

| 文件 | 内容 |
|---|---|
| [`build-test.log`](build-test.log) | 全量构建、ROS 测试、根项目测试和静态检查摘要 |
| [`fault-scenarios.log`](fault-scenarios.log) | 三类故障的输入、可观测结果和自动化断言 |
| [`launch-events.log`](launch-events.log) | 真实进程日志中的延迟、取消、恢复、异常栈与退出码摘录 |

## 自动化复现配置

```text
ROS_DOMAIN_ID=189：Service Server 延迟 1.0 s，Client 截止时间 0.2 s
ROS_DOMAIN_ID=190：Action 时长 2.0 s，在 40% 取消，再提交 0.2 s 恢复目标
ROS_DOMAIN_ID=191：传感器在 4.0 s 崩溃，数据新鲜度阈值 0.4 s
publish_rate=20.0 Hz
diagnostic_rate=20.0 Hz
RViz=false（无图形自动化；人工验收可用默认 true）
```

完整原理、七段式故障记录、人工命令和工业能力边界见 [`../../week03-day5-service-action-crash.md`](../../week03-day5-service-action-crash.md)。
