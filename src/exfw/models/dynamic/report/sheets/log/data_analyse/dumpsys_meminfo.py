def dumpsys_meminfo_summary(meminfo_log_list: list):
    """
    汇总 dumpsys_meminfo 数据并展平供 Excel 导出
    :param meminfo_log_list: 包含 dumpsys_meminfo 解析结果的列表
    :return: 展平后的记录列表 (仅保留 loop_stop 阶段)
    """
    all_records = []

    if not meminfo_log_list:
        return all_records

    for item in meminfo_log_list:
        result = item.get("data") or {}

        # 展平数据
        record = {
            "sn": item.get("serial", ""),
            "loop": item.get("round", ""),
            "log_name": item.get("log_name", ""),
        }

        record.update(result)

        all_records.append(record)

    return all_records
