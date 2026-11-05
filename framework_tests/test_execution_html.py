"""执行结果 HTML 的本地渲染与 runner 集成。"""
import json
import subprocess
import sys
from pathlib import Path

from exfw.models.dynamic.result.execution_html import generate_execution_html


def write_data(root):
    (root / 'SN').mkdir()
    (root / 'SN' / 'execution.log').write_text('details', encoding='utf-8')
    (root / 'task_result.json').write_text(json.dumps({'status': 'interrupted', 'rounds': 2, 'tasks': [
        {'main_serial': 'SN', 'testbed': 'lab', 'output_dir': 'SN', 'status': 'interrupted'},
        {'main_serial': 'missing', 'testbed': 'other', 'output_dir': 'missing', 'status': 'pending'}]}), encoding='utf-8')
    (root / 'SN' / 'session_result.json').write_text(json.dumps({'rounds': [{'round': 1, 'cases': [
        {'case_name': '<script>alert(1)</script>', 'nodeid': 'tests/a.py::test_bad', 'outcome': 'failed', 'duration': 1.5,
         'longrepr': '<unsafe>\nline 42', 'steps': [{'index': 1, 'description': '<login>'}],
         'extensions': {'dynamic_model': {'capture': {'status': 'completed'}, 'upload': {'status': 'disabled'}}}},
        {'case_name': 'test_pass', 'nodeid': 'tests/a.py::test_pass', 'outcome': 'passed'}]}]}), encoding='utf-8')


def test_html_report_escapes_data_and_handles_missing_device(tmp_path):
    write_data(tmp_path)
    html = generate_execution_html(tmp_path).read_text(encoding='utf-8')
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<script>alert(1)</script>' not in html
    assert '&lt;unsafe&gt;' in html and '&lt;login&gt;' in html
    assert '结果尚不可用' in html and '已中断' in html
    assert 'SN/execution.log' in html
    assert 'data-outcome="failed"' in html and 'data-round="1"' in html
    assert html.index('test_bad') < html.index('test_pass')


def test_cli_generates_report_and_missing_input_is_error(tmp_path):
    write_data(tmp_path)
    command = [sys.executable, '-m', 'exfw.models.dynamic.result.execution_html', '--task-dir']
    result = subprocess.run(command + [str(tmp_path)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'execution_report.html').is_file()
    result = subprocess.run(command + [str(tmp_path / 'missing')], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    assert result.returncode != 0


def test_link_rejects_files_outside_result_directory(tmp_path):
    from exfw.models.dynamic.result.execution_html.render import local_link, child_path
    assert not local_link(tmp_path, tmp_path.parent / 'other.log', 'outside')
    assert child_path(tmp_path, '../outside.log') is None


def test_runner_automatically_generates_report(tmp_path, monkeypatch):
    import exfw.models.dynamic.runner.main as runner
    from exfw.models.dynamic.runner.config import DynamicRunnerConfig, DynamicRunnerTask
    root = tmp_path / 'run'
    cfg = DynamicRunnerConfig(tmp_path / 'project.yaml', tmp_path, tmp_path / 'tests', root)
    task = DynamicRunnerTask('lab', 'SN', root / 'SN')
    monkeypatch.setattr(runner, 'load_dynamic_runner_plan', lambda _: (cfg, [task]))
    def fake_run(**kwargs):
        result = {'main_serial': 'SN', 'testbed': 'lab', 'output_dir': 'SN', 'status': 'passed', 'exit_code': 0}
        kwargs['store'].update('SN', status='passed', exit_code=0)
        return [result]
    monkeypatch.setattr(runner, 'run_tasks', fake_run)
    assert runner.main(['--project-config', str(tmp_path / 'project.yaml')]) == 0
    html = (root / 'execution_report.html').read_text(encoding='utf-8')
    assert '测试执行结果' in html and 'SN' in html
