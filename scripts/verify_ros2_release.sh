#!/usr/bin/env bash
# 从当前 HEAD 的已提交内容导出全新源码，构建、测试并验证已安装的 Launch。
set -eo pipefail
if [[ $# -ne 1 ]]; then
  echo "用法：bash scripts/verify_ros2_release.sh /tmp/新的验收目录" >&2
  exit 2
fi
repo_root="$(git rev-parse --show-toplevel)"
release_dir="$(realpath -m "$1")"
if [[ -e "$release_dir" ]]; then
  echo "输出目录已存在，请使用新目录：$release_dir" >&2
  exit 2
fi
mkdir -p "$release_dir/source"
git -C "$repo_root" rev-parse HEAD > "$release_dir/source-commit.txt"
git -C "$repo_root" archive HEAD | tar -x -C "$release_dir/source"
source /opt/ros/jazzy/setup.bash
export ROS_LOG_DIR="$release_dir/ros-logs"
cd "$release_dir/source/ros2_ws"
colcon build --packages-select embodied_comm embodied_comm_cpp \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 2>&1 | tee "$release_dir/build.log"
source install/setup.bash
ros2 pkg prefix embodied_comm | tee "$release_dir/python-prefix.log"
ros2 pkg prefix embodied_comm_cpp | tee "$release_dir/cpp-prefix.log"
colcon test --packages-select embodied_comm embodied_comm_cpp \
  --event-handlers console_direct+ 2>&1 | tee "$release_dir/test.log"
colcon test-result --verbose | tee "$release_dir/test-result.log"
# 上述测试含真实 ros2 launch、参数与服务成功/失败、退出清理，非只测文件存在。
cd "$release_dir/source"
PYTHONPATH="$release_dir/source/src${PYTHONPATH:+:$PYTHONPATH}" /usr/bin/python3 -m unittest discover -s tests 2>&1 | tee "$release_dir/doctor-tests.log"
/usr/bin/python3 scripts/verify_ros2_language_pairs.py \
  --output "$release_dir/language-pairs" --domain-start 204
