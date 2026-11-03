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


def load_runner_result(runner_output_dir: str | Path) -> dict[str, Any]:
    """读取 dynamic runner 输出目录下的 runner_result.json。"""

    runner_output_path = Path(runner_output_dir)
    runner_result_file = runner_output_path / "runner_result.json"

    if not runner_result_file.is_file():
        raise FileNotFoundError(
            f"未找到 runner_result.json，请传入 dynamic runner 输出目录：{runner_result_file}"
        )

    with runner_result_file.open("r", encoding="utf-8") as file:
        runner_result = json.load(file)

    if not isinstance(runner_result, dict):
        raise TypeError("runner_result.json 格式异常，根节点必须是对象。")

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
) -> list[DynamicReportTask]:
    """从 runner_result 中发现需要参与报告生成的 pytest 子任务。"""

    runner_output_path = Path(runner_output_dir)
    old_runner_output_path = _get_old_runner_output_path(runner_result)
    raw_tasks = runner_result.get("tasks") or []

    if not isinstance(raw_tasks, list):
        raise TypeError("runner_result.json 中 tasks 必须是列表。")

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

        session_data = load_session_result(task_dir)
        task_id = session_data.get("extensions", {}).get("dynamic_model", {}).get(
            "task_id"
        )

        if not isinstance(task_id, str) or not task_id:
            raise ValueError(
                f"子任务 session_result.json 中未找到 extensions.dynamic_model.task_id：{task_dir}"
            )

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


def load_all_case_records(
    task_dir: str | Path,
    session_data: dict[str, Any],
    serial: str | None = None,
    rounds: int | None = None,
) -> list[dict[str, Any]]:
    """读取单个 pytest 子任务中所有用例 result.json 的用例/步骤时间线。"""

    task_path = Path(task_dir)
    case_records: list[dict[str, Any]] = []

    for case in session_data.get("cases", []):
        if not isinstance(case, dict):
            continue

        case_round = case.get("round")
        if rounds is not None and case_round != rounds:
            continue

        result_path_value = case.get("result_path")
        artifact_dir = case.get("artifact_dir")

        if result_path_value:
            result_file = task_path / Path(str(result_path_value).replace("\\", "/"))
        elif artifact_dir:
            result_file = (
                task_path / Path(str(artifact_dir).replace("\\", "/")) / "result.json"
            )
        else:
            print("用例缺少 result_path/artifact_dir，跳过用例时间线读取：case_id=%s", case.get("case_id"))
            continue

        if not result_file.is_file():
            print("未找到用例结果文件，跳过用例时间线读取：case_id=%s, file=%s", case.get("case_id"), result_file)
            continue

        try:
            with result_file.open("r", encoding="utf-8") as file:
                result_data = json.load(file)
        except (OSError, json.JSONDecodeError):
            print("读取用例结果文件失败：case_id=%s, file=%s", case.get("case_id"), result_file)
            continue

        if not isinstance(result_data, dict):
            print("用例结果文件格式异常，根节点必须为对象：%s", result_file)
            continue

        started_at = result_data.get("started_at")
        stopped_at = result_data.get("stopped_at")
        case_name = result_data.get("case_name") or case.get("case_name")
        steps = result_data.get("steps") or []

        if not case_name or not isinstance(started_at, (int, float)) or not isinstance(stopped_at, (int, float)):
            continue

        normalized_steps = []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue

                timestamp = step.get("timestamp")
                if not isinstance(timestamp, (int, float)):
                    continue

                normalized_steps.append(
                    {
                        "index": step.get("index"),
                        "description": step.get("description", ""),
                        "timestamp": timestamp,
                    }
                )

        normalized_steps.sort(key=lambda item: item.get("timestamp") or 0)

        case_records.append(
            {
                "serial": serial,
                "round": case_round,
                "case": case_name,
                "started_at": started_at,
                "stopped_at": stopped_at,
                "steps": normalized_steps,
            }
        )

    case_records.sort(
        key=lambda item: (
            str(item.get("serial") or ""),
            item.get("round") if item.get("round") is not None else -1,
            item.get("started_at") or 0,
        )
    )

    return case_records


def load_all_trace_records(
    task_dir: str | Path,
    session_data: dict[str, Any],
    serial: str | None = None,
    rounds: int | None = None,
) -> list[dict[str, Any]]:
    """
    汇总单个 pytest 子任务中所有用例的 traces/trace_records.json。

    返回报告需要的轻量 trace 采集记录列表，并在读取时补齐 serial / round / case，
    方便后续通过 serial + round + case + trace_name 与 API trace_result 对应，
    或通过 serial + round + case + 时间范围与 log_result 对应。
    """

    task_path = Path(task_dir)
    all_traces: list[dict[str, Any]] = []

    for case in session_data.get("cases", []):
        if not isinstance(case, dict):
            continue

        case_round = case.get("round")

        if rounds is not None and case_round != rounds:
            continue

        artifact_dir = case.get("artifact_dir")
        if not artifact_dir:
            print("用例缺少 artifact_dir，跳过 Trace 记录读取：case_id=%s", case.get("case_id"))
            continue

        artifact_path = task_path / Path(str(artifact_dir).replace("\\", "/"))
        trace_records_file = artifact_path / "traces" / "trace_records.json"

        if not trace_records_file.is_file():
            print("未找到用例 Trace 记录文件，跳过：case_id=%s, file=%s", case.get("case_id"), trace_records_file)
            continue

        try:
            with trace_records_file.open("r", encoding="utf-8") as file:
                trace_record_data = json.load(file)

        except (OSError, json.JSONDecodeError):
            print("读取 Trace 记录文件失败：case_id=%s, file=%s", case.get("case_id"), trace_records_file)
            continue

        if not isinstance(trace_record_data, dict):
            print("Trace 记录文件格式异常，根节点必须为对象：%s", trace_records_file)
            continue

        traces = trace_record_data.get("traces", [])

        if not isinstance(traces, list):
            print("Trace 记录文件格式异常，traces 必须为列表：%s", trace_records_file)
            continue

        case_name = case.get("case_name")

        for trace in traces:
            if not isinstance(trace, dict):
                continue

            trace_serial = trace.get("serial") or serial

            if serial is not None and trace_serial != serial:
                continue

            trace_path = trace.get("trace_path", "")
            trace_name = trace.get("trace_name") or Path(str(trace_path)).name

            all_traces.append(
                {
                    "serial": trace_serial,
                    "round": case_round,
                    "case": case_name,
                    "trace_name": trace_name,
                    "trace_path": trace_path,
                    "description": trace.get("description", ""),
                    "start_time": trace.get("start_time"),
                    "end_time": trace.get("end_time"),
                    "duration_seconds": trace.get("duration_seconds"),
                    "time_source": trace.get("time_source") or trace_record_data.get("time_source"),
                }
            )

    all_traces.sort(
        key=lambda item: (
            str(item.get("serial") or ""),
            item.get("round") if item.get("round") is not None else -1,
            str(item.get("case") or ""),
            item.get("start_time") or 0,
        )
    )

    return all_traces
