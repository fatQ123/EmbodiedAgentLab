# 第 3 周第 7 天：干净终端演练与 v0.3 发布

本图把“当前机器能够运行”收敛为“指定 Git 提交能够从新终端重新构建、演示和回归”。发布标记必须保留实际验收的可执行源码；候选后的文档提交需要另存源码树一致性证据。

```mermaid
flowchart TB
    START(["运行 scripts/verify_ros2_release.sh"]) --> INPUT{"源码 ref 可解析<br/>且证据目录尚不存在？"}
    INPUT -- "否" --> ARGERR["报告参数错误<br/>不覆盖已有证据"]
    INPUT -- "是" --> PIN["解析并记录 source_commit<br/>git archive 导出该提交"]
    PIN --> FRESH["env -i + bash --noprofile --norc<br/>进入全新的源码与构建目录"]
    FRESH --> UNDERLAY["显式 source /opt/ros/jazzy/setup.bash<br/>固定 /usr/bin/python3"]
    UNDERLAY --> BUILD["构建 embodied_interfaces<br/>embodied_comm + embodied_comm_cpp"]
    BUILD --> BUILDCHECK{"构建成功<br/>三个安装前缀属于本轮目录？"}
    BUILDCHECK -- "否" --> FIX["查看对应日志<br/>修复源码或文档后提交"]
    BUILDCHECK -- "是" --> OVERLAY["只 source 本轮 install/setup.bash"]
    OVERLAY --> NORMAL["正常工位：Service 查询 + Action Feedback<br/>执行期间 Service 响应"]
    NORMAL --> CANCEL["40% 取消 → CANCELED<br/>下一件工件 → SUCCEEDED"]
    CANCEL --> FAULTS["运行七个独立 Domain 场景<br/>六类故障 rosbag + 日志 + 中文记录"]
    FAULTS --> REG["运行全部 ROS 测试与仓库测试<br/>Python/C++ 四组通信组合"]
    REG --> REVIEW["核对 summary、测试结果、bag、进程清理<br/>补齐复现说明和能力边界"]
    REVIEW --> GATE{"所有必要验收通过<br/>且发布的可执行源码与候选一致？"}
    GATE -- "否" --> FIX
    FIX --> PIN
    GATE -- "是" --> TAG["本地 annotated tag v0.3<br/>记录候选 SHA、发布 SHA 与证据位置"]
    TAG --> TAGCHECK["核对 v0.3 指向发布提交<br/>候选后仅文档变化时保存源码树一致证据"]
    TAGCHECK --> DONE(["可复现的第三周交付"])

    NORMAL --> LOGS[("正常/取消日志")]
    FAULTS --> BAGS[("七场 MCAP + result.json")]
    REG --> TESTLOGS[("构建、测试与语言组合结果")]
    LOGS --> REVIEW
    BAGS --> REVIEW
    TESTLOGS --> REVIEW
```

## Debug 顺序

1. 构建找不到接口：先查 `embodied_interfaces` 是否在归档提交中，再检查依赖顺序和本轮安装前缀。
2. 只有旧终端能运行：检查 `.bashrc`、Conda、旧 `AMENT_PREFIX_PATH` 是否遮住问题；以脚本的新环境结果为准。
3. 演示失败：先查本轮正常工位日志，确认 Domain、服务发现、目标参数和传感器新鲜度。
4. 故障矩阵失败：按第 6 天的 `result.json → diagnostics → Graph → Launch → rosbag` 顺序定位。
5. 测试汇总有失败：核对实际测试框架结果，不能把 `colcon test` 启动成功当作全部断言通过。
6. 验收后修改了可执行源码：重新提交并从新 SHA 演练；仅补文档/精简证据时，保存源码树哈希一致性证据。用 `git rev-parse 'v0.3^{commit}'` 确认最终标记。

对应实现与记录：

- [干净环境验收脚本](../../scripts/verify_ros2_release.sh)
- [四组语言组合验收](../../scripts/verify_ros2_language_pairs.py)
- [第 7 天实验与发布说明](../labs/week03-day7-release.md)
