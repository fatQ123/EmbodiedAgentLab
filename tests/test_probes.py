"""环境诊断边界测试，不要求本机具有 ROS、显卡、串口或外网。"""

import io  # 捕获命令输出。
import json  # 验证完整报告。
import subprocess  # 构造外部命令返回值和超时异常。
import sys  # 核对 Python 探测使用当前解释器。
import unittest  # 使用标准库测试框架。
from contextlib import ExitStack, redirect_stdout  # 管理多个模拟和输出捕获。
from unittest.mock import patch  # 模拟操作系统边界。

from embodied_agent_lab import doctor, probes  # 导入待测模块。


class CommandProbeTest(unittest.TestCase):
    """验证所有命令共享的超时和错误处理。"""

    def test_success_uses_argument_list_and_timeout(self):
        """保留版本证据，并显式设置超时。"""
        completed = subprocess.CompletedProcess([], 0, "git version 2.43.0\n", "")  # 模拟成功输出。
        with patch.object(probes.shutil, "which", return_value="/usr/bin/git"), patch.object(probes.subprocess, "run", return_value=completed) as run:  # 替换系统调用。
            result = probes.run_probe(["git", "--version"])  # 执行待测探测。
        self.assertTrue(result.ok)  # 成功结果应正常。
        self.assertIn("git version 2.43.0", result.detail)  # 保留版本号。
        self.assertEqual(run.call_args.args[0], ["/usr/bin/git", "--version"])  # 不启动 Shell。
        self.assertEqual(run.call_args.kwargs["timeout"], 5.0)  # 防止无限等待。
        self.assertFalse(run.call_args.kwargs.get("shell", False))  # 参数不能被 Shell 解释。

    def test_missing_command_is_not_executed(self):
        """缺少命令时给出明确说明。"""
        with patch.object(probes.shutil, "which", return_value=None), patch.object(probes.subprocess, "run") as run:  # 模拟 PATH 中没有工具。
            result = probes.run_probe(["nvcc", "--version"])  # 检查可选编译器。
        self.assertFalse(result.ok)  # 不报告成功。
        self.assertIn("未找到命令：nvcc", result.detail)  # 保留缺失原因。
        run.assert_not_called()  # 不尝试调用不存在的命令。

    def test_timeout_and_os_error_are_results(self):
        """超时和无权限都变成报告，不抛出到入口。"""
        for error, expected in [(subprocess.TimeoutExpired("probe", 5), "超时"), (PermissionError("无权限"), "无法执行")]:  # 覆盖两类操作系统失败。
            with self.subTest(error=error), patch.object(probes.shutil, "which", return_value="/bin/probe"), patch.object(probes.subprocess, "run", side_effect=error):  # 注入失败。
                result = probes.run_probe(["probe"])  # 调用通用探测。
                self.assertFalse(result.ok)  # 失败不能成为正常状态。
                self.assertIn(expected, result.detail)  # 显示具体失败类别。

    def test_nonzero_and_empty_output_are_not_success(self):
        """命令存在或退出零并不足以证明获得版本信息。"""
        for completed, expected in [(subprocess.CompletedProcess([], 9, "", "driver unavailable"), "退出码 9"), (subprocess.CompletedProcess([], 0, "", ""), "空输出")]:  # 覆盖非零退出和无证据。
            with self.subTest(expected=expected), patch.object(probes.shutil, "which", return_value="/bin/probe"), patch.object(probes.subprocess, "run", return_value=completed):  # 不调用真实程序。
                result = probes.run_probe(["probe"])  # 获取探测结果。
                self.assertFalse(result.ok)  # 不误判成功。
                self.assertIn(expected, result.detail)  # 保留错误信息。

    def test_ros_uses_current_python_and_native_type_support(self):
        """环境变量不能代替导入验证。"""
        with patch.object(probes, "run_probe", return_value=probes.ProbeResult(False, "缺少 yaml")) as run:  # 模拟导入失败。
            result = probes.probe_ros_python()  # 构造并执行导入探测。
        self.assertFalse(result.ok)  # 保留导入失败结果。
        self.assertEqual(run.call_args.args[0][0], sys.executable)  # 必须用当前环境的 Python。
        self.assertIn("check_for_type_support(String)", run.call_args.args[0][2])  # 不只检查包目录存在。

    def test_network_target_is_in_success_and_failure(self):
        """无论成功或失败，都明确实际测试目标。"""
        for ok, detail in [(True, "HTTP 200"), (False, "DNS 解析失败"), (False, "超时"), (False, "证书验证失败")]:  # 覆盖网络常见结果。
            with self.subTest(detail=detail), patch.object(probes, "run_probe", return_value=probes.ProbeResult(ok, detail)) as run:  # 避免真实网络请求。
                result = probes.probe_network()  # 包装目标说明。
                self.assertEqual(result.ok, ok)  # 不改变探测状态。
                self.assertIn(probes.NETWORK_URL, result.detail)  # 不把单目标结果泛化成全网状态。
                self.assertIn(detail, result.detail)  # 保留具体原因。
                self.assertIn("method='HEAD'", run.call_args.args[0][2])  # 不下载整个索引内容。


class SerialProbeTest(unittest.TestCase):
    """验证枚举和权限，测试不打开真实设备。"""

    def test_nonzero_device_numbers_are_discovered(self):
        """覆盖不以零编号的设备。"""
        with patch.object(probes.glob, "glob", side_effect=[["/dev/ttyUSB3"], ["/dev/ttyACM7"]]), patch.object(probes.os, "access", return_value=True):  # 模拟多种串口。
            result = probes.probe_serial()  # 枚举设备。
        self.assertTrue(result.ok)  # 权限满足。
        self.assertIn("/dev/ttyUSB3", result.detail)  # 保留 USB 设备路径。
        self.assertIn("/dev/ttyACM7", result.detail)  # 保留 ACM 设备路径。
        self.assertIn("未验证实际通信", result.detail)  # 不夸大验证范围。

    def test_missing_or_inaccessible_devices(self):
        """无设备与权限不足分别说明。"""
        with patch.object(probes.glob, "glob", return_value=[]):  # 模拟无设备。
            self.assertFalse(probes.probe_serial().ok)  # 转为可选项警告。
        with patch.object(probes.glob, "glob", side_effect=[["/dev/ttyUSB1"], []]), patch.object(probes.os, "access", return_value=False):  # 模拟不可访问设备。
            result = probes.probe_serial()  # 执行权限探测。
        self.assertFalse(result.ok)  # 有路径但无权限不能报告可访问。
        self.assertIn("缺少读写权限", result.detail)  # 明确说明原因。


class CollectionTest(unittest.TestCase):
    """验证真实收集流程对必要项、可选项和离线模式的分类。"""

    def collect_with_results(self, git_ok=True, optional_ok=False, skip_network=False):
        """仅替换外部探测，保留真实检查列表与状态映射。"""
        with ExitStack() as stack:  # 自动恢复模拟环境。
            stack.enter_context(patch.dict(doctor.os.environ, {"ROS_DISTRO": "jazzy", "CONDA_DEFAULT_ENV": "embodied-agent-lab"}, clear=True))  # 固定环境变量。
            run = stack.enter_context(patch.object(doctor, "run_probe", side_effect=lambda argv: probes.ProbeResult(git_ok if argv[0] == "git" else optional_ok, "模拟结果")))  # 区分必要工具与可选工具。
            for name in ("probe_ros_python", "probe_serial", "probe_network"):  # 模拟其他探测。
                stack.enter_context(patch.object(doctor, name, return_value=probes.ProbeResult(optional_ok, "模拟结果")))  # 返回指定成功或失败结果。
            checks = doctor.collect_checks(skip_network=skip_network)  # 运行真实收集逻辑。
        return checks, run.call_args_list  # 返回结果及命令调用证据。

    def test_optional_missing_is_warning_but_git_missing_is_failure(self):
        """仿真机器无硬件仍可通过，缺少 Git 则提示必要项失败。"""
        for git_ok in (True, False):  # 同时验证必要项两种情况。
            with self.subTest(git_ok=git_ok):  # 给失败情况提供上下文。
                checks, _ = self.collect_with_results(git_ok=git_ok)  # 收集真实报告条目。
                by_id = {item.check_id: item for item in checks}  # 按稳定标识查找。
                self.assertEqual(by_id["git"].status, "正常" if git_ok else "失败")  # Git 是必要开发工具。
                for check_id in ("ros_cli", "ros_python", "gpu", "cuda", "serial", "network"):  # 可选能力缺失。
                    self.assertEqual(by_id[check_id].status, "警告")  # 不阻塞第一阶段开发。
                self.assertEqual(by_id["ros"].status, "正常")  # 即使声明 Jazzy，客户端仍可报告异常。

    def test_gpu_driver_and_cuda_toolkit_are_separate(self):
        """分别调用驱动查询与 Toolkit 版本工具。"""
        checks, calls = self.collect_with_results(optional_ok=True)  # 模拟所有工具可用。
        argv = [call.args[0] for call in calls]  # 获取命令参数。
        self.assertIn(["git", "--version"], argv)  # 确实读取 Git 版本。
        self.assertIn(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], argv)  # 读取 GPU 名称与驱动。
        self.assertIn(["nvcc", "--version"], argv)  # Toolkit 单独读取。
        self.assertTrue(all(item.status == "正常" for item in checks))  # 全部探测成功时没有误报。

    def test_skip_network_never_calls_network_probe(self):
        """离线选项要传到收集器，不能只改变显示。"""
        with patch.object(doctor, "run_probe", return_value=probes.ProbeResult(True, "成功")), patch.object(doctor, "probe_ros_python", return_value=probes.ProbeResult(True, "成功")), patch.object(doctor, "probe_serial", return_value=probes.ProbeResult(False, "无设备")), patch.object(doctor, "probe_network") as network, redirect_stdout(io.StringIO()) as output:  # 隔离外部操作。
            code = doctor.main(["doctor", "--json", "--skip-network"])  # 验证完整命令入口。
        network.assert_not_called()  # 确认没有发出请求。
        report = json.loads(output.getvalue())  # 输出仍然符合 JSON 协议。
        entry = next(item for item in report["checks"] if item["check_id"] == "network")  # 查找跳过结果。
        self.assertIn("跳过", entry["detail"])  # 显式说明未验证。
        self.assertEqual(entry["status"], "警告")  # 不能伪装成功。
        self.assertEqual(code, 0)  # 离线不是必要项失败。


if __name__ == "__main__":
    unittest.main()  # 允许直接运行本测试文件。
