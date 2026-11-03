from logging import Logger
from typing import Any, Protocol

import uiautomator2 as u2


class AdbMixinBase(Protocol):
    device: u2.Device
    serial: str
    width: int
    height: int
    logger: Logger
    adb_dev: Any
    scrcpy_path: str

    def shell_cmd(self, cmd: str, timeout: int = 10) -> str: ...
    def adb_cmd(self, cmd: str, timeout: int = 10) -> str: ...
    def reboot_device(self, reboot_wait: int = 300) -> u2.Device: ...
    def reset_uiautomator_service(self) -> bool: ...
