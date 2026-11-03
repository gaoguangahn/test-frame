from collections import defaultdict
from exfw.models.dynamic.report.bd_jank.selection import is_start_exit_animation


def normalize_activity_string(activity_name_raw: str) -> str:
    """标准化 Activity 名称，确保同一页面被正确聚合"""
    if not activity_name_raw or "/" not in activity_name_raw:
        return activity_name_raw if activity_name_raw else ""

    if activity_name_raw.startswith("VRI-"):
        activity_name_raw = activity_name_raw[4:]

    parts = activity_name_raw.split("/", 1)
    package_name = parts[0]
    activity_class_part = parts[1]

    if activity_class_part.startswith("."):
        full_activity_class_name = package_name + activity_class_part
    elif activity_class_part.startswith(package_name):
        full_activity_class_name = activity_class_part
    else:
        full_activity_class_name = f"{package_name}.{activity_class_part}"

    return f"{package_name}/{full_activity_class_name}"


def parse_marks(marks: list) -> list:
    """生成分段名"""
    if not marks:
        return []
    result = [f"Number({start}~{end}ms)" for start, end in zip(marks, marks[1:])]
    result.append(f"Number>{marks[-1]}")
    return result


def process_segment_data(
    filtered_datas: list,
    marks_key="Marks",
    group_by_type: bool = False,
) -> tuple:
    """通用分段数据处理函数，统计每个 Activity 在各个分段的掉帧次数。"""
    if not filtered_datas:
        return [], []

    marks = []
    for d in filtered_datas:
        if d.get(marks_key):
            marks = d[marks_key]
            break

    segment_names = parse_marks(marks)

    def _init_segment():
        segment = {
            "Activity": "",
            "Numbers": 0,
            **{name: 0 for name in segment_names},
        }
        if group_by_type:
            segment["Type"] = ""
        return segment

    segment_dict = defaultdict(_init_segment)

    for data in filtered_datas:
        # 修复 Bug: 接入标准化函数，防止同一个 Activity 被拆成多行
        raw_name = (data.get("Name") or "").split("@")[0]
        activity_name = normalize_activity_string(raw_name)
        type_name = data.get("Type") or ""

        if group_by_type:
            group_key = (activity_name, type_name)
        else:
            group_key = (activity_name,)

        segment_dict[group_key]["Activity"] = activity_name
        if group_by_type:
            segment_dict[group_key]["Type"] = type_name
        segment_dict[group_key]["Numbers"] += 1

        counts = data.get("Counts") or []
        for idx, count in enumerate(counts):
            if idx < len(segment_names):
                segment_dict[group_key][segment_names[idx]] += count

    return list(segment_dict.values()), segment_names


def sum_counts(filtered_datas: list) -> list:
    """统计所有数据的 Counts 总和"""
    if not filtered_datas:
        return []

    # 增加默认值 0，防止 max() 传入空序列报错
    counts_len = max((len(d.get("Counts") or []) for d in filtered_datas), default=0)
    if counts_len == 0:
        return []

    total = [0] * counts_len
    for data in filtered_datas:
        for i, c in enumerate(data.get("Counts") or []):
            if i < counts_len:
                total[i] += c
    return total


def process_all_radar_data(radar_log_list: list):
    """整理性能雷达数据，返回表格输入和第 0 页汇总数据。"""

    all_records, summary_data = radar_summary(radar_log_list)

    return {
        "sheets_data": {
            "all_records": all_records,
            "max_counts": summary_data.get("max_counts", 0),
            "fluency_result": summary_data.get("fluency_result", []),
            "fluency_marks": summary_data.get("fluency_marks", []),
            "animation_result": summary_data.get("animation_result", []),
            "animation_marks": summary_data.get("animation_marks", []),
        },
        "summary_data": {
            "total_bd_time": summary_data.get("total_time", 0),
            "bd_animator_counts": summary_data.get("animator_counts", []),
            "bd_fluency_counts": summary_data.get("fluency_counts", []),
        },
    }



def radar_summary(radar_log_list: list) -> tuple:
    """
    汇总 Radar 数据 (适配未拆分的原始文件级数据)
    :param radar_log_list: 包含完整 result 字典的原始数据列表
    :return: (原始数据列表, 汇总统计字典)
    """
    total_time = 0
    max_counts = 0
    all_records = []

    if not radar_log_list:
        return [], {}

    # 直接定义分类列表，省去后续通过 Comment 再次遍历过滤的性能损耗
    fluency_datas = []
    animation_datas = []

    # ===== 1. 预处理与数据展平 =====
    for item in radar_log_list:
        result_dict = item.get("result", {})
        if not result_dict:
            continue

        file_time = 0
        for metric_name in [
            "parse_animation_jank",
            "parse_fluency_fling_jank",
            "parse_fling_jank",
        ]:
            metric_data = result_dict.get(metric_name)
            if isinstance(metric_data, dict) and metric_data.get("time"):
                file_time = metric_data.get("time", 0)
                break

        total_time += file_time

        # 内部辅助函数，用于提取并展平各个指标的数据
        def _extract_and_flatten(metric_name, target_list):
            nonlocal max_counts
            metric_data = result_dict.get(metric_name, {})
            if not isinstance(metric_data, dict):
                return

            for record in metric_data.get("data") or []:
                # 将外层的元数据注入到每一条具体的记录中，供 Excel 表头读取
                record["sn"] = item.get("serial", "")
                record["loop"] = item.get("round", "")
                record["case"] = item.get("case") or item.get("case_name", "")

                counts = record.get("Counts") or []
                max_counts = max(max_counts, len(counts))

                # 展开 Count 列，方便后续生成表格
                for i, c in enumerate(counts):
                    record[f"Count {i}"] = c

                # 将数据加入总表
                all_records.append(record)
                # 如果指定了分类列表，直接加入，省去后续的 if 判断
                if target_list is not None:
                    target_list.append(record)

        # 分别提取三个指标的数据
        _extract_and_flatten("parse_fluency_fling_jank", fluency_datas)
        _extract_and_flatten("parse_animation_jank", animation_datas)
        _extract_and_flatten("parse_fling_jank", None)  # fling 数据只进 all_records

    # ===== 2. 进一步筛选特定类型的动画数据 =====
    app_animation_datas = [
        r
        for r in animation_datas
        if is_start_exit_animation(r)
    ]

    # ===== 3. 统计 =====
    fluency_result, fluency_marks = process_segment_data(fluency_datas)
    fluency_counts = sum_counts(fluency_datas)

    animation_result, animation_marks = process_segment_data(
        animation_datas, group_by_type=True
    )
    animator_counts = sum_counts(app_animation_datas)

    # ===== 4. 组装安全的字典返回 =====
    summary_data = {
        "total_time": total_time,
        "max_counts": max_counts,
        "all_records": all_records,
        "fluency_result": fluency_result,
        "fluency_marks": fluency_marks,
        "fluency_counts": fluency_counts,
        "animation_result": animation_result,
        "animation_marks": animation_marks,
        "animator_counts": animator_counts,
    }

    return all_records, summary_data
