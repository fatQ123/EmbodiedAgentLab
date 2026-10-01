# 第 3 周第 5 天：Service 超时、Action 取消与节点崩溃

本图把三种故障按层次分开：Service 超时是客户端时限，Action 取消是目标生命周期转换，节点崩溃是进程和 DDS 端点消失。

```mermaid
flowchart TB
    START(["启动 week03_day5.launch.py"]) --> MODE{"选择实验"}

    MODE -- "Service 延迟" --> REQUEST["客户端调用 /execute_task"]
    REQUEST --> DELAY["Server 回调延迟<br/>fault_service_delay_sec"]
    DELAY --> DEADLINE{"客户端截止时间<br/>先到达？"}
    DEADLINE -- "是" --> TIMEOUT["客户端退出码 6<br/>结果暂时未知"]
    TIMEOUT -. "不会取消 Server 回调" .-> SERVERDONE["Server 随后完成<br/>发布一次 /task_status"]
    SERVERDONE --> SERVCHECK["检查 Server 存活<br/>核对终态与副作用"]
    SERVCHECK --> SERVFIX["关闭延迟<br/>短任务继续用 Service"]

    MODE -- "Action 取消" --> GOAL["发送 /execute_task_long Goal"]
    GOAL --> FEEDBACK["preparing → inspecting<br/>持续 Feedback"]
    FEEDBACK --> FORTY{"进度达到 40%？"}
    FORTY -- "是" --> CANCELREQ["客户端发送 Cancel Request"]
    CANCELREQ --> ACCEPT{"Server 接受取消？"}
    ACCEPT -- "是" --> CANCELED["Goal=CANCELED<br/>success=false"]
    CANCELED --> RELEASE["释放单工位占用<br/>发布一次 /task_status"]
    RELEASE --> NEXT["提交下一件工件"]
    NEXT --> SUCCEEDED["Goal=SUCCEEDED<br/>恢复生产"]

    MODE -- "传感器崩溃" --> HEALTHY["sensor_simulator 正常发布"]
    HEALTHY --> CRASH["到时抛出未捕获 RuntimeError<br/>进程 exit code 1"]
    CRASH --> GRAPH["Node 与 Publisher<br/>从 ROS Graph 消失"]
    GRAPH --> LOST["传感器诊断<br/>ERROR + publisher_lost"]
    LOST --> STALECACHE["task_executor 缓存超过<br/>sensor_timeout_sec"]
    STALECACHE --> BLOCK["Service=false<br/>Action 结束检查将 ABORT"]
    CRASH -. "不影响独立空间节点" .-> RVIZ["RViz TF 与 Marker 正常"]
    LOST --> CRASHFIX["关闭崩溃参数并重启<br/>等待新数据 healthy"]

    SERVFIX --> REGRESSION["回归：Service / Action / diagnostics / TF"]
    SUCCEEDED --> REGRESSION
    CRASHFIX --> REGRESSION
    REGRESSION --> EVIDENCE[("日志 + /task_status + /diagnostics<br/>rosbag 时间线")]
```

## 调试映射

| 现象 | ROS Graph | 终态或诊断 | 首查方向 |
|---|---|---|---|
| Service 客户端超时 | Server 仍存在 | 客户端无响应，Server 稍后可能发布终态 | 客户端截止时间、Server 延迟、幂等性 |
| Action 被取消 | Action Server 存在 | `CANCELED`，一条失败 `/task_status` | Cancel Request、Server 接受与资源释放 |
| 传感器节点崩溃 | Node 与 Publisher 消失 | `publisher_lost`，缓存随后过期 | Launch 退出码、异常栈、进程监管 |

Service 超时不能根据客户端表象推断 Server 没有执行；Action 取消必须等待协议终态；节点崩溃则需要把 ROS Graph、诊断和 Launch 进程日志放在同一条时间线上。
