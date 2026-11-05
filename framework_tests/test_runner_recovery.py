"""验证任务中断后的结果可读取以及报告对部分数据的处理。"""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from exfw.models.dynamic.runner.config import load_dynamic_runner_plan, DynamicRunnerConfig, DynamicRunnerTask
from exfw.models.dynamic.runner.main import run_tasks
from exfw.models.dynamic.runner.result import TaskResultStore
from exfw.models.dynamic.runner.terminal import Terminal
from exfw.models.dynamic.report.data.report_dataset import build_report_dataset
from exfw.models.dynamic.report.report_generate import ReportGenerator


def test_output_directory_has_name_and_timestamp(tmp_path):
    config = tmp_path / 'project.yaml'
    config.write_text('''test_models:
  dynamic_model:
    runner:
      output_dir: outputs
      test_name: debug
      test_path: tests
testbeds:
  lab:
    devices: [{name: main, serial: SN, driver: adb}]
''', encoding='utf-8')
    plan, tasks = load_dynamic_runner_plan(config)
    assert plan.output_dir.parent == tmp_path / 'outputs'
    assert len(plan.output_dir.name) == len('debug_20261104_123456')
    assert tasks[0].output_dir == plan.output_dir / 'SN'


def test_crashed_child_keeps_completed_data_and_partial_report(tmp_path):
    (tmp_path / 'project.yaml').write_text('''runtime:
  resources_dir: .
testbeds:
  lab:
    devices: [{name: main, serial: SN, driver: adb}]
''', encoding='utf-8')
    (tmp_path / 'conftest.py').write_text('''
import pytest
from exfw.models.dynamic.result.parsed_store import ParsedResultStore
pytest_plugins = ["exfw.pytest_framework.plugin"]
@pytest.fixture(autouse=True)
def save_parsed(request, case_artifacts):
    yield
    if request.node.name == "test_a_completed":
        store = ParsedResultStore(case_artifacts.root_dir, "test-run")
        store.update({"round": 1, "case_id": case_artifacts.case_id, "nodeid": request.node.nodeid, "case": request.node.name}, [{"success": True, "data": {}}], [])
''', encoding='utf-8')
    (tmp_path / 'test_case.py').write_text('''
import os
def test_a_completed(): pass
def test_b_crash(): os._exit(7)
''', encoding='utf-8')
    root = tmp_path / 'output'
    root.mkdir()
    cfg = DynamicRunnerConfig(tmp_path / 'project.yaml', tmp_path, tmp_path / 'test_case.py', root, None)
    task = DynamicRunnerTask('lab', 'SN', root / 'SN')
    store = TaskResultStore(cfg, [task], 1.0)
    # 即便 runner 此时被强制终止，目录和任务条目已经存在。
    assert json.loads(store.path.read_text(encoding='utf-8'))['tasks'][0]['status'] == 'pending'
    terminal = Terminal([task], io.StringIO())
    result = run_tasks(runner_config=cfg, tasks=[task], terminal=terminal, store=store)
    assert result[0]['exit_code'] == 7
    assert json.loads(store.path.read_text(encoding='utf-8'))['tasks'][0]['status'] == 'interrupted'
    session = json.loads((root / 'SN' / 'session_result.json').read_text(encoding='utf-8'))
    assert session['summary']['passed'] == 1 and session['stopped_at'] is None
    assert json.loads((root / 'SN' / 'parsed_results.json').read_text(encoding='utf-8'))['rounds']
    data = build_report_dataset(runner_output_dir=str(root), source='local')
    assert [item['case'] for item in data.case_results] == ['test_a_completed']
    report = ReportGenerator()
    report.load_report_data(str(root), source='local')
    report.generate_report(root / 'report.xlsx')
    assert (root / 'report.xlsx').is_file()


def test_report_skips_missing_device_and_unmatched_data(tmp_path):
    (tmp_path / 'task_result.json').write_text(json.dumps({'output_dir': '.', 'tasks': [{'output_dir': 'missing', 'main_serial': 'A'}, {'output_dir': 'SN', 'main_serial': 'SN'}]}), encoding='utf-8')
    device = tmp_path / 'SN'
    device.mkdir()
    (device / 'session_result.json').write_text(json.dumps({'rounds': [{'round': 1, 'cases': [{'case_id': 'ok', 'nodeid': 'test_ok'}]}]}), encoding='utf-8')
    (device / 'parsed_results.json').write_text(json.dumps({'rounds': [{'round': 1, 'cases': [
        {'case_id': 'missing', 'nodeid': 'test_missing', 'case_name': 'test_missing'},
        {'case_id': 'ok', 'nodeid': 'test_ok', 'case_name': 'test_ok', 'log_results': [{'success': True}]}]}]}), encoding='utf-8')
    result = build_report_dataset(runner_output_dir=str(tmp_path), source='local')
    assert [case['case'] for case in result.case_results] == ['test_ok']


def test_runner_exception_persists_interrupted_status_and_logs(tmp_path, monkeypatch, capsys):
    import exfw.models.dynamic.runner.main as runner
    root = tmp_path / 'run'
    cfg = DynamicRunnerConfig(tmp_path / 'project.yaml', tmp_path, tmp_path / 'tests', root, 1)
    task = DynamicRunnerTask('lab', 'SN', root / 'SN')
    monkeypatch.setattr(runner, 'load_dynamic_runner_plan', lambda _: (cfg, [task]))
    def fail(**kwargs):
        kwargs['store'].update('SN', status='running')
        raise RuntimeError('runner test error')
    monkeypatch.setattr(runner, 'run_tasks', fail)
    assert runner.main(['--project-config', str(tmp_path / 'project.yaml')]) == 1
    data = json.loads((root / 'task_result.json').read_text(encoding='utf-8'))
    assert data['status'] == 'interrupted' and data['tasks'][0]['status'] == 'interrupted'
    assert 'runner test error' in (root / 'runner.log').read_text(encoding='utf-8')
    assert 'runner test error' in capsys.readouterr().err


def test_existing_output_directory_is_not_overwritten(tmp_path, monkeypatch):
    import exfw.models.dynamic.runner.main as runner
    root = tmp_path / 'same_second'
    root.mkdir()
    marker = root / 'existing.txt'
    marker.write_text('keep', encoding='utf-8')
    cfg = DynamicRunnerConfig(tmp_path / 'project.yaml', tmp_path, tmp_path / 'tests', root)
    monkeypatch.setattr(runner, 'load_dynamic_runner_plan', lambda _: (cfg, [DynamicRunnerTask('lab', 'SN', root / 'SN')]))
    assert runner.main(['--project-config', str(tmp_path / 'project.yaml')]) == 2
    assert marker.read_text(encoding='utf-8') == 'keep'
