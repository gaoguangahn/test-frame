def io_measure_summary(io_log_list: list) -> tuple:
    """
    汇总所有 IOMeasure 日志的数据，并展平用于 Excel 导出
    :param io_log_list: 包含各个文件解析结果的列表
    :return: (展平后的记录列表, 汇总统计字典)
    """
    io_types = ["fs", "blk", "scsi"]

    metric_map = {
        "read-all": "read_cnt",
        "read-16": "read(>16ms)",
    }

    # 初始化汇总字典
    summary_data = {f"{t}-{k}": 0 for t in io_types for k in metric_map}
    all_records = []

    if not io_log_list:
        return all_records, summary_data

    # 遍历累加并展平数据
    for item in io_log_list:
        # 兼容取值，可能是 data 也可能是 result
        result = item.get("result") or item.get("data") or {}

        # ================= 新增：展平数据供 Excel 使用 =================
        record = {
            "sn": item.get("serial", ""),
            "loop": item.get("round", ""),
            "log_name": item.get("log_name", ""),
        }
        # 将 result 里面的具体指标平铺到外层字典
        record.update(result)
        all_records.append(record)
        # ==============================================================

        # 累加汇总数据
        for t in io_types:
            prefix = f"Latency-{t}"
            for metric_name, metric_key in metric_map.items():
                # 假设 JSON 里解析出来的 key 是 "Latency-fs.read_cnt" 这种格式
                key = f"{prefix}.{metric_key}"
                summary_data[f"{t}-{metric_name}"] += result.get(key, 0)

    return all_records, summary_data
