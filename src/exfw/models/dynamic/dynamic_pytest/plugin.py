from __future__ import annotations

import logging
import os
from dataclasses import replace
import pytest
import requests

from exfw.models.dynamic.result import DynamicResultProcessor
from exfw.models.dynamic.upload.service import create_server_task_id as _create_case_result_task_id
from exfw.pytest_framework.core.runtime import EXFW_RUN_CONFIG_KEY
from exfw.pytest_framework.result.store import get_session_result_store
from exfw.pytest_framework.rounds.runner import get_or_create_round_task_runner

from exfw.models.dynamic.capture.service import DynamicModelCaptureService
from .round.round_capture import DynamicModelRoundCaptureTask
from .config import load_dynamic_model_config
from .runtime import DYNAMIC_MODEL_RUNTIME_KEY, DynamicModelRuntime


pytest_plugins = [
    "exfw.models.dynamic.dynamic_pytest.fixtures.recovery",
    "exfw.models.dynamic.dynamic_pytest.fixtures.time_sync",
    "exfw.models.dynamic.dynamic_pytest.fixtures.capture",
    "exfw.models.dynamic.dynamic_pytest.fixtures.device_info",
    "exfw.models.dynamic.dynamic_pytest.fixtures.keyboard",
    "exfw.models.dynamic.dynamic_pytest.fixtures.upload_context",
    "exfw.models.dynamic.dynamic_pytest.fixtures.config",
]

def pytest_configure(config: pytest.Config) -> None:
    """初始化动态模型专用 pytest 扩展。"""

    logger = logging.getLogger("exfw.dynamic_model.plugin")

    if EXFW_RUN_CONFIG_KEY not in config.stash:
        raise pytest.UsageError(
            "dynamic_model pytest 插件依赖 pytest_ext.plugin。"
            "请确保项目根 conftest.py 已加载 pytest_ext.plugin。"
        )

    runtime = config.stash.get(DYNAMIC_MODEL_RUNTIME_KEY, None)

    if runtime is None:
        run_config = config.stash[EXFW_RUN_CONFIG_KEY]
        dynamic_model_config = load_dynamic_model_config(run_config.project_config)
        # 单独 pytest 调试只做本地解析；批量 runner 按项目配置控制上传。
        if not os.environ.get("EXFW_RUNNER_MODE"):
            dynamic_model_config = replace(dynamic_model_config, upload_enabled=False)

        try:
            capture_service = DynamicModelCaptureService()
        except (OSError, TypeError, ValueError) as error:
            raise pytest.UsageError(f"动态模型采集配置无效：{error}") from error

        task_id = None
        if dynamic_model_config.upload_enabled:
            try:
                task_id = _create_case_result_task_id()
            except requests.RequestException as error:
                raise pytest.UsageError(
                    f"无法连接用例结果服务，任务 ID 创建失败：{error}"
                ) from error
            except (TypeError, ValueError, RuntimeError) as error:
                raise pytest.UsageError(
                    f"用例结果服务返回的任务 ID 无效：{error}"
                ) from error
        else:
            logger.info("结果上报已关闭：仍会解析并保存本地结果。")

        try:
            reporter = DynamicResultProcessor(run_config.output_dir, get_session_result_store(config), max_workers=2, parse_max_workers=8, upload_enabled=dynamic_model_config.upload_enabled)
        except (OSError, TypeError, ValueError) as error:
            raise pytest.UsageError(f"动态模型解析配置无效：{error}") from error

        runtime = DynamicModelRuntime(
            task_id=task_id,
            config=dynamic_model_config,
            capture_service=capture_service,
            case_result_reporter=reporter,
        )

        config.stash[DYNAMIC_MODEL_RUNTIME_KEY] = runtime

        get_session_result_store(config).update_extension(
            "dynamic_model", {"task_id": task_id, "local_run_id": reporter.local_run_id, "upload_enabled": dynamic_model_config.upload_enabled}
        )

        if task_id is not None:
            logger.info("动态模型测试任务 ID 已创建：task_id=%s", task_id)

    round_task_runner = get_or_create_round_task_runner(config)

    round_task_runner.add_task(
        DynamicModelRoundCaptureTask(
            capture_service=runtime.capture_service,
            case_result_reporter=runtime.case_result_reporter,
            task_id=runtime.task_id,
        )
    )

    logger.info("动态模型 pytest 扩展初始化完成。")


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus) -> None:
    """在通用 session 结果落盘前等待解析与上传，并汇总处理状态。"""
    runtime = session.config.stash.get(DYNAMIC_MODEL_RUNTIME_KEY, None)
    if runtime is None or runtime.case_result_reporter is None:
        return
    reporter = runtime.case_result_reporter
    try:
        reporter.shutdown(wait=True)
        get_session_result_store(session.config).update_extension(
            "dynamic_model", {"processing": reporter.summary()}
        )
    except Exception:
        logging.getLogger("exfw.dynamic_model.plugin").exception("关闭解析和上传任务失败")
        get_session_result_store(session.config).update_extension(
            "dynamic_model", {"processing_error": "关闭解析和上传任务失败，请查看日志"}
        )


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """动态模型用例失败时，标记对应设备需在下一用例开始前恢复桌面。"""

    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return

    setattr(item, "_dynamic_call_failed", True)

    runtime = item.config.stash.get(DYNAMIC_MODEL_RUNTIME_KEY, None)
    if runtime is None:
        return

    devices = item.funcargs.get("devices") if hasattr(item, "funcargs") else None
    if not isinstance(devices, dict):
        return

    main_device = devices.get("main")
    serial = getattr(main_device, "serial", None)
    if not isinstance(serial, str) or not serial:
        return

    runtime.recovery_required_serials.add(serial)
    logging.getLogger("exfw.dynamic_model.plugin").warning(
        "动态模型用例失败，已标记下个用例开始前恢复桌面：nodeid=%s, serial=%s",
        item.nodeid,
        serial,
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    """关闭动态模型后台解析、上报及上传资源。"""

    logger = logging.getLogger("exfw.dynamic_model.plugin")

    runtime = config.stash.get(
        DYNAMIC_MODEL_RUNTIME_KEY,
        None,
    )

    if runtime is None or runtime.case_result_reporter is None:
        return

    try:
        # CaseResultReporter 内部依次等待并关闭：
        # 1. case / round 编排线程池；
        # 2. Log / Trace 解析线程池；
        # 3. 异步上传器。
        runtime.case_result_reporter.shutdown(wait=True)

    except Exception:
        logger.exception("关闭动态模型用例结果上报器失败。")
