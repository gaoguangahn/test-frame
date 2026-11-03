from __future__ import annotations

from .dumpsys_meminfo import dumpsys_meminfo_summary
from .io_measure import io_measure_summary
from .jank_log import jank_log_summary
from .proc_memory import proc_memory_summary


def process_all_memory_io_data(
    io_measure_data,
    proc_memory_data,
    dumpsys_meminfo_data,
    jank_log_data,
):
    """整理 Memory / IO 相关数据，返回表格输入和第 0 页汇总数据。"""

    measure_data, measure_summary = io_measure_summary(io_measure_data)
    proc_data, proc_summary = proc_memory_summary(proc_memory_data)
    dumpsys_data = dumpsys_meminfo_summary(dumpsys_meminfo_data)
    jank_data, jank_summary = jank_log_summary(jank_log_data)

    return {
        "sheets_data": {
            "proc_data": proc_data,
            "memory_log_data": _merge_memory_log_data(dumpsys_data, jank_data),
            "measure_data": measure_data,
            "jank_data": jank_data,
        },
        "summary_data": {
            "proc_summary": proc_summary,
            "measure_summary": measure_summary,
            "dumpsys_data": dumpsys_data,
            "jank_summary": jank_summary,
        },
    }


def _merge_memory_log_data(dumpsys_data, jank_data):
    """合并 dumpsys meminfo 与 jank 内存日志，生成内存日志 sheet 输入。"""

    merged_dict = {}

    for item in (dumpsys_data or []) + (jank_data or []):
        key = (item.get("sn"), item.get("loop"))

        if key not in merged_dict:
            merged_dict[key] = {
                "sn": item.get("sn"),
                "loop": item.get("loop"),
            }

        for name, value in item.items():
            if name not in ["sn", "loop"]:
                merged_dict[key][name] = value

    return list(merged_dict.values())
