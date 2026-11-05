from __future__ import annotations

import re
import time

import adbutils

from exfw.pytest_framework.core.time_context import CaseTimeContext

DEVICE_REALTIME_ESTIMATED = "device_realtime_estimated"


def capture_android_device_time_context(serial: str) -> CaseTimeContext:
    """采样一次 Android 设备 wall-clock 和 PC wall-clock 的 offset。

    该函数只在用例开始时调用一次，后续用 PC 时间加 offset 估算设备时间，
    避免每个 step/trace start/stop 都访问 ADB。
    """

    pc_before = time.time()
    device_time = _read_android_realtime(serial)
    pc_after = time.time()

    pc_mid = (pc_before + pc_after) / 2
    offset_seconds = device_time - pc_mid

    return CaseTimeContext(
        time_source=DEVICE_REALTIME_ESTIMATED,
        offset_seconds=offset_seconds,
        device_serial=serial,
    )


def _read_android_realtime(serial: str) -> float:
    device = adbutils.adb.device(serial)
    output = device.shell("date +%s.%N", timeout=5).strip()

    match = re.search(r"(\d+)(?:\.(\d+))?", output)
    if not match:
        raise RuntimeError(f"无法解析设备时间输出：serial={serial}, output={output!r}")

    seconds = int(match.group(1))
    fraction = match.group(2) or "0"
    fraction = fraction[:9].ljust(9, "0")

    return seconds + int(fraction) / 1_000_000_000
