"""环境诊断工具的基础自动化测试。"""

import io
import json  # 验证输出是真正可解析的 JSON。
import subprocess  # 验证实际进程的退出状态。
import sys  # 使用运行测试的同一个 Python。
import unittest
from contextlib import redirect_stderr, redirect_stdout  # 分别捕获普通输出和错误输出。
from unittest.mock import patch  # 模拟检查结果，避免依赖本机硬件。

from embodied_agent_lab.doctor import CheckResult, collect_checks, main  # 导入结果模型与入口。


class DoctorTest(unittest.TestCase):
    """验证环境诊断工具的核心行为。"""

    def test_collect_checks_has_core_items(self) -> None:
        """确认首版至少覆盖软件、ROS 2 与设备检查。"""

        names = {result.name for result in collect_checks()}
        expected = {
            "操作系统",
            "Python 版本",
            "Git 版本控制工具",
            "Conda 环境",
            "ROS 2 发行版",
            "串口设备",
        }
        self.assertTrue(expected <= names)

    def test_main_returns_success(self) -> None:
        """确认警告不会使环境诊断命令失败。"""

        output = io.StringIO()
        checks = [CheckResult("可选设备", "警告", "没有设备", "optional", "可忽略")]  # 模拟设备缺失。
        with patch("embodied_agent_lab.doctor.collect_checks", return_value=checks), redirect_stdout(output):  # 隔离本机环境。
            self.assertEqual(main(["doctor"]), 0)  # 显式传入子命令，避免读取 unittest 的参数。
        self.assertIn("EmbodiedAgentLab 环境诊断", output.getvalue())
        self.assertIn("建议：可忽略", output.getvalue())  # 确认文本报告包含处理建议。

    def test_json_report_and_failure_exit_code(self) -> None:
        """正常、警告、失败均可序列化，失败报告与返回码一致。"""

        checks = [  # 构造完整状态集合，不调用真实系统命令。
            CheckResult("解释器", "正常", "3.12", "python"),  # 正常状态。
            CheckResult("可选设备", "警告", "缺失", "optional"),  # 非阻塞警告。
            CheckResult("必要项", "失败", "不可用", "required", "请修复"),  # 阻塞失败。
        ]
        output, errors = io.StringIO(), io.StringIO()  # 分别收集两个输出流。
        with patch("embodied_agent_lab.doctor.collect_checks", return_value=checks), redirect_stdout(output), redirect_stderr(errors):  # 注入可控结果。
            self.assertEqual(main(["doctor", "--json"]), 1)  # 检查失败返回 1。
        report = json.loads(output.getvalue())  # 任何额外标题或日志都会导致此处解析失败。
        self.assertEqual(set(report), {"schema_version", "checks", "summary", "exit_code"})  # 固定顶层协议。
        self.assertEqual(report["schema_version"], 1)  # 确认报告格式版本。
        self.assertEqual(report["summary"], {"正常": 1, "警告": 1, "失败": 1})  # 确认状态统计。
        self.assertEqual(report["exit_code"], 1)  # JSON 与函数返回码一致。
        self.assertEqual(report["checks"][2], {"name": "必要项", "status": "失败", "detail": "不可用", "check_id": "required", "suggestion": "请修复"})  # 固定单项字段。
        self.assertEqual(errors.getvalue(), "")  # 正常生成报告时不泄漏额外错误文本。

    def test_text_failure_exit_code(self) -> None:
        """文本模式也要对失败结果返回非零状态。"""

        checks = [CheckResult("必要项", "失败", "不可用", "required")]  # 模拟必要检查失败。
        output = io.StringIO()  # 捕获文本报告。
        with patch("embodied_agent_lab.doctor.collect_checks", return_value=checks), redirect_stdout(output):  # 使用模拟结果。
            self.assertEqual(main(["doctor"]), 1)  # 文本模式与 JSON 模式遵循相同状态规则。
        self.assertIn("× [失败]", output.getvalue())  # 失败不能显示为普通警告。

    def test_help_does_not_collect_checks(self) -> None:
        """顶层和子命令帮助都成功退出，而且不执行诊断。"""

        for argv in (["--help"], ["doctor", "--help"]):  # 覆盖两个帮助入口。
            with self.subTest(argv=argv):  # 为失败情况显示具体参数。
                output = io.StringIO()  # 捕获帮助内容。
                with patch("embodied_agent_lab.doctor.collect_checks") as collect, redirect_stdout(output):  # 监视检查调用。
                    with self.assertRaises(SystemExit) as caught:  # argparse 使用 SystemExit 结束帮助流程。
                        main(argv)  # 执行指定帮助命令。
                self.assertEqual(caught.exception.code, 0)  # 帮助不是错误。
                collect.assert_not_called()  # 帮助不应探测设备或网络。
                self.assertIn("--help", output.getvalue())  # 帮助确实输出了选项说明。

    def test_invalid_arguments_do_not_collect_checks(self) -> None:
        """缺少子命令、未知命令及未知选项必须被拒绝。"""

        cases = [[], ["unknown"], ["doctor", "--unknown"], ["doctor", "--js"], ["doctor", "extra"]]  # 覆盖常见用法错误及选项缩写。
        for argv in cases:  # 逐项验证输入错误。
            with self.subTest(argv=argv):  # 标记当前错误输入。
                output, errors = io.StringIO(), io.StringIO()  # 捕获输出流。
                with patch("embodied_agent_lab.doctor.collect_checks") as collect, redirect_stdout(output), redirect_stderr(errors):  # 不运行真实诊断。
                    with self.assertRaises(SystemExit) as caught:  # 捕获解析器退出。
                        main(argv)  # 传入错误参数。
                self.assertEqual(caught.exception.code, 2)  # 参数错误采用标准退出码 2。
                self.assertEqual(output.getvalue(), "")  # 参数错误不应污染标准输出。
                self.assertTrue(errors.getvalue())  # 错误说明应写入标准错误。
                collect.assert_not_called()  # 错误输入不能触发诊断。

    def test_module_process_protocol(self) -> None:
        """验证真实进程的 JSON 输出和用法错误退出码。"""

        command = [sys.executable, "-m", "embodied_agent_lab.doctor"]  # 运行真实模块入口。
        result = subprocess.run(command + ["doctor", "--json"], capture_output=True, text=True, timeout=10)  # 获取进程结果。
        report = json.loads(result.stdout)  # 检查真实入口没有附加非 JSON 文本。
        self.assertEqual(result.returncode, report["exit_code"])  # 报告和进程退出码必须一致。
        self.assertEqual(result.stderr, "")  # 普通运行不产生错误流输出。
        identifiers = [item["check_id"] for item in report["checks"]]  # 取得各项稳定标识。
        self.assertEqual(len(identifiers), len(set(identifiers)))  # 检查标识不得重复。
        invalid = subprocess.run(command + ["unknown"], capture_output=True, text=True, timeout=10)  # 通过进程验证非法命令。
        self.assertEqual(invalid.returncode, 2)  # SystemExit 确实传递到操作系统。


if __name__ == "__main__":
    unittest.main()
