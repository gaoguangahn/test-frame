import logging
import os
import shlex
import subprocess
import time
from logging import Logger

import adbutils
import uiautomator2 as u2

from .action import AdbActionMixin
from .exception import InvalidArgumentError, ShellCommandError
from .function import AdbFunctionMixin
from .screen import AdbScreenMixin
from .template import AdbTemplateMatchMixin
from .utils import wait_for_device_online, wait_for_u2_ready


class AdbDriver(
    AdbActionMixin, AdbFunctionMixin, AdbScreenMixin, AdbTemplateMatchMixin
):
    """ADB 设备对外聚合入口。

    ``core/action/function/screen`` 是内部能力拆分；业务侧仍然只拿这个
    ``AdbDevice``，直接调用 ``device.click()`` / ``device.screenshot()`` /
    ``device.shell_cmd()`` 等方法，不感知内部模块结构。
    """

    def __init__(
        self,
        serial: str,
        model: str | None = None,
        logger: Logger | None = None,
    ):
        """初始化 AdbDevice 实例。"""
        self.serial = serial
        self.device = u2.connect(serial)
        self.width, self.height = self.device.window_size()
        self.logger = logger or logging.getLogger("exfw.AdbDriver")
        self._adb_dev = None
        self.model = self._resolve_model(model)
        self.scrcpy_path = os.path.join(
            os.path.dirname(__file__),
            "resources",
            "scrcpy-win64-v2.5",
            "scrcpy.exe",
        )

    def _resolve_model(self, configured_model: str | None = None) -> str:
        """解析设备型号：优先配置值，其次 adb 查询，最后使用 serial 兜底。"""

        if isinstance(configured_model, str) and configured_model:
            return configured_model

        try:
            queried_model = self.shell_cmd("getprop ro.product.model")
            if queried_model:
                return queried_model.strip()
        except Exception:
            self.logger.warning(
                "获取设备型号失败，使用 serial 作为 model：%s",
                self.serial,
                exc_info=True,
            )

        return self.serial or "Unknown_Model"

    @property
    def adb_dev(self):
        if self._adb_dev is None:
            self._adb_dev = adbutils.adb.device(self.serial)
        return self._adb_dev

    def adb_cmd(self, cmd: str, timeout: int = 10) -> str:
        """执行 adb 命令"""

        cmd = cmd.strip()
        if not cmd:
            raise InvalidArgumentError("ADB command is empty")

        if cmd.startswith("adb "):
            cmd = cmd[4:].strip()

        full_cmd = ["adb"] + shlex.split(cmd)

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            return (result.stdout or result.stderr).rstrip()
        except Exception as e:
            raise ShellCommandError(f"ADB command `{cmd}` failed: {e}")

    def shell_cmd(self, cmd: str, timeout: int = 10) -> str:
        """执行 shell 命令"""
        cmd = cmd.strip()
        if not cmd:
            raise InvalidArgumentError("Shell command is empty")

        if cmd.startswith("adb shell "):
            cmd = cmd[10:].strip()
        elif cmd.startswith("shell "):
            cmd = cmd[6:].strip()

        try:
            result = self.adb_dev.shell(cmd, timeout=timeout).rstrip()
            return result
        except Exception as e:
            raise ShellCommandError(f"Shell command `{cmd}` failed: {e}")

    def reboot_device(self, reboot_wait: int = 300) -> u2.Device:
        """重启设备，会等待设备重启完成，返回新设备对象
        arg:
            - reboot_wait: 重启等待时间，单位秒，默认 300
        return:
            - u2.Device: 新设备对象
        """

        try:
            self.adb_cmd(f"adb -s {self.serial} reboot")

            ok = wait_for_device_online(self.serial, timeout=reboot_wait * 0.8)
            if not ok:
                raise RuntimeError(f"{self.serial} did not come online after reboot")
            time.sleep(2)

            d_new = wait_for_u2_ready(self.serial, timeout=reboot_wait * 0.2)
            self.device = d_new
            self._adb_dev = None
            return d_new
        except Exception as e:
            self.logger.error(f"reboot device failed: {e}")
            raise

    def reset_uiautomator_service(self):
        """热重启手机端的 UIAutomator 服务，包含重试和可用性验证机制。"""
        max_retries = 3
        last_error = None

        for i in range(max_retries):
            try:
                self.logger.info(
                    f"尝试重启 UIAutomator 服务 (第 {i + 1}/{max_retries} 次)..."
                )

                # 1. 触发重启
                if hasattr(self.device, "reset_uiautomator"):
                    self.device.reset_uiautomator()
                else:
                    self.device.app_stop("com.github.uiautomator")

                # 2. 缓冲等待：给 Android 系统一点时间注册无障碍服务
                time.sleep(2.0)

                # 3. 连通性验证：发送一个最简单的请求，确认服务真正可用
                _ = self.device.window_size()

                self.logger.info("UIAutomator 服务重启并验证成功！")

                return

            except Exception as e:
                last_error = e
                self.logger.warning(f"第 {i + 1} 次重启/验证失败: {e}")
                time.sleep(2.0)

        self.logger.error(
            "UIAutomator 服务多次重启均失败，可能需要人工介入或硬重启设备。"
        )

        raise RuntimeError("UIAutomator 服务多次重启均失败") from last_error
