from __future__ import annotations

from typing import Any

from .data_fetcher import ReportDataFetcher
from .data_loader import (
    discover_runner_report_tasks,
    load_all_case_records,
    load_all_trace_records,
    load_task_result,
    normalize_serial_filter,
)
from .data_models import ReportDataset
from .local_results import load_local_results
from .data_transformer import (
    build_test_info,
    expand_log_results,
    expand_trace_results,
    merge_case_records,
    merge_trace_records,
    route_log_data_by_metric,
    route_trace_data_by_metric,
    summarize_action_stats,
)


def build_report_dataset(
    *,
    runner_output_dir: str,
    serial: str | list[str] | tuple[str, ...] | None = None,
    round: int | None = None,
    fetcher: ReportDataFetcher | None = None,
    source: str = "server",
) -> ReportDataset:
    """读取 runner 输出、本地记录和服务端结果，构造报表数据集。"""

    if source not in ("server", "local"):
        raise ValueError(f"不支持的报告数据源：{source}")
    data_fetcher = fetcher or ReportDataFetcher()
    serial_filter = normalize_serial_filter(serial)

    runner_result = load_task_result(runner_output_dir)
    tasks = discover_runner_report_tasks(
        runner_output_dir=runner_output_dir,
        runner_result=runner_result,
        serial_filter=serial_filter,
        require_task_id=source == "server",
    )

    if not tasks:
        raise ValueError("未发现符合条件的 dynamic runner 子任务。")

    all_case_results: list[dict[str, Any]] = []
    trace_records_list: list[list[dict[str, Any]]] = []
    case_records_list: list[list[dict[str, Any]]] = []

    for task in tasks:
        # task_id 已经唯一标识一个 pytest 子任务；设备筛选已在 runner task 发现阶段完成。
        # 这里不再向服务端传 serial，避免服务端在 serial 过滤路径上出错导致整份报告取不到数据。
        if source == "local":
            case_results = load_local_results(task, round)
        else:
            case_results = data_fetcher.fetch_case_results(task_id=task.task_id, round=round)

        trace_records = load_all_trace_records(
            task_dir=task.task_dir,
            session_data=task.session_data,
            serial=task.main_serial,
            rounds=round,
        )
        trace_records_list.append(trace_records)

        case_records = load_all_case_records(
            task_dir=task.task_dir,
            session_data=task.session_data,
            serial=task.main_serial,
            rounds=round,
        )
        case_records_list.append(case_records)

        all_case_results.extend(case_results)

    if not all_case_results:
        raise ValueError("没有可用于生成性能报告的解析数据。")

    trace_records = merge_trace_records(trace_records_list)
    case_records = merge_case_records(case_records_list)

    trace_rows = expand_trace_results(all_case_results)
    trace_data = route_trace_data_by_metric(trace_rows)

    log_rows = expand_log_results(all_case_results)
    log_data = route_log_data_by_metric(log_rows)

    action_summary = summarize_action_stats(all_case_results)
    test_info = build_test_info(
        runner_result=runner_result,
        report_tasks=tasks,
        trace_records=trace_records,
        case_records=case_records,
        case_results=all_case_results,
        action_summary=action_summary,
    )

    return ReportDataset(
        case_results=all_case_results,
        test_info=test_info,
        trace_data=trace_data,
        log_data=log_data,
        report_tasks=tasks,
        selected_round=round,
    )
