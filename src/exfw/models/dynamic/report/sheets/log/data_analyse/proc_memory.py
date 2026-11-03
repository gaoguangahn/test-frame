def proc_memory_summary(memory_log_list: list) -> tuple:
    """
    汇总 ProcMemory 数据，提取关键内存指标的时间序列，并展平供 Excel 导出
    :param memory_log_list: 包含各个文件解析结果的列表
    :return: (展平后的记录列表, 汇总统计字典)
    """
    if not memory_log_list:
        return [], {}

    # 配置：原始 key 映射到汇总后的 metric_name
    metric_keys = {
        "/proc/meminfo.MemAvailable": "MemAvailable",
        "/proc/meminfo.MemFree": "MemFree",
        "/proc/meminfo.Active(anon)": "Active(anon)",
        "/proc/meminfo.Inactive(anon)": "Inactive(anon)",
        "/proc/meminfo.Active(file)": "Active(file)",
        "/proc/meminfo.Inactive(file)": "Inactive(file)",
        "/proc/meminfo.Slab": "Slab",
        "/proc/vmstat.workingset_refault_anon": "workingset_refault_anon",
        "/proc/vmstat.workingset_refault_file": "workingset_refault_file",
        "/proc/vmstat.kswapd_high_wmark_hit_quickly": "kswapd_high_wmark_hit_quickly",
        "/proc/vmstat.kswapd_low_wmark_hit_quickly": "kswapd_low_wmark_hit_quickly",
    }

    # 初始化汇总字典，值为列表，用于存放时间序列数据
    summary_data = {v: [] for v in metric_keys.values()}
    all_records = []  # ================= 新增：存放展平数据 =================

    for item in memory_log_list:
        # 兼容取值，可能是 result 也可能是 data
        if not item:
            item = {}
        result = item.get("result") or item.get("data") or {}

        # ================= 新增：展平数据供 Excel 使用 =================
        record = {
            "sn": item.get("serial", ""),
            "loop": item.get("round", ""),
            "case": item.get("case") or item.get("case_name", ""),
        }
        record.update(result)
        all_records.append(record)
        # ==============================================================

        if not result:
            # 如果没有数据，为了保证时间序列长度对齐，填入 None
            for metric_name in metric_keys.values():
                summary_data[metric_name].append(None)
            continue

        # 遍历配置字典，保证每个指标的数组长度严格对齐
        for raw_key, metric_name in metric_keys.items():
            value = result.get(raw_key)

            # 处理缺失值或解析阶段标记的 EMPTY ("-")
            if value is None or value == "-":
                summary_data[metric_name].append(None)
                continue

            try:
                summary_data[metric_name].append(float(value))
            except (TypeError, ValueError):
                summary_data[metric_name].append(None)

    return all_records, summary_data
