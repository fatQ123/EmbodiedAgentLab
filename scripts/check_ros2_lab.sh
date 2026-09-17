#!/usr/bin/env bash
# 检查 ROS 2（机器人操作系统第二代）开源学习实验所需的本地环境。

set -u

failures=0

# 打印一项检查结果；第一个参数是状态，第二个参数是中文说明。
print_result() {
    local status="$1"
    local message="$2"
    printf '[%s] %s\n' "$status" "$message"
}

# 检查当前终端是否加载 Conda（环境与包管理器）。
if command -v conda >/dev/null 2>&1; then
    print_result "正常" "已找到 Conda：$(conda --version 2>/dev/null)"
else
    print_result "失败" "未找到 Conda；请先初始化终端并激活 embodied-agent-lab 环境。"
    failures=$((failures + 1))
fi

# 检查当前是否处于本项目约定的 Conda 环境。
if [[ "${CONDA_DEFAULT_ENV:-}" == "embodied-agent-lab" ]]; then
    print_result "正常" "当前 Conda 环境为 embodied-agent-lab。"
else
    print_result "警告" "当前 Conda 环境为 ${CONDA_DEFAULT_ENV:-未激活}，建议执行 conda activate embodied-agent-lab。"
fi

# 检查 ROS 2 Jazzy（机器人操作系统第二代 Jazzy 发行版）环境变量。
if [[ "${ROS_DISTRO:-}" == "jazzy" ]]; then
    print_result "正常" "ROS 2 发行版为 jazzy。"
else
    print_result "失败" "ROS_DISTRO=${ROS_DISTRO:-未设置}；请执行 source /opt/ros/jazzy/setup.bash。"
    failures=$((failures + 1))
fi

# 检查 ROS 2、colcon（ROS 工作空间构建工具）与 Python 客户端库。
for command_name in ros2 colcon; do
    if command -v "$command_name" >/dev/null 2>&1; then
        print_result "正常" "已找到命令：$command_name。"
    else
        print_result "失败" "未找到命令：$command_name。"
        failures=$((failures + 1))
    fi
done

if python -c 'import rclpy; import std_msgs' >/dev/null 2>&1; then
    print_result "正常" "当前 Python 可以导入 rclpy 与 std_msgs。"
else
    print_result "失败" "当前 Python 无法导入 rclpy 或 std_msgs；不要通过 pip 安装 rclpy。"
    failures=$((failures + 1))
fi

# 检查官方示例是否位于约定的主仓库外目录。
reference_repo="/home/fatbro/open-source-labs/ros2-examples"
if [[ -d "$reference_repo/.git" ]]; then
    commit_id="$(git -C "$reference_repo" rev-parse --short HEAD 2>/dev/null)"
    branch_name="$(git -C "$reference_repo" branch --show-current 2>/dev/null)"
    print_result "正常" "已找到官方示例，分支为 $branch_name，提交为 $commit_id。"
else
    print_result "失败" "未找到官方示例：$reference_repo。"
    failures=$((failures + 1))
fi

if [[ "$failures" -eq 0 ]]; then
    print_result "通过" "实验环境检查全部通过。"
else
    print_result "未通过" "共有 $failures 项必要条件未满足。"
fi

exit "$failures"
