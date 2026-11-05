"""实际 pytest 子进程验证调试和 runner 配置边界。"""
import json
import os
from pathlib import Path
import subprocess
import sys


def make_project(root, beds='''  lab_a:
    devices: [{name: main, serial: SN_A, driver: adb}]
'''):
    (root / 'pyproject.toml').write_text('[tool.pytest.ini_options]\n', encoding='utf-8')
    (root / 'project.yaml').write_text('''runtime:
  resources_dir: .
test_models:
  dynamic_model:
    upload: {enabled: true}
    runner: {output_dir: results, test_name: demo, test_path: test_case.py, rounds: 1}
testbeds:
''' + beds, encoding='utf-8')
    (root / 'conftest.py').write_text('''
from pathlib import Path
import pytest
from exfw.models.dynamic.capture.service import DynamicModelCaptureService
import exfw.models.dynamic.dynamic_pytest.plugin as plugin
pytest_plugins = ["exfw.pytest_framework.plugin", "exfw.models.dynamic.dynamic_pytest.plugin"]
def id_from_server():
    Path("server_called").write_text("yes")
    return "server-id"
plugin._create_case_result_task_id = id_from_server
def before(self, **kwargs): Path("round_started").write_text("yes")
def after(self, **kwargs): pass
DynamicModelCaptureService.start_round_capture = before
DynamicModelCaptureService.stop_round_capture = after
@pytest.fixture(scope="session", autouse=True)
def dynamic_main_device_info(): pass
@pytest.fixture(autouse=True)
def dynamic_pre_case_recovery(): pass
@pytest.fixture(autouse=True)
def dynamic_case_capture(): pass
''', encoding='utf-8')
    (root / 'test_case.py').write_text('''
def test_config(run_config, pytestconfig):
    assert run_config.testbed_name in ("lab_a", "lab_b")
    assert run_config.device_specs[0].serial in ("SN_A", "SN_B")
''', encoding='utf-8')


def run_pytest(root, *args, env=None):
    environ = dict(os.environ)
    environ.pop('EXFW_RUNNER_MODE', None)
    environ.pop('EXFW_SESSION_OUTPUT', None)
    if env:
        environ.update(env)
    return subprocess.run([sys.executable, '-m', 'pytest', str(root / 'test_case.py'), '-q', '-p', 'no:cacheprovider', *args], cwd=root, env=environ, text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=30)


def test_default_debug_auto_device_offline_and_no_round(tmp_path):
    make_project(tmp_path)
    result = run_pytest(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    session = json.loads((tmp_path / 'outputs' / 'debug' / 'session_result.json').read_text(encoding='utf-8'))
    assert session['testbed'] == 'lab_a'
    assert session['extensions']['dynamic_model']['upload_enabled'] is False
    assert not (tmp_path / 'server_called').exists()
    assert not (tmp_path / 'round_started').exists()
    assert str(tmp_path / 'outputs' / 'debug') in result.stdout
    assert (tmp_path / 'outputs' / 'debug' / 'parsed_results.json').is_file()


def test_debug_explicit_rounds_and_output_parent(tmp_path):
    make_project(tmp_path)
    result = run_pytest(tmp_path, '--rounds', '1', '--output-dir', 'custom')
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / 'round_started').is_file()
    assert (tmp_path / 'custom' / 'debug' / 'session_result.json').is_file()


def test_multiple_beds_need_selection(tmp_path):
    make_project(tmp_path, '''  lab_a:
    devices: [{name: main, serial: SN_A, driver: adb}]
  lab_b:
    devices: [{name: main, serial: SN_B, driver: adb}]
''')
    missing = run_pytest(tmp_path)
    assert missing.returncode != 0 and '--testbed' in missing.stderr
    chosen = run_pytest(tmp_path, '--testbed', 'lab_b')
    assert chosen.returncode == 0, chosen.stdout + chosen.stderr
    session = json.loads((tmp_path / 'outputs' / 'debug' / 'session_result.json').read_text(encoding='utf-8'))
    assert session['testbed'] == 'lab_b'


def test_runner_child_uses_exact_directory_and_configured_upload(tmp_path):
    make_project(tmp_path)
    device_dir = tmp_path / 'run' / 'SN_A'
    result = run_pytest(tmp_path, '--testbed', 'lab_a', env={'EXFW_RUNNER_MODE': '1', 'EXFW_SESSION_OUTPUT': str(device_dir)})
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((device_dir / 'session_result.json').read_text(encoding='utf-8'))
    assert data['extensions']['dynamic_model']['upload_enabled'] is True
    assert data['extensions']['dynamic_model']['task_id'] == 'server-id'
    assert (tmp_path / 'server_called').is_file()
    assert not (device_dir / 'debug').exists()


def test_generic_pytest_does_not_autoselect_device(tmp_path):
    make_project(tmp_path)
    (tmp_path / 'conftest.py').write_text('pytest_plugins = ["exfw.pytest_framework.plugin"]\n', encoding='utf-8')
    (tmp_path / 'test_case.py').write_text('def test_plain(run_config):\n    assert run_config.testbed_name is None\n    assert not run_config.device_specs\n', encoding='utf-8')
    result = run_pytest(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_debug_directory_is_reused_without_deleting_user_files(tmp_path):
    make_project(tmp_path)
    target = tmp_path / 'outputs' / 'debug'
    target.mkdir(parents=True)
    marker = target / 'previous.trace'
    marker.write_text('keep', encoding='utf-8')
    result = run_pytest(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.read_text(encoding='utf-8') == 'keep'


def test_runner_uses_default_project_config_from_parent(tmp_path, monkeypatch):
    import exfw.models.dynamic.runner.main as runner
    make_project(tmp_path)
    child = tmp_path / 'nested'
    child.mkdir()
    monkeypatch.chdir(child)
    seen = []
    def fake_load(path):
        seen.append(Path(path))
        raise ValueError('stop before execution')
    monkeypatch.setattr(runner, 'load_dynamic_runner_plan', fake_load)
    assert runner.main([]) == 2
    assert seen == [tmp_path / 'project.yaml']
