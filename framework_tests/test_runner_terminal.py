"""动态 runner 的进度事件、回退输出与设备汇总。"""
import io
import json
import os
import subprocess
import sys
from types import SimpleNamespace

from exfw.models.dynamic.runner.terminal import DeviceProgress, Terminal


def test_events_count_rounds_and_noninteractive_output():
    stream = io.StringIO()
    terminal = Terminal([SimpleNamespace(main_serial="A"), SimpleNamespace(main_serial="B")], stream)
    terminal.event("A", {"event": "collected", "total": 4})
    terminal.event("A", {"event": "start", "round": 1, "nodeid": "test_a"})
    terminal.event("A", {"event": "finish", "round": 1, "nodeid": "test_a", "outcome": "FAILED"})
    terminal.event("B", {"event": "collected", "total": 2})
    terminal.event("B", {"event": "finish", "round": 1, "nodeid": "test_b", "outcome": "SKIPPED"})
    assert terminal.states["A"].completed == 1 and terminal.states["A"].failed == 1
    assert terminal.states["B"].skipped == 1
    assert "[A] round 1 | test_a | FAILED" in stream.getvalue()
    assert "\x1b[" not in stream.getvalue()


def test_summary_uses_session_failures_and_shows_abnormal_exit(tmp_path):
    stream = io.StringIO()
    terminal = Terminal([SimpleNamespace(main_serial="A"), SimpleNamespace(main_serial="B")], stream)
    (tmp_path / "A").mkdir()
    (tmp_path / "A" / "session_result.json").write_text(json.dumps({
        "summary": {"passed": 2, "failed": 1, "skipped": 0},
        "rounds": [{"round": 2, "cases": [{"outcome": "failed", "nodeid": "tests/test_a.py::test_a"}]}],
        "extensions": {"dynamic_model": {"processing": {"upload": {"failed": 1}}}},
    }), encoding="utf-8")
    terminal.summary([{"main_serial": "A", "output_dir": "A", "exit_code": 1},
                      {"main_serial": "B", "output_dir": "B", "exit_code": 2}], tmp_path)
    text = stream.getvalue()
    assert "第 2 轮  tests/test_a.py::test_a" in text
    assert "upload 处理异常" in text
    assert "设备 B  无法读取 session 结果" in text
    assert "pytest 任务退出状态: 2" in text


def test_pytest_events_and_native_failure_report(tmp_path):
    (tmp_path / "project.yaml").write_text("runtime:\n  resources_dir: .\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text('pytest_plugins = ["exfw.pytest_framework.plugin"]\n', encoding="utf-8")
    (tmp_path / "test_example.py").write_text('def test_ok(): pass\ndef test_bad(): assert False\n', encoding="utf-8")
    output = tmp_path / "output"
    events_file = tmp_path / "events.jsonl"
    env = dict(os.environ, EXFW_PROGRESS_FILE=str(events_file), EXFW_RUNNER_MODE="1", EXFW_SESSION_OUTPUT=str(output))
    cmd = [sys.executable, "-m", "pytest", "-p", "exfw.models.dynamic.dynamic_pytest.progress_events",
           str(tmp_path / "test_example.py"), "-q", "-p", "no:cacheprovider", "--rounds", "2",
           "--project-config", str(tmp_path / "project.yaml"), "--output-dir", str(output)]
    proc = subprocess.run(cmd, cwd=tmp_path, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=30)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
    assert next(e for e in events if e["event"] == "collected")["total"] == 4
    assert [e["outcome"] for e in events if e["event"] == "finish"] == ["PASSED", "FAILED", "PASSED", "FAILED"]
    assert "test_example.py" in proc.stdout and "AssertionError" in proc.stdout
    session = json.loads((output / "session_result.json").read_text(encoding="utf-8"))
    assert session["summary"]["failed"] == 2


def test_runner_two_subprocesses_and_final_failures(tmp_path):
    from exfw.models.dynamic.runner.config import DynamicRunnerConfig, DynamicRunnerTask
    from exfw.models.dynamic.runner.main import run_tasks
    (tmp_path / "project.yaml").write_text('''runtime:
  resources_dir: .
testbeds:
  one:
    devices: [{name: main, serial: A, driver: adb}]
  two:
    devices: [{name: main, serial: B, driver: adb}]
''', encoding="utf-8")
    (tmp_path / "conftest.py").write_text('pytest_plugins = ["exfw.pytest_framework.plugin"]\n', encoding="utf-8")
    (tmp_path / "test_case.py").write_text('def test_bad(): assert False\n', encoding="utf-8")
    out = tmp_path / 'out'
    config = DynamicRunnerConfig(tmp_path / 'project.yaml', tmp_path, tmp_path / 'test_case.py', out, 2)
    tasks = [DynamicRunnerTask('one', 'A', out / 'A'), DynamicRunnerTask('two', 'B', out / 'B')]
    terminal = Terminal(tasks, io.StringIO())
    results = run_tasks(runner_config=config, tasks=tasks, terminal=terminal)
    terminal.summary(results, out)
    assert all(item['exit_code'] == 1 for item in results)
    assert all(terminal.states[s].failed == 2 for s in ('A', 'B'))
    assert terminal.stream.getvalue().count('第 2 轮') == 2
    assert all((out / s / 'pytest-output.log').is_file() for s in ('A', 'B'))


def test_direct_pytest_keeps_native_output_and_optional_console_log(tmp_path):
    (tmp_path / "project.yaml").write_text("runtime:\n  resources_dir: .\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text('pytest_plugins = ["exfw.pytest_framework.plugin"]\n', encoding="utf-8")
    (tmp_path / "test_case.py").write_text('def test_bad(test_logger):\n    test_logger.warning("CASE_" + "DEBUG_MARKER")\n    assert False\n', encoding="utf-8")
    base = [sys.executable, "-m", "pytest", str(tmp_path / "test_case.py"), "-q", "-p", "no:cacheprovider", "--project-config", str(tmp_path / "project.yaml")]
    env = dict(os.environ)
    env.pop("EXFW_RUNNER_MODE", None)
    env.pop("EXFW_PROGRESS_FILE", None)
    normal = subprocess.run(base + ["--output-dir", str(tmp_path / "normal")], cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert normal.returncode == 1 and "AssertionError" in normal.stdout
    assert "| WARNING  |" not in normal.stdout + normal.stderr
    assert "CASE_DEBUG_MARKER" in (tmp_path / "normal" / "debug" / "execution.log").read_text(encoding="utf-8")
    assert "AssertionError" in (tmp_path / "normal" / "debug" / "pytest-output.log").read_text(encoding="utf-8")
    verbose = subprocess.run(base + ["--output-dir", str(tmp_path / "verbose"), "--exfw-console-log"], cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert verbose.returncode == 1
    assert "| WARNING  |" in verbose.stdout + verbose.stderr


def test_interactive_terminal_refreshes_without_losing_failures(monkeypatch):
    import exfw.models.dynamic.runner.terminal as terminal_module
    monkeypatch.setattr(terminal_module, "_supports_refresh", lambda stream: True)
    monkeypatch.setattr(terminal_module.shutil, "get_terminal_size", lambda fallback: os.terminal_size((160, 30)))
    stream = io.StringIO()
    terminal = Terminal([SimpleNamespace(main_serial="A")], stream)
    terminal.event("A", {"event": "collected", "total": 2})
    terminal.event("A", {"event": "start", "round": 1, "nodeid": "test_bad"})
    terminal.event("A", {"event": "finish", "round": 1, "nodeid": "test_bad", "outcome": "FAILED"})
    assert "50% 1/2" in stream.getvalue()
    assert "最近失败: A 第 1 轮 test_bad" in stream.getvalue()
    assert "\x1b[" in stream.getvalue()
