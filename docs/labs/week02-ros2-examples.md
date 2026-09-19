# 第 2 周实验：对照学习 ROS 2 的 Python 与 C++ 官方示例

## 0. 本次实验的终点

本实验以 [ros2/examples（ROS 2 官方示例仓库）](https://github.com/ros2/examples) 的 `jazzy（Jazzy 发行分支）` 为参考。完成后你必须能独立解释并演示：

1. `ros2 run（运行 ROS 2 可执行程序）` 如何找到 Python（编程语言）入口或 C++（编程语言）编译后的程序。
2. 发布者如何通过定时器构造并发布消息。
3. 订阅者如何注册回调并接收消息。
4. 话题名、消息类型和 `QoS（服务质量策略）` 为什么必须兼容。
5. 怎样用 ROS 2 命令行定位“节点都在运行，但订阅者收不到消息”。
6. 怎样关闭参考代码后，在自己的仓库重写最小通信系统。
7. 怎样让 Python 发布者与 C++ 订阅者互通，再反向互通。
8. 为什么两种语言使用同一套通信概念，却有不同的构建、回调与对象生命周期写法。

预计用时为 10—14 小时，建议分成三次：第一次侦察、构建并跑通四种通信组合；第二次对照调用链并完成两种语言的“三改一坏”；第三次独立重写、测试、记录与提交。每到“检查点”先停下回答，再看参考答案。

学习顺序是“同一个概念，先看 Python，再对照 C++，最后跨语言验证”。本周只对照成员函数版本的发布与订阅，不要求读完两个客户端库。第 4 周再继续补指针、引用、头文件与构建知识。

仓库网页上 `rclcpp（ROS 2 的 C++ 客户端库）` 与 `rclpy（ROS 2 的 Python 客户端库）` 目录旁的更新时间，表示对应目录最近一次相关提交的时间；它不等于功能完整度，也不能用来判断某个接口已经过时。先确认网页选择的是 `jazzy（发行分支）`，再读具体提交差异。两种语言对照时使用下文记录的同一个仓库提交。

## 1. 环境约定

- 操作系统：`Ubuntu 24.04（乌班图 24.04 操作系统）`。
- ROS 版本：`ROS 2 Jazzy（机器人操作系统第二代 Jazzy 发行版）`，由系统软件包提供。
- Python 环境：`Conda embodied-agent-lab（Conda 管理的具身智能体实验室环境）`，Python 版本固定为 3.12。
- C++ 工具链：`g++（C++ 编译器）`、`CMake（构建配置工具）` 和 `ament_cmake（ROS 2 的 CMake 构建支持）`；本次官方示例使用 `C++17（C++ 语言标准第 17 版）`。
- 参考仓库：`/home/fatbro/open-source-labs/ros2-examples`，位于主项目之外。
- 主项目：`/home/fatbro/workspace`。

本实验延续 Conda 管理项目环境的习惯，系统提供 ROS 2 与 C++ 工具链。下面的加载顺序是“先 Conda，后 ROS 2”；但加载顺序与 Python 小版本相同并不能保证二进制兼容，必须实际验证导入、构建和通信。C++ 节点是编译后的程序，Conda 本身不会替你编译它。

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

把下面命令的输出保存下来；原有环境检查脚本尚不包含 C++ 工具链，因此还要执行新增的检查：

```bash
# 显示当前 Conda 环境
echo "$CONDA_DEFAULT_ENV"

# 显示当前 ROS 2 发行版
echo "$ROS_DISTRO"

# 显示当前 Python 版本和程序路径
python --version && which python

# 验证 ROS 2 Python 客户端库可以导入
python -c 'import rclpy; print(rclpy.__file__)'

# 显示 C++ 编译器与构建工具版本
g++ --version
cmake --version

# 确认 ROS 2 能找到 C++ 客户端库及其构建支持
ros2 pkg prefix rclcpp
ros2 pkg prefix ament_cmake

# 检查构建命令使用的程序路径，便于排查 Conda 与系统工具混用
command -v python colcon g++ cmake
```

通过标准：环境名为 `embodied-agent-lab（具身智能体实验室）`，ROS 发行版为 `jazzy（Jazzy 发行版）`，Python 为 3.12，能够导入 `rclpy（ROS 2 的 Python 客户端库）`，编译器和构建工具均可找到。

若缺少系统编译工具，可安装下列组件后再检查；已有组件无需重复安装：

```bash
# 安装 Ubuntu 的编译工具与 CMake 构建配置工具
sudo apt install build-essential cmake
```

若出现共享库、解释器或链接错误，先记录完整错误、程序路径与版本。不要仅凭激活了 Conda 就判断构建使用了该环境的 Python；系统安装的构建命令可能有自己的解释器入口。必要时在单独终端用系统 ROS 环境作对照诊断，并给不同环境使用独立构建目录，避免复用错误缓存。

## 2. 固定参考仓库版本

参考仓库已经被克隆到主项目之外。先验证它没有本地修改：

```bash
# 进入 ROS 2 官方示例仓库
cd /home/fatbro/open-source-labs/ros2-examples

# 确认当前分支、修改状态和提交编号
git status --short --branch
git rev-parse HEAD
```

本实验核对两种语言源码与构建入口时使用的提交编号（两种语言共用一个基线）是：

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

## 3. 三十分钟双语言仓库侦察

### 3.0 本次只读这些文件

下表路径都相对于 `/home/fatbro/open-source-labs/ros2-examples（官方示例仓库根目录）`。两个 `member_function.cpp（成员函数版本源文件）` 同名但位于不同目录，阅读时确认完整路径。

| 用途 | Python（编程语言）版本 | C++（编程语言）版本 |
|---|---|---|
| 发布者源码 | `rclpy/topics/minimal_publisher/examples_rclpy_minimal_publisher/publisher_member_function.py`（发布节点实现） | `rclcpp/topics/minimal_publisher/member_function.cpp`（发布节点实现） |
| 订阅者源码 | `rclpy/topics/minimal_subscriber/examples_rclpy_minimal_subscriber/subscriber_member_function.py`（订阅节点实现） | `rclcpp/topics/minimal_subscriber/member_function.cpp`（订阅节点实现） |
| 构建与入口 | 两个包各自的 `setup.py`（安装配置）、`setup.cfg`（脚本安装位置配置） | 两个包各自的 `CMakeLists.txt`（构建配置） |
| 依赖与许可 | 两个包各自的 `package.xml`（软件包清单） | 两个包各自的 `package.xml`（软件包清单） |

四个软件包的名称分别是 `examples_rclpy_minimal_publisher（Python 最小发布者包）`、`examples_rclpy_minimal_subscriber（Python 最小订阅者包）`、`examples_rclcpp_minimal_publisher（C++ 最小发布者包）`、`examples_rclcpp_minimal_subscriber（C++ 最小订阅者包）`。

### 3.1 只回答六个问题

不要遍历整个仓库。围绕本实验只回答：

1. 两种语言的发布者软件包分别在哪里？
2. 两种语言的订阅者软件包分别在哪里？
3. `ros2 run（运行 ROS 2 可执行程序）` 使用的可执行名称在哪里声明？
4. 发布者和订阅者依赖哪些 ROS 软件包？
5. 源文件采用什么许可证？
6. 发布频率、话题名和队列深度分别在哪一行决定？

使用以下命令寻找答案：

```bash
# 进入官方示例仓库
cd /home/fatbro/open-source-labs/ros2-examples

# 只列出本次需要的四个软件包
rg --files rclpy/topics/minimal_publisher rclpy/topics/minimal_subscriber \
  rclcpp/topics/minimal_publisher rclcpp/topics/minimal_subscriber

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

# 查找 C++ 可执行目标、依赖声明与安装目录
rg -n "find_package|add_executable|ament_target_dependencies|install|DESTINATION|CXX_STANDARD" \
  rclcpp/topics/minimal_publisher/CMakeLists.txt \
  rclcpp/topics/minimal_subscriber/CMakeLists.txt

# 只跟踪成员函数版本的 C++ 实现
rg -n "class Minimal|create_publisher|create_subscription|create_wall_timer|bind|spin|SharedPtr" \
  rclcpp/topics/minimal_publisher/member_function.cpp \
  rclcpp/topics/minimal_subscriber/member_function.cpp

# 查看 C++ 软件包依赖与许可证，注意依赖标签不只有 exec_depend（运行依赖）
rg -n "depend|license" rclcpp/topics/minimal_{publisher,subscriber}/package.xml
```

### 检查点 2：先自己画目录关系

在纸上或学习卡中补全：

```text
package.xml（软件包元数据与 ROS 依赖）
setup.py（Python 安装配置与可执行入口）
  → console_scripts（控制台程序映射）
  → publisher_member_function（发布者可执行名称）
  → 模块路径:main（Python 模块的主函数）

package.xml（C++ 软件包清单与依赖）
CMakeLists.txt（C++ 构建配置）
  → add_executable（从源文件创建编译目标）
  → ament_target_dependencies（为目标配置依赖）
  → install 到 lib/包名（安装可执行程序到 ROS 2 能查找的位置）
  → ros2 run 包名 程序名（定位并运行程序）
  → main（编译后程序的主函数）
```

<details>
<summary>完成后再展开参考答案</summary>

- 发布者路径：`rclpy/topics/minimal_publisher（Python 最小发布者目录）`。
- 订阅者路径：`rclpy/topics/minimal_subscriber（Python 最小订阅者目录）`。
- 可执行入口：两个软件包各自的 `setup.py（Python 安装配置）` 中的 `console_scripts（控制台程序映射）`。
- 运行依赖：`rclpy（ROS 2 Python 客户端库）` 与 `std_msgs（ROS 标准消息包）`。
- 许可证：`Apache License 2.0（Apache 2.0 开源许可证）`。
- 发布者中 `topic（话题名）` 和 `10（队列深度）` 传给 `create_publisher（创建发布者）`；`0.5（秒）` 是定时器周期，因此默认频率是 2 赫兹。
- C++ 的两个包位于 `rclcpp/topics/minimal_publisher（最小发布者目录）` 与 `rclcpp/topics/minimal_subscriber（最小订阅者目录）`；各自构建配置将 `member_function.cpp（成员函数源文件）` 编译为发布者或订阅者程序。两者使用 `rclcpp（C++ 客户端库）` 和 `std_msgs（标准消息包）`；包中其他示例还可能引入额外依赖，以软件包清单为准。
- C++ 发布者的 `500ms（500 毫秒）` 与 Python 发布者的 `0.5（秒）` 相等；默认都约为每秒两条消息。

</details>

## 4. 构建最小软件包

先加载环境，再构建四个软件包。选择软件包会构建该包声明的其他演示目标，本次只阅读与运行成员函数版本：

```bash
# 激活 Conda 环境并加载 ROS 2 Jazzy
conda activate embodied-agent-lab
source /opt/ros/jazzy/setup.bash

# 进入官方示例仓库
cd /home/fatbro/open-source-labs/ros2-examples

# 构建两种语言的发布者和订阅者；符号链接不会免除 C++ 重新编译
colcon build --symlink-install \
  --packages-select \
  examples_rclpy_minimal_publisher \
  examples_rclpy_minimal_subscriber \
  examples_rclcpp_minimal_publisher \
  examples_rclcpp_minimal_subscriber

# 把本次构建结果加入当前终端
source install/setup.bash
```

若提示缺少依赖，再执行下面的依赖检查；不要在没有错误时盲目安装：

```bash
# 根据四个软件包的清单检查并安装系统依赖
rosdep install --from-paths \
  rclpy/topics/minimal_publisher \
  rclpy/topics/minimal_subscriber \
  rclcpp/topics/minimal_publisher \
  rclcpp/topics/minimal_subscriber \
  --ignore-src --rosdistro jazzy --recursive --yes
```

### 检查点 3：构建产物

```bash
# 确认 ROS 2 能找到四个软件包
ros2 pkg prefix examples_rclpy_minimal_publisher
ros2 pkg prefix examples_rclpy_minimal_subscriber
ros2 pkg prefix examples_rclcpp_minimal_publisher
ros2 pkg prefix examples_rclcpp_minimal_subscriber

# 列出四个包提供的可执行程序
ros2 pkg executables examples_rclpy_minimal_publisher
ros2 pkg executables examples_rclpy_minimal_subscriber
ros2 pkg executables examples_rclcpp_minimal_publisher
ros2 pkg executables examples_rclcpp_minimal_subscriber
```

你应该看到 `publisher_member_function（成员函数版本发布者）`。如果找不到，优先检查是否在当前终端执行了 `source install/setup.bash（加载工作空间构建结果）`。

两种语言的可执行名称相同：`publisher_member_function（成员函数发布者）` 与 `subscriber_member_function（成员函数订阅者）`，通过不同的软件包名区分。四个包的路径都应指向本地构建目录；若指向 `/opt/ros/jazzy（系统安装目录）`，可能正在使用系统预装示例。

## 5. 跑通原版发布与订阅

### 5.1 第一组：Python 发布与 Python 订阅

打开两个终端。两个终端都必须按相同顺序加载环境。每次只运行一对节点；切换组合前，在两个节点终端按 `Ctrl+C（中断当前程序）`。两种语言的默认节点名相同，同时启动会影响节点查询和数量判断。

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

再启动 `rqt_graph（ROS 2 节点关系图）`，把通信关系变成可视证据：

```bash
# 显示节点、发布者、订阅者和话题之间的关系
rqt_graph
```

保存正常连接截图。到“7.4 一坏”制造话题名不一致后，再保存一张错误连接截图；两张图应能直观看到两端没有通过同一话题连接。

### 检查点 4：不要看源码，先写观察结论

记录：节点数量、话题类型、发布者数量、订阅者数量、实际频率。解释为什么队列深度 `10（十条消息）` 不等于发布频率 `2 Hz（每秒两次）`。

参考结论：队列深度决定通信暂时拥塞时可以保留多少条待处理消息；频率由发布者的 0.5 秒定时器决定。两者是不同维度。

注意：`ros2 topic echo（读取话题消息）` 和 `ros2 topic hz（测量话题频率）` 本身也创建订阅；统计端点数量时先退出它们。发现机制也需要短暂时间，退出程序后不要把尚未刷新的端点当成另一个业务节点。

### 5.2 第二组：C++ 发布与 C++ 订阅

停止上一组节点，保留各终端已经加载的环境。下面两条命令分别在终端 A、B 执行：

```bash
# 终端 A：运行 C++ 成员函数版本发布者
ros2 run examples_rclcpp_minimal_publisher publisher_member_function

# 终端 B：运行 C++ 成员函数版本订阅者
ros2 run examples_rclcpp_minimal_subscriber subscriber_member_function
```

在终端 C 重复 5.1 的节点、消息类型、端点数量和频率检查。比较日志里的消息内容与递增计数。字符串标点或大小写可以不同，通信要求的是类型、话题以及兼容的服务质量策略。

### 5.3 第三组：Python 发布与 C++ 订阅

停止第二组节点，再分别运行：

```bash
# 终端 A：Python 发布者
ros2 run examples_rclpy_minimal_publisher publisher_member_function

# 终端 B：C++ 订阅者
ros2 run examples_rclcpp_minimal_subscriber subscriber_member_function
```

### 5.4 第四组：C++ 发布与 Python 订阅

停止第三组节点，再分别运行：

```bash
# 终端 A：C++ 发布者
ros2 run examples_rclcpp_minimal_publisher publisher_member_function

# 终端 B：Python 订阅者
ros2 run examples_rclpy_minimal_subscriber subscriber_member_function
```

四种组合都用 `std_msgs/msg/String（标准字符串消息类型）` 和 `/topic（默认话题）`，客户端库负责各自语言的数据表示与通信接口。本实验无需额外编写跨语言转换程序。

### 检查点 4 补充：填写四组通信记录

| 发布端 → 订阅端 | 是否收到递增消息 | 类型与两端数量 | 实测频率 | 日志或截图位置 |
|---|---|---|---|---|
| Python → Python（同语言通信） | 待实测 | 待实测 | 待实测 | 待填写 |
| C++ → C++（同语言通信） | 待实测 | 待实测 | 待实测 | 待填写 |
| Python → C++（跨语言通信） | 待实测 | 待实测 | 待实测 | 待填写 |
| C++ → Python（跨语言通信） | 待实测 | 待实测 | 待实测 | 待填写 |

保存原有 `rqt_graph（ROS 2 节点关系图工具）` 截图，并在学习卡中注明对应组合。关系图本身不能可靠证明节点由哪种语言实现，需要同时记录实际运行的软件包名。

## 6. 跟踪一条完整调用链

### 6.1 Python：入口映射、构造节点与回调

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

### 6.2 C++：编译目标、主函数与回调

先读两个包的 `CMakeLists.txt（构建配置）`，找到成员函数程序对应的目标，再进入各自的源文件。

```text
CMakeLists.txt（构建配置）
  → add_executable（创建可执行目标）
  → 编译与链接 member_function.cpp（成员函数源文件）
  → install（安装到软件包对应目录）
ros2 run（查找并运行安装的程序）
  → main（主函数）
  → rclcpp::init（初始化 C++ 客户端库）
  → std::make_shared（创建由共享指针管理的节点）
  → 节点构造函数（创建通信实体和定时器）
  → rclcpp::spin（驱动执行器处理就绪回调）
  → timer_callback / topic_callback（定时回调 / 收消息回调）
  → publish / RCLCPP_INFO（发布消息 / 输出日志）
  → rclcpp::shutdown（结束客户端运行上下文）
```

### 6.3 每读一处就写一行对照笔记

| 概念 | Python（编程语言）写法 | C++（编程语言）写法 | 需要理解的区别 |
|---|---|---|---|
| 节点继承 | `class MinimalPublisher(Node)`（继承节点类） | `class MinimalPublisher : public rclcpp::Node`（公开继承节点类） | 两者都把业务行为组织到节点对象中 |
| 父类初始化 | `super().__init__(...)`（父类初始化） | `: Node(...), count_(0)`（构造函数初始化列表） | C++ 成员可在构造函数主体执行前初始化 |
| 消息类型 | `String`（标准字符串消息类） | `std_msgs::msg::String`（带命名空间的字符串消息类型） | 两者映射到相同的 ROS 消息定义 |
| 创建发布者 | `create_publisher(String, ...)`（把类型作为参数） | `create_publisher<std_msgs::msg::String>(...)`（通过模板指定类型） | C++ 在编译阶段确定该接口的消息类型 |
| 回调注册 | `self.timer_callback`（绑定到对象的方法） | `std::bind(..., this)`（将成员函数与当前对象绑定） | 都是在注册以后执行的函数，并非注册时直接调用 |
| 收消息回调 | `listener_callback(self, msg)`（消息参数） | `topic_callback(const ... & msg) const`（只读消息引用与只读成员函数） | 分清两个只读限定符分别约束什么 |
| 通信实体持有 | `self.publisher_`（实例属性持有对象引用） | `SharedPtr publisher_`（成员持有共享指针） | 节点运行期间需保持发布者、订阅和定时器存活 |
| 定时器 | `create_timer(0.5, ...)`（0.5 秒周期） | `create_wall_timer(500ms, ...)`（500 毫秒墙上时间定时器） | 本实验未启用仿真时间；后续不能把两类时钟语义直接等同 |
| 日志 | `get_logger().info(...)`（信息级日志） | `RCLCPP_INFO(...)`（信息级日志宏） | C++ 格式参数类型必须与占位符匹配 |
| 修改后生效 | 修改 Python 源文件后重启节点 | 修改 C++ 源文件后重新编译并重启 | 符号链接安装不会自动重编译二进制程序 |

只补本例需要的 C++ 知识：类与继承、构造函数、模板类型参数、引用、共享指针、成员函数绑定、时间单位和日志格式。不必先学完整本语言教材。

### 检查点 5 补充：解释五个具体问题

1. `std::make_shared（创建共享指针）` 创建的是消息还是节点？
2. `std::bind（绑定函数参数）` 中的 `this（当前对象指针）` 和 `_1（第一个待传入参数占位符）` 分别是什么？
3. 为什么把定时器存在成员 `timer_（定时器共享指针）` 中？
4. `msg.data.c_str()（取得字符串的字符指针）` 为什么用于日志的 `%s（字符串格式占位符）`？
5. 同名可执行程序如何通过软件包名分别运行？改过 C++ 源码却看到旧行为时先查哪里？

## 7. 三改一坏

两种语言都完成本节练习，并用跨语言组合验证。开始前停止第 5 节的节点。先建立仅用于学习的本地分支；已有同名分支时用 `git switch lab/jazzy-pub-sub（切换到已有实验分支）`：

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

停止两端后，将上述包名分别换成 `examples_rclcpp_minimal_publisher（C++ 发布者包）` 和 `examples_rclcpp_minimal_subscriber（C++ 订阅者包）`，再运行一遍。两端使用完全相同的重映射参数；随后把任意一端换回 Python，验证跨语言也能使用新话题。
话题重映射是在程序启动时，把源码使用的名字转换为实际通信名字。它改变本次节点实例连接的话题，不修改源码，也不改变消息类型、发布频率或队列深度。发布者和订阅者最终解析到同一个话题，是它们建立通信的必要条件之一。

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

接着修改 C++ 发布者的 `member_function.cpp（成员函数源文件）`。先在文件的头文件区加入：

```cpp
// 提供非法参数异常；添加在文件顶部的头文件区
#include <stdexcept>
```

在构造函数中，保留创建发布者的代码，把原来使用 `500ms（500 毫秒）` 创建定时器的整条语句替换为：

```cpp
// 声明并取得启动参数，默认发布频率为每秒两次
const double publish_rate = this->declare_parameter<double>("publish_rate", 2.0);

// 拒绝零、负数和非数字值；异常会阻止该节点正常启动
if (!(publish_rate > 0.0)) {
  throw std::invalid_argument("发布频率必须大于零");
}

// 将频率换算为秒，再转换为整数纳秒，供定时器使用
const auto timer_period = std::chrono::duration_cast<std::chrono::nanoseconds>(
  std::chrono::duration<double>(1.0 / publish_rate));

// 避免极大频率经转换后得到零周期
if (timer_period.count() <= 0) {
  throw std::invalid_argument("发布频率过高，定时器周期必须大于零");
}

// 用计算出的周期注册成员函数回调
timer_ = this->create_wall_timer(
  timer_period, std::bind(&MinimalPublisher::timer_callback, this));
```

本实验只使用 2.0、5.0、0.0 和 -1.0 四个有限值。完整产品还应校验合理频率上限、下限与非有限值；这里的代码是理解参数到定时器的最小练习。

```bash
# 每次修改 C++ 源码后重新编译对应的软件包
cd /home/fatbro/open-source-labs/ros2-examples
colcon build --symlink-install --packages-select examples_rclcpp_minimal_publisher
source install/setup.bash

# 终端 A：运行改造后的 C++ 发布者，频率为每秒五次
ros2 run examples_rclcpp_minimal_publisher publisher_member_function \
  --ros-args --param publish_rate:=5.0

# 终端 B：用 Python 订阅者接收，验证参数修改没有破坏跨语言通信
ros2 run examples_rclpy_minimal_subscriber subscriber_member_function

# 终端 C：测量频率，观察一段时间后按中断键退出
ros2 topic hz /topic
```

结束后分别传入 `0.0（零频率）` 和 `-1.0（负频率）`，记录两种实现的错误与退出状态。Python 回溯与 C++ 异常输出不必相同，验收的是非法参数不能正常启动发布。这里实现的是“启动时参数”：运行中修改参数值不会自动重建定时器，动态改频率留作后续练习。

### 7.3 第三改：增加可观测信息

在两种语言的发布者构造函数中，放在创建发布者并读出频率之后，增加实际话题名与发布频率日志：

```python
# 输出影响运行行为的关键配置，便于排查配置错误
self.get_logger().info(
    f'发布者已启动：话题={self.publisher_.topic_name}，发布频率={publish_rate:.2f} 赫兹'
)
```

```cpp
// 读取解析后的真实话题名，日志反映命令行重映射结果
RCLCPP_INFO(
  this->get_logger(), "发布者已启动：话题=%s，发布频率=%.2f 赫兹",
  publisher_->get_topic_name(), publish_rate);
```

分别以 `/sensor_state（传感器状态话题）` 和每秒五次启动两种发布者，核对日志与命令行观察结果。C++ 日志改动也需要重新编译。

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

接着完成同一个故障的跨语言版本，停止上一对节点后分别执行：

```bash
# 终端 A：C++ 发布到新话题
ros2 run examples_rclcpp_minimal_publisher publisher_member_function \
  --ros-args --remap topic:=/sensor_state

# 终端 B：Python 仍订阅默认话题，预期收不到消息
ros2 run examples_rclpy_minimal_subscriber subscriber_member_function
```

先保留诊断证据，再停止订阅者，用下列命令修复：

```bash
# 终端 B：统一话题名，恢复跨语言通信
ros2 run examples_rclpy_minimal_subscriber subscriber_member_function \
  --ros-args --remap topic:=/sensor_state
```

反向组合再做一次：Python 发布到新话题，C++ 先订阅默认话题，再修复。两次故障的根因相同。保留原有正常与故障关系图，用端点和消息证据说明为什么这次失败与语言选择无关。

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

逐行解释两种语言的修改，并回答：参数默认值在哪里、非法值在哪里被拒绝、频率如何换算为周期、启动时怎样覆盖默认值。再解释为什么 C++ 需要重新编译，而 Python 在符号链接安装后通常只需重启。解释不清的地方先用一个小实验验证，再重写。

## 9. 关闭参考代码，独立重写

本节完成双语言发布订阅对照；完整 v0.2 的 Python 三节点、服务与 Launch 按 [三节点系统实施清单](week02-three-node-system.md) 分阶段扩展，同一个 `embodied_comm` 包不重复创建。跨语言实验统一采用清单约定的 JSON 消息格式，下文计数文本仅为格式示例。

现在停止查看 `/home/fatbro/open-source-labs/ros2-examples（官方示例仓库）`。在主项目中保留 `embodied_comm（Python 具身通信软件包）` 这个已有计划名称，新增 `embodied_comm_cpp（C++ 具身通信软件包）`；每个包各实现一对节点，共四个可执行程序。先建立功能分支，再写代码：

```bash
# 进入旗舰项目，在开始实现前建立功能分支
cd /home/fatbro/workspace
git status --short
git switch -c feat/ros2-pub-sub

# 创建工作空间源码目录
mkdir -p ros2_ws/src
cd ros2_ws/src

# 创建 Python 通信包；若已有该包，继续编辑，不重复生成
ros2 pkg create embodied_comm \
  --build-type ament_python \
  --dependencies rclpy std_msgs \
  --license Apache-2.0

# 创建 C++ 通信包；若已有该包，继续编辑，不重复生成
ros2 pkg create embodied_comm_cpp \
  --build-type ament_cmake \
  --dependencies rclcpp std_msgs \
  --license Apache-2.0
```

如果功能分支已经存在，使用 `git switch feat/ros2-pub-sub（切换到已有功能分支）`。以下两个节点在两个包里各实现一次：

- `sensor_simulator（传感器模拟器）`：向 `/sensor_state（传感器状态话题）` 发布 `std_msgs/String（标准字符串消息）`，发布频率由参数控制。
- `status_monitor（状态监控器）`：订阅同一话题，记录最新消息和接收计数。

建议文件布局（括号内是中文用途，实际文件名不含括号）：

```text
ros2_ws/src/（机器人工作空间的源码目录）
├── embodied_comm/（Python 通信包）
│   ├── package.xml（软件包清单）
│   ├── setup.py（两个可执行入口的安装配置）
│   ├── setup.cfg（生成时提供的脚本安装位置配置）
│   ├── embodied_comm/（Python 模块目录）
│   │   ├── sensor_simulator.py（传感器模拟器）
│   │   └── status_monitor.py（状态监控器）
│   └── test/（参数与消息行为测试）
└── embodied_comm_cpp/（C++ 通信包）
    ├── package.xml（软件包清单）
    ├── CMakeLists.txt（编译目标、依赖、安装与测试配置）
    ├── src/（C++ 实现目录）
    │   ├── sensor_simulator.cpp（传感器模拟器）
    │   └── status_monitor.cpp（状态监控器）
    └── test/（参数与消息行为测试）
```

此图省略了生成器创建的资源标记等文件，应保留它们。在 Python 安装配置中把两个入口映射到各自模块的 `main（主函数）`，并保留生成的脚本安装配置。

C++ 代码由你自己写；在生成的构建配置中保留依赖查找，把以下内容加在 `ament_package()（结束软件包配置）` 之前：

```cmake
# 采用与官方示例一致的 C++17 语言标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 编译传感器模拟器，并关联客户端库和标准消息依赖
add_executable(sensor_simulator src/sensor_simulator.cpp)
ament_target_dependencies(sensor_simulator rclcpp std_msgs)

# 编译状态监控器，并关联相同依赖
add_executable(status_monitor src/status_monitor.cpp)
ament_target_dependencies(status_monitor rclcpp std_msgs)

# 安装两个程序到 ROS 2 按包名查找可执行程序的位置
install(TARGETS sensor_simulator status_monitor
  DESTINATION lib/${PROJECT_NAME})
```

约束：

1. 不复制官方类名和日志文本。
2. 发布频率必须是参数，且拒绝零和负数。
3. 话题名使用一个清晰常量或参数，不在多处重复字符串。
4. 每个节点启动时输出关键配置。
5. 保留自己选择的许可证，并在学习卡中注明参考了 `ros2/examples（ROS 2 官方示例）` 的接口用法。
6. 两种实现使用相同的消息格式和启动参数。例如消息文本统一为 `sensor_count=0（传感器计数为零）`，随后递增；参数统一为 `publish_rate（发布频率）`。
7. 启动参数先只要求创建节点时生效；两种实现均需校验数值有限且位于自己声明的合理范围，并对边界写测试。

完成代码后，在工作空间根目录构建：

```bash
# 返回 ROS 2 工作空间根目录
cd /home/fatbro/workspace/ros2_ws

# 构建自己独立实现的两个通信软件包
colcon build --symlink-install --packages-select embodied_comm embodied_comm_cpp

# 加载自己的构建结果
source install/setup.bash

# 列出自己的可执行程序，确认入口配置正确
ros2 pkg executables embodied_comm
ros2 pkg executables embodied_comm_cpp
```

然后用自己实现的入口重做第 5 节的四种组合。两种包都注册 `sensor_simulator（传感器模拟器程序）` 与 `status_monitor（状态监控程序）`，例如：

```bash
# 终端 A：自己的 C++ 发布者
ros2 run embodied_comm_cpp sensor_simulator --ros-args --param publish_rate:=5.0

# 终端 B：自己的 Python 订阅者
ros2 run embodied_comm status_monitor
```

每个运行终端都必须先激活项目环境、加载系统 ROS 2，再加载 `/home/fatbro/workspace/ros2_ws/install/setup.bash（自己的工作空间环境脚本）`。此阶段使用自己的工作空间，不再依靠官方示例工作空间的程序。

## 10. 自动化验证

两种实现使用同一份验收规格。默认生成的包可能只有格式检查，`colcon test（运行包已注册的测试）` 全绿不代表消息功能已经被测试。至少补齐并记录下面三类验证：

1. 静态质量检查：两个包的已注册检查都通过，C++ 编译警告被理解并处理。
2. 参数与消息单元测试：把频率校验、频率到周期换算、计数到消息文本转换提取为可单独调用的函数；用 `pytest（Python 测试框架）` 与 `GoogleTest（C++ 测试框架）` 验证两种实现的同一规格。C++ 测试需通过 `ament_cmake_gtest（ROS 的 C++ 测试集成包）` 注册；仅创建测试源文件不会自动执行。
3. 通信观察：两种同语言、两种跨语言组合都收到递增消息，端点数量正确，频率接近参数值。先按第 5 节手工记录，后续再写启动集成测试；不要把手工检查标为自动化测试。

| 测试输入 | 两种语言共同的预期行为 |
|---|---|
| `2.0（每秒两次）` | 周期为 0.5 秒 |
| `5.0（每秒五次）` | 周期为 0.2 秒，实际通信频率允许调度和观测误差 |
| `0.0（零频率）`、`-1.0（负频率）` | 明确拒绝，不能正常启动发布 |
| 非有限值或超出声明的频率范围 | 校验函数拒绝，不交给定时器隐式处理 |
| 连续两次构造消息 | 两种实现生成相同格式，计数按约定递增 |

```bash
# 运行自己的软件包测试
cd /home/fatbro/workspace/ros2_ws
colcon test --packages-select embodied_comm embodied_comm_cpp

# 显示失败测试的详细输出
colcon test-result --verbose
```

查看测试报告中的测试数量与名称，确认自己增加的参数和消息测试确实运行。后续用 `launch_testing（ROS 2 启动集成测试框架）` 自动化四组通信：每组在超时时间内收到至少一条消息、两端正常退出，并在运行完后清理进程。本次先完成有证据的手工通信验证。

## 11. 把成果提交到自己的仓库

参考仓库的学习分支不进入主项目；只有你独立重写的代码、中文学习卡、故障记录和测试进入 `EmbodiedAgentLab（具身智能体实验室）`。

```bash
# 回到自己的项目，确认当前仍在第 9 节建立的功能分支
cd /home/fatbro/workspace
git branch --show-current

# 先审查再暂存，不使用不加思考的全量提交
git status --short
git diff -- ros2_ws/src/embodied_comm ros2_ws/src/embodied_comm_cpp docs

# 审查两个新包的文件后，暂存本次真实完成的实现与测试
git add ros2_ws/src/embodied_comm ros2_ws/src/embodied_comm_cpp
git diff --cached --stat
git commit -m "feat: 增加双语言发布订阅节点与测试"
```

上述 `feat（功能提交类型）` 表示增加功能。如果你在各阶段完成后就提交，也可以自然形成“Python 功能→C++ 功能→跨语言测试→学习文档”的历史。每次提交必须对应真实新修改，不需要为了次数重做提交。暂存文档时只选择自己的学习卡与故障记录，避免把其他尚未完成的笔记一起加入。

## 12. 最终验收

只有以下项目全部满足，才算完成：

- [ ] 环境检查脚本通过，并另行确认 C++ 编译器、构建工具与客户端库可用。
- [ ] 记录官方仓库分支、提交编号和 Apache 2.0 许可证。
- [ ] 原版四个包构建成功，两种同语言与两种跨语言通信全部有证据。
- [ ] 能用命令行证明消息类型、两端数量和发布频率，并保存正常与错误的 `rqt_graph（节点关系图工具）` 对比截图。
- [ ] 能分别画出 Python 与 C++ 的构建入口、节点、定时器和收发回调链。
- [ ] 能解释共享指针、成员函数绑定、只读引用，以及为什么 C++ 修改后需要编译。
- [ ] 两种语言均完成改话题、改频率参数、加真实话题名日志。
- [ ] 同语言与双向跨语言的“话题不一致”故障都能定位并修复。
- [ ] 在主项目独立完成 `embodied_comm（Python 通信包）` 与 `embodied_comm_cpp（C++ 通信包）`。
- [ ] 两个包的自动化测试通过，并确认自写测试实际被发现和执行。
- [ ] 自写节点的四组通信完成手工验收，未将手工检查冒充自动化覆盖。
- [ ] 学习卡和故障记录完整。
- [ ] 提交历史能区分功能、测试和文档。

## 13. 你现在只做第一步

先执行“检查点 1”的环境检查脚本以及新增 C++ 工具链检查，把完整输出发回来。下一步根据真实环境进入四个包的构建；之后按“每个概念两种语言对照、每个改动验证跨语言通信”的顺序推进。

## 14. 核对过的上游阅读入口

下面链接都固定到本实验的提交，避免默认分支更新后文件内容与说明不一致：

- [Python 发布者源码（成员函数版本）](https://github.com/ros2/examples/blob/07008852303f2a35a91c65d78046b274a35477ea/rclpy/topics/minimal_publisher/examples_rclpy_minimal_publisher/publisher_member_function.py)。
- [Python 订阅者源码（成员函数版本）](https://github.com/ros2/examples/blob/07008852303f2a35a91c65d78046b274a35477ea/rclpy/topics/minimal_subscriber/examples_rclpy_minimal_subscriber/subscriber_member_function.py)。
- [C++ 发布者源码（成员函数版本）](https://github.com/ros2/examples/blob/07008852303f2a35a91c65d78046b274a35477ea/rclcpp/topics/minimal_publisher/member_function.cpp)。
- [C++ 订阅者源码（成员函数版本）](https://github.com/ros2/examples/blob/07008852303f2a35a91c65d78046b274a35477ea/rclcpp/topics/minimal_subscriber/member_function.cpp)。
- [C++ 发布者构建配置（可执行目标与安装规则）](https://github.com/ros2/examples/blob/07008852303f2a35a91c65d78046b274a35477ea/rclcpp/topics/minimal_publisher/CMakeLists.txt)。
- [C++ 订阅者构建配置（可执行目标与安装规则）](https://github.com/ros2/examples/blob/07008852303f2a35a91c65d78046b274a35477ea/rclcpp/topics/minimal_subscriber/CMakeLists.txt)。

本次文档更新核对了本地固定版本的源码与构建声明；本文的运行结果表仍需由实际实验填写，不代表四组节点已经完成运行验证。
