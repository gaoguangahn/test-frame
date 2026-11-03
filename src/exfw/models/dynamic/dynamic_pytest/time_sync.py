from __future__ import annotations

import json
import re
import time
from pathlib import Path

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


def convert_trace_records_file_time_source(
    records_file: Path,
    context: CaseTimeContext | None,
) -> bool:
    """用同一个 CaseTimeContext 转换 trace_records.json 的绝对时间戳。"""

    if context is None or not records_file.is_file():
        return False

    try:
        data = json.loads(records_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(data, dict):
        return False

    traces = data.get("traces")
    if not isinstance(traces, list):
        return False

    for trace in traces:
        if not isinstance(trace, dict):
            continue

        for field in ("start_time", "end_time"):
            trace[field] = context.convert_timestamp(trace.get(field))

    data["time_source"] = context.time_source
    data["time_context"] = context.to_dict()

    temp_file = records_file.with_suffix(records_file.suffix + ".tmp")
    temp_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_file.replace(records_file)

    return True


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
