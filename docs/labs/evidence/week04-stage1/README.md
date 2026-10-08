# 第四周阶段 1：自动检查证据与人工验收停点

> 2026-10-08 收尾说明：本文件以下内容为历史记录。按用户本轮清理要求，旧 `artifacts/week04/stage1-20261003/` 等完整产物与日志已删除，文中原始收据路径不再是本机现存文件。精简 `results.json` 保留原样；本轮未重新运行或改写历史结果。当前操作和最终提交清单见[第四周集成说明](../../week04-integration.md)。

历史状态（2026-10-03）：**实现和自动检查通过，当时 RViz、关节滑块与截图待人工验收**。本阶段是两关节描述与运动学可视化基础，不包含第二阶段 C++ 状态节点、Panda 适配、控制器、Gazebo、模型推理或训练。

2026-10-04 更新：用户报告人工验收完成，但未保存截图，本次不补保存，没有实际截图自动检查通过结果；下面的运行数据仍是历史记录。

[results.json](results.json) 保存 2026-10-03 实现轮的实际结果、判据与源码哈希。2026-10-03 文档收尾只读核对既有收据，补充说明，**当时没有重新构建、运行测试或启动 ROS/GUI，也未改写该 JSON**。后续 C++ 开发与检查独立记录在[第四周集成说明](../../week04-integration.md)。

## 1. 版本与可追溯范围

验证基线为 `v0.4` 分支的提交 `4ec52fb80c4ad458c85ed38fe359a1aeee259f78` 加本阶段尚未提交的文件。提交哈希本身不包含新增描述包；应结合 `results.json` 的八个 `source_sha256` 字段识别实际验证源码。本次逐一核对，这八个当前文件均匹配。

| 实现轮实际版本 | 值 |
|---|---|
| ROS / Python | Jazzy / 3.12.3，系统 `/opt/ros/jazzy` 与 `/usr/bin/python3` |
| Xacro / URDF | 2.1.1 / 2.10.1 |
| robot_state_publisher / joint_state_publisher | 3.3.4 / 2.4.3 |
| joint_state_publisher_gui / RViz | 2.4.3 / 14.1.23（仅确认安装版本，GUI 未验收） |
| rclpy / tf2_ros | 7.1.12 / 0.36.22 |
| pytest / PyYAML / ament_cmake_pytest / CMake | 7.4.4 / 6.0.1 / 2.5.6 / 3.28.3 |

完整日志和构建产物保存在 Git 忽略的 `artifacts/week04/stage1-20261003/`。下表的收据路径均相对此目录；精简结果随建议提交清单交付，完整日志不会自动纳入 Git，也不能假定干净检出中包含这些本机产物。

## 2. 自动检查结论

| 检查 | 实际结果 | 原始收据 |
|---|---|---|
| Xacro 展开、URDF 解析 | 通过，四连杆指定坐标链 | `model/xacro.log`、`model/check_urdf.log`、`model/two_link_arm.urdf` |
| 几何、质量、质心、惯性及 FK | 通过；正式测试含 11 组角度的独立 FK 对照 | `tests/pytest-interrupt-fix.log`、`tests/model-interrupt-fix-junit.xml` |
| Launch / RViz 静态检查 | 四种 gui/rviz 组合、发布器互斥、默认无 GUI、Fixed Frame 和描述 QoS 通过；未启动图形程序 | `ros2/static_check.log`、`tests/pytest-interrupt-fix.log` |
| 包构建 | 通过，退出码 0 | `build-final.log`、`colcon-final-commands.json` |
| 包级测试 | 53 项 pytest，0 失败、0 错误、0 跳过；CTest 包装测试 1 项通过 | `test-scoped-final.log`、`test-scoped-result.log`、`colcon-scoped-commands.json` |
| 无界面零位 | 通过，42 个样本，窗口 2.049787 s，20.002076 Hz；两关节位置均为 0 | `headless-final.json`、`headless-final-run.json` |
| TF | 三条边及合成变换均符合判据，`base_link → tool0` 为 `(0.7,0,0)` m，四元数 `(0,0,0,1)` | `headless-final.json` |
| 模型关联 | 原字节和规范化 XML 两组比对均一致 | `description-final-match.json`、`headless-final.json` |
| 无发布源 | 观察器在 3 s 期限内未取得所需数据，按预期返回 `failed / 1` | `no-source.json`、`negative-runs-before-fix.json` |
| SIGINT 修复后 | 正确记录 `interrupted / 130` | `interrupt-final.json`、`interrupt-final-run.json` |
| 正常运行收尾 | 两业务节点干净退出；观察器、launch 均为 0，自有进程组已回收 | `headless-final-launch.log`、`headless-final-run.json` |
| RViz / 滑块 / 截图 | 历史运行时待人工；2026-10-04 用户报告人工完成，截图未保存 | 用户声明见新交付记录；无实际截图自动检查收据 |

`colcon test-result` 显示的 54 是 53 项 pytest 加 1 项 CTest 包装测试，不能表述为 54 个独立功能用例。历史无界面实验没有使用图形界面，非零姿态的数学检查不能替代实际滑块方向验收。

判据预先写在脚本及测试中：关节零位绝对误差 `1e-12 rad`，TF 数值误差 `1e-9`；至少 10 个样本且观察窗口至少 2 s，频率接受范围 15—25 Hz，动态数据最大年龄 1 s。没有通过放宽容差消除失败。

### 模型哈希的两层含义

1. 源码 Xacro 与安装 Xacro 的**原字节** SHA-256 均为 `31bb39f07b5dbe44dfc92ee45bf9f39c1ff4d7c4db9e4bcfc8bbe8d9fc165602`。
2. 安装模型展开后的 XML 与观察器实收 XML 经 `ET.canonicalize(strip_text=True, with_comments=False)` 规范化后，SHA-256 均为 `3cad4a53f28e903fcbee2f5125f6362ffadc1d1bd11782b6a9fedd8ecac9b5ed`。

两层表示不同，不能写成“源码哈希等于规范化 XML 哈希”。观察脚本保存实收 XML/哈希并检查描述在观察期间是否变化；源码与安装文件及完整规范化 XML 的对照由单独核验步骤完成。只有零位 TF 正确，不足以独立证明轴方向、限位等完整模型语义正确。

## 3. 实际运行命令与资源

历史构建/测试的精确参数与退出码分别记录在 `colcon-final-commands.json`、`colcon-scoped-commands.json`。构建和正式测试均将 `--base-paths` 限定到 `ros2_ws/src/embodied_arm_description`；日志、build、install 使用本轮独立目录。实际测试由 ament/CTest 调用 `/usr/bin/python3 -m pytest`。

历史正常运行使用 Domain **164**，两个业务节点由以下命令启动；观察器随后订阅该 Domain：

```bash
ros2 launch embodied_arm_description display.launch.py gui:=false rviz:=false
/usr/bin/python3 scripts/verify_week04_description.py --timeout 15 \
  --output /home/fatbro/workspace/artifacts/week04/stage1-20261003/headless-final.json
```

历史无发布源和 SIGINT 检查使用 Domain **166**；`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`，日志分别在 `negative-ros-logs/` 和 `interrupt-final-ros-logs/`。负例命令及信号行为见各自 `*-run*.json` 收据。

这些是历史执行记录，不是可覆盖旧产物的重跑指令。新的独立实验必须另分配 Domain、日志与结果目录；观察脚本拒绝覆盖已有结果文件。本次仅在人工说明中为未来无界面复现预留 167、人工 RViz 验收预留 168，没有启动这两个实验。旧说明中出现过的 165 也不沿用。

## 4. 保留的失败、修复与限制

- **观察器中断缺陷**：修复前二次调用 `rclpy.shutdown()` 抛出 `RCLError`，覆盖中断状态，实际退出 2。实现轮已由原测试负责人改为 `try_shutdown()` 并处理 `ExternalShutdownException`；最终真实 SIGINT 返回 130。前后收据分别为 `interrupt-before-fix.json`、`interrupt-final.json`。本次收尾未修改该实现。
- **首轮实验编排收尾**：向整个进程组发 SIGINT 后，launch 又转发信号，关节发布器清理时出现重复中断。`headless-launch.log` 保留异常；编排改为只向 launch PID 发信号，`headless-final-launch.log` 记录两个业务节点干净退出。首轮只证明观测通过，不能写成首轮已干净退出。
- **无发布源负例的时间边界**：`no-source.json` 来自中断修复前，实际含义是该 Domain 没有发布所需消息的源，而非源文件缺失。本次未重跑，不将它冒充为修复后新测结果。
- **检查工具修正**：ROS 静态检查曾错误假设 API 返回类型，修正检查代码后通过，过程见 `ros2/check_notes.txt`。初次 Xacro 检查的 `pi` 重定义提示由实现者报告，后来改为 `arm_pi`；保留的最终展开日志无该提示，未保存初次原始告警日志，因此不将它列作完整前后日志证据。
- **colcon 探索范围**：早期包测试未限定搜索根，提示发现历史解包依赖，但日志明确使用 `/opt/ros/jazzy` 的已安装包；后来增加 `--base-paths` 重跑通过。早期日志保留于 `test-final.log`；默认生成的结果日志已移入 `test-result-default-log/`，没有启用历史解包副本。
- **根惯性限制**：最终运行实际出现 KDL 不支持根连杆惯性的警告；为保持指定四连杆链保留该描述。本阶段只验证运动学，没有动力学或真实控制结果。几何截面、质量、惯性、effort 和 velocity 均为教学假设。

## 5. 本次收尾与人工下一步

2026-10-03 文档收尾当时仅修改三份 Markdown：`docs/HANDOFF.md`、`docs/labs/week04-stage1-description.md` 和本文件。历史 JSON、JUnit、日志与源码哈希的核对收据保存于 `artifacts/week04/stage1-docs-closeout-20261003/checks.json`，其中明确记录当时没有 ROS 实验。2026-10-04 接续时 `docs/HANDOFF.md` 已不在磁盘上，本轮不恢复该文件。

人工操作说明保留在[阶段说明第 5 节](../../week04-stage1-description.md#5-人工-rviz-与滑块验收)。用户已报告本次完成，不要求重复本次操作或补拍；下一次按新流程保存真实截图及基准，自动检查结果与人工复核分别记录。

完整建议提交文件与提交信息见[第四周集成交接](../../week04-integration.md)，其中包含原有包草稿、精简结果和本次文档。Git 写操作由用户手动执行；完整产物与既有工具侧文件不在建议清单中。

用户随后明确要求继续第四周项目开发，因此 C++ 与集成继续推进；第五周控制器等仍须新授权。Git 提交与额度恢复本身不构成授权。
