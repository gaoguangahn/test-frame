from __future__ import annotations

from typing import Any


def build_trace_record_index(
    test_info: dict[str, Any] | None,
) -> dict[tuple[str, int | str, str, str], dict[str, Any]]:
    """按 serial + round + case + trace_name 建立 trace_records 索引。"""

    if not isinstance(test_info, dict):
        return {}

    trace_records = test_info.get("trace_records") or []
    if not isinstance(trace_records, list):
        return {}

    trace_record_index: dict[tuple[str, int | str, str, str], dict[str, Any]] = {}
    for trace_record in trace_records:
        key = build_trace_key(trace_record)
        if key is None:
            continue
        trace_record_index[key] = trace_record

    return trace_record_index


def lookup_trace_description(
    record: dict[str, Any],
    trace_record_index: dict[tuple[str, int | str, str, str], dict[str, Any]],
) -> str:
    """根据 trace 解析结果查找对应采集记录的场景描述。"""

    existed_description = record.get("scene") or record.get("description")
    if existed_description:
        return str(existed_description)

    trace_record = lookup_trace_record(record, trace_record_index)
    if not isinstance(trace_record, dict):
        return ""

    return str(trace_record.get("description") or "")


def lookup_trace_record(
    record: dict[str, Any],
    trace_record_index: dict[tuple[str, int | str, str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    """根据 trace 解析结果查找对应的本地 trace 采集记录。"""

    key = build_trace_key(record)
    if key is None:
        return None

    trace_record = trace_record_index.get(key)
    return trace_record if isinstance(trace_record, dict) else None


def build_trace_key(record: dict[str, Any]) -> tuple[str, int | str, str, str] | None:
    """构造 trace 采集记录和解析结果之间的稳定匹配 key。"""

    if not isinstance(record, dict):
        return None

    serial = record.get("serial") or record.get("sn")
    round_value = record.get("round") if record.get("round") is not None else record.get("loop")
    case_name = record.get("case") or record.get("case_name")
    trace_name = record.get("trace_name")

    if not serial or round_value is None or not case_name or not trace_name:
        return None

    normalized_round = normalize_round(round_value)
    return str(serial), normalized_round, str(case_name), str(trace_name)


def normalize_round(round_value: Any) -> int | str:
    """规范化轮次，避免 int 与可转数字字符串无法匹配。"""

    if isinstance(round_value, bool):
        return str(round_value)

    try:
        return int(round_value)
    except (TypeError, ValueError):
        return str(round_value)
