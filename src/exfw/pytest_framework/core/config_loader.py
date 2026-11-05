from __future__ import annotations

from typing import Any

from exfw.project_config import load_project_config, resolve_project_path
from .runtime import DeviceSpec


def load_testbed_devices(
    project_config: dict[str, Any], testbed_name: str
) -> tuple[DeviceSpec, ...]:
    """加载指定测试床中的全部设备。"""

    testbeds = project_config.get("testbeds")

    if testbeds is None:
        raise ValueError("配置中缺少 testbeds，无法选择测试床。")

    testbed = testbeds.get(testbed_name)

    if testbed is None:
        available_names = ", ".join(testbeds) or "无"
        raise ValueError(f"测试床不存在：{testbed_name}；可用测试床：{available_names}")

    if not isinstance(testbed, dict):
        raise TypeError(f"测试床 {testbed_name} 必须是映射对象。")

    raw_devices = testbed.get("devices")

    if raw_devices is None or not isinstance(raw_devices, list) or not raw_devices:
        raise ValueError(f"测试床 {testbed_name} 必须包含非空 devices 列表。")

    devices: list[DeviceSpec] = []
    seen_names: set[str] = set()
    seen_serials: set[str] = set()

    for index, raw_device in enumerate(raw_devices, start=1):
        if not isinstance(raw_device, dict):
            raise TypeError(
                f"测试床 {testbed_name} 的第 {index} 个设备必须是映射对象。"
            )
        name = raw_device.get("name")
        serial = raw_device.get("serial")
        model = raw_device.get("model")
        driver = raw_device.get("driver")

        if model is not None and (not isinstance(model, str) or not model):
            raise ValueError(f"测试床 {testbed_name} 的第 {index} 个设备 model 有误。")

        if name is None or not isinstance(name, str) or not name:
            raise ValueError(f"测试床 {testbed_name} 的第 {index} 个设备 name 有误。")

        if serial is None or not isinstance(serial, str) or not serial:
            raise ValueError(f"测试床 {testbed_name} 的第 {index} 个设备 serial 有误。")

        if driver is None or not isinstance(driver, str) or not driver:
            raise ValueError(f"测试床 {testbed_name} 的第 {index} 个设备 driver 有误。")

        if name in seen_names:
            raise ValueError(f"测试床 {testbed_name} 的设备 name 重复：{name}")

        if serial in seen_serials:
            raise ValueError(f"测试床 {testbed_name} 的设备 serial 重复：{serial}")

        seen_names.add(name)
        seen_serials.add(serial)

        devices.append(DeviceSpec(name=name, serial=serial, model=model, driver=driver))
    return tuple(devices)
