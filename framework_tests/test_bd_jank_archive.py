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
        for name in (f"demo_loop{number}_AppSwipe1.pftrace", f"demo_loop{number}_AppSwipe2.pftrace", f"demo_loop{number}_AppLaunch1.pftrace", f"demo_loop{number}_AppExit1.pftrace", f"demo_loop{number}_AppClick1.pftrace"):
            (traces / name).write_text(f"{serial}-{number}-{name}")
        cases.append({"round": number, "cases": [{"case_name": "test_demo", "artifacts": {"case_dir": relative}}]})
    return DynamicReportTask(root, "task", serial, {"rounds": cases}, {}, {})


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
    assert (task_a.task_dir / "bd_jank/fluency/demo_loop1_AppSwipe1.pftrace").is_file()
    assert len(list((task_b.task_dir / "bd_jank/animator").glob("*.pftrace"))) == 2
    archive_jank_traces([task_a], {JankCase("A", 2, "test_demo", "animator")})
    assert not list((task_a.task_dir / "bd_jank/fluency").iterdir())
    assert all("_loop2_" in p.name for p in (task_a.task_dir / "bd_jank/animator").iterdir())
    assert len(list((task_b.task_dir / "bd_jank/animator").iterdir())) == 2


def test_same_original_name_does_not_overwrite(tmp_path):
    task = _task(tmp_path / "A", "A")
    for number in (1, 2):
        traces = task.task_dir / f"round_{number:03d}/test_demo__hash/traces"
        (traces / f"demo_loop{number}_AppSwipe1.pftrace").rename(traces / "AppSwipe1.pftrace")
    archive_jank_traces([task], {JankCase("A", 1, "test_demo", "fluency"), JankCase("A", 2, "test_demo", "fluency")})
    copied = list((task.task_dir / "bd_jank/fluency").glob("AppSwipe1*.pftrace"))
    assert len(copied) == 2
    assert {p.read_text() for p in copied} == {"A-1-demo_loop1_AppSwipe1.pftrace", "A-2-demo_loop2_AppSwipe1.pftrace"}


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
