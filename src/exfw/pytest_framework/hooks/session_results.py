from __future__ import annotations

import json
import time
from typing import Any

import pytest

from exfw.pytest_framework.core.runtime import EXFW_RUN_CONFIG_KEY, RunConfig
from exfw.pytest_framework.core.session_result import (
    SessionResultCollector,
    get_or_create_session_result_collector,
)


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """记录 pytest session 开始时间。"""

    get_or_create_session_result_collector(session.config)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(
    session: pytest.Session, exitstatus: int | pytest.ExitCode
) -> None:
    """在 session 结束时写入总览结果。"""

    run_config = session.config.stash.get(EXFW_RUN_CONFIG_KEY, None)

    if run_config is None:
        return

    collector = get_or_create_session_result_collector(session.config)
    stopped_at = time.time()

    result = _build_session_result(
        run_config=run_config,
        collector=collector,
        stopped_at=stopped_at,
        exitstatus=int(exitstatus),
    )

    run_config.output_dir.mkdir(parents=True, exist_ok=True)
    result_file = run_config.output_dir / "session_result.json"
    result_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _build_session_result(
    *,
    run_config: RunConfig,
    collector: SessionResultCollector,
    stopped_at: float,
    exitstatus: int,
) -> dict[str, Any]:
    """构建 session 级汇总结果。"""

    cases = collector.cases
    summary = _build_summary(cases)

    return {
        "testbed": run_config.testbed_name,
        "config_path": str(run_config.config_path),
        "output_dir": str(run_config.output_dir),
        "artifact_layout": run_config.artifact_layout,
        "started_at": collector.started_at,
        "stopped_at": stopped_at,
        "duration": stopped_at - collector.started_at,
        "exitstatus": exitstatus,
        "summary": summary,
        "devices": [
            {
                "name": device.name,
                "serial": device.serial,
                "model": device.model,
                "driver": device.driver,
            }
            for device in run_config.device_specs
        ],
        "extensions": collector.extensions,
        "cases": cases,
    }


def _build_summary(cases: list[dict[str, Any]]) -> dict[str, int]:
    """根据用例索引统计执行结果。"""

    summary = {"total": len(cases), "passed": 0, "failed": 0, "skipped": 0, "error": 0}

    for case in cases:
        outcome = case.get("outcome")

        if outcome == "passed":
            summary["passed"] += 1
        elif outcome == "failed":
            summary["failed"] += 1
        elif outcome == "skipped":
            summary["skipped"] += 1
        else:
            summary["error"] += 1

    return summary
