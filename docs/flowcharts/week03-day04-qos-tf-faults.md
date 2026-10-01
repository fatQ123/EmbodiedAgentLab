# 第 3 周第 4 天：QoS、话题停止与 TF 故障流程

本图把四种注入分成“传感器通信链”和“空间 TF 链”。调试时先根据 `/diagnostics` 的 `status.name` 选择链路，再用稳定的 `state` 缩小根因。

```mermaid
flowchart TB
    START(["启动 week03_day4.launch.py"]) --> MODE{"选择一种故障参数"}

    MODE -- "publisher_reliability=best_effort" --> QOSPUB["/sensor_state Publisher<br/>BEST_EFFORT"]
    QOSPUB --> MATCH{"能满足业务订阅端<br/>RELIABLE 请求？"}
    MATCH -- "否" --> QOSERR["传感器诊断<br/>ERROR + qos_mismatch"]
    QOSERR --> QOSCHECK["topic info --verbose<br/>端点存在但 QoS 不兼容"]
    QOSCHECK --> QOSFIX["统一 Requested / Offered 策略<br/>重启后验证 healthy"]

    MODE -- "fault_stop_after_sec > 0" --> FLOWOK["先正常发布 /sensor_state"]
    FLOWOK --> STOP["到时取消数据 Timer<br/>Node 与 Publisher 保持在线"]
    STOP --> AGE{"age_sec 达到<br/>timeout_sec？"}
    AGE -- "是" --> STALE["传感器诊断<br/>ERROR + stale"]
    STALE --> FLOWCHECK["node list + topic info<br/>再查 topic hz 与序号"]
    FLOWCHECK --> FLOWFIX["恢复数据源<br/>必须等新数据到达"]

    MODE -- "tf_fault_mode=missing" --> STATIC["只发布两段静态边<br/>world→base / camera→tool"]
    STATIC --> TFLOOKUP{"TF Buffer 能合成<br/>world → tool0？"}
    TFLOOKUP -- "从未能合成" --> MISSING["空间诊断<br/>ERROR + missing"]
    MISSING --> MISSVIEW["RViz 子树断开<br/>tool0 Marker 不显示"]
    MISSVIEW --> MISSCHECK["tf2_echo 完整链失败<br/>分别检查两段局部链"]
    MISSCHECK --> TFFIX["恢复唯一权威动态 TF 源"]

    MODE -- "tf_fault_mode=stale" --> TFFLOW["先周期发布<br/>base_link → camera_link"]
    TFFLOW --> TFSTOP["到时停止刷新动态 TF<br/>节点与 Publisher 保持在线"]
    TFSTOP --> TFAGE{"最后时间戳年龄达到<br/>tf_timeout_sec？"}
    TFAGE -- "是" --> TFSTALE["空间诊断<br/>ERROR + stale"]
    TFSTALE --> STALEVIEW["有限寿命 Marker 消失<br/>RViz 报旧数据/外推错误"]
    STALEVIEW --> STALECHECK["tf2_echo 时间戳停止<br/>age_sec 持续增大"]
    STALECHECK --> TFFIX

    QOSERR -. "执行器无可用传感器数据" .-> TASKBLOCK["Service=false<br/>Action=ABORTED"]
    STALE -. "执行器独立新鲜度检查" .-> TASKBLOCK
    MISSING -. "当前仅独立报警" .-> BOUNDARY["Action 尚未接入 TF 门禁"]
    TFSTALE -. "当前仅独立报警" .-> BOUNDARY

    QOSFIX --> REGRESSION["回归：diagnostics healthy<br/>Service + Action + RViz"]
    FLOWFIX --> REGRESSION
    TFFIX --> REGRESSION
    REGRESSION --> BAG[("rosbag：sensor / diagnostics / task_status<br/>tf / tf_static / Marker")]
```

## 最短定位表

| 诊断状态 | 端点 | 数据/时间戳 | RViz | 首查方向 |
|---|---|---|---|---|
| `qos_mismatch` | `/sensor_state` Publisher 存在 | 业务订阅端从未收到 | TF 画面正常 | Requested/Offered QoS |
| 传感器 `stale` | 节点与 Publisher 存在 | 序号先增长后停止 | TF 画面正常 | 数据 Timer、驱动、上游采集 |
| TF `missing` | TF 发布节点存在 | 完整链从未形成 | 子树断开、Marker 不显示 | 缺失边、frame_id、父子关系 |
| TF `stale` | TF Publisher 存在 | 动态 TF 时间戳先增长后停止 | 目标消失或旧数据错误 | 定位线程、时钟、发布频率 |

恢复后不要只验证故障项；应同时检查两个诊断项均为 `healthy`、完整 TF 链可查、RViz 目标存在，并运行 Service 与 Action 回归。
