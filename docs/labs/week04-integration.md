# v0.4：两关节机械臂与交互式 CLI

2026-10-08 开发收尾版。范围为两关节模型、C++ 合成关节状态、运行时调姿、TF/RViz 运动学可视化及终端菜单。无界面功能已检查；CLI 新增图形入口尚未收到人工验收反馈。第五周的控制器、Gazebo、模型推理和训练不在本版本内。

## 模块与数据流

| 位置 | 职责 |
|---|---|
| `ros2_ws/src/embodied_arm_description/` | Xacro、RViz 配置、独立模型入口及已有模型测试 |
| `ros2_ws/src/embodied_arm_cpp/` | C++ 合成状态、统一 launch、Python 原子调姿入口 |
| `src/embodied_agent_lab/arm_cli.py` | 中文菜单、命令解析、自有进程管理与 ROS 观察 |
| `scripts/arm_cli.sh` | 加载已有系统 ROS 和指定安装目录，进入 CLI |
| `ros2_ws/build/`、`install/`、`log/` | 统一 ROS 构建、安装与 colcon 日志，不提交 Git |

```text
Xacro（展开一次） ─┬─→ C++：读取关节顺序和限位
                  └─→ robot_state_publisher
CLI 调姿 → 原子参数服务 → C++ ─┐
GUI 关节滑块 ──────────────────┴─→ /joint_states → robot_state_publisher → TF → RViz
                                状态源二选一                           用户启用
```

统一入口是 `embodied_arm_cpp demo.launch.py`。关节顺序为 `joint1、joint2`，沿 `base_link → tool0` 链读取；角度 rad，速度 rad/s。固定模式的 `velocity`、`effort` 为空，正弦模式发布解析速度，`effort` 仍为空。这些是合成状态，不是传感器实测或控制反馈。

`robot_description` 来自同一次 Xacro 展开，交给 C++ 与 `robot_state_publisher`。C++ 不另发 TF，不支持 `use_sim_time=true`。模型尺寸、关节轴和正运动学见[模型说明](week04-stage1-description.md)。

| 节点参数 | 默认值 | 行为 |
|---|---|---|
| `mode` | `static` | `static` 固定姿态；`sine` 正弦运动；仅启动时设置 |
| `rate` | `20.0` | 发布频率，0.1–100 Hz；仅启动时设置 |
| `positions` | `[0.0, 0.0]` | 固定角度或正弦中心，支持运行时整体更新 |
| `amplitudes` | `[0.5, 0.5]` | 非负正弦振幅；仅启动时设置 |
| `frequency` | `0.1` | 正弦频率 Hz；仅启动时设置 |

两数组必须为长度 2 的有限浮点数组。节点根据 URDF 校验限位；正弦模式还校验完整摆动范围、速度上限和每周期至少 10 个发布样本。拒绝请求不会覆盖上一合法姿态，不静默截断输入。正弦模式更新 `positions` 只改变中心，固定姿态更新直接重定位，不提供平滑轨迹。

## 构建与运行

使用已安装的 `/opt/ros/jazzy` 和系统 Python。依赖下载安装由用户手动完成；不使用历史解包副本。首次检出没有构建产物时，在唯一 ROS 工作空间构建现有五个包：

```bash
cd /home/fatbro/workspace/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --base-paths src --executor sequential \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 -DBUILD_TESTING=OFF
cd ..
```

`install` 是项目编译产物目录，不是系统依赖安装。已有当前产物时无需为 CLI 重新构建，直接运行：

```bash
bash scripts/arm_cli.sh
bash scripts/arm_cli.sh --help
# 独立实验另选未占用 Domain，也可指定其他第四周构建目录。
bash scripts/arm_cli.sh --domain-id 222 \
  --install-dir ros2_ws/install
```

脚本只在自身进程中加载 Jazzy 与所选目录的 `local_setup.bash`，不重放构建时的其他父工作空间，也不改变调用终端的全局配置。Domain 优先级为显式参数、已有 `ROS_DOMAIN_ID`、默认 222，发现范围为 `LOCALHOST`。相对安装路径以当前目录为基准，默认目录以项目根为基准。缺项时显示手动处理提示，不自动安装或构建。

## CLI 操作

| 编号 | 命令 | 功能 |
|---|---|---|
| 1 | `/start static` | 输入初始角度与发布频率，回车使用默认值 |
| 2 | `/start sine` | 额外设置中心、振幅及正弦频率 |
| 3 | `/start gui` | 用户选择后启动关节滑块 |
| 4 | `/pose 0.5 -0.3` | 原子更新两关节角度或正弦中心；不填参数时逐项输入 |
| 5 | `/zero` | 固定模式回零；正弦模式中心归零，仍会摆动 |
| 6 | `/status` | 显示发布者、关节状态和对应时间戳的 TF |
| 7 | `/logs` | 显示最新日志末尾 40 行及日志路径 |
| 8 | `/stop` | 停止本次演示，保留菜单 |
| 0 | `/quit` | 清理本次子进程并退出 |
| — | `/help` | 显示菜单；参数询问中可用 `/cancel` 取消操作 |

每次启动询问是否启用 RViz，默认否；GUI 来源本身会打开滑块。GUI 模式禁用 `/pose` 和 `/zero`。EOF、Ctrl-C 与 `/quit` 一样清理本次进程。

输入提示会显示参数范围；正弦参数的范围随已填内容变化。当前模型两关节限位都是 `[-π/2, π/2]` rad，速度上限为 `1 rad/s`：

| 参数 | 可用范围与联动规则 |
|---|---|
| 固定角度 | `[-π/2, π/2]`，约 `[-1.570796, 1.570796]` rad |
| 正弦中心 `c` | 必须满足 `下限 + A ≤ c ≤ 上限 - A`；默认振幅 `A=0.5` 时，可输入 `[-1.070796, 1.070796]` rad 内的值 |
| 正弦振幅 `A` | `0 ≤ A ≤ min(c - 下限, 上限 - c)`；中心靠近限位时必须减小振幅 |
| 发布频率 `rate` | `[0.1, 100]` Hz |
| 正弦频率 `f` | `f > 0`，且 `f ≤ rate/10`；每个非零振幅还要求 `f ≤ 速度上限/(2πA)` |
| 运行中调姿 | 固定模式使用关节限位；正弦模式按本次演示的振幅收窄中心范围 |

例如中心 `0`、振幅 `0.5`、发布频率 `20 Hz` 时，正弦频率上限约 `0.318309 Hz`，默认 `0.1 Hz` 合法。中心填 `1.2` 时，振幅必须不大于约 `0.370796 rad`，不能继续使用 `0.5`。零振幅不施加速度约束，但正弦频率仍须满足正数和采样频率约束。小数示例向范围内取值；实际 CLI 从所选构建的模型读取限位并计算提示。

交互输入越界时留在当前问题重输；节点仍负责最终运动与限位校验。参数在范围内不代表环境、服务或 TF 观察一定成功。

2026-10-08 范围提示改动已通过语法检查及 Domain 226 的直接终端检查：固定角度、中心、振幅、发布频率和正弦频率越界后可重输；中心 `1.2` 的振幅默认值自动缩小，演示启动成功；运行中 `/pose` 按当前振幅限制中心并成功调姿；零振幅、`rate=0.1` 时频率默认值自动缩小并正常启动。退出码为 0，本次进程已清理。实际日志在 `artifacts/week04/cli/20261008-174656-417617-175730/`；未启动 GUI，未新增测试文件。

CLI 只管理自身的一个演示，切换前先停止旧进程。启动前有界发现其他发布者，发现冲突则拒绝启动；此窗口不能排除外部随后并发启动，独立实验仍须分配独立 Domain。启动就绪需观察到新鲜状态、对应 TF 和参数服务，不仅看 launch 退出码。

状态与 TF 异步到达，CLI 从近期 64 帧中选择已有对应 TF 的状态帧。原调姿客户端首帧 TF 可能跨姿态更新发生插值，CLI 保留并说明原始结果，再最多等待 2 秒显示后续观察。超时不撤销已接收的参数；观察值不自动代表目标角度一致或图形验收通过。

完整日志由运行时按需创建于 `artifacts/week04/cli/`，每次会话和演示分开保存。退出时只处理本次进程组，按 SIGINT、SIGTERM、SIGKILL 有界升级，不按名称终止其他实验。

## 2026-10-08 CLI 指令逐项检查

用户本轮要求检查每个 CLI 指令及 RViz 演示。独立命令检查通过已有 CLI 的 PTY 直接输入完成，Domain 为 225，实际安装目录为 `ros2_ws/install`；未新增测试脚本、报告工具或 GUI 自动化。用户已有的 Domain 222 会话未被操作。

| 指令 | 实际无界面结果 | RViz 画面结果 |
|---|---|---|
| `/help` | 完整菜单与单位显示正常 | 未运行；预期不改变模型 |
| `/start static` | 固定零位启动，唯一发布者 | 未运行；预期显示零位模型与 TF |
| `/pose 0.5 -0.3`、逐项 `/pose` | 接收并观察到 `[0.5,-0.3]`，末端 `(0.645053,0.251371,0)`，yaw 约 0.2 | 未运行；预期模型对应调姿 |
| `/zero` 固定模式 | `[0,0]`、末端 `(0.7,0,0)`、单位四元数 | 未运行；预期回到零位 |
| `/status` | 发布者、关节和同时间戳 TF 可见 | 未运行；预期不改变模型 |
| `/logs` | 真实非空日志可见 | 未运行；预期不改变模型 |
| `/start sine` | 切换后旧进程组消失，唯一发布者，位置随时间变化且速度非空 | 未运行；预期连续往复运动 |
| sine `/pose 0.2 -0.1` 与 `/zero` | 中心参数实测分别为 `[0.2,-0.1]`、`[0,0]`，关节仍继续运动 | 未运行；预期改变运动中心，仍持续摆动 |
| `/cancel` | 配置取消后保留原演示 | 未运行；预期保留原画面 |
| `/start gui` | 配置选择和取消路径通过；实际 GUI 未启动 | 未运行；滑块与 GUI 模式下 pose/zero 拒绝仍待检查 |
| `/stop`、`/quit` | 停止后发布者 0，退出码 0；本轮自有进程组无残留 | 未运行；预期关闭本次图形窗口 |

编号 1–8 和 0 已覆盖对应入口或实际执行。越界 `2.0 0.0` 请求被拒绝且上一合法姿态不变，非法命令与非数字参数提示后菜单可继续操作。独立公式计算 `(0.6450529981085216,0.25137101468019957, yaw=0.2)` 与显示的后续 TF 在输出精度下一致，不将该结果替代画面验收。

实际命令记录位于 `artifacts/week04/cli/20261008-122113-005615-60473/cli.log`，同目录保留各次 launch 和调姿日志；编号 0 的空会话退出记录在 `20261008-122517-790410-61855/cli.log`。图形操作方式已向用户集中澄清，尚未收到本轮例外授权或实际画面反馈，因此不记录 RViz 通过。

## 原生 ROS 入口

保留直接运行方式，用于学习已有 ROS 接口：

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/local_setup.bash
export ROS_DOMAIN_ID=222
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_LOG_DIR=/home/fatbro/workspace/artifacts/week04/manual-222/ros-log
ros2 launch embodied_arm_cpp demo.launch.py state_source:=cpp use_rviz:=false
```

另一终端加载同一安装目录和 Domain 后：

```bash
ros2 run embodied_arm_cpp set_arm_positions.py 0.5 -0.3
ros2 param set /synthetic_joint_publisher positions '[0.0, 0.0]'
```

调姿入口返回码 0 表示参数被接收且取得观察，1 表示拒绝，2 表示服务或观察异常，130 表示用户中断。超时不代表设置未生效。

图形操作由用户启用 `use_rviz:=true`，或选 `state_source:=gui`；`use_rviz:=false` 不会关闭 GUI 状态源的滑块。直接 launch 的 `joint1/joint2` 和 `amplitude1/amplitude2` 映射到数组参数。关闭 RViz 不结束核心链路，最终对 launch 按 Ctrl-C。描述包的 `display.launch.py` 保留作为独立模型学习入口，不与统一入口同时运行于同一 Domain。

## 检查结论与已知边界

以下沿用实际完成的检查，不因收尾整理而重跑整套实验：

- 描述模型已完成构建与模型检查，用户在 2026-10-04 报告模型、方向与滑块人工验收完成，未保存截图。历史精简结果在[阶段记录](evidence/week04-stage1/README.md)。
- 2026-10-05 完成 C++ 构建、运行时调姿、错误长度/越界/非有限值拒绝及合法请求恢复；两核心进程可正常退出。
- 2026-10-07 至 10-08 完成 CLI 的固定/正弦启动、调姿与归零、单发布者观察、同 Domain 冲突防护、模式切换和停止重启。非法输入/缺失安装目录/旧 v0.3 产物会明确拒绝。
- 暂停本次 TF 发布进程时，CLI 正确区分“参数已接收”和“观察未完成”；恢复后可再次观察状态。归零后的后续观察为 `positions=[0,0]`、末端 `(0.7,0,0)`。
- `rate=0` 时 C++ 返回 1、launch 返回 0，CLI 仍报告启动失败；运行中核心节点退出也会主动提示。`/quit`、Ctrl-C、EOF 的实际检查均完成自有进程清理。
- 首轮 CLI 曾永久等待早于首个 TF 的状态帧而误超时，已改为近期帧匹配并复验。独立代码审查指出自定义 install 可能重放旧父工作空间，已修复环境加载并复查。

保留限制：根连杆惯性会触发 KDL 警告，当前仅验证运动学；固定调姿是状态阶跃，TF 首帧可能插值；低发布频率可导致有界观察超时。CLI 新版图形入口未收到人工反馈，SIGTERM/SIGKILL 升级清理没有专项故障注入。未新增控制器或物理仿真，也未将旧检查当作新版完整验收。

实际环境为 Python 3.12.3、ROS Jazzy，rclpy 7.1.12、tf2_ros_py 0.36.23、robot_state_publisher 3.3.4。

## 收尾后的文件与产物

本轮以结构整理和总体代码检查为主，不新增测试脚本、兼容层、哈希校验或报告工具，不重跑机器人回归。Python 项目版本同步为 0.4.0，README 与架构说明改为当前模块导航。

前一轮收尾检查已完成：Shell 语法、5 个运行相关 Python 文件的语法、项目 TOML 版本及两包 XML/Xacro 结构解析通过。独立总体静态审查覆盖 CLI、C++ 节点、调姿客户端、两个 launch、模型/RViz、包安装声明及文档入口，未发现需要修复的确定缺陷。

架构统一续作完成了必要重建：现有五包在 `ros2_ws` 按本页构建命令成功构建，退出码 0，实际耗时 19.7 秒；日志在 `ros2_ws/log/build_2026-10-08_12-07-31/`。默认 CLI 菜单与 EOF 检查通过，Domain 224 下固定姿态启动后观察到唯一发布者、`positions=[0,0]` 和对应时戳末端 `(0.7,0,0)`，`/quit` 完成自有进程清理；该会话记录在 `artifacts/week04/cli/20261008-120938-309170-55425/`。本轮路径、构建命令、README 版本导航与忽略规则的独立静态复查通过。旧安装路径不再是运行依赖，未增加回退或兼容层。没有安装依赖、启动 GUI、新增测试文件或重跑旧版本回归。

前一轮已清理旧第四周构建/运行产物、历史解包依赖、CLI 日志、旧截图测试产物、当时的构建/运行日志、源码缓存，以及空的 `assets/`、`lessons/`、`reference/`、`embodied_arm_demo/` 占位目录。本轮已将五包重建到 `ros2_ws/build` 和 `ros2_ws/install`，新构建日志按标准生成于 `ros2_ws/log`，并删除旧的按日期创建的第四周构建目录；CLI 默认加载标准安装目录。旧完整日志路径只作为历史记录，不再声称文件仍在磁盘上。

模型与通信的既有测试、模型观察脚本及精简历史 JSON 保留。按用户最新清理要求，离线截图工具、配套测试、流程文档及两个 JSON 已删除；项目内 `AGENTS.md` 和 `.codex/` 协作配置也已删除，后续由用户重新构造。第三周功能源码与精简证据保留；架构统一时删除七份旧发布实验的重复源码导出目录，其他实验记录仍保留。`ros2_ws/.workbuddy/`、`ros2_ws/docs/` 的本地记录继续保留。

## 最终 Git 提交清单

所有 Git 操作由用户手动执行。不要 `git add .`，不要提交 `artifacts/`、build/install/log、缓存或本地工具记录。

**主提交：`feat: 完成 v0.4 两关节机械臂与交互式 CLI`**，精确文件为：

```text
.gitignore
README.md
pyproject.toml
src/embodied_agent_lab/__init__.py
src/embodied_agent_lab/arm_cli.py
scripts/arm_cli.sh
scripts/verify_week04_description.py
docs/architecture.md
docs/labs/week04-integration.md
docs/labs/week04-stage1-description.md
docs/labs/evidence/week04-stage1/README.md
docs/labs/evidence/week04-stage1/results.json
ros2_ws/src/embodied_arm_description/CMakeLists.txt
ros2_ws/src/embodied_arm_description/LICENSE
ros2_ws/src/embodied_arm_description/package.xml
ros2_ws/src/embodied_arm_description/launch/display.launch.py
ros2_ws/src/embodied_arm_description/rviz/two_link_arm.rviz
ros2_ws/src/embodied_arm_description/test/test_model.py
ros2_ws/src/embodied_arm_description/urdf/two_link_arm.urdf.xacro
ros2_ws/src/embodied_arm_cpp/CMakeLists.txt
ros2_ws/src/embodied_arm_cpp/LICENSE
ros2_ws/src/embodied_arm_cpp/package.xml
ros2_ws/src/embodied_arm_cpp/launch/demo.launch.py
ros2_ws/src/embodied_arm_cpp/scripts/set_arm_positions.py
ros2_ws/src/embodied_arm_cpp/src/synthetic_joint_publisher.cpp
```

离线截图工具五个文件此前未被 Git 跟踪，已从工作目录删除，无需为它们提交删除记录。七个协作配置文件已被 Git 跟踪，需要由用户提交删除，建议 `chore: 移除项目协作规范与角色配置`：

```text
AGENTS.md
.codex/config.toml
.codex/agents/cpp_engineer.toml
.codex/agents/reviewer.toml
.codex/agents/ros2_engineer.toml
.codex/agents/simulation_engineer.toml
.codex/agents/test_engineer.toml
```

以上是功能文件与已跟踪配置删除的提交整理建议，不是新的验收关卡。`ros2_ws/.workbuddy/memory/2026-10-01.md`、`ros2_ws/.workbuddy/memory/2026-10-03.md` 和 `ros2_ws/docs/embodied_comm-源码逐文件详解.html` 保留在本地，排除在 v0.4 建议提交清单之外。
