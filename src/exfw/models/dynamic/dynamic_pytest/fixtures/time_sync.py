from __future__ import annotations

import logging

import pytest

from exfw.models.dynamic.dynamic_pytest.time_sync import (
    capture_android_device_time_context,
)
from exfw.pytest_framework.core.runtime import DeviceSpec
from exfw.pytest_framework.core.time_context import (
    CaseTimeContext,
    set_case_time_context,
)


@pytest.fixture(scope="function")
def dynamic_case_time_context(
    request: pytest.FixtureRequest,
    device_specs: tuple[DeviceSpec, ...],
) -> CaseTimeContext | None:
    """动态模型用例的设备时间上下文。

    每个用例开始时只对 main 设备采样一次 PC/设备时间 offset，并挂到
    pytest item 上。通用 result.json 写入逻辑会自动使用该上下文转换
    started_at / stopped_at / steps.timestamp。
    """

    main_device = _get_main_device(device_specs)

    try:
        context = capture_android_device_time_context(main_device.serial)
    except Exception:
        logging.getLogger("exfw.dynamic_model.time_sync").exception(
            "动态模型设备时间同步失败，当前用例继续使用 PC 时间：serial=%s",
            main_device.serial,
        )
        return None

    set_case_time_context(request.node, context)
    return context


def _get_main_device(device_specs: tuple[DeviceSpec, ...]) -> DeviceSpec:
    main_device = device_specs[0]

    for spec in device_specs:
        if spec.name == "main":
            return spec

    return main_device
