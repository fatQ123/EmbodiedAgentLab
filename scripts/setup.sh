#!/usr/bin/env bash
# 使用 Conda（环境与包管理器）创建 EmbodiedAgentLab（具身智能体实验室）开发环境。

set -euo pipefail

# 检查当前终端是否能找到 Conda；若已安装但未加载，请先初始化终端。
if ! command -v conda >/dev/null 2>&1; then
    echo "当前终端找不到 Conda。请先执行 conda init bash，重新打开终端后再运行本脚本。" >&2
    exit 1
fi

# 根据 environment.yml（环境配置文件）创建或更新同名环境，并移除配置中已删除的依赖。
conda env update --name embodied-agent-lab --file environment.yml --prune

# 在目标环境内以可编辑方式安装当前项目，修改源码后无需重复安装。
conda run --name embodied-agent-lab python -m pip install --editable .

echo "环境安装完成。请运行：conda activate embodied-agent-lab"
