# 系统架构

## v0.4 当前实现

当前版本包含两条可独立运行的实验链路：v0.2/v0.3 工位通信与故障诊断，以及 v0.4 两关节机械臂合成状态与运动学可视化。不同实验使用独立 ROS Domain；两条链路都可能使用 `base_link`、`tool0`，不应混在同一 Domain 中。

| 模块 | 职责 | 接口与边界 |
|---|---|---|
| `scripts/arm_cli.sh` | 加载既有 Jazzy 和指定第四周安装目录 | 仅子进程环境；不安装、不构建 |
| `src/embodied_agent_lab/arm_cli.py` | 菜单、启动/停止、观察与日志 | 管理自有进程组；复用 ROS launch 和调姿入口 |
| `embodied_arm_description` | 两关节模型、RViz 配置、模型说明 | Xacro 是关节顺序、限位与几何的来源 |
| `embodied_arm_cpp` | 合成 JointState 与统一启动 | static 固定姿态或 sine 周期运动；运行时原子更新 `positions` |
| `robot_state_publisher` | 根据同一份描述将关节状态转为 TF | 唯一负责模型坐标变换；C++ 不另发 TF |
| `embodied_interfaces`、`embodied_comm`、`embodied_comm_cpp` | 历史工位、Action、诊断与双语言通信 | 保留 v0.2/v0.3 功能，不接入第四周模型控制 |
| `doctor.py`、`probes.py` | 通用环境诊断 | 与机械臂菜单分离，保留既有命令与 JSON 协议 |

## 机械臂数据流

```text
用户 → arm_cli.sh → Python 菜单
                       ├─ demo.launch.py → 展开一次 Xacro
                       │                    ├─ robot_state_publisher
                       │                    └─ C++ 或 GUI 状态源（二选一）
                       ├─ set_arm_positions.py → C++ 原子参数服务
                       └─ 只读观察 /joint_states、/tf、/tf_static

状态源 → /joint_states → robot_state_publisher → TF → RViz（用户启用）
```

运动链为 `base_link → joint1 → link1 → joint2 → link2 → tool0`。角度为 rad，长度为 m；GUI 与 C++ 发布源在统一 launch 中互斥。CLI 发现外部来源时拒绝启动，不接管其他实验。正弦模式的 `positions` 是中心，固定模式才表示固定角度。

参数被接收与观察成功分开呈现。TF 按状态消息时间戳查询；姿态阶跃附近可能发生 TF 插值，CLI 会标注首帧并补充后续观察。日志和观察结果不能替代真实控制、轨迹执行或人工图形验收。

## 源码、产物和文档

- Python 用户工具在 `src/embodied_agent_lab/`，ROS 包在 `ros2_ws/src/`，启动及既有辅助命令在 `scripts/`。
- 所有 ROS 包共用 `ros2_ws/build/`、`ros2_ws/install/` 和 `ros2_ws/log/`，CLI 默认加载 `ros2_ws/install/`。`artifacts/` 只存实验日志、录包与截图，CLI 会话日志写入 `artifacts/week04/cli/`。生成产物不提交 Git。
- 当前使用入口和最终文件清单在 `docs/labs/week04-integration.md`；模型细节在 `week04-stage1-description.md`；旧实验结论保留在对应阶段文档和精简结果中。
- 通用 Python 包版本为 0.4.0；历史通信包保留各自版本，不为统一数字修改未涉及的功能。

## 后续阶段

规划控制、物理仿真、感知、智能体及学习能力按后续阶段逐步加入。第四周不包含 Gazebo、MoveIt、ros2_control、模型推理或训练，当前的 Python 调参入口不作为未来的轨迹控制接口。
