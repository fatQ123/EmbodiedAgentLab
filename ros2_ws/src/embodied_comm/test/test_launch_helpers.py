"""验证 Launch 测试的 TTY、进程组与单次信号契约。"""
import signal
import subprocess
import sys

from launch_helpers import PtyLaunch


def test_pty_stdin_and_duplicate_interrupt_are_safe():
    code = (
        'import signal, sys, time\n'
        'count = 0\n'
        'def stop(sig, frame):\n'
        '    global count\n'
        '    count += 1\n'
        'signal.signal(signal.SIGINT, stop)\n'
        'print(sys.stdin.isatty(), flush=True)\n'
        'while not count:\n'
        '    time.sleep(0.01)\n'
        'time.sleep(0.05)\n'
        'print(count, flush=True)\n'
    )
    process = PtyLaunch(
        [sys.executable, '-u', '-c', code],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        assert process.stdout.readline().strip() == 'True'
        process.send_signal(signal.SIGINT)
        process.send_signal(signal.SIGINT)
        output, _ = process.communicate(timeout=3.0)
        assert process.returncode == 0
        assert output.strip() == '1'
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3.0)
        process.close_terminal()
    assert process.terminal_master is None
