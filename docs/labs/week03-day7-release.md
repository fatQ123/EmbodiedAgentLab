# 第 3 周第 7 天：干净终端完整演练与 v0.3

> 发布分支见[第 7 天流程图](../flowcharts/week03-day07-release.md)，跨天关系见[第 1～7 天总流程图](../flowcharts/week03-overall.md)。

## 完成目标

用一个确定的 Git 提交重新构建第三周系统，运行正常质检、取消恢复、六类故障和全部测试，保存验收证据，再创建本地 `v0.3` 标记。发布提交的可执行源码须与实际演练候选一致。已有终端、旧 `build/install` 和未提交文件不能成为隐含依赖。

## 干净终端的含义与前置条件

验收脚本通过 `git archive` 导出指定提交，用 `env -i` 和 `bash --noprofile --norc` 启动新 shell，显式加载 `/opt/ros/jazzy/setup.bash`，在新的源码目录构建三个 ROS 包。ROS Python 部分使用 `/usr/bin/python3`；仓库环境诊断工具的测试按本项目说明运行。

本轮仍使用主机已安装的 Ubuntu/ROS 2 Jazzy、colcon、Python、编译器、pytest、GoogleTest 和 MCAP 插件；它验证终端与工作空间隔离，不等于从空白操作系统安装全部依赖。GUI 的 RViz 观察另需可用的桌面会话。依赖安装和图形界面步骤见项目 README 与[第 2 天实验](week03-day2-tf-rviz.md)。环境诊断报告通过本轮归档源码模块生成，不依赖已安装的旧 CLI。

## 一键复现

先确保待验收功能已进入 Git 提交；脚本按提交导出源码，不会把未提交修改混进发布证据。以下输出目录必须尚不存在：

```bash
cd /home/fatbro/workspace
bash scripts/verify_ros2_release.sh /tmp/embodiedagentlab-v0.3-acceptance

# 发布后固定 v0.3 复现；使用另一个尚不存在的输出目录
bash scripts/verify_ros2_release.sh /tmp/embodiedagentlab-v0.3-replay refs/tags/v0.3
```

参数为 `OUTPUT_DIR [REF]`，省略 `REF` 时使用 `HEAD`。发布后按 `refs/tags/v0.3` 复现，新输出记录的提交 SHA 应与 `git rev-parse 'refs/tags/v0.3^{commit}'` 一致。显式使用标签路径以避免同名分支歧义；首次验收的候选 SHA 单独保留。

演练依次检查：

1. `embodied_interfaces`、`embodied_comm`、`embodied_comm_cpp` 从空构建目录成功安装，接口可导入；
2. 正常工位的 Service 即时查询、Action 阶段反馈、执行期间的 Service 响应；
3. 收到首个达到或超过 40% 阈值的反馈后请求取消，进入 `CANCELED`，下一件工件重新进入 `SUCCEEDED`；
4. QoS 不匹配、话题停止、TF 缺失、TF 过期、Service 超时、Action 取消和节点崩溃七场采集；
5. 全部 ROS 包测试、仓库级测试和 Python/C++ 四组通信组合；
6. rosbag 可读取、中文故障记录完整、测试断言通过且本轮进程正常清理。

## 证据与验收结果

完整输出保存在本轮指定目录。故障采集细节见[第 6 天说明](week03-day6-automated-evidence.md)。

```text
验收目录/
├── source/                       # git archive 导出的源码及本轮构建
├── source-commit.txt             # 实际演练的候选 SHA
├── clean-environment.log         # 干净 shell 的环境记录
├── build.log / prefixes.log      # 三包构建及安装前缀
├── interface-import.log / doctor.json
├── normal/
│   ├── normal-demo.json
│   └── launch.log
├── normal-demo.log               # 正常质检、取消与恢复输出
├── faults/
│   ├── 各场景/                   # 七场 MCAP、客户端/Launch 日志
│   ├── summary.json / 故障记录.md
│   └── 三份回归日志              # ROS 测试、汇总、仓库测试
├── language-pairs/               # 四组语言通信结果
└── status.txt                    # 本轮最终通过/失败
```

下表在最终演练后填写，不能用历史结果替代本轮结果。

| 验收项 | 本轮结果 | 证据 |
|---|---|---|
| 已测试候选 SHA | 待最终演练填写 | `source-commit.txt` |
| 干净目录构建三个 ROS 包 | 待最终演练填写 | `build.log`、`prefixes.log` |
| 正常 Service/Action 与运行中即时查询 | 待最终演练填写 | `normal/normal-demo.json`、`normal-demo.log` |
| 取消时限与取消后恢复 | 待最终演练填写 | `normal/normal-demo.json`、`normal-demo.log` |
| 六类故障、七场 MCAP | 待最终演练填写 | `faults/summary.json` 与各场 `bag-info.log` |
| 全部 ROS 测试 | 待最终演练填写 | `faults/colcon-test-result.log` |
| 仓库级测试 | 待最终演练填写 | `faults/repository-tests.log` |
| Python/C++ 四组组合 | 待最终演练填写 | `language-pairs/*/result.json` |
| 本轮进程清理 | 待最终演练填写 | 演练结束进程检查 |
| 本地 annotated tag `v0.3` | 待最终验收后创建 | tag 对象及发布提交；候选/发布源码一致性证据 |

`colcon test-result` 的汇总记录可能包含 CTest 包装项；独立测试数量以 pytest、GoogleTest 和仓库测试各自结果为准，避免重复计数。

## 本轮修复与调试教训

| 发现的问题 | 修复与判断依据 |
|---|---|
| 旧发布脚本只选 Python/C++ 包，漏掉 Action 接口包 | 使用 `--packages-up-to embodied_comm embodied_comm_cpp` 构建依赖，并核对三包安装前缀和接口导入。旧 overlay 中已有接口不能证明干净构建成功。 |
| 诊断调用漏掉 `doctor` 子命令 | 从归档源码执行 `/usr/bin/python3 -m embodied_agent_lab.doctor doctor --skip-network --json`，生成实际 JSON 报告。 |
| 超时命令的日志被重复拼接 | `communicate()` 重试返回完整缓存输出，不再把 `TimeoutExpired.output` 与它重复相加，保留真实事件次数和顺序。 |
| rosbag 可读被误当作 Recorder 成功退出 | 同时核对 Recorder 干净退出、停止方式与 bag 可读性；强制结束或非正常退出必须使场景失败。 |
| Day 4 观察器已断流，但执行器仍可能消费积压样本 | DDS 消费者有独立队列。先确认停止注入与执行器收到最后序号，再等待其接收时钟超过新鲜度阈值，最后验证 Service 拒绝旧缓存。 |
| Day 5 Launch 壳进程退出慢，容易掩盖节点状态 | 按节点名核对正常退出；崩溃场景单独核对传感器退出码 1。所有预期节点退出已证实后，只回收本次残留 Launch PID，并保存清理报告。 |
| 越界 Action 结果与接口契约不一致 | 失败 Action Result 的 `sensor_seq` 统一为 `0`；`/task_status` JSON 仍保留越界样本的实际序号供定位，无合法样本时继续为 `null`。 |

这些修复改变的是构建、接口契约或验收判据。表中的修复说明不代表当前候选已通过全部验收；通过状态以本轮完整演练日志为准。

## 发布标记

所有必要验收通过后，核对证据中的候选 SHA。如修改了运行代码、测试或构建配置，应对新提交重新演练；若后续提交只补充文档与精简验收证据，可比较候选与发布提交的可执行源码树哈希，并保存一致性结果。候选 SHA 和最终发布 SHA 分开记录，避免在被标记的文档里填写自身提交 SHA 形成循环。

创建 annotated tag 时明确使用通过上述检查的发布提交：

```bash
git tag -a v0.3 <发布提交SHA> -m "v0.3: 第三周 Action、TF、diagnostics 与六类故障验收通过"
git show --no-patch refs/tags/v0.3
git rev-parse 'refs/tags/v0.3^{commit}'
```

标记仅在本地创建。完整 MCAP 与生成的构建目录保存在验收输出目录；提交精简日志、中文说明和证据索引，便于复查而不把运行产物混入源代码。

## 工业质检线推演

设想集成工程师把该版本交给另一班组。班组从干净终端构建 `v0.3`，让 `WP-001` 完成质检；处理 `WP-002` 时模拟安全门打开，在反馈达到或超过 40% 阈值后请求取消，等待 `CANCELED` 后提交 `WP-003` 验证工位恢复。短时状态查询由 Service 承担，持续工序由 Action 提供进度和终止协议。本场景只演练软件任务终止，真实安全门联锁与硬件急停需独立实现。

若测量值突然消失，班组通过 ROS Graph、QoS、新鲜度诊断和 Launch 日志区分断流与崩溃；若检查区域不显示，则沿静态/动态 TF 链定位缺失或过期。自动 rosbag 和中文记录把这次问题交给下一班工程师，固定版本 SHA 则让两人验证同一套软件。这对应工业交付中的版本追溯、工厂验收与故障复盘流程。

当前系统已验证通信、任务调度、空间显示、健康报警、故障注入和证据采集。传感器是测量信号替身，Action 尚未控制机械臂，TF 报警尚未接入任务门禁；视觉缺陷识别、PLC 接入、硬件急停和真实分拣仍需后续工程实现。客户端取消请求本身也不能替代硬件安全联锁。

新鲜度门禁按执行器收到消息的单调时钟计时，不代表测量源采集时间；DDS 积压样本可能晚到，因此测试须先核对最后样本已消费。工业升级需要源时间戳、时钟同步和端到端延迟门禁。`--cancel-at 40` 是反馈阈值而非精确 40% 停止；普通 Linux/ROS 2 调度可能使反馈跨过阈值，不具备硬实时安全停止保证。
