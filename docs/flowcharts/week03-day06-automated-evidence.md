# 第 3 周第 6 天：自动证据流水线

本图描述六类故障如何展开为七次隔离运行，以及 rosbag、文件日志、机器判据和中文报告如何汇合。

```mermaid
flowchart TB
    START(["运行 week03_day6_evidence"]) --> VALIDATE{"工作空间、输出目录、<br/>Domain 范围有效？"}
    VALIDATE -- "否" --> ARGERR["退出码 2<br/>不覆盖已有证据"]
    VALIDATE -- "是" --> SELECT["选择场景<br/>默认七个全部运行"]
    SELECT --> MATRIX{"故障矩阵"}
    MATRIX --> QOS["QoS 不匹配"]
    MATRIX --> STOP["话题停止"]
    MATRIX --> TFMISS["TF 缺失"]
    MATRIX --> TFSTALE["TF 过期"]
    MATRIX --> SERVICE["Service 超时"]
    MATRIX --> ACTION["Action 取消 + 恢复"]
    MATRIX --> CRASH["节点崩溃"]

    QOS --> ISOLATE
    STOP --> ISOLATE
    TFMISS --> ISOLATE
    TFSTALE --> ISOLATE
    SERVICE --> ISOLATE
    ACTION --> ISOLATE
    CRASH --> ISOLATE

    subgraph RUN["每个场景的独立采集事务"]
        ISOLATE["独立 ROS_DOMAIN_ID<br/>新建场景目录"] --> RECORDER["先启动 rosbag Recorder<br/>MCAP + /rosout + 业务 Topics"]
        RECORDER --> LIVE["系统启动前创建常驻 diagnostics 观察器<br/>显式指定 DiagnosticArray 类型"]
        LIVE --> LAUNCH["启动 week03_day5.launch.py<br/>RViz=false"]
        LAUNCH --> READY{"五个节点就绪？"}
        READY -- "是" --> INJECT["等待定时注入<br/>或执行 Service/Action Client"]
        READY -- "否：记失败并继续留证" --> INJECT
        INJECT --> SNAP["采集 node/topic/service/action<br/>diagnostics/TF 快照"]
        SNAP --> STOPREC["先停止观察器与 Recorder<br/>刷新 MCAP"]
        STOPREC --> STOPLAUNCH["再让 Launch 干净退出"]
        STOPLAUNCH --> BAGINFO["ros2 bag info<br/>消息数必须大于 0"]
        BAGINFO --> ASSERT["核对命令退出码与关键日志<br/>Recorder/Launch 必须干净退出"]
        ASSERT --> RESULT["result.json"]
    end

    RESULT --> MORE{"还有场景？"}
    MORE -- "是；即使前场失败" --> MATRIX
    MORE -- "否" --> REGRESSION["colcon test + test-result<br/>仓库 Python 测试"]
    REGRESSION --> MERGE["合并七场结果与六类知识模板"]
    MERGE --> JSON["summary.json<br/>供 CI 解析"]
    MERGE --> CN["故障记录.md<br/>七段式中文报告"]
    JSON --> FINAL{"场景与回归全通过？"}
    CN --> FINAL
    FINAL -- "是" --> OK["退出码 0"]
    FINAL -- "否" --> FAIL["退出码 1<br/>保留全部失败证据"]
```

## Debug 顺序

1. `result.json` 先告诉你失败的是命令退出码、关键字还是空 bag。
2. `diagnostics-live.log` 用于判断健康状态是否真的发生转换。
3. `sensor-topic.log` 和 `nodes.log` 区分 QoS、断流与进程消失。
4. `launch.log` 用于确认注入参数、异常栈和进程退出码。
5. `bag-info.log` 证明 bag 可读取；再用 `bag play` 对齐消息时间线。
6. 故障场景通过后仍要看回归日志，防止修复破坏正常路径。
