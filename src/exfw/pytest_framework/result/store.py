"""单 session 结果存储，统一串行合并并原子写入，支持业务扩展先于 pytest report。"""
from __future__ import annotations

import json
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from exfw.pytest_framework.core.runtime import EXFW_RUN_CONFIG_KEY
from .models import CaseResult, RoundResult, SessionResult


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _merge(target: dict, values: dict) -> None:
    for key, value in values.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)


class SessionResultStore:
    def __init__(self, run_config):
        self.path = run_config.output_dir / "session_result.json"
        self._lock = threading.RLock()
        self.data = SessionResult(
            testbed=run_config.testbed_name, config_path=str(run_config.config_path),
            output_dir=str(run_config.output_dir), artifact_layout=run_config.artifact_layout,
            started_at=time.time(), devices=[asdict(device) for device in run_config.device_specs],
        )

    def initialize(self):
        """在执行前创建可读取的空 session。"""
        self._commit(lambda: None)

    def _round(self, round_no: int) -> RoundResult:
        for item in self.data.rounds:
            if item.round == round_no:
                return item
        item = RoundResult(round=round_no)
        self.data.rounds.append(item)
        return item

    def _case(self, round_no: int, case_id: str, nodeid: str) -> CaseResult:
        round_result = self._round(round_no)
        for case in round_result.cases:
            if case.case_id == case_id:
                if nodeid and case.nodeid != nodeid:
                    raise ValueError(f"同轮用例 ID 冲突：{case_id}")
                return case
        case = CaseResult(case_id=case_id, nodeid=nodeid, case_name=nodeid.split("::")[-1])
        round_result.cases.append(case)
        return case

    def _commit(self, operation) -> None:
        with self._lock:
            previous = deepcopy(self.data)
            try:
                operation()
                self._refresh_summary()
                atomic_write_json(self.path, asdict(self.data))
            except BaseException:
                self.data = previous
                raise

    def _refresh_summary(self):
        counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0}
        for round_result in self.data.rounds:
            for case in round_result.cases:
                if case.outcome == "pending":
                    continue
                counts["total"] += 1
                counts[case.outcome if case.outcome in ("passed", "failed", "skipped") else "error"] += 1
        self.data.summary = counts

    def set_case(self, round_no: int, result: CaseResult):
        def apply():
            existing = self._case(round_no, result.case_id, result.nodeid)
            result.extensions = deepcopy(existing.extensions)
            cases = self._round(round_no).cases
            cases[cases.index(existing)] = result
        self._commit(apply)

    def update_case_extension(self, round_no: int, case_id: str, nodeid: str, namespace: str, value: dict):
        def apply():
            case = self._case(round_no, case_id, nodeid)
            _merge(case.extensions.setdefault(namespace, {}), value)
        self._commit(apply)

    def update_round_extension(self, round_no: int, namespace: str, value: dict):
        self._commit(lambda: _merge(self._round(round_no).extensions.setdefault(namespace, {}), value))

    def update_extension(self, name: str, value: dict):
        self._commit(lambda: _merge(self.data.extensions.setdefault(name, {}), value))

    def finish(self, exitstatus: int):
        def apply():
            self.data.stopped_at = time.time()
            self.data.duration = self.data.stopped_at - self.data.started_at
            self.data.exitstatus = int(exitstatus)
        self._commit(apply)


SESSION_RESULT_KEY: pytest.StashKey[SessionResultStore] = pytest.StashKey()


def get_session_result_store(config: pytest.Config) -> SessionResultStore:
    store = config.stash.get(SESSION_RESULT_KEY, None)
    if store is None:
        store = SessionResultStore(config.stash[EXFW_RUN_CONFIG_KEY])
        config.stash[SESSION_RESULT_KEY] = store
    return store
