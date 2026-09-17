"""环境诊断工具的基础自动化测试。"""

import io
import unittest
from contextlib import redirect_stdout

from embodied_agent_lab.doctor import collect_checks, main


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
        with redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("EmbodiedAgentLab 环境诊断", output.getvalue())


if __name__ == "__main__":
    unittest.main()
