"""环境诊断命令行工具。"""

from __future__ import annotations

import argparse  # 使用标准库解析子命令和选项。
import json  # 将报告序列化为机器可读的 JSON。
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass  # 将检查结果数据类转换为字典。
from typing import Literal  # 限定检查状态的类型标注。


@dataclass(frozen=True)
class CheckResult:
    """保存一项环境检查的名称、状态和说明。"""

    name: str
    status: Literal["正常", "警告", "失败"]  # 警告不阻塞运行，失败导致退出码为 1。
    detail: str
    check_id: str  # 为机器提供不随中文显示名称变化的标识。
    suggestion: str = ""  # 可选的后续处理建议。


def collect_checks() -> list[CheckResult]:
    """收集第一版无需外部依赖的环境检查结果。"""

    return [
        CheckResult("操作系统", "正常", platform.platform(), "os"),  # 标识操作系统检查。
        CheckResult("Python 版本", "正常", platform.python_version(), "python"),  # 标识解释器检查。
        CheckResult(
            "Git 版本控制工具",
            "正常" if shutil.which("git") else "警告",
            shutil.which("git") or "未找到可执行文件",
            "git",  # Git 检查的稳定标识。
            "若未找到 Git，请通过系统包管理器安装。",  # 仅提供建议，不自动修改系统。
        ),
        CheckResult(
            "Conda 环境",
            "正常" if os.getenv("CONDA_DEFAULT_ENV") else "警告",
            os.getenv("CONDA_DEFAULT_ENV", "当前终端未激活 Conda 环境"),
            "conda",  # Conda 检查的稳定标识。
            "如使用项目 Conda 环境，请先激活 embodied-agent-lab。",  # 环境缺失仅作提示。
        ),
        CheckResult(
            "ROS 2 发行版",
            "正常" if os.getenv("ROS_DISTRO") else "警告",
            os.getenv("ROS_DISTRO", "未设置 ROS_DISTRO 环境变量"),
            "ros",  # ROS 检查的稳定标识。
            "运行 ROS 实验前，请加载 /opt/ros/jazzy/setup.bash。",  # 提示加载已有安装。
        ),
        CheckResult(
            "串口设备",
            "正常" if any(os.path.exists(path) for path in ("/dev/ttyUSB0", "/dev/ttyACM0")) else "警告",
            "已检测到常见串口设备"
            if any(os.path.exists(path) for path in ("/dev/ttyUSB0", "/dev/ttyACM0"))
            else "未检测到 /dev/ttyUSB0 或 /dev/ttyACM0",
            "serial",  # 串口检查的稳定标识。
            "仿真实验可忽略；使用真实设备时检查连接和设备路径。",  # 无硬件不阻塞实验。
        ),
    ]


def build_parser() -> argparse.ArgumentParser:
    """建立命令行协议；帮助返回 0，用法错误由 argparse 返回 2。"""

    parser = argparse.ArgumentParser(  # 构造顶层解析器，禁止模糊缩写选项。
        prog="embodiedlab", description="具身智能体实验室命令行工具", allow_abbrev=False
    )
    commands = parser.add_subparsers(dest="command", required=True)  # 要求明确选择子命令。
    doctor = commands.add_parser(  # 注册诊断子命令，并提供独立帮助页面。
        "doctor", help="检查开发环境", description="检查开发环境并输出诊断报告", allow_abbrev=False
    )
    doctor.add_argument(  # --json 是开关，不需要额外的参数值。
        "--json", dest="json_output", action="store_true", help="仅向标准输出写入 JSON 报告"
    )
    return parser  # 返回解析器，供命令入口使用。


def main(argv: list[str] | None = None) -> int:
    """运行选定命令；正常或警告返回 0，检查失败返回 1。"""

    args = build_parser().parse_args(argv)  # None 表示读取真实命令行，列表便于测试。
    checks = collect_checks()  # 解析成功后才执行诊断，帮助和非法参数不会触发检查。
    summary = {status: sum(item.status == status for item in checks) for status in ("正常", "警告", "失败")}  # 统计各状态数量。
    exit_code = 1 if summary["失败"] else 0  # 可选能力缺失仅为警告，不改变成功退出状态。
    if args.json_output:  # JSON 模式只输出一个 JSON 对象，不混入普通文本。
        report = {  # 固定报告字段，并为后续协议变更保留版本号。
            "schema_version": 1,  # 报告格式版本，不是项目发布版本。
            "checks": [asdict(item) for item in checks],  # 保留每项检查的完整字段。
            "summary": summary,  # 给调用方提供结果数量汇总。
            "exit_code": exit_code,  # 与进程实际退出状态保持一致。
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))  # 保留中文，使用两空格缩进。
    else:  # 默认输出适合终端阅读的文本报告。
        print("EmbodiedAgentLab 环境诊断")  # 显示报告标题。
        for result in checks:  # 依次打印每项检查。
            symbol = {"正常": "✓", "警告": "!", "失败": "×"}[result.status]  # 状态对应显示符号。
            print(f"{symbol} [{result.status}] {result.name}: {result.detail}")  # 打印状态与证据。
            if result.status != "正常" and result.suggestion:  # 只为异常状态显示已有建议。
                print(f"  建议：{result.suggestion}")  # 不自动执行建议中的操作。
        print(f"汇总：正常 {summary['正常']}，警告 {summary['警告']}，失败 {summary['失败']}")  # 展示总体结果。
    return exit_code  # 交给控制台入口或 sys.exit 转换为进程退出状态。


if __name__ == "__main__":
    sys.exit(main())
