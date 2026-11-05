"""读取 runner 和每个 pytest session 的结果；设备缺失不影响其他设备。"""
from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class DeviceResult:
    serial: str
    testbed: str
    status: str
    directory: Path | None
    task: dict
    session: dict | None
    cases: list[dict] = field(default_factory=list)


@dataclass
class ExecutionData:
    root: Path
    task: dict
    devices: list[DeviceResult]


def load_execution_data(root: str | Path) -> ExecutionData:
    root = Path(root).expanduser().resolve()
    with (root / "task_result.json").open(encoding="utf-8") as stream:
        task = json.load(stream)
    if not isinstance(task, dict) or not isinstance(task.get("tasks"), list):
        raise ValueError("task_result.json 格式异常：tasks 必须是列表")
    devices = []
    for item in task["tasks"]:
        if not isinstance(item, dict):
            continue
        relative = item.get("output_dir")
        directory = None
        session = None
        if isinstance(relative, str) and relative:
            candidate = (root / Path(relative.replace("\\", "/"))).resolve()
            if candidate.is_relative_to(root):
                directory = candidate
                try:
                    with (directory / "session_result.json").open(encoding="utf-8") as stream:
                        data = json.load(stream)
                    if isinstance(data, dict):
                        session = data
                except (OSError, ValueError):
                    pass
        cases = []
        for group in (session or {}).get("rounds", []):
            if not isinstance(group, dict) or not isinstance(group.get("cases"), list):
                continue
            for case in group["cases"]:
                if isinstance(case, dict):
                    cases.append({**case, "round": group.get("round")})
        devices.append(DeviceResult(serial=str(item.get("main_serial") or "未知设备"),
                                    testbed=str(item.get("testbed") or "—"),
                                    status=str(item.get("status") or "unknown"),
                                    directory=directory, task=item, session=session, cases=cases))
    return ExecutionData(root=root, task=task, devices=devices)
