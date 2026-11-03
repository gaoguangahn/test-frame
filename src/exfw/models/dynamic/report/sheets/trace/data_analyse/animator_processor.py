from collections import defaultdict
import numpy as np

from .trace_context import build_trace_record_index, lookup_trace_description

FRAME_BUCKETS = (
    ("Number(34~50ms)", 34, 50),
    ("Number(50~84ms)", 50, 84),
    ("Number(84~134ms)", 84, 134),
    ("Number(>134ms)", 134, None),
)


def process_all_animator_data(startup_transition, exit_animation, test_info=None):
    """处理 trace 启动/退出动效数据，返回 sheet 数据和汇总数据。"""

    trace_record_index = build_trace_record_index(test_info)

    launcher_detail = _process_animator_detail(
        startup_transition,
        exit_animation,
        frame_key="animation_frames",
        trace_record_index=trace_record_index,
    )
    engine_detail = _process_animator_detail(
        startup_transition,
        exit_animation,
        frame_key="transaction_frames",
        trace_record_index=trace_record_index,
    )

    launcher_summary = _process_animator_summary(launcher_detail)
    engine_summary = _process_animator_summary(engine_detail)

    return {
        "sheets_data": {
            "launcher_detail": launcher_detail,
            "launcher_summary": launcher_summary,
            "engine_detail": engine_detail,
            "engine_summary": engine_summary,
        },
        "summary_data": {
            "startexit_launcher_frame_summary": _build_frame_summary(launcher_detail),
            "startexit_engine_frame_summary": _build_frame_summary(engine_detail),
        },
    }


def _process_animator_detail(startup_data, exit_data, frame_key, trace_record_index):
    """处理一次动效内所有帧在各耗时区间内的数量。"""

    detail_rows = []
    tagged_records = [
        ("Startup", record) for record in filter(None, startup_data or [])
    ] + [("Exit", record) for record in filter(None, exit_data or [])]

    for animation_type, record in tagged_records:
        frames = record.get(frame_key)

        if not frames:
            continue

        frame_counts = _count_frames_by_bucket(frames)
        detail_rows.append(
            {
                "SN": record.get("serial") or record.get("sn") or "-",
                "Loop": record.get("round") or record.get("loop") or "-",
                "Case": record.get("case") or record.get("case_name") or "-",
                "Trace": record.get("trace_name") or "-",
                "Package": record.get("name") or record.get("new_package") or "-",
                "Animation": animation_type,
                "Scene": lookup_trace_description(record, trace_record_index),
                **frame_counts,
                "Numbers": len(frames),
                "Frames": str(frames),
            }
        )

    return detail_rows


def _process_animator_summary(detail_data):
    """按 Package + Animation + Scene 汇总所有动效帧区间数量。"""

    grouped_counts = defaultdict(lambda: defaultdict(int))
    summary_rows = []

    for detail_row in detail_data:
        group_key = (
            detail_row.get("Package", "-"),
            detail_row.get("Animation", "-"),
            detail_row.get("Scene", ""),
        )

        for bucket_name, _, _ in FRAME_BUCKETS:
            grouped_counts[group_key][bucket_name] += detail_row.get(bucket_name, 0)

        grouped_counts[group_key]["Numbers"] += detail_row.get("Numbers", 0)

    for (package, animation_type, scene), bucket_counts in grouped_counts.items():
        summary_row = {
            "Package": package,
            "Animation": animation_type,
            "Scene": scene,
        }

        for bucket_name, _, _ in FRAME_BUCKETS:
            summary_row[bucket_name] = bucket_counts[bucket_name]

        summary_row["Numbers"] = bucket_counts["Numbers"]
        summary_rows.append(summary_row)

    return summary_rows


def _count_frames_by_bucket(frames):
    """统计一组帧耗时在各区间内的数量。"""

    frame_array = np.array(frames)
    counts = {}

    for bucket_name, lower, upper in FRAME_BUCKETS:
        if upper is None:
            counts[bucket_name] = int(np.sum(frame_array >= lower))
        else:
            counts[bucket_name] = int(
                np.sum((frame_array >= lower) & (frame_array < upper))
            )

    return counts


def _build_frame_summary(detail_data):
    """汇总所有启退动效帧区间数量，供第 0 页使用。"""

    summary = {bucket_name: 0 for bucket_name, _, _ in FRAME_BUCKETS}
    summary["Numbers"] = 0
    # 启退次数是动效 record 数，不是发生卡顿的帧数。
    summary["AnimatorCounts"] = len(detail_data)

    for detail_row in detail_data:
        for bucket_name, _, _ in FRAME_BUCKETS:
            summary[bucket_name] += detail_row.get(bucket_name, 0)

        summary["Numbers"] += detail_row.get("Numbers", 0)

    return summary
