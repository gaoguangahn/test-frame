"""按汇总页口径筛选发生 BD 卡顿的用例。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def is_start_exit_animation(record: dict[str, Any]) -> bool:
    kind = record.get("Type") or ""
    return isinstance(kind, str) and (
        "HOME_TO_APP_ANIMATION" in kind or "APP_TO_HOME_ANIMATION" in kind
    )


def jank_count(counts: list) -> float:
    """与汇总页一致：第 0 档不算卡顿，第 1 档起累计。"""
    return sum(counts[1:]) if counts else 0


@dataclass(frozen=True)
class JankCase:
    serial: str
    round: int
    case: str
    category: str
    case_id: str | None = None


def select_jank_cases(rows: list[dict[str, Any]], selected_round: int | None = None) -> set[JankCase]:
    selected: set[JankCase] = set()
    for row in rows:
        serial, round_no, case = row.get("serial"), row.get("round"), row.get("case")
        if not isinstance(serial, str) or not serial or not isinstance(round_no, int) or not isinstance(case, str) or not case:
            continue
        if selected_round is not None and round_no != selected_round:
            continue
        result = row.get("result") or {}
        if not isinstance(result, dict):
            continue
        for metric, category in (("parse_fluency_fling_jank", "fluency"), ("parse_animation_jank", "animator")):
            data = result.get(metric) or {}
            if not isinstance(data, dict):
                continue
            for record in data.get("data") or []:
                if not isinstance(record, dict):
                    continue
                if category == "animator" and not is_start_exit_animation(record):
                    continue
                counts = record.get("Counts") or []
                if jank_count(counts) > 0:
                    selected.add(JankCase(serial, round_no, case, category, row.get("case_id")))
    return selected
