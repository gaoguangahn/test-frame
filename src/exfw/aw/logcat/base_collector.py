import logging
import os
from abc import ABC, abstractmethod

import adbutils
from adbutils import AdbDevice


class BaseCollector(ABC):
    """日志采集基础类：提供设备获取和路径构建等公共工具。"""

    name: str | None = None

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("exfw." + self.__class__.__name__)

    def _get_device(self, device: str | AdbDevice) -> AdbDevice | None:
        try:
            if isinstance(device, str):
                return adbutils.adb.device(device)
            return device
        except Exception:
            return None

    def build_path(self, context: dict, filename: str) -> str:
        root_dir = context.get("root_dir", "logs")
        os.makedirs(root_dir, exist_ok=True)

        return os.path.join(root_dir, filename)


class ContinuousCollector(BaseCollector):
    """持续采集器基类：具有完整的生命周期 (start -> stop)

    设备入参约定: start/stop 必须传设备序列号 serial (str), 内部直接拼
    `adb -s <serial>` 命令，因此不接受 AdbDevice 实例。
    """

    @abstractmethod
    def start(self, serial: str, context: dict):
        pass

    @abstractmethod
    def stop(self, serial: str, context: dict) -> str | None:
        pass


class InstantCollector(BaseCollector):
    """单次/瞬时采集器基类：只有一个动作 (collect)

    设备入参约定: collect 既可传设备序列号 (str) ，也可传 AdbDevice 实例，
    内部经 _get_device 统一为 AdbDevice 后再执行命令。
    """

    @abstractmethod
    def collect(self, device: str | AdbDevice, context: dict) -> str | None:
        pass
