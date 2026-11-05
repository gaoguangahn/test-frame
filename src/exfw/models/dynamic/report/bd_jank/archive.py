"""将发生 BD 卡顿的用例所采集的同类 Trace 复制到设备目录。"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import uuid
from pathlib import Path

from exfw.pytest_framework.core.path import safe_path_name
from ..data.data_models import DynamicReportTask
from ..data.data_loader import iter_session_cases
from .selection import JankCase


def archive_jank_traces(tasks: list[DynamicReportTask], cases: set[JankCase]) -> None:
    for task in tasks:
        matching = {case for case in cases if case.serial == task.main_serial}
        _archive_device(task, matching)


def _archive_device(task: DynamicReportTask, selected: set[JankCase]) -> None:
    root = task.task_dir.resolve()
    destination = root / "bd_jank"
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError(f"BD 归档目标不是普通目录：{destination}")

    stage = Path(tempfile.mkdtemp(prefix=".bd_jank_staging_", dir=root))
    backup = root / f".bd_jank_backup_{uuid.uuid4().hex}"
    copied = 0
    missing: list[str] = []
    try:
        for category in ("fluency", "animator"):
            (stage / category).mkdir()
        index: dict[tuple[int, str], list[dict]] = {}
        for case in iter_session_cases(task.session_data):
            if isinstance(case, dict):
                index.setdefault((case.get("round"), case.get("case_name")), []).append(case)
        for item in sorted(selected, key=lambda x: (x.round, x.case, x.category)):
            matches = index.get((item.round, item.case), [])
            if item.case_id:
                matches = [case for case in matches if case.get("case_id") == item.case_id]
            if len(matches) != 1:
                missing.append(f"round={item.round} case={item.case} category={item.category}：匹配到 {len(matches)} 个用例")
                continue
            relative = matches[0].get("artifact_dir")
            if not isinstance(relative, str) or not relative:
                missing.append(f"round={item.round} case={item.case}：缺少产物目录")
                continue
            case_dir = (root / Path(relative.replace("\\", "/"))).resolve()
            if not case_dir.is_relative_to(root):
                raise ValueError(f"用例产物路径不在设备目录中：{case_dir}")
            traces_dir = case_dir / "traces"
            patterns = ("appswipe",) if item.category == "fluency" else ("applaunch", "appexit")
            traces = sorted(p for p in traces_dir.iterdir() if p.is_file() and p.suffix.lower() in (".pftrace", ".trace") and any(pattern in p.stem.lower() for pattern in patterns)) if traces_dir.is_dir() else []
            if not traces:
                missing.append(f"round={item.round} case={item.case} category={item.category}：未找到 Trace")
            for trace in traces:
                target = stage / item.category / trace.name
                if target.exists():
                    stem = safe_path_name(trace.stem, max_length=180)
                    digest = hashlib.sha256(str(trace).encode("utf-8")).hexdigest()[:10]
                    target = stage / item.category / f"{stem}_{digest}{trace.suffix}"
                    if target.exists():
                        raise FileExistsError(f"归档文件名冲突：{target}")
                shutil.copy2(trace, target)
                copied += 1

        had_old = destination.exists()
        if had_old:
            destination.rename(backup)
        try:
            stage.rename(destination)
        except Exception:
            if had_old:
                backup.rename(destination)
            raise
        if had_old:
            shutil.rmtree(backup)
        print(f"[BD卡顿] 设备 {task.main_serial}：复制 {copied} 个 Trace，未匹配 {len(missing)} 项，目录={destination}")
        for message in missing:
            print(f"[BD卡顿] {task.main_serial} {message}")
    finally:
        if stage.exists():
            shutil.rmtree(stage)
