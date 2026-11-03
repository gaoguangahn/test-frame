from collections import defaultdict

import numpy as np


def process_all_swipe_data(swipe_data):
    """一键处理所有滑动掉帧数据，返回表格数据和全局汇总数据"""

    # 1. 处理详情数据（同时计算好单次滑动的总卡顿时间，供汇总页直接使用）
    detail_data = _process_swipe_detail(swipe_data)

    # 2. 处理汇总数据
    summary_data, jank_all = _process_swipe_summary(detail_data)

    return {
        "sheets_data": {
            "detail": detail_data,
            "summary": summary_data,
        },
        "summary_data": {
            "swipe_jank_all": jank_all,
        },
    }


def _process_swipe_detail(swipe_data):
    """处理滑动掉帧详情页数据"""
    result_data = []

    for record in filter(None, swipe_data):
        # 安全处理 off_count，防止 None 导致 float() 崩溃
        off_count_val = record.get("off_count")
        off_count = round(float(off_count_val), 2) if off_count_val is not None else 0.0

        # 直接在这里计算单次滑动的总卡顿时间 (Total Jank Time)
        # 数据格式: off_jank = [[timestamp, jank_time], ...]
        off_jank_list = record.get("off_jank", [])
        total_jank_time = sum(j[1] for j in off_jank_list) if off_jank_list else 0.0

        start_time = record.get("on_deliver_start", "-")
        trace_start = record.get("trace_start")
        try:
            if trace_start:
                start_s = round((start_time - trace_start) / 1e9, 2)
            else:
                start_s = start_time
        except Exception as e:
            start_s = start_time

        result_data.append(
            {
                "SN": record.get("sn", "-"),
                "Loop": record.get("loop", "-"),
                "Case": record.get("case_name", "UNKNOWN"),
                "Activity": record.get("activity", "UNKNOWN"),
                "Package": record.get("package", "UNKNOWN"),
                "Off_avg_fps": record.get("off_avg_fps", "-"),
                "Trace": record.get("trace_name", "-"),
                "Off_Jank": str(off_jank_list),  # 转为字符串供 Excel 展示
                "SwipeStart": start_s,
                "Off_Count": off_count,
                "_raw_total_jank": total_jank_time,
            }
        )

    return result_data


def _process_swipe_summary(detail_data):
    """处理滑动数据汇总页"""
    raw_groups = defaultdict(lambda: defaultdict(list))
    jank_all = []
    group_stats = []

    # 1. 数据分组
    for item in detail_data:
        case = item["Case"]
        pkg = item["Package"]
        act = item["Activity"]
        key = (case, pkg, act)

        # 直接读取详情页算好的总时间
        total_time = item["_raw_total_jank"]
        raw_groups[key]["JankTime"].append(round(total_time, 2))
        jank_all.append(round(total_time, 2))

    # 2. 统计计算
    for (case, pkg, activity), fields in raw_groups.items():
        data_array = np.array(fields["JankTime"])

        top_values = sorted(fields["JankTime"], reverse=True)

        stat_record = {
            "Case": case,
            "Package": pkg,
            "Activity": activity,
            "SlideNumbers": len(data_array),
            # 使用 int() 包装 numpy 结果，防止 Excel 库无法识别 numpy.int64 类型
            "Number(25~58ms)": int(((data_array >= 25) & (data_array < 58)).sum()),
            "Number(58~84ms)": int(((data_array >= 58) & (data_array < 84)).sum()),
            "Number(84~133ms)": int(((data_array >= 84) & (data_array < 133)).sum()),
            "Number(>133ms)": int((data_array >= 133).sum()),
            # 优化展示：用逗号拼接，去掉中括号
            "Top Values": ", ".join(str(x) for x in top_values) if top_values else "-",
        }
        group_stats.append(stat_record)

    return group_stats, jank_all
