# 阶段⑥：双语言对照、源码复现与 v0.2 验收

## 本轮增量

- 新增独立 `embodied_comm_cpp` 包，C++17 实现传感器和订阅监控器；没有复制官方示例实现，也没有改变外部学习仓库。
- 两种发布者使用相同 JSON 协议：`seq` 从 1 递增，`value` 按 0～100 循环；默认 2 Hz，支持话题重映射。
- 根据实验文档补充明确范围：`publish_rate` 必须在 `[0.1, 100]` Hz 且有限，仅启动时生效。Python/C++ 都测试周期换算、范围边界、非法参数和连续消息。阶段①～⑤记录的是当时实现，本条是最终约束。
- Python 保持完整三节点与服务；C++ 只做发布订阅对照，监控器不复制 Python 的超时检测、任务状态订阅或服务。
- 两个包和主项目版本号准备为 `0.2.0`。版本号变更不等于已发布标签，发布状态见本文末尾。

## 构建与运行

前置环境：Ubuntu 24.04、ROS 2 Jazzy；系统 Python 3.12、colcon、g++、CMake，项目 Conda 环境为 `embodied-agent-lab`。构建工具和 ROS CLI 使用系统 Python，Conda 只激活不保证改变其解释器。

C++ JSON 解析使用系统 JsonCpp（`libjsoncpp-dev`），测试使用 `ament_cmake_gtest`。首次缺依赖时通过系统包管理器安装实际缺失组件；不要复制外部构建产物或用 pip 安装 rclpy。

```bash
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
cd /home/fatbro/workspace
./scripts/check_ros2_lab.sh
g++ --version
cmake --version
ros2 pkg prefix rclcpp
ros2 pkg prefix ament_cmake_gtest
cd ros2_ws
colcon build --packages-select embodied_comm embodied_comm_cpp \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash
ros2 pkg executables embodied_comm
ros2 pkg executables embodied_comm_cpp
ros2 launch embodied_comm three_nodes.launch.py
```

另一个终端激活同一环境，source 系统及工作空间后，等待执行器出现最新读数再调用：

```bash
ros2 service call /execute_task std_srvs/srv/Trigger "{}"
```

预期成功，并在监控器看到同一次任务结果。Ctrl+C 关闭 Launch 全部三个节点。无数据失败实验需先关闭传感器，再重启执行器清空缓存，参见 [阶段③](week02-stage3.md)。

## Python/C++ 学习卡

参考为 `ros2/examples` 的 Jazzy 基线提交 `07008852303f2a35a91c65d78046b274a35477ea`，许可证 Apache 2.0。外部工作区当前分支为 `lab/jazzy-pub-sub`，已有用户学习修改，保留原样。主项目独立实现沿用 MIT 许可证；参考的是 ROS 接口用法。

| 概念 | Python 主项目 | C++ 对照包 |
|---|---|---|
| 构建入口 | `setup.py` 的 `console_scripts` → 模块 `main` | `CMakeLists.txt` 的 `add_executable` → 编译后的 `main` |
| 安装定位 | `setup.cfg` 安装到 `lib/embodied_comm` | `install(TARGETS)` 安装到 `lib/embodied_comm_cpp` |
| 节点对象 | `SensorSimulator(Node)` | `SensorSimulator : public rclcpp::Node` |
| 定时回调 | `create_timer(period, self.publish_reading)` | `create_wall_timer(duration, std::bind(..., this))` |
| 消息对象 | `String(data=...)` | `std_msgs::msg::String` 栈对象，赋值后发布 |
| 订阅回调 | 传入绑定方法 `self.receive` | 捕获 `this` 的 lambda 调用成员函数 |
| 内部状态 | Python 对象字段 | 类成员，`std::optional<Reading>` 表示还没有数据 |
| JSON | 标准库 `json` | JsonCpp，需要声明链接依赖 |
| 生命周期 | 持有属性引用，finally 销毁节点 | 发布器/订阅器/定时器的 `SharedPtr` 持有共享所有权，节点销毁时释放 |
| 修改后生效 | 符号链接安装下修改模块后重启；入口/安装配置改变仍需重建 | 源码修改必须重新编译再启动 |
| 测试 | pytest | GoogleTest，经 ament 注册后才能被 colcon 执行 |

调用链：

```text
Python: ros2 run → console_scripts → main → Node → timer → JSON → publish
C++:    ros2 run → 安装的 ELF → main → make_shared<Node> → wall_timer → JSON → publish
两端:   DDS 发现同话题/类型/兼容 QoS → 回调 → 保存最新读数 → 日志
```

`SharedPtr` 用于管理对象寿命，不是跨进程共享 Python/C++ 对象。两种进程交换的是相同 ROS 消息类型的序列化内容。

`std::bind(&SensorSimulator::publish_reading, this)` 把具体对象绑定到成员函数，形成定时器可调用的无参回调。订阅 lambda 中的 `const String &` 是只读引用，避免把消息值复制给回调；不能在回调结束后保留该引用。本实现提取序号和数值，保存自己的副本。

所有发布/订阅用深度 10、可靠、易失 QoS。队列深度不是频率；类型相同也不能弥补话题名不一致。JSON 字段含义一致，空白和字段顺序不影响解析。Python 整数任意精度，C++ 序号用 uint64，本实验生成的正常序号在双方范围内。

### 三改一坏的主项目对照

1. 改话题：两种节点均接受 `--ros-args -r /sensor_state:=/其他名称`。
2. 改频率：两种发布者均接受 `--ros-args -p publish_rate:=5.0`。
3. 加可观测信息：两种语言均日志输出重映射后的真实话题、频率和递增读数。
4. 一坏：只将订阅者移到 `/sensor_state_wrong`，验证其无消息；重启订阅者恢复话题，日志继续接收。

## 实际测试结果

本机两个包构建成功，C++ 启用 `-Wall -Wextra -Wpedantic`，构建无代码警告。53 项 Python 测试和 5 项 C++ GoogleTest 全部通过。`colcon test-result` 汇总为 59：包含 CTest 的外层测试记录，不能把该数字当成 59 个独立功能用例。原环境诊断的 18 项 unittest 也通过。

- [ROS 测试汇总](evidence/week02-stage6/tests.log)
- [环境诊断回归](evidence/week02-stage6/doctor-tests.log)

首次跨进程测试在沙箱中出现 UDP socket `Operation not permitted`，单进程测试可运行但进程间发现失败。获准在沙箱外运行后通过，未把环境限制算成业务节点修复。

### 主项目四组通信

以下是脚本发起、带断言的真实进程通信，明确属于自动化实验，不冒充用户手工操作。每组先检查 1 发布端和 1 业务订阅端，再创建临时观察订阅采样测频；订阅者日志另作实际接收证据。

| 组合 | 正常实测 Hz（目标 5） | 错连→修复 | 证据 |
|---|---:|---|---|
| Python → Python | 4.995 | 无接收→恢复 | [结果](evidence/week02-stage6/language-pairs/rclpy-to-rclpy/result.json) |
| C++ → C++ | 5.006 | 无接收→恢复 | [结果](evidence/week02-stage6/language-pairs/rclcpp-to-rclcpp/result.json) |
| Python → C++ | 5.000 | 无接收→恢复 | [结果](evidence/week02-stage6/language-pairs/rclpy-to-rclcpp/result.json) |
| C++ → Python | 5.000 | 无接收→恢复 | [结果](evidence/week02-stage6/language-pairs/rclcpp-to-rclpy/result.json) |

每个目录包含发布日志、正常/错误/修复订阅日志。错误阶段观察端仍收到正常传感器数据，只有业务订阅者接错；修复只重启订阅者，不靠改发布端掩盖根因。

重跑命令（需要本机 DDS 网络权限，四个指定域需空闲）：

```bash
source /opt/ros/jazzy/setup.bash
source /home/fatbro/workspace/ros2_ws/install/setup.bash
cd /home/fatbro/workspace
/usr/bin/python3 scripts/verify_ros2_language_pairs.py \
  --output /tmp/新的双语言验收目录 --domain-start 194
```

你手工对照时，每次只启动一对节点。例如先 C++ 发布、Python 订阅，再反向：

```bash
# 两个终端分别执行，均先加载同一工作空间
ros2 run embodied_comm_cpp sensor_simulator --ros-args -p publish_rate:=5.0
ros2 run embodied_comm status_monitor
# Ctrl+C 结束上一组后，两个终端分别执行
ros2 run embodied_comm sensor_simulator --ros-args -p publish_rate:=5.0
ros2 run embodied_comm_cpp status_monitor
```

## 完成条件与范围

| v0.2 条件 | 证据 |
|---|---|
| 一个 Launch 启动三个业务节点 | [阶段④](week02-stage4.md)与真实 Launch 测试 |
| 频率可配置，执行器/监控器收数据 | [阶段①](week02-stage1.md)、[阶段②](week02-stage2.md)、本轮双语言实测 |
| 无数据失败、有数据成功，任务状态到监控器 | [阶段③](week02-stage3.md)及服务测试 |
| 传感器停止后监控报警 | 阶段①停止/恢复日志和自动化测试 |
| 正常/错误/修复证据完整 | [阶段⑤](week02-stage5.md)，含真实 rqt_graph 截图与服务响应 |
| 非法参数、服务分支、实际通信测试 | 本轮 53 项 Python 与 5 项 C++ 测试 |
| C++ 独立实现与四组通信 | 本文学习卡和四组自动化实测 |
| 已提交源码复现 | 全新源码构建、53 项 Python + 5 项 C++、18 项原项目测试及四组通信均通过，见下方证据 |

限制：模拟读数没有物理单位；任务只检查缓存值，不检查数据新鲜度或零件身份；不执行真实动作，不提供自动恢复；任务状态为易失消息，晚加入的监控器不补历史结果。非法启动参数会使对应节点退出，Launch 不自动修复其他节点。C++ 包仅为发布订阅对照，不是另一个完整三节点系统。

## 源码复现与发布记录

使用 `scripts/verify_ros2_release.sh` 从当前 Git HEAD 导出全新目录，不复制工作区中的未提交文件、build、install。它重新构建、运行两包测试与原项目测试，并再次运行四组语言通信；测试中实际启动安装后的 Launch、读取参数、调用服务并检查监控结果。

```bash
# 从仓库根目录执行，需要已有代码提交以及系统 ROS 依赖
bash scripts/verify_ros2_release.sh /tmp/新的源码验收目录
```

主项目的阶段⑥工程验收已完成。提交 `fe8ffdc` 包含三节点系统和阶段①～⑤证据；提交 `5d2b4b8aa052255ec60153402447e4583cd2948e` 包含 C++ 对照及源码复现流程。

从 `5d2b4b8` 导出的源码在 `/tmp/embodied-v02-clean-5d2b4b8` 全新构建：53 项 Python、5 项 C++、18 项原项目测试通过；四组语言组合的正常、错连、修复也重新通过。包定位确认指向新目录的 install，不依赖主项目旧 build/install。

- [源码提交编号](evidence/week02-stage6/clean-source/source-commit.txt)
- [全新构建日志](evidence/week02-stage6/clean-source/build.log)
- [完整测试日志](evidence/week02-stage6/clean-source/test.log)
- [测试汇总](evidence/week02-stage6/clean-source/test-result.log)
- [从源码启动的服务成功结果](evidence/week02-stage6/clean-source/launch-normal-result.json)
- [从源码启动的错连失败结果](evidence/week02-stage6/clean-source/launch-wrong-result.json)
- [四组重新实测结果](evidence/week02-stage6/clean-source/language-pairs/)

后续只补充本轮验收证据与文档，不改变已验证的业务源码。本轮采用本地发布流程：验收后合并到本地 main 并创建带说明的 v0.2 标签，不包含远端推送或 GitHub Release。可用以下命令核对实际本地发布状态：

```bash
git log --oneline --decorate -5
git show --no-patch v0.2
git status --short
```

官方原版四组对照按用户本轮要求暂缓，不将主项目独立实现的四组结果冒充官方示例验收。

官方固定基线的四个包已在临时目录独立构建；第一组原版 Python 通信收到递增消息，但 Ctrl+C 出现 `KeyboardInterrupt`，ros2 run 返回 254。该版本示例没有捕获中断，主项目则在 finally 清理资源。这是实测的生命周期差异。其余原版组合尚未运行完成，不能据此宣布原实验文档所有学习项完成。


## 你下一步做什么

1. 按本文构建两个包，运行一次三节点 Launch 和服务调用。
2. 在两个终端亲自运行 C++ 发布 → Python 订阅，然后交换方向，说明为何不用额外写语言转换节点。
3. 用自己的话解释：话题错名时三个进程为什么仍存在；SharedPtr 管理什么；停止传感器后服务为什么可能仍成功。
4. 官方原版实验按本轮决定暂缓，之后需要时再补全；不自动进入第 3 周或连接真实硬件。
