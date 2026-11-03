"""
设备管理模块

提供设备实例的统一管理, 当前支持 Android ADB
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from logging import Logger
from typing import Any, TypeAlias, TypeVar

import adbutils

from .adb.driver import AdbDriver
from .adb.preset import adb_install_apks_and_push_agent
from .device_type import DeviceType

DeviceDriver: TypeAlias = AdbDriver

TDriver = TypeVar("TDriver", bound=DeviceDriver)


@dataclass
class DeviceContext:
    name: str
    serial: str
    brand: str
    device_type: DeviceType
    driver: DeviceDriver
    connected_at: float = field(default_factory=time.time)


class DeviceManager:
    """设备管理类，负责设备的创建、连接、断开，并提供统一的设备实例"""

    def __init__(self, logger: Logger | None = None):
        """初始化设备管理器"""
        self.logger = logger or logging.getLogger("exfw.DeviceManager")
        self._devices: dict[str, DeviceContext] = {}
        self._connect_lock = threading.Lock()

    def connect(
        self,
        serial: str,
        name: str | None = None,
        device_type: DeviceType = DeviceType.ADB,
        brand: str = "Honor",
        model: str | None = None,
    ) -> DeviceDriver:
        """连接设备

        Args:
            name: 设备名称
            serial: 设备序列号
            device_type: 设备操作实现类型，默认为 ADB
            brand: 手机品牌，默认为 Honor
            model: 配置中的设备型号，可选。未配置时由具体 driver 自行查询。
        """
        with self._connect_lock:
            if not serial:
                raise ValueError("serial 不能为空")

            name = name or serial

            if device_type == DeviceType.ADB:
                driver = self._connect_adb(serial, model=model)
            else:
                raise ValueError(f"不支持的设备类型: {device_type}")

            context = DeviceContext(
                name=name,
                serial=serial,
                brand=brand,
                device_type=device_type,
                driver=driver,
            )
            self._devices[serial] = context

            self.logger.info(f"设备连接并保存成功: {name} / {serial} / {device_type}")
            return driver

    def _connect_adb(self, serial: str, model: str | None = None) -> AdbDriver:
        """连接 Android 设备"""

        # 原生 adb 设备对象
        adb_dev = adbutils.adb.device(serial) if serial else adbutils.adb.device()

        # 确保必要资源就绪
        adb_install_apks_and_push_agent(serial)

        # 唤醒屏幕并解锁
        try:
            adb_dev.shell("input keyevent 224")
            adb_dev.shell("wm dismiss-keyguard")
        except Exception as e:
            self.logger.warning(f"唤醒/解锁设备时发生异常(可忽略): {serial}, {e}")

        self.logger.info("连接前清理环境：重启 atx-agent 并停止 uiautomator...")
        try:
            adb_dev.shell("/data/local/tmp/atx-agent server --stop")  # 停止 atx-agent
            adb_dev.app_stop("com.github.uiautomator")  # 杀 uiautomator
            adb_dev.app_stop("com.github.uiautomator.test")
            adb_dev.shell("pkill -9 -f uiautomator")  # 清理残留进程
            adb_dev.shell("killall uiautomator || true")
            time.sleep(2.0)
            # adb_dev.shell("/data/local/tmp/atx-agent server -d")  # 重启 atx-agent
            # time.sleep(2.0)
        except Exception as e:
            self.logger.warning(f"清理环境时发生异常(通常可忽略): {e}")

        # 4. 正式连接 uiautomator2
        try:
            self.logger.info(f"环境清理完毕, uiautomator2 连接设备 {serial}...")
            driver = AdbDriver(serial=serial, model=model, logger=self.logger)
            self.logger.info(f"ADB 设备连接成功: {serial}")
            return driver
        except Exception as e:
            self.logger.error(f"ADB 设备连接失败: {serial}, {e}")
            raise ConnectionError(f"ADB 设备连接失败: {serial}, {e}") from e

    def _connect_robot(self, serial: str, brand: str) -> tuple[Any, Any]:
        """
        预留机械臂设备连接入口
        """
        raise NotImplementedError("Robot device is not implemented yet")

    def get(self, key: str) -> DeviceDriver:
        """
        按 name 优先，其次按 serial 获取设备 driver。

        若需要得到精确的具体驱动类型，请使用 get_as()。
        """
        return self.get_context(key).driver

    def get_as(self, key: str, driver_type: type[TDriver]) -> TDriver:
        """
        获取指定设备，并校验其实际驱动类型。

        Args:
            key: 设备 name 或 serial。
            driver_type: 期望的驱动类，例如 AdbDriver。

        Returns:
            经过类型校验后的驱动实例。
        """
        driver = self.get(key)

        if not isinstance(driver, driver_type):
            context = self.get_context(key)
            raise TypeError(
                f"设备 {key!r} 的驱动类型不符合预期："
                f"期望 {driver_type.__name__}，"
                f"实际 {type(driver).__name__}，"
                f"配置类型为 {context.device_type.value!r}。"
            )

        return driver

    def get_context(self, key: str) -> DeviceContext:
        """
        按 name 优先，其次按 serial 获取设备上下文
        取不到则抛出 KeyError
        """
        for ctx in self._devices.values():
            if ctx.name == key:
                return ctx

        ctx = self._devices.get(key)
        if ctx:
            return ctx

        raise KeyError(f"设备上下文不存在: {key}")

    def list_serials(self) -> list[str]:
        """返回所有已连接设备 serial"""
        return list(self._devices.keys())

    def list_devices(self) -> list[DeviceContext]:
        """返回所有设备上下文"""
        return list(self._devices.values())

    def is_connected(self, serial: str) -> bool:
        """检查设备是否已连接"""
        return serial in self._devices

    def disconnect(self, serial: str, hard_cleanup: bool = False) -> bool:
        """
        断开单台设备

        Args:
            serial: 设备序列号
            hard_cleanup: 是否执行深度清理

        Returns:
            是否断开成功
        """
        ctx = self._devices.get(serial)
        if ctx is None:
            return True

        try:
            if ctx.device_type == DeviceType.ADB:
                self._disconnect_adb(serial, hard_cleanup=hard_cleanup)
            else:
                raise ValueError(f"不支持的设备类型: {ctx.device_type}")

            self._devices.pop(serial, None)
            self.logger.info(f"设备已断开连接: {serial}")
            return True

        except Exception as e:
            self.logger.error(f"断开设备连接失败: {serial}, {e}")
            return False

    def _disconnect_adb(self, serial: str, hard_cleanup: bool = False) -> None:
        """断开 ADB 设备"""
        if not hard_cleanup:
            return

        self.logger.info(f"执行 ADB 设备深度清理: {serial}")
        adb_dev = adbutils.adb.device(serial)

        try:
            adb_dev.shell("/data/local/tmp/atx-agent server --stop")
            time.sleep(0.5)

            adb_dev.app_stop("com.github.uiautomator")
            adb_dev.app_stop("com.github.uiautomator.test")

            adb_dev.shell("pkill -9 -f uiautomator")
            time.sleep(0.5)
        except Exception as e:
            self.logger.warning(f"ADB 深度清理失败(可忽略): {serial}, {e}")

    def _disconnect_robot(self, serial: str, hard_cleanup: bool = False) -> None:
        """预留机械臂设备断开入口"""
        raise NotImplementedError("Robot device is not implemented yet")

    def disconnect_all(self, hard_cleanup: bool = False) -> None:
        """断开所有设备"""
        for serial in list(self._devices.keys()):
            self.disconnect(serial, hard_cleanup=hard_cleanup)

    def close(self, hard_cleanup: bool = False) -> None:
        """
        关闭设备管理器，断开所有设备并释放资源
        """
        self.disconnect_all(hard_cleanup=hard_cleanup)
        self.logger.info("DeviceManager 已关闭")
