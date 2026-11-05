from __future__ import annotations

import re
from collections.abc import Callable, Generator
from typing import Any

import cv2
import pytest

from exfw.aw.device import AdbDriver
from exfw.aw.keyboard import Keyboard
from exfw.pytest_framework import BaseTestCase, Step
from exfw.pytest_framework.result.store import get_session_result_store

from .action_stats import ActionStatsRecorder, instrument_device_actions
from .dynamic_pytest.config import DynamicModelConfig
from .services.page_verify import PopupWaiter
from .services.popup_handler import DynamicPopupHandler
from .capture.trace import DynamicTraceCollector


class DynamicCase(BaseTestCase):
    """动态模型测试基类。"""

    # 当前用例上传、解析等任务上下文
    dynamic_upload_context: dict[str, Any]
    dynamic_model_config: DynamicModelConfig
    action_stats: ActionStatsRecorder

    # 固定使用主设备
    device: AdbDriver

    # 设备交互辅助能力
    keyboard_factory: Callable[[Any], Keyboard]
    popup_handler: DynamicPopupHandler
    page_waiter: PopupWaiter
    tracer: DynamicTraceCollector

    @pytest.fixture(autouse=True)
    def _inject_dynamic_model_context(
        self,
        request: pytest.FixtureRequest,
        devices,
        dynamic_upload_context: dict[str, Any],
        dynamic_model_config: DynamicModelConfig,
        dynamic_capture_service,
        keyboard_factory: Callable[[Any], Keyboard],
        dynamic_pre_case_recovery: None,
    ) -> Generator[None, None, None]:
        """注入动态模型测试专属上下文与能力。"""
        try:
            raw_device: AdbDriver = devices["main"]
        except KeyError:
            pytest.fail(
                "动态模型用例需要名为 main 的主设备，但当前未找到。",
                pytrace=False,
            )

        def sync_action_stats(stats: dict[str, int]) -> None:
            dynamic_upload_context["action_stats"] = stats

        self.action_stats = ActionStatsRecorder(on_change=sync_action_stats)
        dynamic_upload_context["action_stats"] = self.action_stats.snapshot()

        with instrument_device_actions(raw_device, self.action_stats):
            self.device = raw_device
            self.dynamic_upload_context = dynamic_upload_context
            self.dynamic_model_config = dynamic_model_config
            self.tracer = dynamic_capture_service.create_tracer(
                case_name=request.node.name,
                round_no=self.current_round,
            )
            self._step_index = 0

            self.keyboard_factory = keyboard_factory

            # device 就绪后，创建当前用例专属的弹窗处理器。
            self.popup_handler = DynamicPopupHandler(device=self.device)
            self.page_waiter = PopupWaiter(
                device=self.device, popup_handler=self.popup_handler
            )

            try:
                yield
            finally:
                if getattr(request.node, "_dynamic_call_failed", False):
                    self.capture_failure_screenshot()

                action_stats = self.action_stats.snapshot()
                dynamic_upload_context["action_stats"] = action_stats
                get_session_result_store(request.config).update_case_extension(
                    self.current_round, self.case_artifacts.case_id, request.node.nodeid,
                    "dynamic_model", {"action_stats": action_stats},
                )

    def step(
        self, description: str, *, screenshot: bool | None = None, **extra: Any
    ) -> dict[str, Any]:
        """
        记录动态模型测试步骤。

        Args:
            description: 步骤描述。
            screenshot: 是否在记录步骤时截取当前页面。
            **extra: 要写入步骤记录的额外信息，例如 op_type、target。
        """

        self._step_index += 1

        if screenshot is None:
            screenshot = self.dynamic_model_config.steps.screenshot

        if screenshot:
            screenshot_path = self.capture_screenshot(
                description=description, step_index=self._step_index
            )

            if screenshot_path is not None:
                extra["screenshot_path"] = screenshot_path

        return Step(description, **extra)

    def capture_failure_screenshot(self) -> str | None:
        """用例失败时截取当前页面，保存到步骤图片目录。"""

        return self.capture_screenshot(
            description="用例失败",
            step_index=self._step_index + 1,
        )

    def capture_screenshot(self, *, description: str, step_index: int) -> str | None:
        """
        截取主设备当前页面。

        返回相对于当前用例产物目录的路径，便于产物归档、上传及报告展示。
        截图失败不影响测试执行。
        """

        picture_dir = (
            self.case_artifacts.case_dir / self.dynamic_model_config.steps.picture_dir
        )
        picture_dir.mkdir(parents=True, exist_ok=True)

        safe_description = self._safe_filename(
            description,
            max_length=self.dynamic_model_config.steps.filename_max_length,
        )
        picture_file = f"step_{step_index:03d}_{safe_description}.png"
        absolute_path = picture_dir / picture_file

        try:
            image = self.device.screenshot()

            if image is None:
                raise RuntimeError("设备截图结果为空")

            success, encoded_image = cv2.imencode(
                ".jpg",
                image,
                [cv2.IMWRITE_JPEG_QUALITY, 85],
            )

            if not success:
                raise RuntimeError("截图 PNG 编码失败")

            encoded_image.tofile(str(absolute_path))
        except Exception:
            self.test_logger.exception(
                "步骤截图失败：step=%s, description=%s", step_index, description
            )
            return None

        return str(absolute_path.relative_to(self.case_artifacts.case_dir))

    @staticmethod
    def _safe_filename(value: str, max_length: int = 80) -> str:
        """将步骤描述转换成安全文件名。"""

        filename = re.sub(r'[\\/:*?"<>|\s]+', "_", value).strip("_")
        return filename[:max_length] or "step"
