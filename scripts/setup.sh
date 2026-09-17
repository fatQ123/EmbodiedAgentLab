#!/usr/bin/env bash
# 为 EmbodiedAgentLab（具身智能体实验室）创建本地开发环境。

set -euo pipefail

# 检查系统是否安装 Python 虚拟环境组件，并给出明确的中文修复方法。
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
    echo "缺少 Python 虚拟环境组件。Ubuntu 24.04 请先执行：sudo apt install python3.12-venv" >&2
    exit 1
fi

# 创建隔离的 Python（编程语言）虚拟环境。
python3 -m venv .venv

# 激活虚拟环境。
source .venv/bin/activate

# 更新安装工具并安装项目与测试依赖。
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

echo "环境安装完成。请运行：source .venv/bin/activate"
