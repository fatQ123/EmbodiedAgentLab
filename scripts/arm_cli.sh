#!/usr/bin/env bash
# 在本脚本的进程中加载现有 ROS 环境，不安装依赖或修改终端配置。

set -eo pipefail

arm_project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
arm_install_dir="$arm_project_root/ros2_ws/install"
arm_domain_id="${ROS_DOMAIN_ID:-222}"

arm_usage() {
    cat <<'USAGE'
用法：bash scripts/arm_cli.sh [--install-dir DIR] [--domain-id ID]

启动 v0.4 两关节机械臂中文交互菜单，无需提前 source。
  --install-dir DIR  已构建的安装目录（相对路径以当前目录为基准）
                    默认 ros2_ws/install
  --domain-id ID     ROS Domain，0–232；默认继承 ROS_DOMAIN_ID，否则 222
  -h, --help        显示帮助，不加载 ROS 或启动节点

使用已有 /opt/ros/jazzy 和系统 Python；不安装、不自动构建。
默认无界面；仅手动选择滑块或启用 RViz 时打开图形程序。
USAGE
}

arm_error() {
    printf '错误：%s\n' "$*" >&2
    exit 2
}

while (( $# )); do
    case "$1" in
        -h|--help) arm_usage; exit 0 ;;
        --install-dir|--domain-id)
            (( $# >= 2 )) || arm_error "$1 缺少参数；使用 --help 查看用法。"
            [[ -n "$2" && "$2" != --* ]] || arm_error "$1 缺少参数。"
            if [[ "$1" == --install-dir ]]; then
                arm_install_dir="$2"
            else
                arm_domain_id="$2"
            fi
            shift 2
            ;;
        --install-dir=*) arm_install_dir="${1#*=}"; shift ;;
        --domain-id=*) arm_domain_id="${1#*=}"; shift ;;
        *) arm_error "未知参数 $1；使用 --help 查看用法。" ;;
    esac
done

[[ "$arm_domain_id" =~ ^[0-9]{1,3}$ ]] || arm_error 'Domain 必须是 0–232 的整数。'
arm_domain_id=$((10#$arm_domain_id))
(( arm_domain_id <= 232 )) || arm_error 'Domain 必须是 0–232 的整数。'
[[ -n "$arm_install_dir" ]] || arm_error '--install-dir 不能为空。'

if [[ ! -r /opt/ros/jazzy/setup.bash || ! -x /usr/bin/python3 ]]; then
    printf '%s\n' '错误：缺少 /opt/ros/jazzy/setup.bash 或系统 Python。' \
        '请先按 docs/labs/week04-integration.md 手动准备 ROS Jazzy 环境。' \
        '验证命令：source /opt/ros/jazzy/setup.bash && /usr/bin/python3 -c "import rclpy"' >&2
    exit 2
fi

if [[ ! -r "$arm_install_dir/setup.bash" || ! -r "$arm_install_dir/local_setup.bash" ]]; then
    printf '错误：构建产物 %s 缺少 setup.bash 或 local_setup.bash\n' "$arm_install_dir" >&2
    printf '%s\n' '可用 --install-dir 指定已构建安装目录，或手动构建标准 ROS 工作空间：' >&2
    printf '  cd %q\n' "$arm_project_root/ros2_ws" >&2
    printf '%s\n' '  source /opt/ros/jazzy/setup.bash' \
        '  colcon build --base-paths src --executor sequential \' \
        '    --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 -DBUILD_TESTING=OFF' >&2
    exit 2
fi
arm_install_dir="$(cd -- "$arm_install_dir" && pwd)"

# 仅影响本脚本；不混入调用终端的 Conda、旧 overlay 或历史下载库。
unset PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH
unset LD_LIBRARY_PATH COLCON_CURRENT_PREFIX AMENT_CURRENT_PREFIX
unset COLCON_PYTHON_EXECUTABLE AMENT_PYTHON_EXECUTABLE
unset ROS_DISTRO ROS_VERSION ROS_PYTHON_VERSION ROS_LOCALHOST_ONLY ROS_STATIC_PEERS
export PATH=/usr/bin:/bin
export COLCON_PYTHON_EXECUTABLE=/usr/bin/python3
export AMENT_PYTHON_EXECUTABLE=/usr/bin/python3
export PYTHONNOUSERSITE=1
source /opt/ros/jazzy/setup.bash
# 只加载此安装目录，不重放 setup.bash 中构建时保存的旧 underlay 链。
source "$arm_install_dir/local_setup.bash"
export PYTHONPATH="$arm_project_root/src${PYTHONPATH:+:$PYTHONPATH}"
export ROS_DOMAIN_ID="$arm_domain_id"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST

exec /usr/bin/python3 -m embodied_agent_lab.arm_cli \
    --project-root "$arm_project_root" --install-dir "$arm_install_dir" \
    --domain-id "$arm_domain_id"
