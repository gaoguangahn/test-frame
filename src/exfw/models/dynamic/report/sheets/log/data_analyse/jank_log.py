def jank_log_summary(jank_log_list: list) -> tuple:
    """
    汇总 jank_logcat 数据并计算好所有 Excel 需要的字段
    :param jank_log_list: 包含 jank_logcat 解析结果的列表
    :return: 包含表格数据和汇总数据的字典
    """
    all_records = []

    # 【优化】：初始值设为 None，代表“未获取到数据”
    total_type_jank_numbers = None

    if not jank_log_list:
        return all_records, total_type_jank_numbers

    total_type_jank_numbers = 0

    for item in jank_log_list:
        # 【新增】：兼容 item 可能为 None 的情况
        if not item:
            continue

        result = item.get("data", {})

        # 获取 type_jank 列表
        type_jank_list = result.get("type_jank", [])

        # 直接在这里完成计算
        numbers = len(type_jank_list)
        records_str = ",".join(type_jank_list)

        total_type_jank_numbers += numbers

        # 严格按照 Excel 表头需要的字段名组装数据
        record = {
            "sn": item.get("serial", ""),
            "loop": item.get("round", ""),
            "Numbers": numbers,
            "Records": records_str,
        }
        record.update(result)
        all_records.append(record)

    return all_records, total_type_jank_numbers
