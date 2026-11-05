"""采集基础组件的失败与轮次清理不需要连接设备。"""

import subprocess
import sys
from types import SimpleNamespace

import pytest

from exfw.aw.logcat import CmdRunner
from exfw.pytest_framework.rounds.runner import RoundTaskRunner
from exfw.models.dynamic.capture.profile import CaptureProfile
from exfw.models.dynamic.capture.service import DynamicModelCaptureService


def test_failed_round_start_cleans_started_tasks_in_reverse_order():
    calls = []

    class Task:
        def __init__(self, name, fail=False):
            self.name, self.fail = name, fail

        def before_round(self, context):
            calls.append(f"start:{self.name}")
            if self.fail:
                raise RuntimeError("start failed")

        def after_round(self, context):
            calls.append(f"stop:{self.name}")

    runner = RoundTaskRunner([Task("one"), Task("two", fail=True), Task("three")])
    with pytest.raises(RuntimeError, match="start failed"):
        runner.before_round(SimpleNamespace(round_no=1))
    assert calls == ["start:one", "start:two", "stop:two", "stop:one"]


def test_command_start_failure_closes_file_and_propagates(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("cannot start")

    monkeypatch.setattr(subprocess, "Popen", fail)
    runner = CmdRunner(str(tmp_path / "output.log"), ["missing"], "test")
    with pytest.raises(OSError, match="cannot start"):
        runner.start()
    assert runner.file is None
    assert runner not in CmdRunner._procs


def test_command_rejects_second_start_and_closes_finished_process(tmp_path, monkeypatch):
    class Process:
        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Process())
    runner = CmdRunner(str(tmp_path / "output.log"), ["tool"], "test")
    runner.start()
    with pytest.raises(RuntimeError, match="已经启动"):
        runner.start()
    runner.stop()
    assert runner.proc is None and runner.file is None
    assert runner not in CmdRunner._procs


def test_dynamic_capture_keeps_order_and_records_missing_artifact(tmp_path):
    calls = []
    class Collector:
        def __init__(self, name):
            self.name = name
        def start(self, serial, context):
            calls.append(f"start:{self.name}")
            return str(tmp_path / self.name)
        def stop(self, serial, context):
            calls.append(f"stop:{self.name}")
            return None if self.name == "events_log" else str(tmp_path / self.name)
        def collect(self, serial, context):
            calls.append(f"collect:{self.name}")
            return str(tmp_path / self.name)
    class Manager:
        def get(self, name):
            return Collector(name)
    profile = CaptureProfile(("jank_log", "events_log"), ("dumpsys_meminfo",), (), ())
    service = DynamicModelCaptureService(Manager(), profile)
    service.start_round_capture(serial="SN", round_no=1, logs_dir=tmp_path / "logs")
    service.stop_round_capture(serial="SN", round_no=1)
    assert calls == ["start:jank_log", "start:events_log", "collect:dumpsys_meminfo", "stop:events_log", "stop:jank_log"]
    status = service.last_round_results[(1, "SN")]
    assert status["status"] == "partial"
    assert any(item["name"] == "events_log" and item["status"] == "failed" for item in status["items"])


def test_dynamic_tracer_and_case_collection_share_trace_instance(tmp_path):
    calls = []

    class Trace:
        def clean_device_traces(self, *, serial):
            calls.append(("clean", serial))
            return True

        def pull_trace_directory(self, *, serial, local_dir):
            calls.append(("pull", serial))
            return local_dir

        def completed_trace_records(self, serial):
            calls.append(("records", serial))
            return ()

        def acknowledge_trace_records(self, serial, records):
            calls.append(("ack", serial))

    trace = Trace()
    service = DynamicModelCaptureService(profile=CaptureProfile((), (), (), ()), trace_collector=trace)
    tracer = service.create_tracer(case_name="test_demo", round_no=1)
    assert tracer._collector is trace
    service.prepare_case(serial="SN", logs_dir=tmp_path / "logs")
    status, traces, snapshot = service.finish_case(serial="SN", logs_dir=tmp_path / "logs", traces_dir=tmp_path / "traces", root_dir=tmp_path, time_context=None)
    service.acknowledge_traces("SN", snapshot)
    assert traces == []
    assert [event[0] for event in calls] == ["clean", "pull", "records", "ack"]
    assert status["status"] == "completed"


def test_dynamic_capture_instances_do_not_share_collectors():
    first, second = DynamicModelCaptureService(), DynamicModelCaptureService()
    assert first._collectors.get("radar") is not second._collectors.get("radar")
    assert first._trace_collector is not second._trace_collector


def test_pytest_round_lifecycle_keeps_session_fixture_until_after_last_round(tmp_path):
    (tmp_path / "project.yaml").write_text("runtime:\n  resources_dir: .\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text('''
from pathlib import Path
import pytest
from exfw.pytest_framework.rounds.runner import get_or_create_round_task_runner
pytest_plugins = ["exfw.pytest_framework.plugin"]
def record(value):
    with Path("events.txt").open("a") as f: f.write(value + "\\n")
class Task:
    name = "test"
    def before_round(self, context): record(f"before:{context.round_no}")
    def after_round(self, context): record(f"after:{context.round_no}")
@pytest.hookimpl(trylast=True)
def pytest_configure(config): get_or_create_round_task_runner(config).add_task(Task())
@pytest.fixture(scope="session")
def resource():
    record("session:start")
    yield
    record("session:end")
@pytest.fixture
def per_case(resource):
    record("case:start")
    yield
    record("case:end")
''', encoding="utf-8")
    (tmp_path / "test_sample.py").write_text("def test_one(per_case): pass\n", encoding="utf-8")
    process = subprocess.run([sys.executable, "-m", "pytest", str(tmp_path / "test_sample.py"), "-q", "-p", "no:cacheprovider", "--project-config", str(tmp_path / "project.yaml"), "--output-dir", str(tmp_path / "out"), "--rounds", "2"], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
    assert (tmp_path / "events.txt").read_text().splitlines() == [
        "before:1", "session:start", "case:start", "case:end", "after:1",
        "before:2", "case:start", "case:end", "after:2", "session:end",
    ]
