# 第 3 周第 7 天发布验收证据

本轮完整演练于 2026-10-01 通过，源码候选为 `e24bfacbbbba86694cfa8e100e867cd97dad51ed`。发布提交只在此候选上补充文档与精简证据，可执行源码、测试和构建配置保持一致；最终提交通过 `git rev-parse 'refs/tags/v0.3^{commit}'` 查询。

完整日志、源码归档、构建目录及七场 MCAP 保存在：

```text
/home/fatbro/workspace/artifacts/week03-day7/clean-candidate-20261001-g/
```

该目录是本机运行产物，不随 Git 分发。其他机器按[第 7 天实验](../../week03-day7-release.md)从 `refs/tags/v0.3` 重新生成；输出目录必须尚不存在。先前失败候选 a～f 同样保留在 `artifacts/week03-day7/`，不作为本版通过凭证。

## 结果与收据

| 项目 | 实测结果 | 文件 |
|---|---|---|
| 干净环境 | 初始 AMENT/COLCON/PYTHONPATH/CONDA 均未设置 | [环境](clean-environment.log)、[候选 SHA](source-commit.txt) |
| 构建 | 三包成功，9.26 秒，安装前缀全部属于本轮 | [构建](build.log)、[安装前缀](prefixes.log)、[接口导入](interface-import.log)、[Action 定义](action-interface.log) |
| 正常质检与恢复 | WP-001 成功、WP-002 取消、WP-003 再次成功；四个终态记录各一次 | [演示输出](normal-demo.log)、[协议结果](normal-demo.json)、[节点日志](normal-launch.log) |
| 响应时间 | Action 运行中 Service 0.003215 秒；取消到 CANCELED 0.201968 秒 | [演示结果](normal-demo.json) |
| ROS 回归 | Python 156 + GoogleTest 5 全通过；colcon 162 条包含一个 CTest 包装项 | [测试输出](colcon-test.log)、[汇总](colcon-test-result.log) |
| 仓库回归 | 18 项通过；合计 179 项独立测试，零失败、零跳过 | [仓库测试](repository-tests.log) |
| 六类故障 | 七场通过，Recorder/Launch 均以 SIGINT 正常退出，MCAP 共 7,426 条 | [采集汇总](fault-summary.json)、[原始中文记录](fault-records.md)、[独立读包审查](bag-review.json) |
| 四组通信 | 每组正常、错连、修复均通过，所有项目节点退出码为 0 | [输出](language-pairs.log)、[Python→Python](rclpy-to-rclpy.json)、[C++→C++](rclcpp-to-rclcpp.json)、[Python→C++](rclpy-to-rclcpp.json)、[C++→Python](rclcpp-to-rclpy.json) |
| 最终通过状态 | `passed` | [脚本状态](status.txt)、[源码树与进程检查](release-check.json) |

按 QoS、话题停止、TF 缺失、TF 过期、Service 超时、Action 取消、节点崩溃顺序，实际包消息数为 **817 / 887 / 851 / 1,301 / 1,091 / 1,588 / 891**。独立读包报告逐条反序列化 MCAP，不使用采集配置中的预设 Topic 列表代替实际话题计数；其审查范围仅为录包内容，回归结论来自另外的测试收据。

## 解读边界

- `--cancel-at 40` 表示收到首个达到或超过阈值的反馈后请求取消。正常演示实测触发反馈为 40.1735%，故障矩阵为 44.1719%；原始故障记录中“40%”是阈值简称，不表示精确停止。
- 原始报告的“画面”条目描述预期 RViz 差异。本轮自动验收使用 `use_rviz:=false`，检验 TF、Marker 与诊断数据，没有声称新做了桌面截图验收。人工观察按[第 2 天实验](../../week03-day2-tf-rviz.md)执行。
- Service 超时和进程退出不能只用话题回放解释，须结合完整目录中的客户端与 Launch 日志。Topic 停止时执行器消费到的实际最后序号可能不同于注入 Timer 的停止序号，详见独立读包记录。
- 当前验收的是工业工位的软件通信、取消恢复、诊断和可追溯交付；不代表已实现缺陷识别、PLC、机械臂动作、真实分拣或硬件安全联锁。

## 源码一致性与标签核对

[executable-tree.txt](executable-tree.txt) 保存候选的 Git blob 清单；SHA-256 为 `32953a1dbc4baf7047aecbd653a148a12583e21046f0022e98d458ab963d4627`。比对范围包括 `src`、`ros2_ws/src`、`scripts`、`tests`、`pyproject.toml`、`environment.yml`，不把测试排除在发布一致性之外。

```bash
git diff --exit-code e24bfacbbbba86694cfa8e100e867cd97dad51ed \
  'refs/tags/v0.3^{commit}' -- \
  src ros2_ws/src scripts tests pyproject.toml environment.yml
git show --no-patch refs/tags/v0.3
```

本地 annotated tag 与最终提交的实际对象 ID、源码树复核结果另保存到完整目录的 `tag-verification.log`，避免已标记文档填写自身 SHA 形成循环。本次不向远端推送。
