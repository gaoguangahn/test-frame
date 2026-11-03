from __future__ import annotations

import logging
import time
from typing import Any

from exfw.aw.device import AdbDriver
from exfw.aw.popup import PopupDetector


class DynamicPopupHandler:
    """动态模型场景的弹窗检测与自动处理器。"""

    def __init__(self, device: AdbDriver) -> None:
        self.device = device
        self.popup_detector = PopupDetector()
        self.logger = logging.getLogger(__name__)

    @property
    def _u2_device(self):
        return self.device.device

    def handle(
        self, watcher: list[dict[str, Any]] | None = None, cv: bool = False
    ) -> bool:
        """
        检测并自动处理当前页面弹窗。

        检测优先级：
        1. watcher 命中 click / back：执行对应动作；
        2. watcher 命中 cv：执行一次 CV 弹窗处理；
        3. watcher 未命中且 cv=True：执行一次 CV 弹窗处理。
        """

        if watcher:
            action, coord = self.popup_detector.detect_watcher(
                device=self._u2_device, watcher=watcher
            )

            if action != "unknown":
                if action == "cv":
                    self.logger.info("watcher 命中，触发一次 CV 弹窗检测")
                    return self._handle_cv_popup()

                self._execute_action(action=action, coord=coord, source="watcher")
                return True

        if cv:
            return self._handle_cv_popup()

        return False

    def handle_continuously(
        self,
        watcher: list[dict[str, Any]] | None = None,
        cv: bool = False,
        *,
        timeout: float = 5.0,
        interval: float = 0.5,
    ) -> int:
        """
        在指定时间内按固定间隔持续尝试处理弹窗。

        适用于 App 启动后连续弹出多个弹窗，或弹窗延迟几秒才出现的场景。
        该方法不会因为某一次未检测到弹窗就提前结束，而是一直检测到 timeout。
        每次检测只执行一次轻量 watcher 检测；仅当 cv=True 时才会在 watcher
        未命中后执行截图/CV 兜底。

        Args:
            watcher: Android 控件弹窗规则。
            cv: watcher 未命中时，是否启用图片弹窗检测。
            timeout: 最长连续处理时长，单位秒。
            interval: 两次检测之间的等待间隔，单位秒。

        Returns:
            int: 本轮连续处理中成功处理的弹窗数量。
        """

        if timeout <= 0:
            raise ValueError(f"timeout 必须大于 0，当前值：{timeout}")

        if interval <= 0:
            raise ValueError(f"interval 必须大于 0，当前值：{interval}")

        handled_count = 0
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if self.handle(watcher=watcher, cv=cv):
                handled_count += 1

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            time.sleep(min(interval, remaining))

        if handled_count:
            self.logger.info("连续弹窗处理完成：handled=%s", handled_count)

        return handled_count

    def _handle_cv_popup(self) -> bool:
        """执行一次 CV 弹窗检测与关闭。"""

        image = self.device.screenshot()

        click_coord, _, _ = self.popup_detector.detect_image(image=image)

        if click_coord is None:
            self.logger.info("CV 未检测到可处理的弹窗关闭按钮")
            return False

        x, y = click_coord

        self._execute_action(action="click", coord=(int(x), int(y)), source="cv")

        return True

    def _execute_action(
        self, *, action: str, coord: tuple[int, int], source: str
    ) -> None:
        """执行弹窗处理动作。"""

        if action == "back":
            self.logger.info("检测到弹窗，执行返回关闭：source=%s", source)
            self.device.back()
            return

        if action == "click":
            x, y = coord

            self.logger.info(
                "检测到弹窗，执行坐标点击：source=%s, x=%s, y=%s", source, x, y
            )
            self.device.click(point=(x, y))
            return

        self.logger.warning(
            "弹窗检测返回了不支持的动作：source=%s, action=%s", source, action
        )
