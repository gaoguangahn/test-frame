"""验证动态模型离线解析落盘和上传状态，不依赖设备或内网。"""
import json
import subprocess
import sys
from types import SimpleNamespace

from exfw.models.dynamic.capture.profile import load_capture_profile
from exfw.models.dynamic.analyse.profile import load_analysis_profile
from exfw.models.dynamic.result.processor import DynamicResultProcessor
from exfw.pytest_framework.result.store import SessionResultStore
from exfw.models.dynamic.report.data.local_results import load_local_results
from exfw.models.dynamic.report.data.data_models import DynamicReportTask
from exfw.models.dynamic.report.data.report_dataset import build_report_dataset
from exfw.models.dynamic.report.report_generate import ReportGenerator


def test_profiles_keep_existing_capture_and_parser_defaults():
    capture = load_capture_profile()
    assert capture.round_start == ("jank_log", "events_log", "adb_log", "dmesg_log")
    assert capture.case_start == ("io_stat", "proc_memory", "radar")
    analysis = load_analysis_profile()
    assert analysis.trace["AppLaunch"] == [{"metric": "startup_transition"}]
    assert "parse_fluency_fling_jank" in analysis.log["actionstats"]


def make_store(tmp_path):
    return SessionResultStore(SimpleNamespace(output_dir=tmp_path, testbed_name=None, config_path=tmp_path / "project.yaml", artifact_layout="plain", device_specs=()))


def test_offline_analysis_saved_without_creating_uploader(tmp_path):
    store = make_store(tmp_path)
    reporter = DynamicResultProcessor(tmp_path, store, upload_enabled=False, local_run_id="offline-1")
    reporter._analysis.parse = lambda *args: ([{"success": True, "data": {"metric": 1}}], [])
    reporter.submit_case_result({"task_id": None, "round": 1, "case": "test_a", "case_id": "a", "nodeid": "test_a"}, log_path=tmp_path / "logs", trace_path=tmp_path / "traces")
    reporter.shutdown()
    result = json.loads((tmp_path / "parsed_results.json").read_text(encoding="utf-8"))
    status = json.loads((tmp_path / "session_result.json").read_text(encoding="utf-8"))["rounds"][0]["cases"][0]["extensions"]["dynamic_model"]
    assert result["local_run_id"] == "offline-1"
    assert result["rounds"][0]["cases"][0]["log_results"][0]["success"] is True
    assert status["analysis"]["status"] == "completed"
    assert status["upload"]["status"] == "disabled"
    assert reporter.summary()["upload"] == {"disabled": 1}


def test_upload_failure_recorded_without_losing_local_result(tmp_path):
    reporter = DynamicResultProcessor(tmp_path, make_store(tmp_path), upload_enabled=False)
    reporter._analysis.parse = lambda *args: ([{"success": False, "error": "parse failed"}], [{"success": True}])

    class FailedUpload:
        def submit(self, payload, on_success, on_failure):
            assert (tmp_path / "parsed_results.json").is_file()
            on_failure(None, TimeoutError("offline"))

        def close(self):
            pass

    reporter._upload = FailedUpload()
    reporter.submit_case_result({"task_id": "server-id", "round": 1, "case": "test_b", "case_id": "b", "nodeid": "test_b"}, log_path=tmp_path / "logs", trace_path=None)
    reporter.shutdown()
    status = json.loads((tmp_path / "session_result.json").read_text(encoding="utf-8"))["rounds"][0]["cases"][0]["extensions"]["dynamic_model"]
    assert status["analysis"]["status"] == "partial"
    assert status["upload"]["status"] == "failed"
    assert "offline" in status["upload"]["error"]


def test_local_report_loads_only_selected_round_without_server_id(tmp_path):
    parsed = {"rounds": [{"round": r, "round_logs": [{"success": True}], "cases": [{"case_id": "a", "nodeid": "test_a", "case_name": "test_a", "log_results": [], "trace_results": []}]} for r in (1, 2)]}
    (tmp_path / "parsed_results.json").write_text(json.dumps(parsed), encoding="utf-8")
    session = {"artifact_layout": "round", "rounds": [{"round": r, "cases": [{"case_id": "a", "nodeid": "test_a", "artifacts": {"case_dir": f"round_{r:03d}/test_a"}}]} for r in (1, 2)]}
    task = DynamicReportTask(tmp_path, None, "SN", session, {}, {})
    results = load_local_results(task, 2)
    assert {item["case"] for item in results} == {"test_a", "__round_logs__"}
    assert {item["round"] for item in results} == {2}


def test_pytest_session_waits_for_offline_result_before_summary(tmp_path):
    (tmp_path / "project.yaml").write_text("runtime:\n  resources_dir: .\ntest_models:\n  dynamic_model:\n    upload:\n      enabled: false\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text('''
import pytest
pytest_plugins = ["exfw.pytest_framework.plugin", "exfw.models.dynamic.dynamic_pytest.plugin"]
@pytest.fixture(scope="session", autouse=True)
def dynamic_main_device_info(): pass
@pytest.fixture(autouse=True)
def dynamic_pre_case_recovery(): pass
@pytest.fixture(autouse=True)
def dynamic_case_capture(request, case_artifacts, dynamic_case_result_reporter):
    yield
    dynamic_case_result_reporter._analysis.parse = lambda *args: ([{"success": True, "data": {}}], [])
    dynamic_case_result_reporter.submit_case_result(
        {"task_id": None, "serial": "fake", "round": 1, "case": "test_ok", "case_id": case_artifacts.case_id, "nodeid": request.node.nodeid},
        log_path=case_artifacts.case_dir / "logs", trace_path=None,
    )
''', encoding="utf-8")
    (tmp_path / "test_case.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    output = tmp_path / "out" / "debug"
    process = subprocess.run([sys.executable, "-m", "pytest", str(tmp_path / "test_case.py"), "-q", "-p", "no:cacheprovider", "--project-config", str(tmp_path / "project.yaml"), "--output-dir", str(output.parent)], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
    session = json.loads((output / "session_result.json").read_text(encoding="utf-8"))
    dynamic = session["extensions"]["dynamic_model"]
    assert dynamic["task_id"] is None and dynamic["local_run_id"]
    assert dynamic["processing"]["analysis"] == {"completed": 1}
    assert dynamic["processing"]["upload"] == {"disabled": 1}
    assert (output / "parsed_results.json").is_file()
    assert session["rounds"][0]["cases"][0]["extensions"]["dynamic_model"]["analysis"]["status"] == "completed"
    runner = {"output_dir": ".", "summary": {"total": 1, "passed": 1, "failed": 0}, "tasks": [{"output_dir": "out/debug", "main_serial": "fake"}]}
    (tmp_path / "task_result.json").write_text(json.dumps(runner), encoding="utf-8")
    dataset = build_report_dataset(runner_output_dir=str(tmp_path), source="local")
    assert len(dataset.case_results) == 1
    assert dataset.case_results[0]["case"] == "test_ok"
    reporter = ReportGenerator()
    reporter.load_report_data(str(tmp_path), source="local")
    reporter.generate_report(tmp_path / "report.xlsx")
    assert (tmp_path / "report.xlsx").is_file()


def test_common_base_does_not_initialize_capture_without_use(tmp_path):
    (tmp_path / "project.yaml").write_text("runtime:\n  resources_dir: .\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text('pytest_plugins = ["exfw.pytest_framework.plugin"]\n', encoding="utf-8")
    (tmp_path / "test_base.py").write_text('''
from exfw.pytest_framework import BaseTestCase
class TestPlain(BaseTestCase):
    def test_no_capture(self, pytestconfig):
        assert not hasattr(self, "logcat_manager")
        assert not hasattr(self, "trace_collector")
        assert not pytestconfig.pluginmanager.hasplugin("exfw.pytest_framework.fixtures.capture")
''', encoding="utf-8")
    process = subprocess.run([sys.executable, "-m", "pytest", str(tmp_path / "test_base.py"), "-q", "-p", "no:cacheprovider", "--project-config", str(tmp_path / "project.yaml"), "--output-dir", str(tmp_path / "out")], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr


def test_dynamic_case_injects_model_owned_shared_tracer(tmp_path):
    (tmp_path / "project.yaml").write_text("runtime:\n  resources_dir: .\ntest_models:\n  dynamic_model:\n    upload:\n      enabled: false\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text('''
from types import SimpleNamespace
import pytest
pytest_plugins = ["exfw.pytest_framework.plugin", "exfw.models.dynamic.dynamic_pytest.plugin"]
@pytest.fixture(scope="session")
def devices(): return {"main": SimpleNamespace(serial="fake", model="fake")}
@pytest.fixture(scope="session", autouse=True)
def dynamic_main_device_info(): pass
@pytest.fixture(autouse=True)
def dynamic_case_capture(): pass
''', encoding="utf-8")
    (tmp_path / "test_case.py").write_text('''
from exfw.models.dynamic import DynamicCase
class TestDynamic(DynamicCase):
    def test_tracer(self, dynamic_capture_service):
        assert self.tracer._collector is dynamic_capture_service._trace_collector
        assert self.tracer.build_trace_name("AppSwipe1") == "tracer_loop1_AppSwipe1"
''', encoding="utf-8")
    process = subprocess.run([sys.executable, "-m", "pytest", str(tmp_path / "test_case.py"), "-q", "-p", "no:cacheprovider", "--project-config", str(tmp_path / "project.yaml"), "--output-dir", str(tmp_path / "out")], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
