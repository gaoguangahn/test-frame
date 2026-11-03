from pathlib import Path

import pytest

from exfw.models.dynamic.report.bd_jank.archive import archive_jank_traces
from exfw.models.dynamic.report.bd_jank.selection import JankCase, select_jank_cases
from exfw.models.dynamic.report.data.data_models import DynamicReportTask


def _task(root: Path, serial: str) -> DynamicReportTask:
    root.mkdir()
    cases = []
    for number in (1, 2):
        relative = f"round_{number:03d}/test_demo__hash"
        traces = root / relative / "traces"
        traces.mkdir(parents=True)
        for name in ("demo_AppSwipe1.pftrace", "demo_AppSwipe2.pftrace", "demo_AppLaunch1.pftrace", "demo_AppExit1.pftrace", "demo_AppClick1.pftrace"):
            (traces / name).write_text(f"{serial}-{number}-{name}")
        cases.append({"round": number, "case_name": "test_demo", "artifact_dir": relative})
    return DynamicReportTask(root, "task", serial, {"cases": cases}, {}, {})


def test_selection_matches_summary_and_round():
    rows = [{"serial": "A", "round": 1, "case": "test_demo", "result": {
        "parse_fluency_fling_jank": {"data": [{"Counts": [3, 1, 0]}]},
        "parse_animation_jank": {"data": [{"Type": "HOME_TO_APP_ANIMATION", "Counts": [1, 0, 1]}, {"Type": "OTHER", "Counts": [0, 9]}]},
    }}, {"serial": "A", "round": 2, "case": "test_demo", "result": {
        "parse_fluency_fling_jank": {"data": [{"Counts": [10, 0]}]},
    }}]
    assert select_jank_cases(rows, 1) == {JankCase("A", 1, "test_demo", "fluency"), JankCase("A", 1, "test_demo", "animator")}
    assert select_jank_cases(rows, 2) == set()


def test_regeneration_replaces_only_selected_device(tmp_path):
    task_a, task_b = _task(tmp_path / "A", "A"), _task(tmp_path / "B", "B")
    archive_jank_traces([task_a, task_b], {JankCase("A", 1, "test_demo", "fluency"), JankCase("B", 1, "test_demo", "animator")})
    assert len(list((task_a.task_dir / "bd_jank/fluency").glob("*.pftrace"))) == 2
    assert len(list((task_b.task_dir / "bd_jank/animator").glob("*.pftrace"))) == 2
    archive_jank_traces([task_a], {JankCase("A", 2, "test_demo", "animator")})
    assert not list((task_a.task_dir / "bd_jank/fluency").iterdir())
    assert all(p.name.startswith("loop2_") for p in (task_a.task_dir / "bd_jank/animator").iterdir())
    assert len(list((task_b.task_dir / "bd_jank/animator").iterdir())) == 2


def test_copy_error_preserves_previous_archive(tmp_path, monkeypatch):
    task = _task(tmp_path / "A", "A")
    selection = {JankCase("A", 1, "test_demo", "fluency")}
    archive_jank_traces([task], selection)
    old = sorted(p.name for p in (task.task_dir / "bd_jank/fluency").iterdir())
    def fail(*args, **kwargs):
        raise OSError("copy failed")
    monkeypatch.setattr("exfw.models.dynamic.report.bd_jank.archive.shutil.copy2", fail)
    with pytest.raises(OSError):
        archive_jank_traces([task], selection)
    assert sorted(p.name for p in (task.task_dir / "bd_jank/fluency").iterdir()) == old
