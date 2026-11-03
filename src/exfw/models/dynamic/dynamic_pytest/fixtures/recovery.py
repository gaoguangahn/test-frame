from __future__ import annotations

import logging

import pytest

from exfw.models.dynamic.dynamic_pytest.runtime import get_dynamic_model_runtime
from exfw.models.dynamic.services.failure_recovery import recover_to_desktop


@pytest.fixture(scope="function", autouse=True)
def dynamic_pre_case_recovery(
    pytestconfig: pytest.Config,
    devices,
) -> None:
    """在动态模型下一个用例开始采集前，恢复上一失败用例遗留的设备状态。"""

    runtime = get_dynamic_model_runtime(pytestconfig)
    main_device = devices.get("main") if isinstance(devices, dict) else None
    serial = getattr(main_device, "serial", None)

    if main_device is None or not isinstance(serial, str) or not serial:
        return

    if serial not in runtime.recovery_required_serials:
        return

    logger = logging.getLogger("exfw.fixture.dynamic_pre_case_recovery")
    recovered = recover_to_desktop(
        device=main_device,
        serial=serial,
        logger=logger,
    )

    if recovered:
        runtime.recovery_required_serials.discard(serial)
    else:
        logger.warning(
            "动态模型用例前恢复桌面失败，保留恢复标记，下个用例前继续尝试：serial=%s",
            serial,
        )
