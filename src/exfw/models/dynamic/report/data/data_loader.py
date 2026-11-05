from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .data_models import DynamicReportTask


def load_session_result(task_dir: str | Path) -> dict[str, Any]:
    """读取单个 pytest 子任务目录下的 session_result.json。"""

    task_path = Path(task_dir)
    session_file = task_path / "session_result.json"

    if not session_file.is_file():
        raise FileNotFoundError(f"未找到 session_result.json：{session_file}")

    with session_file.open("r", encoding="utf-8") as file:
        session_data = json.load(file)

    if not isinstance(session_data, dict):
        raise TypeError(f"session_result.json 格式异常，根节点必须是对象：{session_file}")

    return session_data


def load_task_result(runner_output_dir: str | Path) -> dict[str, Any]:
    """读取 dynamic runner 输出目录下的 task_result.json。"""

    runner_output_path = Path(runner_output_dir)
    runner_result_file = runner_output_path / "task_result.json"

    if not runner_result_file.is_file():
        raise FileNotFoundError(
            f"未找到 task_result.json，请传入 dynamic runner 输出目录：{runner_result_file}"
        )

    with runner_result_file.open("r", encoding="utf-8") as file:
        runner_result = json.load(file)

    if not isinstance(runner_result, dict):
        raise TypeError("task_result.json 格式异常，根节点必须是对象。")

    return runner_result


def load_main_device_info(task_dir: str | Path) -> dict[str, Any]:
    """读取单个 pytest 子任务目录下的 main_device_info.json。"""

    device_info_file = Path(task_dir) / "main_device_info.json"

    if not device_info_file.is_file():
        return {}

    try:
        with device_info_file.open("r", encoding="utf-8") as file:
            device_info = json.load(file)

        return device_info if isinstance(device_info, dict) else {}

    except (OSError, json.JSONDecodeError):
        return {}


def normalize_serial_filter(serial: str | list[str] | tuple[str, ...] | None) -> set[str] | None:
    """规范化报告设备筛选条件。"""

    if serial is None:
        return None

    if isinstance(serial, str):
        return {serial} if serial else None

    serials = {item for item in serial if isinstance(item, str) and item}
    return serials or None


def discover_runner_report_tasks(
    runner_output_dir: str | Path,
    runner_result: dict[str, Any],
    serial_filter: set[str] | None = None,
    *, require_task_id: bool = True,
) -> list[DynamicReportTask]:
    """从 runner_result 中发现需要参与报告生成的 pytest 子任务。"""

    runner_output_path = Path(runner_output_dir)
    old_runner_output_path = _get_old_runner_output_path(runner_result)
    raw_tasks = runner_result.get("tasks") or []

    if not isinstance(raw_tasks, list):
        raise TypeError("task_result.json 中 tasks 必须是列表。")

    report_tasks: list[DynamicReportTask] = []

    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            continue

        output_dir_value = raw_task.get("output_dir")
        if not isinstance(output_dir_value, str) or not output_dir_value:
            continue

        task_dir = _resolve_runner_task_path(
            path_value=output_dir_value,
            runner_output_path=runner_output_path,
            old_runner_output_path=old_runner_output_path,
        )

        device_info = load_main_device_info(task_dir)
        main_serial = device_info.get("serial") or raw_task.get("main_serial")

        if serial_filter is not None and main_serial not in serial_filter:
            continue

        try:
            session_data = load_session_result(task_dir)
        except (OSError, ValueError, TypeError):
            continue
        task_id = session_data.get("extensions", {}).get("dynamic_model", {}).get(
            "task_id"
        )

        if require_task_id and (not isinstance(task_id, str) or not task_id):
            continue

        report_tasks.append(
            DynamicReportTask(
                task_dir=task_dir,
                task_id=task_id,
                main_serial=main_serial if isinstance(main_serial, str) else None,
                session_data=session_data,
                device_info=device_info,
                runner_task=raw_task,
            )
        )

    return report_tasks


def _get_old_runner_output_path(runner_result: dict[str, Any]) -> Path | None:
    """从旧 runner_result 中获取原始输出根目录，用于移动结果目录后的路径重映射。"""

    output_dir = runner_result.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir:
        return None

    path = Path(output_dir)
    return path if path.is_absolute() else None


def _resolve_runner_task_path(
    *,
    path_value: str,
    runner_output_path: Path,
    old_runner_output_path: Path | None,
) -> Path:
    """解析 runner task 路径。

    新 runner_result 使用相对路径，直接基于当前 --task-dir 解析。
    旧 runner_result 可能保存绝对路径；若原路径已不存在，则尝试按旧 runner 根目录
    映射到当前 --task-dir，保证结果目录整体移动后仍可生成报告。
    """

    task_path = Path(path_value)

    if not task_path.is_absolute():
        return runner_output_path / task_path

    if task_path.exists():
        return task_path

    if old_runner_output_path is not None:
        try:
            relative_path = task_path.relative_to(old_runner_output_path)
        except ValueError:
            pass
        else:
            return runner_output_path / relative_path

    return task_path


def iter_session_cases(session_data: dict[str, Any]):
    """展开 session 的轮次和用例；产物路径始终相对设备子任务目录。"""
    for round_data in session_data.get("rounds", []):
        if not isinstance(round_data, dict):
            continue
        for case in round_data.get("cases", []):
            if not isinstance(case, dict):
                continue
            artifacts = case.get("artifacts") or {}
            yield {**case, "round": round_data.get("round"), "artifact_dir": artifacts.get("case_dir")}


def load_all_case_records(task_dir: str | Path, session_data: dict[str, Any], serial: str | None = None, rounds: int | None = None) -> list[dict[str, Any]]:
    """从 session 结果读取用例时间线。"""
    records = []
    for case in iter_session_cases(session_data):
        if rounds is not None and case.get("round") != rounds:
            continue
        started, stopped = case.get("started_at"), case.get("stopped_at")
        if not isinstance(started, (int, float)) or not isinstance(stopped, (int, float)):
            continue
        steps = [{"index": step.get("index"), "description": step.get("description", ""), "timestamp": step["timestamp"]} for step in case.get("steps", []) if isinstance(step, dict) and isinstance(step.get("timestamp"), (int, float))]
        steps.sort(key=lambda item: item["timestamp"])
        records.append({"serial": serial, "round": case.get("round"), "case": case.get("case_name"), "case_id": case.get("case_id"), "nodeid": case.get("nodeid"), "started_at": started, "stopped_at": stopped, "steps": steps})
    return sorted(records, key=lambda item: (str(item.get("serial") or ""), item.get("round") or 0, item.get("started_at") or 0))


def load_all_trace_records(task_dir: str | Path, session_data: dict[str, Any], serial: str | None = None, rounds: int | None = None) -> list[dict[str, Any]]:
    """从动态模型用例扩展读取 Trace 元数据。"""
    records = []
    for case in iter_session_cases(session_data):
        if rounds is not None and case.get("round") != rounds:
            continue
        dynamic = (case.get("extensions") or {}).get("dynamic_model") or {}
        for trace in dynamic.get("traces", []):
            if not isinstance(trace, dict):
                continue
            records.append({"serial": serial, "round": case.get("round"), "case": case.get("case_name"), "case_id": case.get("case_id"), "nodeid": case.get("nodeid"), "trace_name": trace.get("name"), "trace_path": trace.get("path"), "description": trace.get("description", ""), "start_time": trace.get("start_time"), "end_time": trace.get("end_time"), "duration_seconds": trace.get("duration_seconds"), "time_source": trace.get("time_source")})
    return sorted(records, key=lambda item: (str(item.get("serial") or ""), item.get("round") or 0, str(item.get("case") or ""), item.get("start_time") or 0))
