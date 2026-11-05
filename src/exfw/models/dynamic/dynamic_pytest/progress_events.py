"""动态 runner 的子进程事件，仅用于运行时通信。"""
import json
import os
from pathlib import Path
import pytest
from exfw.pytest_framework.core.runtime import EXFW_CURRENT_ROUND_KEY


def _emit(event, **fields):
    path = os.environ.get("EXFW_PROGRESS_FILE")
    if path:
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": event, **fields}, ensure_ascii=True) + "\n")


@pytest.hookimpl(trylast=True)
def pytest_collection_finish(session):
    rounds = session.config.getoption("--rounds", default=None) or 1
    _emit("collected", total=len(session.items) * rounds, per_round=len(session.items), rounds=rounds)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    info = {"nodeid": item.nodeid, "round": item.config.stash.get(EXFW_CURRENT_ROUND_KEY, 1)}
    item._exfw_progress_reports = []
    _emit("start", **info)
    try:
        yield
        reports = item._exfw_progress_reports
        result = ("FAILED" if any(r.failed for r in reports) else
                  "SKIPPED" if any(r.skipped for r in reports) else
                  "PASSED" if reports else "UNKNOWN")
        _emit("finish", outcome=result, **info)
    finally:
        del item._exfw_progress_reports


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    item._exfw_progress_reports.append(outcome.get_result())
