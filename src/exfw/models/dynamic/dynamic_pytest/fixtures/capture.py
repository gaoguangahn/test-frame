from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from exfw.models.dynamic.capture.service import (
    DynamicModelCaptureService,
)
from exfw.models.dynamic.dynamic_pytest.runtime import get_dynamic_model_runtime
from exfw.models.dynamic.result import DynamicResultProcessor
from exfw.pytest_framework.core.artifacts import CaseArtifacts
from exfw.pytest_framework.core.runtime import DeviceSpec
from exfw.pytest_framework.core.time_context import CaseTimeContext
from exfw.pytest_framework.result.store import get_session_result_store


@pytest.fixture(scope="session")
def dynamic_case_result_reporter(
    pytestconfig: pytest.Config,
) -> DynamicResultProcessor | None:
    """获取动态模型全局唯一的用例结果上报器。"""

    return get_dynamic_model_runtime(
        pytestconfig,
    ).case_result_reporter


@pytest.fixture(scope="session")
def dynamic_capture_service(
    pytestconfig: pytest.Config,
) -> DynamicModelCaptureService:
    """获取动态模型全局唯一的日志采集服务。"""

    return get_dynamic_model_runtime(pytestconfig).capture_service


@pytest.fixture(scope="function", autouse=True)
def dynamic_case_capture(
    dynamic_pre_case_recovery: None,
    pytestconfig: pytest.Config,
    device_specs: tuple[DeviceSpec, ...],
    case_artifacts: CaseArtifacts,
    dynamic_case_time_context: CaseTimeContext | None,
    dynamic_upload_context: dict[str, Any],
    dynamic_capture_service: DynamicModelCaptureService,
    dynamic_case_result_reporter: DynamicResultProcessor | None,
) -> Generator[None, None, None]:
    """在动态模型用例执行期间采集并异步上报 case 日志和 Trace。"""

    if not device_specs:
        raise pytest.UsageError("动态模型需要设备；请在项目配置中设置 testbeds 并选择 --testbed。")
    main_device = device_specs[0]
    for spec in device_specs:
        if spec.name == "main":
            main_device = spec
            break

    serial = main_device.serial
    logs_dir = case_artifacts.case_dir / "logs"
    traces_dir = case_artifacts.case_dir / "traces"

    task_context = {**dynamic_upload_context, "serial": serial}
    try:
        dynamic_capture_service.prepare_case(serial=serial, logs_dir=logs_dir)
    except Exception as error:
        if dynamic_case_result_reporter is not None:
            try:
                dynamic_case_result_reporter.record_capture_failure(task_context, error)
            except Exception:
                logging.getLogger("exfw.fixture.dynamic_model_capture").exception("保存采集失败状态失败")
        raise

    try:
        yield
    finally:
        try:
            capture_status, traces, snapshot = dynamic_capture_service.finish_case(
                serial=serial, logs_dir=logs_dir, traces_dir=traces_dir,
                root_dir=case_artifacts.root_dir, time_context=dynamic_case_time_context,
            )

            task_context = {**dynamic_upload_context, "serial": serial}

            logs = []
            for item in capture_status.get("items", []):
                if item.get("name") == "trace":
                    continue
                entry = dict(item)
                if entry.get("path"):
                    path = Path(entry["path"])
                    try:
                        entry["path"] = path.relative_to(case_artifacts.root_dir).as_posix()
                    except ValueError:
                        entry["path"] = None
                logs.append(entry)
            # 日志条目已单独保存，采集状态只保留汇总及 Trace 操作状态。
            capture_status = {
                "status": capture_status["status"],
                "items": [{key: value for key, value in item.items() if key != "path"}
                          for item in capture_status.get("items", []) if item.get("name") == "trace"],
            }
            # 确认 session 保存成功后才能释放 AW 中的 Trace 记录。
            get_session_result_store(pytestconfig).update_case_extension(
                case_artifacts.round_no, case_artifacts.case_id, task_context["nodeid"],
                "dynamic_model", {"traces": traces, "logs": logs, "capture": capture_status},
            )
            dynamic_capture_service.acknowledge_traces(serial, snapshot)

            if dynamic_case_result_reporter is not None:
                dynamic_case_result_reporter.submit_case_result(
                    task_context=task_context,
                    log_path=logs_dir,
                    trace_path=traces_dir,
                    brand=getattr(main_device, "brand", "Honor"),
                    capture_status=capture_status,
                )

        except Exception as error:
            if dynamic_case_result_reporter is not None:
                try:
                    dynamic_case_result_reporter.record_capture_failure(task_context, error)
                except Exception:
                    logging.getLogger("exfw.fixture.dynamic_model_capture").exception("保存采集失败状态失败")
            logging.getLogger("exfw.fixture.dynamic_model_capture").exception(
                "动态模型 case 日志解析任务提交失败：serial=%s, logs_dir=%s",
                serial,
                logs_dir,
            )
