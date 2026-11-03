import numpy as np

from .trace_context import build_trace_record_index, lookup_trace_description

FRAME_BUCKETS = (
    ("Number(34~50ms)", 34, 50),
    ("Number(50~84ms)", 50, 84),
    ("Number(84~134ms)", 84, 134),
    ("Number(>134ms)", 134, None),
)


def process_all_keyboard_data(keyboard_data, test_info=None):
    """处理 trace 输入法数据，返回 sheet 数据和汇总数据。"""

    trace_record_index = build_trace_record_index(test_info)
    response_data, animation_data, response_values = _process_keyboard_detail(
        keyboard_data,
        trace_record_index,
    )

    return {
        "sheets_data": {
            "response": response_data,
            "animation": animation_data,
        },
        "summary_data": {
            "keyboard_popup_count": len(response_data),
            "keyboard_response_values": response_values,
            "keyboard_frame_summary": _build_frame_summary(animation_data),
        },
    }


def _process_keyboard_detail(keyboard_data, trace_record_index):
    """处理输入法弹出响应和弹窗动效数据。"""

    response_rows = []
    animation_rows = []
    response_values = []

    for record in filter(None, keyboard_data):
        frames = record.get("animation_frames") or []
        response_time = record.get("response_time")
        animator_type = record.get("animator_type", "-")

        common_data = {
            "SN": record.get("serial") or record.get("sn") or "-",
            "Loop": record.get("round") or record.get("loop") or "-",
            "Case": record.get("case") or record.get("case_name") or "UNKNOWN",
            "Trace": record.get("trace_name", "-"),
            "Scene": lookup_trace_description(record, trace_record_index),
            "Package": record.get("name") or record.get("new_package") or "UNKNOWN",
            "AnimatorType": animator_type,
        }

        if _is_valid_response_time(response_time):
            response_values.append(response_time)

        response_rows.append(
            {
                **common_data,
                "ResponseTime": response_time if response_time is not None else "-",
            }
        )

        if frames:
            frame_counts = _count_frames_by_bucket(frames)
            animation_rows.append(
                {
                    **common_data,
                    **frame_counts,
                    "Numbers": len(frames),
                    "Frames": str(frames),
                }
            )

    return response_rows, animation_rows, response_values


def _is_valid_response_time(response_time):
    """判断输入法响应耗时是否可用于统计。"""

    if isinstance(response_time, bool):
        return False

    return isinstance(response_time, (int, float)) and response_time >= 0


def _count_frames_by_bucket(frames):
    """统计一组帧间隔在各区间内的数量。"""

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


def _build_frame_summary(animation_data):
    """汇总输入法弹窗动效帧区间数量，供第 0 页使用。"""

    summary = {bucket_name: 0 for bucket_name, _, _ in FRAME_BUCKETS}
    summary["Numbers"] = 0
    summary["Animations"] = len(animation_data)

    for item in animation_data:
        for bucket_name, _, _ in FRAME_BUCKETS:
            summary[bucket_name] += item.get(bucket_name, 0)

        summary["Numbers"] += item.get("Numbers", 0)

    return summary
