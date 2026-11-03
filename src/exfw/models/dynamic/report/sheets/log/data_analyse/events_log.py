import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any

STARTUP_THRESHOLDS = [
    ("轻微启动慢次数（1~2s）", 1000, 2000),
    ("明显启动慢次数（2~3s）", 2000, 3000),
    ("严重启动慢次数（>=3s）", 3000, None),
]

CLICK_THRESHOLDS = [
    ("轻微延迟次数（155~245ms）", 155, 245),
    ("明显延迟次数（245~390ms）", 245, 390),
    ("严重延迟次数（>=390ms）", 390, None),
]


# ====================== 通用统计工具 ====================== #


def parse_log_time_to_timestamp(time_str: str | None, year: int | None = None) -> float:
    """将 events log 的 MM-DD HH:MM:SS.mmm 时间转换为时间戳。"""

    if not time_str:
        return 0.0

    parse_year = year or datetime.now().year

    try:
        full_time_str = f"{parse_year}-{time_str}"
        dt = datetime.strptime(full_time_str, "%Y-%m-%d %H:%M:%S.%f")
        return dt.timestamp()
    except Exception as error:
        print(f"时间转换失败: {time_str}, year={parse_year}, 错误: {error}")
        return 0.0


def calc_avg_std(values):
    """计算均值和标准差。"""

    value_count = len(values)
    if value_count == 0:
        return "", ""
    if value_count == 1:
        return values[0], 0

    avg = statistics.mean(values)
    std = statistics.stdev(values)
    return round(avg, 2), round(std, 2)


def build_stats(values, thresholds):
    """根据阈值构建统计数据。"""

    stats = {
        "最大值": max(values) if values else "",
        "最小值": min(values) if values else "",
    }
    counters = {label: 0 for label, _, _ in thresholds}

    for value in values:
        for label, low, high in thresholds:
            if (high is None and value >= low) or (high and low <= value < high):
                counters[label] += 1

    stats.update(counters)
    return stats


# ====================== 主处理逻辑 ====================== #


def process_all_events_log_data(events_log_list, app_map, test_info=None):
    """整理 events log 数据，返回表格输入和第 0 页汇总数据。"""

    all_data, organized_data, startup_data, click_data = events_log_summary(
        events_log_list,
        app_map,
        test_info,
    )

    return {
        "sheets_data": {
            "all_data": all_data,
            "organized_data": organized_data,
            "startup_data": startup_data,
            "click_data": click_data,
        },
        "summary_data": {
            "startup_data": startup_data,
            "click_data": click_data,
        },
    }


def events_log_summary(events_log_list, app_map, test_info=None) -> tuple:
    if not events_log_list:
        return [], [], [], []

    app_map = app_map or {}
    trace_context = _build_trace_context(test_info)
    case_context = _build_case_context(test_info)
    all_data = []

    for event_log in events_log_list:
        result_list = event_log.get("data")
        if not result_list:
            continue

        serial = event_log.get("serial")
        round_value = event_log.get("round")
        case_name = event_log.get("case") or event_log.get("case_name")
        candidate_traces = _get_candidate_traces(
            trace_context=trace_context,
            serial=serial,
            round_value=round_value,
        )
        candidate_cases = _get_candidate_cases(
            case_context=case_context,
            serial=serial,
            round_value=round_value,
        )

        processed_results = []
        for item in result_list:
            if not isinstance(item, dict):
                continue

            log_time = item.get("Time")
            log_timestamp = parse_log_time_to_timestamp(log_time)
            matched_trace = _match_trace_record_by_log_timestamp(
                log_timestamp,
                candidate_traces,
            )
            matched_case = _match_case_record_by_log_timestamp(
                log_timestamp,
                candidate_cases,
            )
            log_type = _classify_log_type(matched_trace)
            scene = _get_scene(matched_trace, matched_case, log_timestamp)

            processed_item = item.copy()
            processed_item["SN"] = serial
            processed_item["Loop"] = round_value
            processed_item["Case"] = _get_result_case(matched_case, case_name)
            processed_item["_timestamp"] = log_timestamp
            processed_item["Type"] = log_type
            processed_item["Scene"] = scene
            processed_item["Trace"] = (
                matched_trace.get("trace_name")
                if isinstance(matched_trace, dict)
                else ""
            )
            processed_results.append(processed_item)

        processed_results.sort(key=lambda item: item["_timestamp"])

        for item in processed_results:
            item.pop("_timestamp", None)
            all_data.append(item)

    organized_data, startup_data, click_data = _aggregate_events_log(all_data, app_map)
    return all_data, organized_data, startup_data, click_data


def _aggregate_events_log(all_data, app_map) -> tuple[list, list, list]:
    """聚合 events log 源数据，生成整理页、启动页和窗口响应页数据。"""

    merged_data = defaultdict(
        lambda: {
            "Package": "",
            "Activity": "",
            "Scene": "",
            "Type": "",
            "ValuesList": [],
        }
    )

    for entry in all_data:
        package = entry.get("Package", "Unknown")
        activity = entry.get("Activity", "Unknown")
        scene = entry.get("Scene", "Unknown")
        log_type = entry.get("Type", "unknown")

        try:
            value = float(entry.get("Value", 0))
        except (ValueError, TypeError):
            continue

        group_key = (package, activity, log_type, scene)
        group_data = merged_data[group_key]
        group_data["Package"] = package
        group_data["Activity"] = activity
        group_data["Scene"] = scene
        group_data["Type"] = log_type
        group_data["ValuesList"].append(value)

    organized_data = []
    startup_data = []
    click_data = []

    for data in merged_data.values():
        values = data["ValuesList"]
        number = len(values)
        avg, std = calc_avg_std(values)

        organized_entry = {
            **data,
            "Number": number,
            "Average": avg,
            "Standard": std,
            "Values": ", ".join(map(str, values)),
        }
        organized_data.append(organized_entry)

        if data["Type"] == "startApp":
            stats = build_stats(values, STARTUP_THRESHOLDS)
            startup_data.append(
                {
                    "Application": app_map.get(data["Package"], ""),
                    "Activity": data["Activity"],
                    "启动时长均值ms": avg,
                    "标准差": std,
                    **stats,
                    "冷启动总次数": number,
                    "Top Values": organized_entry["Values"],
                }
            )
        elif data["Type"] == "InApp":
            stats = build_stats(values, CLICK_THRESHOLDS)
            click_data.append(
                {
                    "应用内转场": data["Scene"],
                    "Activity": data["Activity"],
                    "响应时延均值ms": avg,
                    "标准差": std,
                    **stats,
                    "转场总次数": number,
                    "Top Values": organized_entry["Values"],
                }
            )

    return organized_data, startup_data, click_data


# ====================== trace_records 匹配逻辑 ====================== #


def _build_trace_context(test_info: dict[str, Any] | None) -> dict:
    """
    按 serial + round 对 trace_records 建立候选索引。

    events log 是整轮采集文件，API 里的 case 通常是 __round_logs__，
    不能用 case 与 trace_records 对齐，只能在同设备同轮次内按时间范围匹配。
    """

    if not isinstance(test_info, dict):
        return {}

    trace_records = test_info.get("trace_records") or []
    if not isinstance(trace_records, list):
        return {}

    trace_context = defaultdict(list)
    for trace_record in trace_records:
        if not isinstance(trace_record, dict):
            continue

        serial = trace_record.get("serial")
        round_value = _normalize_round(trace_record.get("round"))

        if not serial or round_value is None:
            continue

        key = (str(serial), round_value)
        trace_context[key].append(trace_record)

    for traces in trace_context.values():
        traces.sort(key=lambda record: record.get("start_time") or 0)

    return dict(trace_context)


def _build_case_context(test_info: dict[str, Any] | None) -> dict:
    """按 serial + round 对用例时间范围建立候选索引。"""

    if not isinstance(test_info, dict):
        return {}

    case_records = test_info.get("case_records") or []
    if not isinstance(case_records, list):
        return {}

    case_context = defaultdict(list)
    for case_record in case_records:
        if not isinstance(case_record, dict):
            continue

        serial = case_record.get("serial")
        round_value = _normalize_round(case_record.get("round"))

        if not serial or round_value is None:
            continue

        key = (str(serial), round_value)
        case_context[key].append(case_record)

    for cases in case_context.values():
        cases.sort(key=lambda record: record.get("started_at") or 0)

    return dict(case_context)


def _get_candidate_traces(trace_context, serial, round_value) -> list[dict[str, Any]]:
    """获取同设备、同轮次下的 trace 候选记录。"""

    normalized_round = _normalize_round(round_value)
    if not serial or normalized_round is None:
        return []

    return trace_context.get((str(serial), normalized_round), [])


def _get_candidate_cases(case_context, serial, round_value) -> list[dict[str, Any]]:
    """获取同设备、同轮次下的用例候选记录。"""

    normalized_round = _normalize_round(round_value)
    if not serial or normalized_round is None:
        return []

    return case_context.get((str(serial), normalized_round), [])


def _match_case_record_by_log_timestamp(
    log_timestamp: float,
    candidate_cases: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """根据日志时间戳匹配所属用例时间范围。"""

    if not log_timestamp or not candidate_cases:
        return None

    for case_record in candidate_cases:
        started_at = case_record.get("started_at")
        stopped_at = case_record.get("stopped_at")

        if not isinstance(started_at, (int, float)) or not isinstance(
            stopped_at, (int, float)
        ):
            continue

        if started_at <= log_timestamp <= stopped_at:
            return case_record

    return None


def _match_trace_record_by_log_timestamp(
    log_timestamp: float,
    candidate_traces: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """根据 log 时间戳严格匹配所在的 trace 采集时间范围。"""

    if not log_timestamp or not candidate_traces:
        return None

    for trace_record in candidate_traces:
        start_time = trace_record.get("start_time")
        end_time = trace_record.get("end_time")

        if not isinstance(start_time, (int, float)) or not isinstance(
            end_time, (int, float)
        ):
            continue

        if start_time <= log_timestamp <= end_time:
            return trace_record

    return None


def _classify_log_type(trace_record: dict[str, Any] | None) -> str:
    """根据 trace 文件名判断 events log 记录类型。"""

    if not isinstance(trace_record, dict):
        return "unknown"

    trace_name = str(trace_record.get("trace_name") or "")

    if "AppLaunch" in trace_name:
        return "startApp"

    if "AppClick" in trace_name or "KbdPopup" in trace_name:
        return "InApp"

    return "unknown"


def _get_scene(
    trace_record: dict[str, Any] | None,
    matched_case: dict[str, Any] | None,
    log_timestamp: float,
) -> str:
    """获取 Scene：优先使用匹配 trace 的描述，失败再回退到 result.json step。"""

    trace_scene = _get_trace_scene(trace_record)
    if trace_scene != "unknown":
        return trace_scene

    return _get_result_scene(matched_case, log_timestamp)


def _get_trace_scene(trace_record: dict[str, Any] | None) -> str:
    """获取匹配 trace 的场景描述。"""

    if not isinstance(trace_record, dict):
        return "unknown"

    return str(trace_record.get("description") or "unknown")


def _get_result_case(matched_case: dict[str, Any] | None, fallback_case: Any) -> Any:
    """源数据页的 Case 使用 result.json 用例时间线判断。"""

    if isinstance(matched_case, dict):
        case_name = matched_case.get("case") or matched_case.get("case_name")
        if case_name:
            return case_name

    return fallback_case


def _get_result_scene(matched_case: dict[str, Any] | None, log_timestamp: float) -> str:
    """源数据页的 Scene 使用 result.json steps 时间线判断。"""

    if not isinstance(matched_case, dict) or not log_timestamp:
        return "unknown"

    steps = matched_case.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return "unknown"

    matched_step = None
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue

        timestamp = step.get("timestamp")
        if not isinstance(timestamp, (int, float)):
            continue

        next_timestamp = None
        for next_step in steps[index + 1 :]:
            if not isinstance(next_step, dict):
                continue
            candidate_timestamp = next_step.get("timestamp")
            if isinstance(candidate_timestamp, (int, float)):
                next_timestamp = candidate_timestamp
                break

        if next_timestamp is None:
            stopped_at = matched_case.get("stopped_at")
            next_timestamp = (
                stopped_at if isinstance(stopped_at, (int, float)) else None
            )

        if next_timestamp is None:
            if log_timestamp >= timestamp:
                matched_step = step
            continue

        if timestamp <= log_timestamp < next_timestamp:
            matched_step = step
            break

    if not isinstance(matched_step, dict):
        return "unknown"

    return str(matched_step.get("description") or "unknown")


def _normalize_round(round_value):
    if round_value is None:
        return None

    if isinstance(round_value, bool):
        return str(round_value)

    try:
        return int(round_value)
    except (TypeError, ValueError):
        return str(round_value)
