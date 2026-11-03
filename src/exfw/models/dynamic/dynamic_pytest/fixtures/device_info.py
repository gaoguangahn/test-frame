from __future__ import annotations

import json
from typing import Any

import pytest

from exfw.aw.device import AdbDriver
from exfw.pytest_framework.core.runtime import DeviceSpec, RunConfig


@pytest.fixture(scope="session", autouse=True)
def dynamic_main_device_info(
    run_config: RunConfig,
    device_specs: tuple[DeviceSpec, ...],
    devices,
) -> dict[str, Any]:
    """获取动态模型 main 设备信息，并保存到本次任务目录。"""

    try:
        main_device: AdbDriver = devices["main"]
    except KeyError:
        pytest.fail(
            "动态模型用例需要名为 main 的主设备，但当前未找到。",
            pytrace=False,
        )

    main_spec = None
    for spec in device_specs:
        if spec.name == "main":
            main_spec = spec
            break

    detail_info = main_device.get_detail_info()
    device_info: dict[str, Any] = {
        "name": "main",
        "serial": main_spec.serial
        if main_spec is not None
        else getattr(main_device, "serial", ""),
        "model": (
            main_spec.model
            if main_spec is not None and main_spec.model
            else getattr(main_device, "model", None) or detail_info.get("model", "")
        ),
        "driver": main_spec.driver if main_spec is not None else "adb",
        "detail": detail_info,
    }

    run_config.output_dir.mkdir(parents=True, exist_ok=True)
    device_info_file = run_config.output_dir / "main_device_info.json"
    device_info_file.write_text(
        json.dumps(device_info, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return device_info
