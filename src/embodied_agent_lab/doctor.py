"""环境诊断命令行工具。"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    """保存一项环境检查的名称、状态和说明。"""

    name: str
    status: str
    detail: str


def collect_checks() -> list[CheckResult]:
    """收集第一版无需外部依赖的环境检查结果。"""

    return [
        CheckResult("操作系统", "正常", platform.platform()),
        CheckResult("Python 版本", "正常", platform.python_version()),
        CheckResult(
            "Git 版本控制工具",
            "正常" if shutil.which("git") else "警告",
            shutil.which("git") or "未找到可执行文件",
        ),
        CheckResult(
            "ROS 2 发行版",
            "正常" if os.getenv("ROS_DISTRO") else "警告",
            os.getenv("ROS_DISTRO", "未设置 ROS_DISTRO 环境变量"),
        ),
        CheckResult(
            "串口设备",
            "正常" if any(os.path.exists(path) for path in ("/dev/ttyUSB0", "/dev/ttyACM0")) else "警告",
            "已检测到常见串口设备"
            if any(os.path.exists(path) for path in ("/dev/ttyUSB0", "/dev/ttyACM0"))
            else "未检测到 /dev/ttyUSB0 或 /dev/ttyACM0",
        ),
    ]


def main() -> int:
    """打印诊断结果；警告用于提示，不导致命令失败。"""

    print("EmbodiedAgentLab 环境诊断")
    for result in collect_checks():
        symbol = "✓" if result.status == "正常" else "!"
        print(f"{symbol} [{result.status}] {result.name}: {result.detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
