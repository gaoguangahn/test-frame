"""通用持续命令采集：明确暴露启动失败并负责释放进程和文件。"""

import atexit
import logging
import os
import subprocess
from logging import Logger


class CmdRunner:
    _procs = []

    def __init__(
        self, output_path: str, cmd: list, name: str, logger: Logger | None = None
    ):
        self.output_path = output_path
        self.cmd = cmd
        self.name = name
        self.logger = logger or logging.getLogger("exfw." + self.__class__.__name__)

        self.proc = None
        self.file = None

    def start(self):
        """启动日志采集（直接写入电脑本地）"""
        if self.proc is not None:
            raise RuntimeError(f"采集进程已经启动：{self.name}")
        os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)

        try:
            self.file = open(self.output_path, "wb")
            self.proc = subprocess.Popen(
                self.cmd, stdout=self.file, stderr=subprocess.STDOUT
            )

            CmdRunner._procs.append(self)
            self.logger.debug(f"Start {self.name} success")

        except Exception as e:
            self.logger.error(f"Start {self.name} failed: {e}")
            self._close_file()
            raise

    def stop(self):
        """停止日志采集"""
        if not self.proc:
            return

        try:
            if self.proc.poll() is None:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=1)
        finally:
            self.proc = None
            self._close_file()
            if self in CmdRunner._procs:
                CmdRunner._procs.remove(self)

        self.logger.debug(f"Stop {self.name} finished")

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def _close_file(self):
        if self.file and not self.file.closed:
            self.file.close()
            self.file = None


def _cleanup():
    """进程退出时的全局清理"""
    for c in list(CmdRunner._procs):
        try:
            c.stop()
        except Exception:
            pass


atexit.register(_cleanup)
