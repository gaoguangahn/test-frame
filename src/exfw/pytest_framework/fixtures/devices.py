from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from exfw.aw.device import DeviceManager, DeviceType
from exfw.pytest_framework.core.runtime import DeviceSpec


def _to_device_type(driver_name: str) -> DeviceType:
    """将 YAML 的 driver 字段转换为设备类型枚举。"""
    normalized_name = driver_name.strip().lower()

    try:
        return DeviceType(normalized_name)
    except ValueError as error:
        supported_drivers = ", ".join(device_type.value for device_type in DeviceType)
        raise ValueError(
            f"不支持的设备驱动类型：{driver_name}；当前支持：{supported_drivers}"
        ) from error


@pytest.fixture(scope="session")
def device_specs(run_config) -> tuple[DeviceSpec, ...]:
    """获取本次执行选中的设备静态配置，不会连接设备。"""
    return run_config.device_specs


@pytest.fixture(scope="session")
def device_manager() -> Iterator[DeviceManager]:
    """创建本次 Pytest 会话共用的设备管理器。"""
    manager = DeviceManager()

    try:
        yield manager
    finally:
        manager.close(hard_cleanup=False)


@pytest.fixture(scope="session")
def devices(
    device_manager: DeviceManager,
    device_specs: tuple[DeviceSpec, ...],
) -> dict[str, Any]:
    """
    连接全部选中的设备，并按设备名称返回真实驱动对象。

    例如：
    {"main": AdbDriver(...), "assistant": AdbDriver(...)}
    """
    connected_devices: dict[str, Any] = {}

    for spec in device_specs:
        device_type = _to_device_type(spec.driver)

        driver = device_manager.connect(
            name=spec.name,
            serial=spec.serial,
            device_type=device_type,
            model=spec.model,
        )

        connected_devices[spec.name] = driver

    return connected_devices
