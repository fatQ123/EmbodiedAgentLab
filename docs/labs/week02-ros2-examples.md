# 第 2 周实验：完整学习 ROS 2 官方示例

## 0. 本次实验的终点

本实验以 [ros2/examples（ROS 2 官方示例仓库）](https://github.com/ros2/examples) 的 `jazzy（Jazzy 发行分支）` 为参考。完成后你必须能独立解释并演示：

1. `ros2 run（运行 ROS 2 可执行程序）` 如何从软件包找到 Python 入口。
2. 发布者如何通过定时器构造并发布消息。
3. 订阅者如何注册回调并接收消息。
4. 话题名、消息类型和 `QoS（服务质量策略）` 为什么必须兼容。
5. 怎样用 ROS 2 命令行定位“节点都在运行，但订阅者收不到消息”。
6. 怎样关闭参考代码后，在自己的仓库重写最小通信系统。

预计用时为 6—8 小时，建议分成两天。不要一次复制完所有命令；每到“检查点”先停下回答，再看参考答案。

## 1. 环境约定

- 操作系统：`Ubuntu 24.04（乌班图 24.04 操作系统）`。
- ROS 版本：`ROS 2 Jazzy（机器人操作系统第二代 Jazzy 发行版）`，由系统软件包提供。
- Python 环境：`Conda embodied-agent-lab（Conda 管理的具身智能体实验室环境）`，Python 版本固定为 3.12。
- 参考仓库：`/home/fatbro/open-source-labs/ros2-examples`，位于主项目之外。
- 主项目：`/home/fatbro/workspace`。

ROS 2 由系统安装、项目依赖由 Conda 管理。激活顺序必须是“先 Conda，后 ROS 2”：

```bash
# 激活项目的 Conda 环境
conda activate embodied-agent-lab

# 把系统安装的 ROS 2 Jazzy 加入当前终端
source /opt/ros/jazzy/setup.bash

# 运行本仓库提供的前置条件检查脚本
cd /home/fatbro/workspace
./scripts/check_ros2_lab.sh
```

若 `python -c 'import rclpy'（用当前 Python 导入 ROS 2 客户端库）` 失败，不要执行 `pip install rclpy（从 Python 软件源安装 rclpy）`；它不是官方支持的完整安装方式。先确认 Python 为 3.12，再确认已经加载 `/opt/ros/jazzy/setup.bash（ROS 2 Jazzy 环境脚本）`。

### 检查点 1：环境

把下面四条命令的输出保存下来：

```bash
# 显示当前 Conda 环境
echo "$CONDA_DEFAULT_ENV"

# 显示当前 ROS 2 发行版
echo "$ROS_DISTRO"

# 显示当前 Python 版本和程序路径
python --version && which python

# 验证 ROS 2 Python 客户端库可以导入
python -c 'import rclpy; print(rclpy.__file__)'
```

通过标准：环境名为 `embodied-agent-lab（具身智能体实验室）`，ROS 发行版为 `jazzy（Jazzy 发行版）`，Python 为 3.12，并且能够导入 `rclpy（ROS 2 的 Python 客户端库）`。

## 2. 固定参考仓库版本

参考仓库已经被克隆到主项目之外。先验证它没有本地修改：

```bash
# 进入 ROS 2 官方示例仓库
cd /home/fatbro/open-source-labs/ros2-examples

# 确认当前分支、修改状态和提交编号
git status --short --branch
git rev-parse HEAD
```

本实验编写时固定的提交是：

```text
07008852303f2a35a91c65d78046b274a35477ea
```

提交编号以后发生变化并不代表错误，但你的学习卡必须记录自己实际使用的编号。不要把参考仓库复制进 `/home/fatbro/workspace（主项目目录）`。

如需在另一台机器重新获取：

```bash
# 创建专门存放外部开源项目的目录
mkdir -p /home/fatbro/open-source-labs

# 只克隆 Jazzy 分支的最新历史
git clone --branch jazzy --depth 1 \
  https://github.com/ros2/examples.git \
  /home/fatbro/open-source-labs/ros2-examples
```

## 3. 二十分钟仓库侦察

### 3.1 只回答六个问题

不要遍历整个仓库。围绕本实验只回答：

1. Python 发布者软件包在哪里？
2. Python 订阅者软件包在哪里？
3. `ros2 run（运行 ROS 2 可执行程序）` 使用的可执行名称在哪里声明？
4. 发布者和订阅者依赖哪些 ROS 软件包？
5. 源文件采用什么许可证？
6. 发布频率、话题名和队列深度分别在哪一行决定？

使用以下命令寻找答案：

```bash
# 进入官方示例仓库
cd /home/fatbro/open-source-labs/ros2-examples

# 只列出本次需要的两个软件包
find rclpy/topics/minimal_publisher rclpy/topics/minimal_subscriber \
  -maxdepth 2 -type f | sort

# 查找 ros2 run 对应的 Python 控制台入口
rg -n "console_scripts|publisher_member_function|subscriber_member_function" \
  rclpy/topics/minimal_publisher rclpy/topics/minimal_subscriber

# 查找节点、发布者、订阅者、定时器与回调
rg -n "class Minimal|create_publisher|create_subscription|create_timer|callback|spin" \
  rclpy/topics/minimal_publisher rclpy/topics/minimal_subscriber

# 查看运行依赖与许可证
rg -n "exec_depend|license" \
  rclpy/topics/minimal_publisher/package.xml \
  rclpy/topics/minimal_subscriber/package.xml
```

### 检查点 2：先自己画目录关系

在纸上或学习卡中补全：

```text
package.xml（软件包元数据与 ROS 依赖）
setup.py（Python 安装配置与可执行入口）
  → console_scripts（控制台程序映射）
  → publisher_member_function（发布者可执行名称）
  → 模块路径:main（Python 模块的主函数）
```

<details>
<summary>完成后再展开参考答案</summary>

- 发布者路径：`rclpy/topics/minimal_publisher（Python 最小发布者目录）`。
- 订阅者路径：`rclpy/topics/minimal_subscriber（Python 最小订阅者目录）`。
- 可执行入口：两个软件包各自的 `setup.py（Python 安装配置）` 中的 `console_scripts（控制台程序映射）`。
- 运行依赖：`rclpy（ROS 2 Python 客户端库）` 与 `std_msgs（ROS 标准消息包）`。
- 许可证：`Apache License 2.0（Apache 2.0 开源许可证）`。
- 发布者中 `topic（话题名）` 和 `10（队列深度）` 传给 `create_publisher（创建发布者）`；`0.5（秒）` 是定时器周期，因此默认频率是 2 赫兹。

</details>

## 4. 构建最小软件包

先加载环境，再只构建本次需要的两个软件包：

```bash
# 激活 Conda 环境并加载 ROS 2 Jazzy
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash

# 进入官方示例仓库
cd /home/fatbro/open-source-labs/ros2-examples

# 仅构建最小发布者与最小订阅者；符号链接模式便于修改 Python 后快速验证
colcon build --symlink-install \
  --packages-select \
  examples_rclpy_minimal_publisher \
  examples_rclpy_minimal_subscriber

# 把本次构建结果加入当前终端
source install/setup.bash
```

若提示缺少依赖，再执行下面的依赖检查；不要在没有错误时盲目安装：

```bash
# 根据两个软件包的 package.xml 检查并安装系统依赖
rosdep install --from-paths \
  rclpy/topics/minimal_publisher \
  rclpy/topics/minimal_subscriber \
  --ignore-src --rosdistro jazzy --recursive --yes
```

### 检查点 3：构建产物

```bash
# 确认 ROS 2 能找到两个软件包
ros2 pkg prefix examples_rclpy_minimal_publisher
ros2 pkg prefix examples_rclpy_minimal_subscriber

# 列出发布者软件包提供的可执行程序
ros2 pkg executables examples_rclpy_minimal_publisher
```

你应该看到 `publisher_member_function（成员函数版本发布者）`。如果找不到，优先检查是否在当前终端执行了 `source install/setup.bash（加载工作空间构建结果）`。

## 5. 跑通原版发布与订阅

打开两个终端。两个终端都必须按相同顺序加载环境。

终端 A：

```bash
# 加载 Conda、系统 ROS 2 和刚构建的示例工作空间
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
source /home/fatbro/open-source-labs/ros2-examples/install/setup.bash

# 运行成员函数版本的发布者
ros2 run examples_rclpy_minimal_publisher publisher_member_function
```

终端 B：

```bash
# 加载与终端 A 完全相同的环境
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
source /home/fatbro/open-source-labs/ros2-examples/install/setup.bash

# 运行成员函数版本的订阅者
ros2 run examples_rclpy_minimal_subscriber subscriber_member_function
```

再打开终端 C 做观察，不写代码：

```bash
# 加载 ROS 2；观察命令不依赖示例包入口，但保持环境一致更容易排错
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash
source /home/fatbro/open-source-labs/ros2-examples/install/setup.bash

# 列出节点和话题
ros2 node list
ros2 topic list --show-types

# 查看话题类型、发布者和订阅者数量
ros2 topic info /topic --verbose

# 读取一条消息后退出
ros2 topic echo /topic --once

# 测量实际发布频率
ros2 topic hz /topic
```

### 检查点 4：不要看源码，先写观察结论

记录：节点数量、话题类型、发布者数量、订阅者数量、实际频率。解释为什么队列深度 `10（十条消息）` 不等于发布频率 `2 Hz（每秒两次）`。

参考结论：队列深度决定通信暂时拥塞时可以保留多少条待处理消息；频率由发布者的 0.5 秒定时器决定。两者是不同维度。

## 6. 跟踪一条完整调用链

先从 `setup.py（Python 安装配置）` 找到入口，再进入源文件，不从文件第一行盲读。

发布路径：

```text
ros2 run（运行可执行程序）
  → setup.py 的 console_scripts（控制台程序映射）
  → main（主函数）
  → rclpy.init（初始化 ROS 2 Python 客户端）
  → MinimalPublisher（创建最小发布者节点）
  → create_publisher（创建发布者）
  → create_timer（创建周期定时器）
  → rclpy.spin（持续处理事件）
  → timer_callback（定时回调）
  → publish（发布消息）
```

订阅路径：

```text
ros2 run（运行可执行程序）
  → setup.py 的 console_scripts（控制台程序映射）
  → main（主函数）
  → MinimalSubscriber（创建最小订阅者节点）
  → create_subscription（创建订阅）
  → rclpy.spin（持续处理事件）
  → listener_callback（收到消息后的回调）
  → logger（日志输出）
```

用以下命令逐段核实，而不是相信上面的答案：

```bash
# 查看入口映射附近的行号
rg -n -C 3 "publisher_member_function|subscriber_member_function" \
  rclpy/topics/minimal_publisher/setup.py \
  rclpy/topics/minimal_subscriber/setup.py

# 查看发布和订阅主路径附近的上下文
rg -n -C 2 "rclpy.init|create_publisher|create_subscription|create_timer|spin|publish" \
  rclpy/topics/minimal_publisher/examples_rclpy_minimal_publisher/publisher_member_function.py \
  rclpy/topics/minimal_subscriber/examples_rclpy_minimal_subscriber/subscriber_member_function.py
```

### 检查点 5：口述测试

不看笔记，用两分钟回答：

- 为什么需要 `rclpy.spin（持续处理事件）`？
- 定时器回调由谁触发？
- 订阅者从哪里知道消息类型？
- `ros2 run（运行可执行程序）` 为什么不直接使用 Python 文件名？

答不出来就回到调用链中定位具体一行，不重新看整篇教程。

## 7. 三改一坏

先建立仅用于学习的本地分支：

```bash
# 确保位于官方示例仓库，并从 jazzy 建立实验分支
cd /home/fatbro/open-source-labs/ros2-examples
git switch -c lab/jazzy-pub-sub
```

### 7.1 第一改：运行时修改话题名

不改源代码，同时把两端的 `/topic（默认话题）` 重映射为 `/sensor_state（传感器状态话题）`。

终端 A：

```bash
# 启动发布者，并把默认话题重映射为传感器状态话题
ros2 run examples_rclpy_minimal_publisher publisher_member_function \
  --ros-args --remap topic:=/sensor_state
```

终端 B：

```bash
# 启动订阅者，并使用相同的话题重映射
ros2 run examples_rclpy_minimal_subscriber subscriber_member_function \
  --ros-args --remap topic:=/sensor_state
```

验证 `/topic（默认话题）` 是否消失、`/sensor_state（传感器状态话题）` 是否有一个发布者和一个订阅者。

### 7.2 第二改：把发布周期变成参数

在发布者构造函数中，用下面的逻辑替换固定的 `timer_period = 0.5（固定周期为 0.5 秒）`。先自己输入，不整段复制：

```python
# 声明 publish_rate 参数，默认值为每秒 2 次
self.declare_parameter('publish_rate', 2.0)

# 读取参数并转换为浮点数
publish_rate = float(self.get_parameter('publish_rate').value)

# 拒绝零或负数，避免除零和无意义配置
if publish_rate <= 0.0:
    raise ValueError('发布频率必须大于零')

# 把每秒次数换算成定时器周期
timer_period = 1.0 / publish_rate
```

因为使用了 `--symlink-install（符号链接安装）`，Python 文件通常无需重新构建即可生效；但改动 `setup.py（Python 安装配置）` 或新建入口后必须重新构建。使用以下命令验证 5 赫兹：

```bash
# 以每秒 5 次启动发布者
ros2 run examples_rclpy_minimal_publisher publisher_member_function \
  --ros-args --param publish_rate:=5.0

# 在另一个终端测量频率
ros2 topic hz /topic
```

再传入零，确认程序明确失败，而不是静默产生错误。

### 7.3 第三改：增加可观测信息

启动时增加一条日志，至少包含实际话题名与发布频率。不要只写“启动成功”；日志必须能帮助排错。示例意图如下：

```python
# 输出影响运行行为的关键配置，便于排查配置错误
self.get_logger().info(
    f'发布者已启动：话题=/topic，发布频率={publish_rate:.2f} 赫兹'
)
```

思考：若支持话题重映射，硬编码日志里的 `/topic（默认话题）` 可能不准确。进阶做法是从发布者对象读取实际解析后的话题名，而不是写死。

### 7.4 一坏：制造话题不一致

发布者重映射，订阅者保持默认：

```bash
# 终端 A：发布到传感器状态话题
ros2 run examples_rclpy_minimal_publisher publisher_member_function \
  --ros-args --remap topic:=/sensor_state

# 终端 B：仍然订阅默认话题；此时它不会收到消息
ros2 run examples_rclpy_minimal_subscriber subscriber_member_function
```

严格按以下顺序诊断，不先猜答案：

```bash
# 第一步：节点是否都存在
ros2 node list

# 第二步：系统中到底有哪些话题
ros2 topic list --show-types

# 第三步：分别检查两个话题的发布者和订阅者数量
ros2 topic info /sensor_state --verbose
ros2 topic info /topic --verbose

# 第四步：查看两个节点各自连接了什么话题
ros2 node info /minimal_publisher
ros2 node info /minimal_subscriber

# 第五步：证明传感器状态话题确实有消息
ros2 topic echo /sensor_state --once
```

按固定格式写故障记录：

```text
现象：两个节点都在运行，但订阅者没有日志。
证据：发布者连接 /sensor_state，订阅者连接 /topic。
根因：两端解析后的话题名不同。
修复：给订阅者增加相同重映射，或统一从启动文件传入。
回归测试：/sensor_state 显示一个发布者和一个订阅者，订阅日志恢复。
```

## 8. 查看并解释自己的差异

```bash
# 查看本次实验修改了哪些文件和行
git status --short
git diff --stat
git diff

# 检查空白符错误
git diff --check
```

不要把官方示例的实验提交推送到自己的旗舰仓库。这个分支只是学习现场。把差异和固定提交编号记录到学习卡即可。

### 检查点 6：代码审查

逐行解释自己的修改，并回答：参数默认值在哪里、非法值在哪里被拒绝、频率如何换算为周期、运行时怎样覆盖默认值。任何一行解释不清，就删掉重新写。

## 9. 关闭参考代码，独立重写

现在停止查看 `/home/fatbro/open-source-labs/ros2-examples（官方示例仓库）`。在主项目中创建自己的 ROS 2 工作空间和 Python 软件包：

```bash
# 进入自己的旗舰项目并创建 ROS 2 源码目录
cd /home/fatbro/workspace
mkdir -p ros2_ws/src
cd ros2_ws/src

# 创建自己的通信软件包，并声明真正使用的依赖
ros2 pkg create embodied_comm \
  --build-type ament_python \
  --dependencies rclpy std_msgs \
  --license Apache-2.0
```

第一版只实现两个节点：

- `sensor_simulator（传感器模拟器）`：向 `/sensor_state（传感器状态话题）` 发布 `std_msgs/String（标准字符串消息）`，发布频率由参数控制。
- `status_monitor（状态监控器）`：订阅同一话题，记录最新消息和接收计数。

约束：

1. 不复制官方类名和日志文本。
2. 发布频率必须是参数，且拒绝零和负数。
3. 话题名使用一个清晰常量或参数，不在多处重复字符串。
4. 每个节点启动时输出关键配置。
5. 保留自己选择的许可证，并在学习卡中注明参考了 `ros2/examples（ROS 2 官方示例）` 的接口用法。

完成代码后，在工作空间根目录构建：

```bash
# 返回 ROS 2 工作空间根目录
cd /home/fatbro/workspace/ros2_ws

# 构建自己的通信软件包
colcon build --symlink-install --packages-select embodied_comm

# 加载自己的构建结果
source install/setup.bash

# 列出自己的可执行程序，确认入口配置正确
ros2 pkg executables embodied_comm
```

## 10. 自动化验证

最少完成三类验证：

1. 静态质量检查：`colcon test（运行 ROS 软件包测试）` 全部通过。
2. 参数测试：默认频率可用，零和负数明确失败。
3. 集成观察：两个节点运行时，话题有一个发布者和一个订阅者，频率接近参数值。

```bash
# 运行自己的软件包测试
cd /home/fatbro/workspace/ros2_ws
colcon test --packages-select embodied_comm

# 显示失败测试的详细输出
colcon test-result --verbose
```

后续应增加 `launch_testing（ROS 2 启动集成测试框架）`，但第一次实验先把节点和参数行为测试清楚，不同时扩展过多工具。

## 11. 把成果提交到自己的仓库

参考仓库的学习分支不进入主项目；只有你独立重写的代码、中文学习卡、故障记录和测试进入 `EmbodiedAgentLab（具身智能体实验室）`。

```bash
# 回到自己的项目并建立功能分支
cd /home/fatbro/workspace
git switch -c feat/ros2-pub-sub

# 先审查再暂存，不使用不加思考的全量提交
git status --short
git diff -- ros2_ws/src/embodied_comm docs

# 分三次提交，体现真实工程过程
git add ros2_ws/src/embodied_comm
git commit -m "feat: 增加传感器状态发布与监控节点"

git add ros2_ws/src/embodied_comm
git commit -m "test: 增加通信节点参数与行为测试"

git add docs
git commit -m "docs: 记录 ROS 2 发布订阅调用链与故障定位"
```

第二、第三次提交前必须确实有对应的新修改；不要为了提交数量拆分同一份未变化的文件。

## 12. 最终验收

只有以下项目全部满足，才算完成：

- [ ] 环境检查脚本全部通过。
- [ ] 记录官方仓库分支、提交编号和 Apache 2.0 许可证。
- [ ] 原版发布者和订阅者运行成功。
- [ ] 能用命令行证明消息类型、两端数量和发布频率。
- [ ] 能脱稿画出入口、节点、定时器、发布和订阅回调链。
- [ ] 完成改话题、改频率参数、加观测日志。
- [ ] 成功制造并定位话题名不一致。
- [ ] 在主项目独立完成 `embodied_comm（具身通信软件包）`。
- [ ] 自动化测试通过。
- [ ] 学习卡和故障记录完整。
- [ ] 提交历史能区分功能、测试和文档。

## 13. 你现在只做第一步

先不要继续构建。执行“检查点 1”的四条命令和环境检查脚本，把完整输出发回来。下一步将根据你的真实环境决定是直接构建，还是先解决 Conda 与 ROS 2 的加载问题。
