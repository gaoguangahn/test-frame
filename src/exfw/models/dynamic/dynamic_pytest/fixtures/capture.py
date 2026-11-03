from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

import pytest

from exfw.aw.trace.collector import TraceCollector
from exfw.models.dynamic.dynamic_pytest.capture.capture_service import (
    DynamicModelCaptureService,
)
from exfw.models.dynamic.dynamic_pytest.runtime import get_dynamic_model_runtime
from exfw.models.dynamic.dynamic_pytest.time_sync import (
    convert_trace_records_file_time_source,
)
from exfw.models.dynamic.result import CaseResultReporter
from exfw.pytest_framework.core.artifacts import CaseArtifacts
from exfw.pytest_framework.core.runtime import DeviceSpec
from exfw.pytest_framework.core.time_context import CaseTimeContext


@pytest.fixture(scope="session")
def dynamic_case_result_reporter(
    pytestconfig: pytest.Config,
) -> CaseResultReporter | None:
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
    device_specs: tuple[DeviceSpec, ...],
    case_artifacts: CaseArtifacts,
    trace_collector: TraceCollector,
    dynamic_case_time_context: CaseTimeContext | None,
    dynamic_upload_context: dict[str, Any],
    dynamic_capture_service: DynamicModelCaptureService,
    dynamic_case_result_reporter: CaseResultReporter | None,
) -> Generator[None, None, None]:
    """在动态模型用例执行期间采集并异步上报 case 日志和 Trace。"""

    main_device = device_specs[0]
    for spec in device_specs:
        if spec.name == "main":
            main_device = spec
            break

    serial = main_device.serial
    logs_dir = case_artifacts.case_dir / "logs"
    traces_dir = case_artifacts.case_dir / "traces"

    # 用例开始前清理设备端残留的 Trace，避免混入前序用例数据。
    trace_collector.clean_device_traces(serial=serial)

    dynamic_capture_service.start_case_capture(serial=serial, logs_dir=logs_dir)

    try:
        yield
    finally:
        dynamic_capture_service.stop_case_capture(serial=serial, logs_dir=logs_dir)

        try:
            # 用例结束后拉取本次用例产生的 Trace 文件。
            trace_collector.pull_trace_directory(
                serial=serial,
                local_dir=traces_dir,
            )

            # 保存本进程中已完成的 Trace 采集记录，便于报告侧关联 Trace
            # 的开始时间、结束时间和描述。
            trace_records_file = traces_dir / "trace_records.json"
            trace_collector.save_completed_trace_records(trace_records_file)

            convert_trace_records_file_time_source(
                trace_records_file,
                dynamic_case_time_context,
            )

            task_context = {
                **dynamic_upload_context,
                "serial": serial,
            }

            if dynamic_case_result_reporter is not None:
                dynamic_case_result_reporter.submit_case_result(
                    task_context=task_context,
                    log_path=logs_dir,
                    trace_path=traces_dir,
                    brand=getattr(main_device, "brand", "Honor"),
                )

        except Exception:
            logging.getLogger("exfw.fixture.dynamic_model_capture").exception(
                "动态模型 case 日志解析任务提交失败：serial=%s, logs_dir=%s",
                serial,
                logs_dir,
            )
