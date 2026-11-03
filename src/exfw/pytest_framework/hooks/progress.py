"""Record pytest terminal output and emit progress for the batch runner."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from exfw.pytest_framework.core.runtime import EXFW_CURRENT_ROUND_KEY, EXFW_RUN_CONFIG_KEY
from exfw.pytest_framework.core.logging_setup import log_context


class _Tee:
    def __init__(self, original, output):
        self.original, self.output = original, output

    def write(self, text):
        self.original.write(text)
        self.output.write(text)
        self.output.flush()

    def flush(self):
        self.original.flush()
        self.output.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session):
    if os.environ.get("EXFW_RUNNER_MODE"):
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    run_config = session.config.stash.get(EXFW_RUN_CONFIG_KEY, None)
    if reporter is not None and run_config is not None:
        output = (run_config.output_dir / "pytest-output.log").open("w", encoding="utf-8")
        original = reporter._tw._file
        reporter._tw._file = _Tee(original, output)
        session.config._exfw_terminal_tee = (reporter, original, output)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    tee = getattr(config, "_exfw_terminal_tee", None)
    if tee:
        reporter, original, output = tee
        reporter._tw._file = original
        output.close()


def _event(item, event, **fields):
    path = os.environ.get("EXFW_PROGRESS_FILE")
    if path:
        payload = {"event": event, "nodeid": item.nodeid,
                   "round": item.config.stash.get(EXFW_CURRENT_ROUND_KEY, 1), **fields}
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=True) + "\n")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    token = log_context.set({"case": item.nodeid, "round": item.config.stash.get(EXFW_CURRENT_ROUND_KEY, 1)})
    item._exfw_progress_reports = []
    _event(item, "start")
    try:
        yield
        reports = item._exfw_progress_reports
        if any(r.failed for r in reports):
            result = "FAILED"
        elif any(r.skipped for r in reports):
            result = "SKIPPED"
        else:
            result = "PASSED" if reports else "UNKNOWN"
        _event(item, "finish", outcome=result)
    finally:
        log_context.reset(token)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    item._exfw_progress_reports.append(outcome.get_result())
