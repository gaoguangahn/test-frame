from __future__ import annotations

import logging
from typing import Any

from exfw.models.dynamic.result import DynamicResultProcessor
from exfw.pytest_framework.core.artifacts import build_run_artifact_dir
from exfw.pytest_framework.core.runtime import DeviceSpec
from exfw.pytest_framework.rounds.tasks import RoundContext

from exfw.models.dynamic.capture.service import DynamicModelCaptureService


class DynamicModelRoundCaptureTask:
    """动态模型 round 生命周期的日志采集与解析任务。"""

    def __init__(
        self,
        capture_service: DynamicModelCaptureService,
        case_result_reporter: DynamicResultProcessor | None,
        task_id: str | None,
    ) -> None:
        self._capture_service = capture_service
        self._case_result_reporter = case_result_reporter
        self._task_id = task_id

        self._logger = logging.getLogger("exfw.round_task.dynamic_model_capture")

    @property
    def name(self) -> str:
        return "dynamic_model_round_capture"

    def before_round(self, context: RoundContext) -> None:
        """在 round 开始前启动主设备的持续日志采集。"""

        device_spec = self._get_main_device_spec(context)
        logs_dir = self._build_round_logs_dir(context)

        self._capture_service.start_round_capture(
            serial=device_spec.serial,
            round_no=context.round_no,
            logs_dir=logs_dir,
        )

    def after_round(self, context: RoundContext) -> None:
        """停止 round 采集，并提交 round 日志解析、上传。"""

        device_spec = self._get_main_device_spec(context)
        logs_dir = self._build_round_logs_dir(context)

        self._capture_service.stop_round_capture(
            serial=device_spec.serial,
            round_no=context.round_no,
        )

        if self._case_result_reporter is None:
            return

        try:
            self._case_result_reporter.submit_case_result(
                task_context=self._build_round_task_context(
                    context=context,
                    device_spec=device_spec,
                ),
                log_path=logs_dir,
                trace_path=None,
                brand=getattr(device_spec, "brand", "Honor"),
                capture_status=self._capture_service.last_round_results.get((context.round_no, device_spec.serial)),
            )

        except Exception:
            self._logger.exception(
                "动态模型 round 日志解析任务提交失败："
                "round=%03d, serial=%s, logs_dir=%s",
                context.round_no,
                device_spec.serial,
                logs_dir,
            )

    @staticmethod
    def _build_round_logs_dir(context: RoundContext):
        """返回当前 round 的持续日志目录。"""

        round_dir = build_run_artifact_dir(
            output_dir=context.run_config.output_dir,
            round_no=context.round_no,
            use_round_dir=context.run_config.artifact_layout == "round",
        )

        return round_dir / "logs"

    def _build_round_task_context(
        self,
        *,
        context: RoundContext,
        device_spec: DeviceSpec,
    ) -> dict[str, Any]:
        """构建 round 日志解析、上传所需的上下文。"""

        return {
            "task_id": self._task_id,
            "serial": device_spec.serial,
            "round": context.round_no,
            "case": "__round_logs__",
            "step": "__round__",
        }

    @staticmethod
    def _get_main_device_spec(context: RoundContext) -> DeviceSpec:
        """获取运行配置中的主设备。"""

        device_specs = context.run_config.device_specs

        if not device_specs:
            raise RuntimeError(
                "动态模型 round 采集需要至少配置一个设备。"
                "请通过 --testbed NAME 指定测试床，或不要在无设备测试中加载动态模型 round 采集。"
            )

        device_spec = device_specs[0]
        for spec in device_specs:
            if spec.name == "main":
                device_spec = spec
                break

        return device_spec
