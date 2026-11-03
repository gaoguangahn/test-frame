from __future__ import annotations

from collections import defaultdict
from typing import Any

from .data_models import ActionStatsSummary, DynamicReportTask

CONTEXT_FIELDS = ("id", "task_id", "serial", "round", "case", "step")


# 以下方法用于将 CaseResult 数据按步骤展开，方便报告生成。
def expand_trace_results(case_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    将步骤级 CaseResult 数据展开为 Trace 明细行。

    一条 CaseResult 中可能包含多个 trace_result，
    展开后每条 Trace 解析结果对应一行。
    """
    return _expand_artifact_results(
        case_results=case_results,
        result_key="trace_result",
    )


def expand_log_results(case_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    将步骤级 CaseResult 数据展开为 Log 明细行。

    一条 CaseResult 中可能包含多个 log_result，
    展开后每条 Log 解析结果对应一行。
    """
    return _expand_artifact_results(
        case_results=case_results,
        result_key="log_result",
    )


def filter_success_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """筛选解析成功的结果。"""
    return [row for row in rows if row.get("success") is True]


def filter_failed_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """筛选解析失败的结果。"""
    return [row for row in rows if row.get("success") is False]


def _expand_artifact_results(
    case_results: list[dict[str, Any]],
    result_key: str,
) -> list[dict[str, Any]]:
    """
    通用展开方法。

    将 CaseResult 中指定的 JSON 字段展开为行数据，并补齐步骤上下文。
    """
    rows: list[dict[str, Any]] = []

    for case_result in case_results:
        artifact_results = case_result.get(result_key) or []

        if not isinstance(artifact_results, list):
            artifact_results = [artifact_results]

        context = {field: case_result.get(field) for field in CONTEXT_FIELDS}

        for artifact_result in artifact_results:
            if isinstance(artifact_result, dict):
                row = dict(artifact_result)
            else:
                row = {
                    "value": artifact_result,
                }

            # 上下文字段后写入，避免 artifact_result 中同名字段覆盖真实归属信息。
            row.update(context)
            rows.append(row)

    return rows


# 以下方法用于将 Trace 数据按 metric 汇总, 方便报告生成。
def route_trace_data_by_metric(
    trace_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    展开每个 Trace 的 data，并按 metric 汇总。

    一个 Trace 对应一个 metric；
    一个 Trace 的 data 中每个元素，都会生成对应 metric 下的一条明细数据。
    """
    routed_data: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for trace_row in trace_rows:
        metric = trace_row.get("metric")

        # Trace 解析失败、无指标名时，不能生成有效指标明细。
        if trace_row.get("success") is not True or not metric:
            continue

        data = trace_row.get("data")

        # 约定 data 通常是列表；同时兼容历史数据中可能存在的单个字典。
        if isinstance(data, dict):
            data_items = [data]
        elif isinstance(data, list):
            data_items = data
        else:
            continue

        trace_info = trace_row.get("trace_info") or {}

        base_info = {
            "task_id": trace_row.get("task_id"),
            "serial": trace_row.get("serial"),
            "round": trace_row.get("round"),
            "case": trace_row.get("case"),
            "step": trace_row.get("step"),
            "sn": trace_row.get("serial"),
            "loop": trace_row.get("round"),
            "case_name": trace_row.get("case"),
            "trace_file": trace_row.get("trace_file"),
            "trace_name": trace_row.get("trace_name"),
            "metric": metric,
            "trace_start": trace_info.get("trace_start"),
            "trace_end": trace_info.get("trace_end"),
            "trace_length": trace_info.get("trace_length"),
        }

        for item in data_items:
            # data 内不是字典的值无法与元数据合并，跳过。
            if not isinstance(item, dict):
                continue

            # 兼容解析器将局部错误记录放在 data 列表中的情形。
            if item.get("error"):
                continue

            payload = {**base_info, **item}

            if metric == "startup_transition" and _is_camera_photo_trace(payload):
                routed_data["click_transition"].append(
                    _convert_camera_startup_to_click_payload(payload)
                )
                continue

            routed_data[metric].append(payload)

    return dict(routed_data)


def _is_camera_photo_trace(record: dict[str, Any]) -> bool:
    """判断是否为 CameraPhoto 特殊场景的 trace 记录。"""

    trace_name = str(record.get("trace_name") or record.get("trace_file") or "")
    return "CameraPhoto" in trace_name


def _convert_camera_startup_to_click_payload(
    record: dict[str, Any],
) -> dict[str, Any]:
    """将 CameraPhoto 的启动解析结果适配为点击响应报告数据。"""

    converted = dict(record)
    converted["metric"] = "click_transition"
    converted["source_metric"] = record.get("metric", "startup_transition")
    converted["source_result_type"] = "StartupTransitionResult"

    converted["new_process"] = (
        record.get("new_process") or record.get("new_package") or "UNKNOWN"
    )
    converted["new_activity"] = record.get("new_activity") or "UNKNOWN"
    converted["startup_type"] = record.get("startup_type") or "unknown"
    converted["response_time"] = record.get("response_time")
    converted["thread_state"] = (
        record.get("thread_state") or record.get("thread_states") or {}
    )

    return converted


RADAR_METRICS = {"parse_animation_jank", "parse_fling_jank", "parse_fluency_fling_jank"}


def _is_valid_metric_data(metric_data: Any) -> bool:
    """判断单个 metric 的解析结果是否可用于报表。"""
    if metric_data is None:
        return False

    if isinstance(metric_data, dict) and metric_data.get("error"):
        return False

    if isinstance(metric_data, list):
        return any(
            not (isinstance(item, dict) and item.get("error")) for item in metric_data
        )

    return True


def route_log_data_by_metric(
    log_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    将文件级日志解析结果路由到各指标。

    规则：
    1. Radar 指标统一合并至 parse_radar_log；
    2. 一个原始 Log 最多生成一条 parse_radar_log；
    3. 普通指标仍按 metric 单独存放；
    """
    routed_data: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for log_row in log_rows:
        if log_row.get("success") is not True:
            continue

        result_dict = log_row.get("data")
        if not isinstance(result_dict, dict):
            continue

        # 同时保留新字段和旧报表所使用的字段。
        base_payload = {
            "task_id": log_row.get("task_id"),
            "serial": log_row.get("serial"),
            "round": log_row.get("round"),
            "case": log_row.get("case"),
            "step": log_row.get("step"),
            "sn": log_row.get("serial"),
            "loop": log_row.get("round"),
            "case_name": log_row.get("case"),
            "id": log_row.get("id"),
            "log_file": log_row.get("log_file"),
            "log_name": log_row.get("log_name"),
        }

        # ==========================================================
        # 1. Radar 指标：将同一个 Log 中的多个 Radar metric 合并
        # ==========================================================
        radar_result = {}

        for metric_name in RADAR_METRICS:
            metric_data = result_dict.get(metric_name)

            if not _is_valid_metric_data(metric_data):
                continue

            radar_result[metric_name] = metric_data

        if radar_result:
            routed_data["parse_radar_log"].append(
                {**base_payload, "result": radar_result}
            )

        # ==========================================================
        # 2. 普通指标：按 metric 分开存储
        # ==========================================================
        for metric_name, metric_data in result_dict.items():
            if metric_name in RADAR_METRICS:
                continue

            if not _is_valid_metric_data(metric_data):
                continue

            # 若结果是列表，过滤其中的错误项。
            if isinstance(metric_data, list):
                metric_data = [
                    item
                    for item in metric_data
                    if not (isinstance(item, dict) and item.get("error"))
                ]

                if not metric_data:
                    continue

            routed_data[metric_name].append({**base_payload, "data": metric_data})

    return dict(routed_data)


def build_trace_scene_index(
    trace_records: list[dict[str, Any]],
) -> dict[tuple[Any, Any, Any, str], str]:
    """根据本地 trace_records 建立 scene 索引。"""

    scene_index: dict[tuple[Any, Any, Any, str], str] = {}

    for trace in trace_records:
        if not isinstance(trace, dict):
            continue

        key = (
            trace.get("round"),
            trace.get("serial"),
            trace.get("case"),
            trace.get("trace_name"),
        )
        scene_index[key] = trace.get("description", "")

    return scene_index


def add_scene_to_trace_results(
    case_results: list[dict[str, Any]],
    trace_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """将本地 trace_records 中的 description 写入服务端 Trace 结果的 scene 字段。"""

    scene_index = build_trace_scene_index(trace_records)

    for case_result in case_results:
        task_round = case_result.get("round")
        serial = case_result.get("serial")
        case_name = case_result.get("case")
        trace_results = case_result.get("trace_result") or []

        if not isinstance(trace_results, list):
            continue

        for trace_result in trace_results:
            if not isinstance(trace_result, dict):
                continue

            trace_name = trace_result.get("trace_name")

            if not trace_name:
                trace_result["scene"] = ""
                continue

            key = (task_round, serial, case_name, trace_name)
            trace_result["scene"] = scene_index.get(key, "")

    return case_results


def merge_trace_records(records_list: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """合并多个子任务的轻量 trace_records 列表。"""

    all_traces: list[dict[str, Any]] = []

    for records in records_list:
        if isinstance(records, list):
            all_traces.extend(item for item in records if isinstance(item, dict))

    all_traces.sort(
        key=lambda item: (
            str(item.get("serial") or ""),
            item.get("round") if item.get("round") is not None else -1,
            str(item.get("case") or ""),
            item.get("start_time") or 0,
        )
    )

    return all_traces


def merge_case_records(records_list: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """合并多个子任务的用例/步骤时间线记录。"""

    all_cases: list[dict[str, Any]] = []

    for records in records_list:
        if isinstance(records, list):
            all_cases.extend(item for item in records if isinstance(item, dict))

    all_cases.sort(
        key=lambda item: (
            str(item.get("serial") or ""),
            item.get("round") if item.get("round") is not None else -1,
            item.get("started_at") or 0,
        )
    )

    return all_cases


def build_case_summary(report_tasks: list[DynamicReportTask]) -> dict[str, Any]:
    """汇总各 SN 子任务 session_result.json 中的用例总数和通过率。"""

    total = 0
    passed = 0

    for task in report_tasks:
        summary = task.session_data.get("summary") or {}
        if not isinstance(summary, dict):
            continue

        task_total = summary.get("total", 0)
        task_passed = summary.get("passed", 0)

        if isinstance(task_total, bool) or not isinstance(task_total, (int, float)):
            task_total = 0
        if isinstance(task_passed, bool) or not isinstance(task_passed, (int, float)):
            task_passed = 0

        total += int(task_total)
        passed += int(task_passed)

    pass_rate = round(passed / total, 4) if total else 0

    return {
        "total": total,
        "passed": passed,
        "pass_rate": pass_rate,
    }


def summarize_action_stats(case_results: list[dict[str, Any]]) -> ActionStatsSummary:
    """汇总 action_stats，供汇总页使用操作总次数作为分母。"""

    def _safe_count(value: Any) -> int:
        """将 action_stats 中的次数安全转换为非负整数。"""

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0
        return max(int(value), 0)

    total_clicks = 0
    total_swipes = 0
    total_start_app = 0
    total_home = 0
    case_actions: list[dict[str, Any]] = []

    for case_result in case_results:
        stats = case_result.get("action_stats") or {}

        if not isinstance(stats, dict):
            continue

        click_count = _safe_count(stats.get("click", 0))
        swipe_count = _safe_count(stats.get("swipe", 0))
        start_app_count = _safe_count(stats.get("start_app", stats.get("app_start", 0)))
        home_count = _safe_count(stats.get("home", 0))

        total_clicks += click_count
        total_swipes += swipe_count
        total_start_app += start_app_count
        total_home += home_count

        case_actions.append(
            {
                "serial": case_result.get("serial"),
                "round": case_result.get("round"),
                "case": case_result.get("case"),
                "click": click_count,
                "swipe": swipe_count,
                "start_app": start_app_count,
                "home": home_count,
                "start_exit": start_app_count + home_count,
            }
        )

    return ActionStatsSummary(
        total_clicks=total_clicks,
        total_swipes=total_swipes,
        total_start_app=total_start_app,
        total_home=total_home,
        total_start_exit=total_start_app + total_home,
        case_actions=case_actions,
    )


def build_report_devices(report_tasks: list[DynamicReportTask]) -> dict[str, dict[str, Any]]:
    """从 main_device_info.json 中提取报告需要展示的设备信息。"""

    devices: dict[str, dict[str, Any]] = {}

    for task in report_tasks:
        device_info = task.device_info or {}
        detail = device_info.get("detail") or {}
        serial = task.main_serial or device_info.get("serial")

        if not serial:
            continue

        devices[str(serial)] = {
            "brand": detail.get("brand", ""),
            "model": detail.get("model") or device_info.get("model", ""),
            "system_version": detail.get("system_version", ""),
            "mem_total": detail.get("mem_total", ""),
            "storage_size": detail.get("storage_size", ""),
        }

    return devices


def build_test_info(
    *,
    runner_result: dict[str, Any],
    report_tasks: list[DynamicReportTask],
    trace_records: list[dict[str, Any]],
    case_records: list[dict[str, Any]],
    case_results: list[dict[str, Any]],
    action_summary: ActionStatsSummary,
) -> dict[str, Any]:
    """构造报告公共上下文，只保留报告会使用的测试信息。"""

    runner_summary = runner_result.get("summary") or {}
    if not isinstance(runner_summary, dict):
        runner_summary = {}

    duration_seconds = runner_result.get("duration_seconds")
    if not isinstance(duration_seconds, (int, float)):
        task_durations = [
            task.runner_task.get("duration_seconds")
            for task in report_tasks
            if isinstance(task.runner_task.get("duration_seconds"), (int, float))
        ]
        duration_seconds = max(task_durations) if task_durations else 0

    return {
        "runner": {
            "duration_seconds": duration_seconds or 0,
            "summary": {
                "total": runner_summary.get("total", len(report_tasks)),
                "passed": runner_summary.get("passed", 0),
                "failed": runner_summary.get("failed", 0),
            },
        },
        "devices": build_report_devices(report_tasks),
        "case_summary": build_case_summary(report_tasks),
        "trace_records": trace_records,
        "case_records": case_records,
        "action_stats": {
            "total_clicks": action_summary.total_clicks,
            "total_swipes": action_summary.total_swipes,
            "total_start_app": action_summary.total_start_app,
            "total_home": action_summary.total_home,
            "total_start_exit": action_summary.total_start_exit,
            "case_actions": action_summary.case_actions,
            # 兼容旧字段，避免其他地方仍按 case_swipes 读取时报错。
            "case_swipes": action_summary.case_swipes,
        },
    }
