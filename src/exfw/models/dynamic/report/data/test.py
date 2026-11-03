from .data_fetcher import ReportDataFetcher
from .data_transformer import (
    expand_log_results,
    expand_trace_results,
    filter_failed_results,
    route_log_data_by_metric,
    route_trace_data_by_metric,
)

with ReportDataFetcher() as fetcher:
    case_results = fetcher.fetch_case_results(
        task_id="e660a69dd9ca414baec2f986e6f22493",
    )
    trace_rows = expand_trace_results(case_results)
    log_rows = expand_log_results(case_results)

    failed_trace_rows = filter_failed_results(trace_rows)
    failed_log_rows = filter_failed_results(log_rows)

    routed_trace_data = route_trace_data_by_metric(trace_rows)
    routed_log_data = route_log_data_by_metric(log_rows)
    # print(routed_trace_data.get("click_transition"))
    print(log_rows[4])
