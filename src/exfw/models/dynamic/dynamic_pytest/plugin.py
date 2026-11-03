from __future__ import annotations

import logging
from typing import Any

import pytest
import requests

from exfw.aw.logcat import LogCollectorFactory
from exfw.models.dynamic.result import CaseResultReporter
from exfw.models.dynamic.server_config import CASE_RESULT_SERVER
from exfw.pytest_framework.capture.manager import get_or_create_logcat_manager
from exfw.pytest_framework.core.runtime import EXFW_RUN_CONFIG_KEY
from exfw.pytest_framework.core.session_result import (
    get_or_create_session_result_collector,
)
from exfw.pytest_framework.rounds.runner import get_or_create_round_task_runner

from .capture.capture_service import DynamicModelCaptureService
from .capture.round_capture import DynamicModelRoundCaptureTask
from .config import load_dynamic_model_config
from .runtime import DYNAMIC_MODEL_RUNTIME_KEY, DynamicModelRuntime


def _create_case_result_task_id() -> str:
    """向结果服务申请本次动态模型测试唯一的任务 ID。"""

    response = requests.post(
        CASE_RESULT_SERVER.task_id_url,
        timeout=10.0,
    )
    response.raise_for_status()

    body: dict[str, Any] = response.json()

    if body.get("code") != 200:
        raise RuntimeError(f"获取任务 ID 失败：response={body}")

    task_id = body.get("data", {}).get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise RuntimeError(f"服务端未返回有效 task_id：response={body}")

    return task_id


pytest_plugins = [
    "exfw.models.dynamic.dynamic_pytest.fixtures.recovery",
    "exfw.models.dynamic.dynamic_pytest.fixtures.time_sync",
    "exfw.models.dynamic.dynamic_pytest.fixtures.capture",
    "exfw.models.dynamic.dynamic_pytest.fixtures.device_info",
    "exfw.models.dynamic.dynamic_pytest.fixtures.keyboard",
    "exfw.models.dynamic.dynamic_pytest.fixtures.upload_context",
    "exfw.models.dynamic.dynamic_pytest.fixtures.config",
]

DYNAMIC_MODEL_COLLECTOR_NAMES = (
    "jank_log",
    "events_log",
    "adb_log",
    "dmesg_log",
    "dumpsys_meminfo",
    "io_measure",
    "io_stat",
    "radar",
    "broadcasts_history",
    "proc_memory",
    "soft_resource",
)


def pytest_configure(config: pytest.Config) -> None:
    """初始化动态模型专用 pytest 扩展。"""

    logger = logging.getLogger("exfw.dynamic_model.plugin")

    if EXFW_RUN_CONFIG_KEY not in config.stash:
        raise pytest.UsageError(
            "dynamic_model pytest 插件依赖 pytest_ext.plugin。"
            "请确保项目根 conftest.py 已加载 pytest_ext.plugin。"
        )

    logcat_manager = get_or_create_logcat_manager(config)
    _register_dynamic_model_collectors(logcat_manager)

    runtime = config.stash.get(DYNAMIC_MODEL_RUNTIME_KEY, None)

    if runtime is None:
        run_config = config.stash[EXFW_RUN_CONFIG_KEY]
        dynamic_model_config = load_dynamic_model_config(run_config.project_config)

        task_id = None
        reporter = None
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
            reporter = CaseResultReporter(max_workers=2, parse_max_workers=8)
        else:
            logger.warning("结果上报已关闭：保留本地采集产物，不执行后台解析和上传。")

        runtime = DynamicModelRuntime(
            task_id=task_id,
            config=dynamic_model_config,
            capture_service=DynamicModelCaptureService(logcat_manager=logcat_manager),
            case_result_reporter=reporter,
        )

        config.stash[DYNAMIC_MODEL_RUNTIME_KEY] = runtime

        get_or_create_session_result_collector(config).update_extension(
            "dynamic_model", {"task_id": task_id, "upload_enabled": dynamic_model_config.upload_enabled}
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


def _register_dynamic_model_collectors(logcat_manager) -> None:
    """注册动态模型日志采集器。"""

    for name in DYNAMIC_MODEL_COLLECTOR_NAMES:
        logcat_manager.register(
            name,
            LogCollectorFactory.get_collector(name),
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
