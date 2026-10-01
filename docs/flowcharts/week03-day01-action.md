# 第 3 周第 1 天：长任务 Action、取消与恢复

这张图从 `inspection_demo` 客户端出发，覆盖目标校验、单工位并发保护、阶段反馈、取消、成功/中止终态以及取消后的恢复生产。图中陈旧数据分支是第 3 天后来加到同一个执行器中的保护，特意标出以保持流程图与当前代码一致。

```mermaid
flowchart TD
    A["inspection_demo 解析参数<br/>task_name、duration、cancel_at"] --> B{"5 秒内发现<br/>/execute_task_long？"}
    B -- "否" --> U["退出码 5：接口不可用<br/>检查 action list 和 action info"]
    B -- "是" --> C["发送 ExecuteTask Goal"]
    C --> D{"5 秒内收到目标响应？"}
    D -- "否" --> U
    D -- "是" --> E{"服务端目标校验"}
    E -- "名称为空或时长非法" --> R["拒绝目标<br/>退出码 4<br/>不执行、不发布 Action 终态"]
    E -- "工位已被预留" --> R
    E -- "合法且工位空闲" --> F["预留单工位<br/>记录活动 Goal<br/>启动长任务"]

    S0["sensor_simulator"] -- "/sensor_state" --> S1["互斥回调串行更新<br/>latest_reading 和接收时间"]
    S1 -. "结束时读取原子快照" .-> K

    F --> G{"收到已接受的取消请求？"}
    G -- "是" --> X["goal_handle.canceled<br/>Result: success=false、sensor_seq=0<br/>task_status: sensor_seq=null"]
    G -- "否" --> H{"达到 duration？"}
    H -- "否" --> I["发布单调反馈<br/>preparing → inspecting → validating<br/>配置周期不超过 0.2 秒，实际受调度影响"]
    I --> J{"达到 cancel_at？"}
    J -- "是" --> J1["客户端只发送一次取消请求"]
    J1 --> J2{"仍是当前活动 Goal？"}
    J2 -- "是：接受" --> G
    J2 -- "否：拒绝" --> H
    J -- "否" --> G

    H -- "是" --> K["发布 99% validating<br/>检查结束时的传感器快照"]
    K --> L{"传感器数据状态"}
    L -- "没有合法读数" --> N["ABORTED<br/>Result sensor_seq=0<br/>task_status sensor_seq=null"]
    L -- "数据过期：第 3 天新增" --> N
    L -- "value 不在 0～100" --> O["ABORTED<br/>Result sensor_seq=0<br/>task_status 保留越界样本序号"]
    L -- "新鲜且范围有效" --> P["发布 100% completed<br/>SUCCEEDED<br/>返回最新 sensor_seq"]

    X --> Z["设置 ROS Action 终态<br/>另发布一次 /task_status<br/>finally 释放工位"]
    N --> Z
    O --> Z
    P --> Z
    Z --> Q{"客户端最终状态"}
    Q -- "SUCCEEDED" --> Q0["退出码 0"]
    Q -- "CANCELED" --> Q3["退出码 3"]
    Q -- "ABORTED 或失败" --> Q2["退出码 2"]
    Z --> REC["提交下一件 WP-003<br/>验证工位已恢复"]

    F -. "MultiThreadedExecutor 并行处理" .-> SV["/execute_task 快速 Service"]
    SV --> SV1["读取同一传感器快照<br/>立即响应并发布自己的 task_status"]
```

## 最短调试路径

```text
找不到 Action
  → source install/setup.bash
  → ros2 action list -t
  → ros2 action info /execute_task_long

目标被拒绝
  → 检查空 task_name、duration 范围、是否已有活动目标

反馈停止或取消不生效
  → 同时检查客户端反馈和 task_executor 日志
  → 确认多线程执行器仍运行、目标仍是当前活动 Goal

终态异常
  → 对照 Action 状态、Result、/task_status、客户端退出码
  → 检查 /sensor_state 是否存在、越界或过期

取消后工位卡死
  → 立即提交 WP-003
  → 若被拒绝，检查 finally 是否释放 _goal_reserved
```

对应实现与证据：

- [Action Server 与快速 Service](../../ros2_ws/src/embodied_comm/embodied_comm/task_executor.py)
- [演示客户端](../../ros2_ws/src/embodied_comm/embodied_comm/inspection_demo.py)
- [自定义 Action 接口](../../ros2_ws/src/embodied_interfaces/action/ExecuteTask.action)
- [第 1 天实验记录](../labs/week03-day1-action.md)
