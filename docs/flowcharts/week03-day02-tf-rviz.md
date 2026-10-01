# 第 3 周第 2 天：TF 坐标树与 RViz 工位

这张图把启动编排、TF/Marker 发布、RViz 合成显示和画面异常定位放在同一条路径中。最重要的边界是：Action 与空间可视化目前只是并行运行，Action 成功还不能证明空间定位正确。

```mermaid
flowchart TD
    START["启动 week03_day2.launch.py"]

    subgraph BOOT["启动编排"]
        START --> CORE["包含 three_nodes.launch.py"]
        CORE --> SENSOR["sensor_simulator<br/>发布 /sensor_state"]
        CORE --> EXECUTOR["task_executor<br/>Service + Action"]
        CORE --> MONITOR["status_monitor<br/>状态观察"]
        SENSOR --> EXECUTOR
        SENSOR -- "/sensor_state" --> MONITOR
        EXECUTOR -- "/task_status" --> MONITOR

        START --> VIS["启动 workcell_visualizer"]
        START --> RVIZ_SWITCH{"use_rviz = true？"}
        RVIZ_SWITCH -- "是" --> RVIZ["rviz2 加载<br/>week03_workcell.rviz"]
        RVIZ_SWITCH -- "否" --> HEADLESS["无界面运行<br/>用于自动化测试"]
    end

    subgraph PUBLISH["空间数据发布"]
        VIS --> RATE{"frame_publish_rate<br/>是否为 0.1～100 Hz 有限值？"}
        RATE -- "否" --> START_FAIL["参数校验失败<br/>节点安全退出"]
        RATE -- "是" --> PUB_INIT["创建静态/动态 TF Broadcaster<br/>和 Marker Publisher"]
        PUB_INIT --> STATIC["一次发布 /tf_static<br/>world → base_link<br/>camera_link → tool0"]
        PUB_INIT --> TIMER["启动时立即执行<br/>随后周期调用 publish_scene"]
        TIMER --> DYNAMIC["发布 /tf<br/>base_link → camera_link<br/>时间戳持续刷新"]
        TIMER --> MARKER["发布目标 Marker<br/>tool0 前方 0.25 m 绿色 Cube<br/>Reliable + Transient Local"]
    end

    subgraph DISPLAY["TF 合成与 RViz 呈现"]
        STATIC --> BUFFER["TF Buffer 合成<br/>world → tool0"]
        DYNAMIC --> BUFFER
        RVIZ --> TF_DISPLAY["TF Display<br/>Fixed Frame = world"]
        BUFFER --> TF_DISPLAY
        RVIZ --> MARKER_FILTER["Marker Display<br/>请求 tool0 → world"]
        MARKER --> MARKER_FILTER
        BUFFER --> MARKER_FILTER
        MARKER_FILTER --> CAN_TRANSFORM{"变换可用且 Marker 字段有效？"}
        CAN_TRANSFORM -- "是" --> NORMAL["正常画面<br/>四帧树为 OK<br/>tool0 坐标轴 + 绿色检查区域"]
        CAN_TRANSFORM -- "否" --> VISUAL_ERROR["Marker 不显示<br/>或 RViz 报变换错误"]
    end

    EXECUTOR -. "并行运行；当前 Action 不读取 TF" .-> NORMAL

    subgraph DEBUG["画面异常的调试决策"]
        NORMAL --> ACCEPT{"位置和数值符合预期？"}
        VISUAL_ERROR --> TF_OK{"等待 DDS 发现后<br/>tf2_echo world tool0 是否持续成功？"}
        TF_DISPLAY --> TF_OK

        TF_OK -- "否" --> STATIC_OK{"/tf_static 两条静态边存在？"}
        STATIC_OK -- "否" --> FIX_STATIC["检查节点、frame_id、父子关系<br/>和 Transient Local QoS"]
        STATIC_OK -- "是" --> DYNAMIC_OK{"/tf 中 base_link → camera_link<br/>是否持续刷新？"}
        DYNAMIC_OK -- "否" --> FIX_DYNAMIC["检查节点存活、发布频率和时间戳<br/>定位缺失或过期动态 TF"]
        DYNAMIC_OK -- "是" --> FIX_RVIZ["检查 Fixed Frame=world<br/>并排除初始发现延迟"]

        TF_OK -- "是" --> MARKER_OK{"使用 Transient Local + Reliable<br/>能收到 Marker？"}
        MARKER_OK -- "否" --> TOPIC_QOS["检查话题名、Publisher endpoint<br/>和 RViz Topic QoS"]
        MARKER_OK -- "是" --> PAYLOAD_OK{"frame_id、时间戳、alpha、scale<br/>和 Namespace 正确？"}
        PAYLOAD_OK -- "否" --> FIX_MARKER["修复 Marker 消息<br/>或 RViz Display 配置"]
        PAYLOAD_OK -- "是" --> FIX_FILTER["检查 TF 时间覆盖范围<br/>和 RViz Message Filter"]

        ACCEPT -- "否" --> CALIBRATE["对照各段平移、四元数和局部位姿<br/>定位外参或标定错误"]
        ACCEPT -- "是" --> EVIDENCE["保存 RViz 截图、tf2_echo、view_frames、<br/>Marker、Action 日志和测试结果"]
    end
```

## 最短调试命令

```bash
ros2 run tf2_ros tf2_echo world tool0
ros2 topic echo /tf_static --qos-durability transient_local --once
ros2 topic hz /tf
ros2 topic echo /inspection_target_marker visualization_msgs/msg/Marker \
  --qos-durability transient_local --qos-reliability reliable --once
ros2 run tf2_tools view_frames -t 5 -o /tmp/week03_frames
```

判断顺序是“整链是否连通 → 静态边 → 动态边 → Marker 消息与 QoS → RViz 配置 → 数值是否正确”。刚启动 `tf2_echo` 时出现一次 `frame does not exist` 可能只是 DDS 发现延迟，持续失败才是故障。

对应实现与证据：

- [TF 与 Marker 发布器](../../ros2_ws/src/embodied_comm/embodied_comm/workcell_visualizer.py)
- [Day 2 Launch](../../ros2_ws/src/embodied_comm/launch/week03_day2.launch.py)
- [RViz 配置](../../ros2_ws/src/embodied_comm/config/week03_workcell.rviz)
- [第 2 天实验记录](../labs/week03-day2-tf-rviz.md)
