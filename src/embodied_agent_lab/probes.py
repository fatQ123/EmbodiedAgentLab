"""只读环境探测；所有外部命令均有超时，不依赖第三方 Python 包。"""

from __future__ import annotations  # 延迟求值类型标注。

import glob  # 查找所有常见串口编号。
import os  # 检查设备访问权限。
import shutil  # 按当前 PATH 定位命令。
import subprocess  # 使用参数列表运行命令，不启动 Shell。
import sys  # 使用当前解释器检查 Python 依赖。
from dataclasses import dataclass  # 保存命令探测结果。

COMMAND_TIMEOUT = 5.0  # 每个外部命令最多等待五秒。
NETWORK_URL = "https://pypi.org/simple/"  # 只检查这个明确的 Python 软件源入口。


@dataclass(frozen=True)
class ProbeResult:
    """保存探测是否成功及其证据，不在此层决定必需或可选。"""

    ok: bool  # 命令是否成功并返回非空输出。
    detail: str  # 命令路径、输出或失败原因。


def run_probe(argv: list[str], timeout: float = COMMAND_TIMEOUT) -> ProbeResult:
    """捕获缺失、权限、超时及非零退出，并限制报告中的输出长度。"""

    executable = shutil.which(argv[0])  # 确认当前环境真正能找到命令。
    if executable is None:  # 不把命令不存在伪装为版本未知。
        return ProbeResult(False, f"未找到命令：{argv[0]}")  # 交给调用方决定状态。
    try:  # 执行可能失败的只读外部命令。
        result = subprocess.run(  # 使用绝对命令路径，避免 Shell 解释输入。
            [executable, *argv[1:]], capture_output=True, text=True, errors="replace", timeout=timeout
        )
    except subprocess.TimeoutExpired:  # 包括网络子进程中的 DNS 或连接阻塞。
        return ProbeResult(False, f"{executable} 执行超时（上限 {timeout:g} 秒）")  # 保留超时证据。
    except OSError as error:  # 处理无执行权限、文件消失等系统错误。
        return ProbeResult(False, f"{executable} 无法执行：{error}")  # 不让单项异常中断全部检查。
    output = (result.stdout.strip() or result.stderr.strip())[:2000]  # 选择输出证据，并限制报告长度。
    if result.returncode != 0:  # 命令存在并不代表能正常运行。
        return ProbeResult(False, f"{executable} 退出码 {result.returncode}：{output or '无错误详情'}")  # 记录原始错误。
    if not output:  # 这些版本和状态命令正常时均应给出结果。
        return ProbeResult(False, f"{executable} 返回空输出，无法确认状态")  # 不报告假成功。
    return ProbeResult(True, f"{executable}：{output}")  # 返回成功证据。


def probe_ros_python() -> ProbeResult:
    """使用当前 Python 导入客户端，并加载 String 的原生消息类型支持。"""

    script = "\n".join([  # 子进程可隔离原生库加载错误，并受到外层超时保护。
        "import sys  # 获取当前解释器路径",
        "import rclpy  # 导入 ROS Python 客户端",
        "from std_msgs.msg import String  # 导入标准消息类",
        "from rclpy.type_support import check_for_type_support  # 导入原生类型支持检查函数",
        "check_for_type_support(String)  # 加载并验证消息类型支持",
        "print(f'解释器={sys.executable}；rclpy={rclpy.__file__}；String 类型支持可用')  # 输出成功证据",
    ])
    return run_probe([sys.executable, "-c", script])  # 与启动 doctor 的解释器保持一致。


def probe_network() -> ProbeResult:
    """对子进程中的 HTTPS HEAD 请求设置总等待上限，不下载软件源索引。"""

    script = "\n".join([  # 外层超时还能限制 DNS 解析耗时。
        "import urllib.request  # 使用标准库 HTTPS 客户端并遵循系统代理设置",
        f"request = urllib.request.Request({NETWORK_URL!r}, method='HEAD')  # 仅请求响应头",
        "with urllib.request.urlopen(request, timeout=3.0) as response:  # 设置连接和读取等待时间",
        "    print(f'HTTP {response.status}；最终地址={response.url}')  # 显示实际响应目标",
    ])
    result = run_probe([sys.executable, "-c", script])  # 限制整个请求子进程最多等待五秒。
    return ProbeResult(result.ok, f"目标={NETWORK_URL}；{result.detail}")  # 成败都记录所检查的地址。


def probe_serial() -> ProbeResult:
    """枚举常见 USB/ACM 串口路径，仅检查权限，不打开设备或发送数据。"""

    try:  # 防止设备查询异常影响其他诊断项。
        devices = sorted(set(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')))  # 支持所有设备编号。
        if not devices:  # 仿真机器通常没有串口设备。
            return ProbeResult(False, "未发现 /dev/ttyUSB* 或 /dev/ttyACM*；未检查其他类型串口")  # 明确扫描范围。
        inaccessible = [path for path in devices if not os.access(path, os.R_OK | os.W_OK)]  # 检查当前用户读写权限。
    except OSError as error:  # 设备文件查询失败也要给出解释。
        return ProbeResult(False, f"串口枚举或权限检查失败：{error}")  # 返回非阻塞结果。
    detail = "发现设备：" + ", ".join(devices)  # 保留所有已发现路径。
    if inaccessible:  # 存在不代表当前用户可用。
        return ProbeResult(False, detail + "；当前用户缺少读写权限：" + ", ".join(inaccessible))  # 提示权限问题。
    return ProbeResult(True, detail + "；当前用户有读写权限，未验证实际通信")  # 不把文件权限当成通信验证。
