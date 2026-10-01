#!/usr/bin/env bash
# 导出确定提交，在无终端配置、无旧 overlay 的环境中验收第三周发布。
set -eo pipefail
if [[ "${1:-}" != "--clean-worker" ]]; then
  if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "用法：bash scripts/verify_ros2_release.sh OUTPUT_DIR [REF]" >&2
    exit 2
  fi
  release_repo="$(git rev-parse --show-toplevel)"
  release_dir="$(realpath -m "$1")"
  release_ref="${2:-HEAD}"
  release_commit="$(git -C "$release_repo" rev-parse "${release_ref}^{commit}")"
  if [[ -e "$release_dir" ]]; then
    echo "输出目录已存在，请使用新目录：$release_dir" >&2
    exit 2
  fi
  mkdir -p "$release_dir/source"
  printf '%s\n' "$release_commit" > "$release_dir/source-commit.txt"
  git -C "$release_repo" ls-tree -r "$release_commit" -- \
    src ros2_ws/src scripts pyproject.toml environment.yml \
    > "$release_dir/executable-tree.txt"
  git -C "$release_repo" archive "$release_commit" | tar -x -C "$release_dir/source"
  exec env -i HOME="${HOME}" USER="$(id -un)" PATH=/usr/bin:/bin \
    LANG=C.UTF-8 TZ=Asia/Shanghai \
    /bin/bash --noprofile --norc \
    "$release_dir/source/scripts/verify_ros2_release.sh" --clean-worker "$release_dir"
fi
release_dir="$2"
trap 'release_code=$?; if [[ $release_code -eq 0 ]]; then printf "passed\n"; else printf "failed (exit=%s)\n" "$release_code"; fi > "$release_dir/status.txt"' EXIT
{
  date --iso-8601=seconds
  /usr/bin/python3 --version
  printf 'initial AMENT_PREFIX_PATH=%s\n' "${AMENT_PREFIX_PATH:-<unset>}"
  printf 'initial COLCON_PREFIX_PATH=%s\n' "${COLCON_PREFIX_PATH:-<unset>}"
  printf 'initial PYTHONPATH=%s\n' "${PYTHONPATH:-<unset>}"
  printf 'initial CONDA_PREFIX=%s\n' "${CONDA_PREFIX:-<unset>}"
} | tee "$release_dir/clean-environment.log"
source /opt/ros/jazzy/setup.bash
export ROS_LOG_DIR="$release_dir/ros-logs"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS2CLI_DISABLE_DAEMON=1
export PYTHONNOUSERSITE=1
cd "$release_dir/source/ros2_ws"
colcon build --packages-up-to embodied_comm embodied_comm_cpp \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 2>&1 | tee "$release_dir/build.log"
source install/setup.bash
for release_package in embodied_interfaces embodied_comm embodied_comm_cpp; do
  release_prefix="$(ros2 pkg prefix "$release_package")"
  printf '%s: %s\n' "$release_package" "$release_prefix"
  case "$release_prefix" in
    "$release_dir/source/ros2_ws/install/"*) ;;
    *) echo "错误：依赖了本轮安装目录外的包" >&2; exit 1 ;;
  esac
done | tee "$release_dir/prefixes.log"
/usr/bin/python3 -c \
  'import embodied_interfaces.action; from embodied_interfaces.action import ExecuteTask; print(embodied_interfaces.action.__file__); print(ExecuteTask.Goal(), ExecuteTask.Result(), ExecuteTask.Feedback())' \
  | tee "$release_dir/interface-import.log"
ros2 interface show embodied_interfaces/action/ExecuteTask \
  | tee "$release_dir/action-interface.log"
cd "$release_dir/source"
export PYTHONPATH="$release_dir/source/src${PYTHONPATH:+:$PYTHONPATH}"
/usr/bin/python3 -m embodied_agent_lab.doctor --skip-network --json > "$release_dir/doctor.json"
/usr/bin/python3 scripts/rehearse_week03.py --output "$release_dir/normal" \
  2>&1 | tee "$release_dir/normal-demo.log"
cd "$release_dir/source/ros2_ws"
# 七场录包之后，编排器执行全部 ROS 包测试和仓库级测试。
ros2 run embodied_comm week03_day6_evidence --output-dir "$release_dir/faults" \
  2>&1 | tee "$release_dir/fault-matrix.log"
cd "$release_dir/source"
/usr/bin/python3 scripts/verify_ros2_language_pairs.py \
  --output "$release_dir/language-pairs" --domain-start 204 \
  2>&1 | tee "$release_dir/language-pairs.log"
printf '干净终端发布演练通过：%s\n' "$release_dir"
