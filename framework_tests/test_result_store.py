"""结果合并必须支持异步模型处理和失败回滚。"""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from exfw.pytest_framework.result.models import CaseResult
from exfw.pytest_framework.result.store import SessionResultStore


def test_concurrent_extensions_merge_with_final_case_and_rounds(tmp_path):
    store = SessionResultStore(SimpleNamespace(output_dir=tmp_path, testbed_name=None,
        config_path=tmp_path / 'project.yaml', artifact_layout='round', device_specs=()))
    def update(n):
        store.update_case_extension(1, 'case', 'test_case', 'model', {f'item_{n}': n})
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(update, range(12)))
    store.set_case(1, CaseResult(case_id='case', nodeid='test_case', case_name='test_case', outcome='passed'))
    store.set_case(2, CaseResult(case_id='case', nodeid='test_case', case_name='test_case', outcome='failed'))
    data = json.loads((tmp_path / 'session_result.json').read_text(encoding='utf-8'))
    assert len(data['rounds'][0]['cases'][0]['extensions']['model']) == 12
    assert data['summary']['total'] == 2
    assert data['summary']['failed'] == 1


def test_failed_write_rolls_back_in_memory_result(tmp_path, monkeypatch):
    import exfw.pytest_framework.result.store as module
    store = SessionResultStore(SimpleNamespace(output_dir=tmp_path, testbed_name=None,
        config_path=tmp_path / 'project.yaml', artifact_layout='plain', device_specs=()))
    def fail(*args):
        raise OSError('disk error')
    monkeypatch.setattr(module, 'atomic_write_json', fail)
    with pytest.raises(OSError):
        store.update_case_extension(1, 'case', 'test_case', 'model', {'status': 'done'})
    assert store.data.rounds == []
