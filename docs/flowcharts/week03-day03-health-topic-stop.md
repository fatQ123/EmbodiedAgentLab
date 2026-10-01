# 第 3 周第 3 天：健康诊断、话题停止与 rosbag

这张图同时覆盖正常数据流、可复现的话题停止、diagnostics 状态转换、任务新鲜度联锁、现场根因定位、恢复和回归测试。

```mermaid
flowchart TB
    START["启动 week03_day3.launch.py"] --> CFG{"fault_stop_after_sec > 0？"}
    START --> VIS["workcell_visualizer<br/>持续发布 TF 与 Marker"]
    START --> WAITING["/diagnostics<br/>WARN + state=waiting"]
    START -. "节点启动后等待事件" .-> SERVICE_EVENT["外部 Service 请求到达"]
    START -. "长任务内部计时" .-> ACTION_EVENT["Action 到达终态检查点"]
    BAG_START["操作员另开终端<br/>启动 ros2 bag record"] -. "按需创建 Recorder" .-> BAG[("rosbag2 / MCAP")]

    CFG -- "否：正常模式" --> PUB["sensor_simulator<br/>定时发布 /sensor_state"]
    CFG -- "是：先正常发布" --> PUB
    PUB --> PARSE{"monitor 解析：<br/>消息是否合法？"}
    PUB --> EXEC_PARSE{"executor 解析：<br/>消息是否合法？"}
    EXEC_PARSE -- "否" --> EXEC_INVALID["记录警告并忽略<br/>不更新任务缓存"]
    EXEC_PARSE -- "是" --> CACHE["task_executor<br/>原子保存 reading + 单调接收时间"]

    PARSE -- "否" --> INVALID["invalid_count + 1<br/>不刷新健康时间"]
    PARSE -- "是" --> FRESH["status_monitor<br/>刷新 last_received_at"]
    FRESH --> OK["/diagnostics<br/>OK + state=healthy"]
    INVALID --> AGE
    WAITING --> AGE{"距启动或最后合法消息<br/>是否达到 timeout_sec？"}
    OK -- "下一次 diagnostic_rate 周期" --> AGE

    CFG -- "是：到达指定秒数" --> STOP["取消传感器发布 Timer<br/>保留节点与 DDS Publisher"]
    STOP --> LOG["写故障注入日志<br/>记录最后 seq"]
    LOG --> AGE

    AGE -- "否，且尚无合法消息" --> WAITING
    AGE -- "否，且已有合法消息" --> OK
    AGE -- "是" --> ERR["/diagnostics<br/>ERROR + state=stale"]
    ERR -- "下一次 diagnostic_rate 周期<br/>继续发布 ERROR" --> AGE
    PUB -- "/sensor_state" --> BAG
    WAITING -- "/diagnostics" --> BAG
    OK -- "/diagnostics" --> BAG
    ERR --> BAG

    SERVICE_EVENT --> SNAP["读取缓存与接收时间快照"]
    ACTION_EVENT --> SNAP
    CACHE --> SNAP
    SNAP --> USABLE{"有数据且 age < sensor_timeout_sec？"}
    USABLE -- "是" --> RANGE{"value 在 0～100？"}
    RANGE -- "是" --> PASS["Service success<br/>或 Action SUCCEEDED"]
    RANGE -- "否" --> VALUEFAIL["任务失败<br/>保留越界读数 sensor_seq"]
    USABLE -- "否" --> BLOCK["Service false<br/>或 Action ABORTED"]
    BLOCK --> NULLSEQ["Action Result sensor_seq=0<br/>task_status sensor_seq=null"]
    PASS --> STATUS["发布一次 /task_status"]
    VALUEFAIL --> STATUS
    NULLSEQ --> STATUS
    STATUS --> BAG

    ERR --> OBSERVE["操作员开始定位"]
    OBSERVE --> NODE{"node list 中<br/>sensor_simulator 存在？"}
    NODE -- "否" --> CRASH["节点崩溃类故障<br/>不是今天的根因"]
    NODE -- "是" --> ENDPOINT{"topic info --verbose<br/>Publisher count = 1？"}
    ENDPOINT -- "否" --> PUBLOSS["Publisher 丢失<br/>不是今天的根因"]
    ENDPOINT -- "是" --> FLOW{"topic hz / echo<br/>仍有新 seq？"}
    FLOW -- "是" --> TRANSIENT["数据已恢复<br/>或尚未真正断流"]
    FLOW -- "否" --> QOS{"发布与订阅 QoS 兼容？"}
    QOS -- "否" --> QOSFAULT["QoS 不匹配<br/>属于后续故障任务"]
    QOS -- "是" --> ROOT["结合注入日志确认<br/>发布 Timer 已停止"]

    ROOT --> RVIZ["tf2_echo / RViz 仍正常<br/>空间链没有故障"]
    ROOT --> BAGCHECK["bag info / play<br/>传感器计数冻结，诊断继续增长"]
    ROOT --> FIX["重启 Launch<br/>fault_stop_after_sec:=0.0"]
    FIX --> RECOVER["新 monitor 和 executor<br/>收到合法 /sensor_state"]
    RECOVER --> RECOK["/diagnostics 进入 OK<br/>独立新鲜度检查重新通过"]
    RECOK --> REGRESS["Service 再次成功<br/>运行全量回归测试"]

    VIS -. "传感器断流期间不受影响" .-> RVIZ
```

## 最短调试命令

```bash
ros2 node list
ros2 topic info /sensor_state --verbose
ros2 topic hz /sensor_state
ros2 topic echo /diagnostics diagnostic_msgs/msg/DiagnosticArray
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
ros2 run tf2_ros tf2_echo world tool0
ros2 bag info /tmp/week03_day3_topic_stop
```

关键判断不是“话题名是否存在”，而是“端点是否存在、消息是否仍更新、QoS 是否兼容、最后合法消息的年龄是多少”。诊断中的业务字符串为 `state=stale`，但等级是 `DiagnosticStatus.ERROR`，因为监控器自身仍在正常发布诊断。

对应实现与证据：

- [故障注入](../../ros2_ws/src/embodied_comm/embodied_comm/sensor_simulator.py)
- [标准健康诊断](../../ros2_ws/src/embodied_comm/embodied_comm/status_monitor.py)
- [陈旧数据联锁](../../ros2_ws/src/embodied_comm/embodied_comm/task_executor.py)
- [真实 DDS 集成测试](../../ros2_ws/src/embodied_comm/test/test_health_diagnostics.py)
- [第 3 天实验记录](../labs/week03-day3-health-topic-stop.md)
