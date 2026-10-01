"""用真实终端语义测试 Launch，并防止重复 Ctrl+C 破坏节点清理。"""
import os
import signal
import subprocess


class PtyLaunch(subprocess.Popen):
    """保持 PTY stdin；一次 SIGINT 仅投递到本测试创建的独立组。"""

    def __init__(self, *args, **kwargs):
        self.terminal_master, slave = os.openpty()
        self.interrupted = False
        kwargs.update(stdin=slave, start_new_session=True)
        try:
            super().__init__(*args, **kwargs)
        except Exception:
            self.close_terminal()
            raise
        finally:
            os.close(slave)

    def send_signal(self, sig):
        if sig != signal.SIGINT:
            return super().send_signal(sig)
        if self.interrupted:
            return
        if self.poll() is None:
            assert os.getpgid(self.pid) == self.pid, '不是本测试的独立进程组'
        self.interrupted = True
        os.killpg(self.pid, signal.SIGINT)

    def close_terminal(self):
        if self.terminal_master is not None:
            os.close(self.terminal_master)
            self.terminal_master = None
