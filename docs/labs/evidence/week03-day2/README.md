# 第 3 周第 2 天实测证据

本目录保存正常 TF 树与工业质检工位可视化的可审计证据。测试日期为 2026-09-20，环境为 Ubuntu 24.04 与 ROS 2 Jazzy。

| 文件 | 证据 |
|---|---|
| `build-test.log` | 全量构建、ROS 测试、根项目测试和差异检查的关键输出 |
| `tf-chain.log` | `tf2_echo world tool0` 的合成变换 |
| `view-frames.log` | `view_frames` 发现三条 TF 边的原始响应 |
| `tf-tree.png` / `tf-tree.pdf` | `view_frames` 生成的坐标树图 |
| `marker.log` | `/inspection_target_marker` 的实际消息 |
| `action-spatial-demo.log` | RViz 场景运行期间完成 `WP-DAY2` Action 的输出 |
| `rviz-normal.png` | 正常工位 RViz 截图，TF 全局状态为 OK |

说明：`tf2_echo` 起始的一次 frame 不存在提示来自新进程的 DDS 发现阶段，后续连续两帧已成功；`view_frames` 中静态边的 `10000 Hz` 是 TF 工具的显示惯例。
