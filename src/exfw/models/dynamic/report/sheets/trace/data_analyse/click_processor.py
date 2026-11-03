from collections import defaultdict

import numpy as np

from ....utils.report_util import safe_int
from .trace_context import build_trace_record_index, lookup_trace_description


def process_all_click_data(click_transition, test_info=None):
    """处理 trace 应用内点击响应数据，返回 sheet 数据和汇总数据。"""

    trace_record_index = build_trace_record_index(test_info)

    # 1. 处理详情数据。
    detail_data, state_columns = _process_click_detail(
        click_transition, trace_record_index
    )

    # 2. 处理汇总数据。
    summary_data, spend_values, states_values = _process_click_summary(detail_data)

    return {
        "sheets_data": {
            "detail": detail_data,
            "state_columns": state_columns,
            "summary": summary_data,
        },
        "summary_data": {
            "click_spend_values": spend_values,
            "click_states_values": states_values,
        },
    }


def _process_click_detail(click_transition, trace_record_index):
    """处理应用内点击响应详情页数据。"""

    detail_rows = []
    state_columns = []

    for record in filter(None, click_transition):
        response_time = safe_int(record.get("response_time"))
        round_value = safe_int(record.get("round"))

        detail_row = {
            "SN": record.get("serial", "-"),
            "Loop": round_value if round_value is not None else -1,
            "Case": record.get("case", "UNKNOWN"),
            "Trace": record.get("trace_name", "-"),
            "Scene": lookup_trace_description(record, trace_record_index),
            "Package": record.get("new_process") or "UNKNOWN",
            "Activity": record.get("new_activity") or "UNKNOWN",
            "Type": record.get("startup_type", "unknown"),
            "dur": response_time if response_time is not None else "-",
        }

        thread_states = record.get("thread_state") or record.get("thread_states") or {}
        if not isinstance(thread_states, dict):
            thread_states = {}

        for state_name, state_value in thread_states.items():
            int_value = safe_int(state_value)
            detail_row[state_name] = (
                int(int_value / 1_000_000) if int_value is not None else "-"
            )
            if state_name not in state_columns:
                state_columns.append(state_name)

        detail_rows.append(detail_row)

    return detail_rows, state_columns


def _process_click_summary(detail_data):
    """处理应用内点击汇总页数据。"""

    grouped_values = defaultdict(lambda: defaultdict(list))
    states_values = defaultdict(list)
    spend_values = {"cold": [], "warm": [], "hot": [], "unknown": []}
    summary_rows = []

    state_names = [
        "running_dur_ns",
        "runnable_dur_ns",
        "uninterruptible_sleep_dur_ns",
        "interruptible_sleep_dur_ns",
        "uninterruptible_io_sleep_dur_ns",
        "uninterruptible_non_io_sleep_dur_ns",
    ]
    metric_names = ["dur"] + state_names

    for detail_row in detail_data:
        package = detail_row.get("Package", "UNKNOWN")
        activity = detail_row.get("Activity", "UNKNOWN")
        case_name = detail_row.get("Case", "UNKNOWN")
        group_key = (package, activity, case_name)

        duration = detail_row.get("dur")
        start_type = detail_row.get("Type", "unknown")
        if start_type not in spend_values:
            start_type = "unknown"

        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            spend_values[start_type].append(duration)
            grouped_values[group_key]["dur"].append(duration)

        for state_name in state_names:
            state_value = detail_row.get(state_name)
            if isinstance(state_value, (int, float)) and not isinstance(state_value, bool):
                grouped_values[group_key][state_name].append(state_value)
                states_values[state_name].append(state_value)

    statistics = ["Count", "Avg", "Std", "Min", "Max", "25%", "50%", "75%"]
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

    for (package, activity, case_name), metric_values in grouped_values.items():
        for statistic in statistics:
            summary_row = {
                "Case": case_name,
                "Package": package,
                "Activity": activity,
                "statistics": statistic,
            }
            for metric_name in metric_names:
                data_array = np.array(metric_values.get(metric_name, []))
                summary_row[metric_name] = (
                    stat_funcs[statistic](data_array) if len(data_array) > 0 else "-"
                )
            summary_rows.append(summary_row)

    return summary_rows, spend_values, states_values
