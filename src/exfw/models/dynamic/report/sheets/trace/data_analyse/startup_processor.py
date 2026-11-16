from collections import defaultdict
import numpy as np

from ....utils.report_util import safe_int
from ..thread_states import THREAD_STATE_COLUMNS
from .trace_context import build_trace_record_index, lookup_trace_description


SPEND_METRIC_NAMES = ["SpendTime", *THREAD_STATE_COLUMNS]
START_TYPE_GROUPS = ("all", "cold", "warm", "hot")


def process_all_startup_data(startup_data, app_map, test_info=None):
    """处理 trace 启动指标，返回启动相关 sheet 数据和汇总数据。"""

    trace_record_index = build_trace_record_index(test_info)

    # 1. 处理详情数据。
    detail_data, state_columns = _process_detail(startup_data, trace_record_index)

    # 2. 处理响应汇总。
    response_summary, response_values = _process_response_summary(detail_data, app_map)

    # 3. 处理耗时汇总。
    spend_summary, spend_values, states_values = _process_spend_summary(
        detail_data, app_map
    )

    # 4. 处理包名单行耗时汇总。
    spend_package_summary = _process_spend_package_summary(detail_data, app_map)

    return {
        "sheets_data": {
            "detail": detail_data,
            "state_columns": state_columns,
            "response_summary": response_summary,
            "spend_summary": spend_summary,
            "spend_type_summary": _process_spend_type_summary(detail_data, app_map),
            "spend_package_summary": spend_package_summary,
        },
        "summary_data": {
            "start_response_values": response_values,
            "start_spend_values": spend_values,
            "start_states_values": states_values,
        },
    }


def _process_detail(startup_data, trace_record_index):
    """处理启动详情页数据。"""

    detail_rows = []
    state_columns = list(THREAD_STATE_COLUMNS)

    for item in filter(None, startup_data):
        scene = lookup_trace_description(item, trace_record_index)
        detail_row = {
            "SN": item.get("serial"),
            "Loop": int(item.get("round", -1)),
            "Case": item.get("case", "UNKNOWN"),
            "Trace": item.get("trace_name"),
            "Scene": scene,
            "Package": item.get("new_package", "UNKNOWN"),
            "Activity": item.get("new_activity", "UNKNOWN"),
            "StartType": item.get("startup_type", "UNKNOWN"),
            "ResponseTime": safe_int(item.get("response_time")),
            "SpendTime": safe_int(item.get("spend_time")),
        }

        # 处理线程状态（纳秒转毫秒）。
        thread_states = {}
        for state_name, state_value in item.get("thread_states", {}).items():
            int_value = safe_int(state_value)
            thread_states[state_name] = (
                int(int_value / 1_000_000) if int_value is not None else "-"
            )
            if state_name not in state_columns:
                state_columns.append(state_name)

        detail_rows.append({**detail_row, **thread_states})

    return detail_rows, state_columns


def _calc_basic_stats(values):
    """计算基础统计指标，返回 (Avg, Std, Max, Min)。"""

    if not values:
        return "-", "-", "-", "-"

    if len(values) == 1:
        return values[0], 0, values[0], values[0]

    return (
        round(np.mean(values), 2),
        round(np.std(values, ddof=1), 2),
        np.max(values),
        np.min(values),
    )


def _process_response_summary(detail_data, app_map):
    """按 Package 汇总启动响应时间。"""

    package_summary = {}
    response_values = {"cold": [], "warm": [], "hot": [], "unknown": []}

    for detail_row in detail_data:
        package = detail_row["Package"]
        if package not in package_summary:
            package_summary[package] = {
                "Package": package,
                "Application": app_map.get(package, "UNKNOWN"),
                "Values": [],
            }

        response_time = detail_row.get("ResponseTime")
        if isinstance(response_time, int):
            package_summary[package]["Values"].append(response_time)
            start_type = detail_row.get("StartType", "unknown")
            response_values.setdefault(start_type, []).append(response_time)

    result_data = list(package_summary.values())
    for summary_row in result_data:
        values = summary_row["Values"]
        (
            summary_row["Average"],
            summary_row["Standard"],
            summary_row["Max"],
            summary_row["Min"],
        ) = _calc_basic_stats(values)
        summary_row["Number(155~245ms)"] = (
            len([value for value in values if 155 < value <= 245]) if values else "-"
        )
        summary_row["Number(245~390ms)"] = (
            len([value for value in values if 245 < value <= 390]) if values else "-"
        )
        summary_row["Number(>=390ms)"] = (
            len([value for value in values if value > 390]) if values else "-"
        )
        summary_row["Numbers"] = len(values)
        summary_row["Top Values"] = (
            ", ".join(str(value) for value in sorted(values, reverse=True))
            if values
            else "-"
        )

    return result_data, response_values


def _process_spend_summary(detail_data, app_map):
    """按 Package + Activity 汇总启动耗时和线程状态。"""

    grouped_values = defaultdict(lambda: defaultdict(list))
    states_values = defaultdict(list)
    spend_values = {"cold": [], "warm": [], "hot": [], "unknown": []}
    group_stats = []

    state_names = THREAD_STATE_COLUMNS
    metric_names = SPEND_METRIC_NAMES

    for detail_row in detail_data:
        package = detail_row["Package"]
        activity = detail_row["Activity"]
        group_key = (package, activity)

        start_type = detail_row.get("StartType", "unknown")
        spend_time = detail_row.get("SpendTime")
        if isinstance(spend_time, int):
            if start_type in spend_values:
                spend_values[start_type].append(spend_time)
            else:
                spend_values["unknown"].append(spend_time)

        for metric_name in metric_names:
            metric_value = detail_row.get(metric_name)
            if isinstance(metric_value, int):
                grouped_values[group_key][metric_name].append(metric_value)
                if metric_name in state_names:
                    states_values[metric_name].append(metric_value)

    for (package, activity), metric_values in grouped_values.items():
        for statistics in _calculate_spend_statistics(metric_values):
            group_stats.append({
                "Application": app_map.get(package, "UNKNOWN"),
                "Package": package,
                "Activity": activity,
                **statistics,
            })

    return group_stats, spend_values, states_values


def _calculate_spend_statistics(metric_values):
    """第 3 和 3.1 页共享统计口径，线程状态在详情阶段已转换为毫秒。"""
    stat_funcs = {
        "Count": len,
        "Avg": lambda values: round(np.mean(values), 2),
        "Std": lambda values: round(np.std(values, ddof=1), 2)
        if len(values) > 1
        else 0.0,
        "Min": lambda values: round(np.min(values), 2),
        "Max": lambda values: round(np.max(values), 2),
        "25%": lambda values: round(np.percentile(values, 25), 2),
        "50%": lambda values: round(np.percentile(values, 50), 2),
        "75%": lambda values: round(np.percentile(values, 75), 2),
    }

    rows = []
    for statistic, calculate in stat_funcs.items():
        row = {"statistics": statistic}
        for metric_name in SPEND_METRIC_NAMES:
            values = np.array(metric_values.get(metric_name, []))
            if len(values):
                row[metric_name] = calculate(values)
            else:
                row[metric_name] = "-"
        rows.append(row)
    return rows


def _process_spend_type_summary(detail_data, app_map):
    """按实际有有效指标的启动类型细分；all 包含未知类型的数据。"""
    grouped_values = {}
    for detail_row in detail_data:
        key = (detail_row["Package"], detail_row["Activity"])
        start_type = str(detail_row.get("StartType", "")).strip().lower()
        for metric_name in SPEND_METRIC_NAMES:
            value = detail_row.get(metric_name)
            if not isinstance(value, int):
                continue
            if key not in grouped_values:
                grouped_values[key] = {
                    group: defaultdict(list) for group in START_TYPE_GROUPS
                }
            groups = grouped_values[key]
            groups["all"][metric_name].append(value)
            if start_type in ("cold", "warm", "hot"):
                groups[start_type][metric_name].append(value)

    rows = []
    for (package, activity), groups in grouped_values.items():
        for start_type in START_TYPE_GROUPS:
            metric_values = groups[start_type]
            if not metric_values:
                continue
            for statistics in _calculate_spend_statistics(metric_values):
                rows.append({
                    "Application": app_map.get(package, "UNKNOWN"),
                    "Package": package,
                    "Activity": activity,
                    "StartType": start_type,
                    **statistics,
                })
    return rows


def _process_spend_package_summary(detail_data, app_map):
    """按 Package 汇总启动耗时。"""

    package_summary = {}

    for detail_row in detail_data:
        package = detail_row["Package"]
        if package not in package_summary:
            package_summary[package] = {
                "Package": package,
                "Application": app_map.get(package, "UNKNOWN"),
                "Values": [],
            }

        spend_time = detail_row.get("SpendTime")
        if isinstance(spend_time, (int, float)):
            package_summary[package]["Values"].append(spend_time)

    result_data = list(package_summary.values())
    for summary_row in result_data:
        values = summary_row["Values"]
        (
            summary_row["Average"],
            summary_row["Standard"],
            summary_row["Max"],
            summary_row["Min"],
        ) = _calc_basic_stats(values)

        summary_row["Numbers"] = len(values)
        summary_row["Top Values"] = (
            ", ".join(str(value) for value in sorted(values, reverse=True))
            if values
            else "-"
        )

    return result_data
