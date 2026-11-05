from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from exfw.pytest_framework.core.artifacts import build_case_artifacts
from exfw.pytest_framework.core.runtime import (
    EXFW_CURRENT_ROUND_KEY,
    EXFW_RUN_CONFIG_KEY,
    RunConfig,
)
from exfw.pytest_framework.result.models import CaseResult
from exfw.pytest_framework.result.store import get_session_result_store
from exfw.pytest_framework.core.time_context import (
    CaseTimeContext,
    get_case_time_context,
)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """在每个用例阶段结束后更新结果文件，teardown 后得到最终结果。"""
    outcome = yield
    report: pytest.TestReport = outcome.get_result()

    if report.when == "setup":
        phase_reports: dict[str, pytest.TestReport] = {}
    else:
        phase_reports = getattr(
            item,
            "_exfw_phase_reports",
            {},
        )

    phase_reports[report.when] = report
    setattr(item, "_exfw_phase_reports", phase_reports)

    if not _should_write_result(report):
        return

    config = item.config
    run_config = config.stash.get(EXFW_RUN_CONFIG_KEY, None)

    if run_config is None:
        return

    current_round = config.stash.get(EXFW_CURRENT_ROUND_KEY, 1)
    case_artifacts = _build_case_artifacts(
        run_config=run_config,
        nodeid=report.nodeid,
        round_no=current_round,
    )
    case_artifacts.case_dir.mkdir(parents=True, exist_ok=True)

    result = _build_case_result(
        item=item,
        phase_reports=phase_reports,
        run_config=run_config,
        round_no=current_round,
        case_id=case_artifacts.case_id,
        case_dir=case_artifacts.case_dir,
    )

    get_session_result_store(config).set_case(current_round, result)


def _should_write_result(report: pytest.TestReport) -> bool:
    """判断当前阶段是否已经可以落盘一次用例结果。"""
    if report.when == "teardown":
        return True

    return report.when == "setup" and (report.failed or report.skipped)


def _build_case_artifacts(*, run_config: RunConfig, nodeid: str, round_no: int):
    """返回通用用例产物路径。"""
    return build_case_artifacts(
        output_dir=run_config.output_dir,
        round_no=round_no,
        nodeid=nodeid,
        use_round_dir=run_config.artifact_layout == "round",
    )


def _build_case_result(
    *,
    item: pytest.Item,
    phase_reports: dict[str, pytest.TestReport],
    run_config: RunConfig,
    round_no: int,
    case_id: str,
    case_dir: Path,
) -> CaseResult:
    """构建可落盘的单用例结果。"""
    final_report = _select_final_report(phase_reports)

    duration = sum(report.duration for report in phase_reports.values())
    stopped_at = time.time()
    started_at = stopped_at - duration
    time_context = get_case_time_context(item)

    steps = getattr(item, "_exfw_steps", None)

    if steps is None:
        steps = dict(getattr(final_report, "user_properties", [])).get("exfw_steps", [])

    steps = _convert_steps_timestamps(steps, time_context)
    return CaseResult(
        nodeid=final_report.nodeid,
        case_id=case_id,
        case_name=final_report.nodeid.split("::")[-1],
        outcome=final_report.outcome,
        duration=duration,
        started_at=_convert_timestamp(started_at, time_context),
        stopped_at=_convert_timestamp(stopped_at, time_context),
        longrepr=_longrepr_text(final_report),
        steps=steps,
        artifacts=_build_artifacts_index(
            output_dir=run_config.output_dir,
            case_dir=case_dir,
        ),
        time_source=time_context.time_source if time_context is not None else None,
        time_context=time_context.to_dict() if time_context is not None else None,
    )


def _convert_timestamp(
    timestamp: Any,
    time_context: CaseTimeContext | None,
) -> Any:
    """按用例时间上下文转换绝对时间戳。"""

    if time_context is None:
        return timestamp

    return time_context.convert_timestamp(timestamp)


def _convert_steps_timestamps(
    steps: Any,
    time_context: CaseTimeContext | None,
) -> Any:
    """转换 Step 记录中的 timestamp，保持原始 steps 对象不被原地修改。"""

    if time_context is None or not isinstance(steps, list):
        return steps

    converted_steps = []

    for step in steps:
        if not isinstance(step, dict):
            converted_steps.append(step)
            continue

        converted_step = dict(step)
        converted_step["timestamp"] = _convert_timestamp(
            converted_step.get("timestamp"),
            time_context,
        )
        converted_steps.append(converted_step)

    return converted_steps


def _build_artifacts_index(*, output_dir: Path, case_dir: Path) -> dict[str, str]:
    """构建相对 output_dir 的通用产物路径索引。"""

    try:
        relative_case_dir = case_dir.relative_to(output_dir)
    except ValueError:
        relative_case_dir = case_dir

    return {
        "case_dir": str(relative_case_dir),
        "logs_dir": str(relative_case_dir / "logs"),
        "traces_dir": str(relative_case_dir / "traces"),
        "pictures_dir": str(relative_case_dir / "pictures"),
    }


def _select_final_report(
    phase_reports: dict[str, pytest.TestReport],
) -> pytest.TestReport:
    """按 pytest 执行阶段选择最终代表结果。"""
    for name in ("setup", "call", "teardown"):
        report = phase_reports.get(name)
        if report is not None and report.failed:
            return report

    for name in ("setup", "call", "teardown"):
        report = phase_reports.get(name)
        if report is not None and report.skipped:
            return report

    if "call" in phase_reports:
        return phase_reports["call"]

    return next(iter(phase_reports.values()))


def _longrepr_text(report: pytest.TestReport) -> str | None:
    if not report.failed and not report.skipped:
        return None

    longrepr = getattr(report, "longrepr", None)

    if longrepr is None:
        return None

    return str(longrepr)
