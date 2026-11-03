from pathlib import Path


def get_io_stat_stage(log_name: str) -> str:
    """
    从 IOStat 日志文件名中提取阶段。

    示例：
    - io_stat_start_1788167596.txt -> start
    - io_stat_end_1788167696.txt   -> end
    """
    file_stem = Path(log_name or "").stem.lower()

    if file_stem.startswith("io_stat_start_"):
        return "start"

    if file_stem.startswith("io_stat_end_"):
        return "end"

    return ""


def process_all_io_stat_data(io_stat_list: list):
    """整理 IOStat 数据，返回表格输入和第 0 页汇总数据。"""

    stat_data, stat_summary = io_stat_summary(io_stat_list)

    return {
        "sheets_data": {
            "stat_data": stat_data,
            "stat_summary": stat_summary,
        },
        "summary_data": {
            "io_stat_summary": stat_summary,
        },
    }



def io_stat_summary(io_stat_list: list) -> tuple:
    """
    汇总 IOStat 数据，按 SN 分组计算读写扇区的差值，并展平原始数据供 Excel 导出
    :param io_stat_list: 包含各个文件解析结果的列表
    :return: (展平后的原始数据列表, 汇总统计字典列表)
    """
    sn_groups = {}
    all_records = []
    summary_data = []

    if not io_stat_list:
        return all_records, summary_data

    # 1. 按 SN 分组并找出最早(start)和最晚(end)的记录，同时展平数据
    for item in io_stat_list:
        sn = item.get("serial")
        # 兼容取值
        result = item.get("data") or item.get("result") or {}

        record = {
            "sn": sn,
            "loop": item.get("round", ""),
            "case": item.get("case") or item.get("case_name", ""),
            "stage": get_io_stat_stage(item.get("log_name", "")),
        }
        record.update(result)
        all_records.append(record)

        if not sn or not result:
            continue

        ts = result.get("Timestamp")
        if ts is None:
            continue

        if sn not in sn_groups:
            sn_groups[sn] = {"start": result, "end": result}
        else:
            if ts < sn_groups[sn]["start"]["Timestamp"]:
                sn_groups[sn]["start"] = result
            if ts > sn_groups[sn]["end"]["Timestamp"]:
                sn_groups[sn]["end"] = result

    # 2. 计算差值并生成汇总数据
    for sn, rec in sn_groups.items():
        start_rec = rec["start"]
        end_rec = rec["end"]

        try:
            # 严格取值：如果不包含该键，会触发 KeyError；如果无法转为 int，会触发 ValueError
            r_start = int(start_rec["R-sectors"])
            r_end = int(end_rec["R-sectors"])
            w_start = int(start_rec["W-sectors"])
            w_end = int(end_rec["W-sectors"])
            d_start = int(start_rec["discard-sectors"])
            d_end = int(end_rec["discard-sectors"])
        except (KeyError, ValueError) as e:
            # 数据不完整或格式错误时，直接跳过该 SN 的统计，防止产生脏数据
            print(
                f"警告: SN {sn} 的 IOStat 数据不完整或格式错误，已跳过。错误信息: {e}"
            )
            continue

        summary_data.append(
            {
                "sn": sn,
                "R-sectors-start": r_start,
                "R-sectors-end": r_end,
                "R-sectors": r_end - r_start,
                "W-sectors-start": w_start,
                "W-sectors-end": w_end,
                "W-sectors": w_end - w_start,
                "discard-sectors-start": d_start,
                "discard-sectors-end": d_end,
                "discard-sectors": d_end - d_start,
            }
        )

    return all_records, summary_data
