"""环境诊断命令行工具。"""

from __future__ import annotations

import argparse  # 使用标准库解析子命令和选项。
import json  # 将报告序列化为机器可读的 JSON。
import os
import platform
import sys
from dataclasses import asdict, dataclass  # 将检查结果数据类转换为字典。
from typing import Literal  # 限定检查状态的类型标注。

from embodied_agent_lab.probes import NETWORK_URL, ProbeResult, probe_network, probe_ros_python, probe_serial, run_probe  # 引入有超时保护的只读探测。


@dataclass(frozen=True)
class CheckResult:
    """保存一项环境检查的名称、状态和说明。"""

    name: str
    status: Literal["正常", "警告", "失败"]  # 警告不阻塞运行，失败导致退出码为 1。
    detail: str
    check_id: str  # 为机器提供不随中文显示名称变化的标识。
    suggestion: str = ""  # 可选的后续处理建议。


def command_check(name: str, check_id: str, result: ProbeResult, suggestion: str, required: bool = False) -> CheckResult:
    """将底层探测结果映射为必要项失败或可选项警告。"""

    status = "正常" if result.ok else ("失败" if required else "警告")  # 当前仅 Git 属于必要的外部开发工具。
    return CheckResult(name, status, result.detail, check_id, "" if result.ok else suggestion)  # 正常结果无需处理建议。


def collect_checks(skip_network: bool = False) -> list[CheckResult]:
    """逐项收集环境证据；可选硬件或 ROS 缺失不阻塞第一阶段开发。"""

    ros_distro = os.getenv("ROS_DISTRO")  # 分开发行版声明和真实工具可用性。
    conda_env = os.getenv("CONDA_DEFAULT_ENV")  # Conda 是推荐环境管理方式，不是运行本工具的必要条件。
    python_ok = sys.version_info >= (3, 10)  # 与 pyproject.toml 声明的最低版本保持一致。
    checks = [  # 每个结果使用固定标识，便于 JSON 调用方处理。
        CheckResult("操作系统", "正常", platform.platform(), "os"),  # 报告系统信息，不声称所有平台都支持 ROS Jazzy。
        CheckResult("Python 版本", "正常" if python_ok else "失败", f"{platform.python_version()}；解释器={sys.executable}；最低要求 3.10", "python", "" if python_ok else "请使用 Python 3.10 或更高版本；ROS Jazzy 实验使用 3.12。"),  # 检查解释器最低版本。
        command_check("Git 版本控制工具", "git", run_probe(["git", "--version"]), "通过系统包管理器安装或修复 Git，并检查 PATH。", required=True),  # 实际运行版本命令。
        CheckResult("Conda 环境", "正常" if conda_env else "警告", conda_env or "当前终端未激活 Conda 环境", "conda", "" if conda_env else "如使用项目 Conda 环境，请先激活 embodied-agent-lab。"),  # 保留环境提示。
        CheckResult("ROS 2 发行版", "正常" if ros_distro == "jazzy" else "警告", f"ROS_DISTRO={ros_distro or '未设置'}；仅代表环境变量声明", "ros", "" if ros_distro == "jazzy" else "本实验使用 Jazzy；请加载 /opt/ros/jazzy/setup.bash。"),  # 不把变量当作安装成功证据。
        command_check("ROS 2 命令行", "ros_cli", run_probe(["ros2", "--help"]), "确认系统已安装 ROS 2，并在当前终端加载其 setup.bash。"),  # 检查命令能够启动，不创建节点。
        command_check("ROS Python 客户端", "ros_python", probe_ros_python(), "确认当前 Python 与系统 ROS 兼容，加载 ROS 环境并按错误补齐依赖；不要 pip 安装 rclpy。"),  # 验证真实解释器与消息原生库。
        command_check("NVIDIA 显卡与驱动", "gpu", run_probe(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"]), "无 NVIDIA 显卡可忽略；需要 GPU 时检查驱动和 nvidia-smi。"),  # 显示每块 NVIDIA GPU 的名称和驱动版本。
        command_check("CUDA 编译工具链", "cuda", run_probe(["nvcc", "--version"]), "未找到 nvcc 不代表显卡或框架 CUDA 运行时不可用；需要编译 CUDA 程序时再检查 Toolkit 与 PATH。"),  # 只检查 Toolkit 编译器，不冒充运行时验证。
        command_check("串口设备", "serial", probe_serial(), "仿真实验可忽略；真实设备请检查连接、用户组和读写权限。"),  # 只读枚举设备。
    ]
    if skip_network:  # 离线运行时明确记录未验证，避免假报正常。
        checks.append(CheckResult("网络连接", "警告", f"已按 --skip-network 跳过；目标={NETWORK_URL}；未验证连接", "network", "需要网络诊断时移除 --skip-network。"))  # 不发出外部请求。
    else:  # 默认检查明确的软件源 HTTPS 入口。
        checks.append(command_check("网络连接", "network", probe_network(), "仅该目标检查失败，不代表整个网络断开；请检查 DNS、代理、证书及目标可达性。"))  # 网络不可达为警告。
    return checks  # 返回全部结果，不因单项失败提前结束。


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
    doctor.add_argument("--skip-network", action="store_true", help="跳过对 https://pypi.org/simple/ 的 HTTPS 检查")  # 提供离线诊断开关。
    return parser  # 返回解析器，供命令入口使用。


def main(argv: list[str] | None = None) -> int:
    """运行选定命令；正常或警告返回 0，检查失败返回 1。"""

    args = build_parser().parse_args(argv)  # None 表示读取真实命令行，列表便于测试。
    checks = collect_checks(skip_network=args.skip_network)  # 解析成功后才执行诊断，帮助和非法参数不会触发检查。
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
