from .trace_context import build_trace_record_index, lookup_trace_description, lookup_trace_record


def process_all_other_animator_data(control_center_data, multi_task_data, test_info=None):
    """处理通知栏/控制中心、多任务等其他动效数据。"""

    trace_record_index = build_trace_record_index(test_info)

    control_center_rows = _process_records(
        records=control_center_data,
        default_scene="通知栏/控制中心",
        trace_record_index=trace_record_index,
    )
    multi_task_rows = _process_records(
        records=multi_task_data,
        default_scene="上滑多任务",
        trace_record_index=trace_record_index,
    )

    return {
        "sheets_data": {
            "detail": control_center_rows + multi_task_rows,
        },
        "summary_data": {},
    }


def _process_records(records, default_scene, trace_record_index):
    """处理单类其他动效记录。"""

    detail_rows = []

    for record in filter(None, records):
        fps = record.get("animator_fps")
        frames = record.get("animation_frames")

        # 防止 fps 为 0/None 导致除零，防止 frames 为空导致 len/sum 异常。
        if not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0:
            continue
        if not isinstance(frames, list) or not frames:
            continue

        frame_interval = round(1000 / fps, 2)
        jank_time = sum(
            max(frame - frame_interval, 0)
            for frame in frames
            if isinstance(frame, (int, float)) and not isinstance(frame, bool)
        )

        trace_record = lookup_trace_record(record, trace_record_index)
        scene = lookup_trace_description(record, trace_record_index) or default_scene

        detail_rows.append(
            {
                "SN": record.get("serial") or record.get("sn") or "-",
                "Loop": record.get("round") or record.get("loop") or "-",
                "Case": record.get("case") or record.get("case_name") or "UNKNOWN",
                "Scene": scene,
                "Trace": record.get("trace_name", "-"),
                "StartTime": _get_trace_start_time(record, trace_record),
                "Operation": scene,
                "VsyncFps": fps,
                "JankTime": round(jank_time, 2),
                "FrameCounts": len(frames),
                "Frames": str(frames),
            }
        )

    return detail_rows


def _get_trace_start_time(record, trace_record):
    """优先使用本地 trace_records 的 start_time，兜底使用解析结果中的 trace_start。"""

    if isinstance(trace_record, dict):
        start_time = trace_record.get("start_time")
        if start_time is not None:
            return start_time

    trace_start = record.get("trace_start")
    return trace_start if trace_start is not None else "-"
