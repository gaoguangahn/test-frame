"""将设备级本地解析数据转换为报告内部的数据格式。"""
import json

from .data_models import DynamicReportTask
from .data_loader import iter_session_cases


def load_local_results(task: DynamicReportTask, selected_round: int | None) -> list[dict]:
    path = task.task_dir / "parsed_results.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("rounds"), list):
        return []
    cases = {(case.get("round"), case.get("case_id")): case for case in iter_session_cases(task.session_data)}
    results = []
    for round_data in data["rounds"]:
        if not isinstance(round_data, dict):
            continue
        number = round_data.get("round")
        if selected_round is not None and number != selected_round:
            continue
        context = {"task_id": task.task_id, "serial": task.main_serial, "round": number}
        if round_data.get("round_logs"):
            results.append({**context, "case": "__round_logs__", "step": "__round__", "log_result": round_data["round_logs"], "trace_result": []})
        parsed_cases = round_data.get("cases")
        for parsed in parsed_cases if isinstance(parsed_cases, list) else []:
            if not isinstance(parsed, dict):
                continue
            case = cases.get((number, parsed.get("case_id")))
            if case is None or case.get("nodeid") != parsed.get("nodeid"):
                continue
            dynamic = (case.get("extensions") or {}).get("dynamic_model") or {}
            results.append({**context, "case": parsed.get("case_name"), "case_id": parsed.get("case_id"), "nodeid": parsed.get("nodeid"), "step": "__case__", "action_stats": dynamic.get("action_stats") or {}, "log_result": parsed.get("log_results") or [], "trace_result": parsed.get("trace_results") or []})
    return results
