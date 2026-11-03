from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

import cv2

from exfw.aw.cv.template_match import TemplateMatchCapability
from exfw.aw.device import AdbDriver

from .popup_handler import DynamicPopupHandler

Verifier = Callable[[], bool]


class PopupWaiter:
    """带自动弹窗处理能力的页面等待与验证器。"""

    def __init__(
        self,
        device: AdbDriver,
        popup_handler: DynamicPopupHandler,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.device = device
        self.popup_handler = popup_handler
        self.logger = logger or logging.getLogger("exfw.PopupWaiter")

    def wait_activity(
        self,
        activity: str,
        *,
        timeout: float = 5.0,
        interval: float = 1.0,
        watcher: list[dict[str, Any]] | None = None,
        cv: bool = False,
    ) -> bool:
        """
        等待当前顶层 Activity 切换为目标 Activity。

        Args:
            activity: 目标 Activity 全限定类名。
            timeout: 最大等待时长，单位：秒。
            interval: 每轮验证之间的等待间隔，单位：秒。
            watcher: Android 控件弹窗规则。
            cv: watcher 未命中时，是否启用图片弹窗检测。

        Returns:
            Activity 匹配成功返回 True；超时未成功返回 False。
        """

        if not activity:
            raise ValueError("activity 不能为空")

        return self._wait(
            verifier=lambda: self._check_activity(activity),
            verify_name=f"Activity验证 activity={activity}",
            timeout=timeout,
            interval=interval,
            watcher=watcher,
            cv=cv,
        )

    def wait_ui(
        self,
        judge_elements: dict,
        *,
        timeout: float = 5.0,
        interval: float = 1.0,
        watcher: list[dict[str, Any]] | None = None,
        cv: bool = False,
    ) -> bool:
        """
        等待 UI 元素满足预期，失败时自动检测并处理弹窗。

        Args:
            judge_elements: 传给 device.check_page_elements() 的元素条件。
            timeout: 最大等待时长，单位：秒。
            interval: 每轮验证之间的等待间隔，单位：秒。
            watcher: Android 控件弹窗规则。
            cv: watcher 未命中时，是否启用图片弹窗检测。

        Returns:
            页面验证成功返回 True；超时未成功返回 False。
        """

        if not judge_elements:
            raise ValueError("judge_elements 不能为空")

        return self._wait(
            verifier=lambda: self.device.check_page_elements(**judge_elements),
            verify_name=f"UI元素验证 judge={judge_elements}",
            timeout=timeout,
            interval=interval,
            watcher=watcher,
            cv=cv,
        )

    def wait_template(
        self,
        template_path: str,
        *,
        timeout: float = 5.0,
        interval: float = 1.0,
        score_threshold: float = 0.7,
        watcher: list[dict[str, Any]] | None = None,
        cv: bool = False,
    ) -> bool:
        """
        等待模板图片匹配成功，失败时自动检测并处理弹窗。

        Args:
            template_path: 目标模板路径。
            timeout: 最大等待时长，单位：秒。
            interval: 每轮验证之间的等待间隔，单位：秒。
            score_threshold: 模板匹配最低分数阈值。
            watcher: Android 控件弹窗规则。
            cv: watcher 未命中时，是否启用图片弹窗检测。

        Returns:
            模板匹配成功返回 True；超时未成功返回 False。
        """

        if not os.path.isfile(template_path):
            msg = f"模板不存在或不是文件：{template_path}"
            self.logger.warning(msg)
            raise ValueError(msg)

        return self._wait(
            verifier=lambda: self._match_template(
                template_path=template_path,
                score_threshold=score_threshold,
            ),
            verify_name=f"模板验证 template={template_path}",
            timeout=timeout,
            interval=interval,
            watcher=watcher,
            cv=cv,
        )

    def _wait(
        self,
        *,
        verifier: Verifier,
        verify_name: str,
        timeout: float,
        interval: float,
        watcher: list[dict[str, Any]] | None,
        cv: bool,
    ) -> bool:
        """
        等待并验证页面。

        验证流程：
        1. 执行页面验证；
        2. 验证成功则结束；
        3. 验证失败后处理弹窗；
        5. 未成功则等待 interval 后重试。
        """

        if timeout <= 0:
            raise ValueError(f"timeout 必须大于 0，当前值：{timeout}")

        if interval <= 0:
            raise ValueError(f"interval 必须大于 0，当前值：{interval}")

        start_time = time.monotonic()
        attempt = 0
        consecutive_failures = 0

        while time.monotonic() - start_time < timeout:
            attempt += 1

            # 1. 先验证当前页面是否已满足目标条件。
            if verifier():
                self.logger.debug("页面验证通过：name=%s", verify_name)
                return True

            # 2. 验证失败后，检测并尝试处理弹窗。
            consecutive_failures += 1
            if consecutive_failures == 2:
                consecutive_failures = 0
                try:
                    self.popup_handler.handle(watcher=watcher, cv=cv)
                except Exception as error:
                    self.logger.warning(
                        "弹窗处理异常：name=%s，error=%s", verify_name, error
                    )
                    raise

            time.sleep(interval)

        self.logger.error(
            "页面验证超时失败：name=%s，timeout=%.2fs，attempt=%s",
            verify_name,
            timeout,
            attempt,
        )
        return False

    def _match_template(
        self,
        *,
        template_path: str,
        score_threshold: float,
    ) -> bool:
        """检查当前截图是否匹配目标模板。"""

        template = cv2.imread(
            template_path,
            cv2.IMREAD_GRAYSCALE,
        )

        if template is None:
            msg = f"【模板验证】模板加载失败：{template_path}"
            self.logger.warning(msg)
            raise ValueError(msg)

        height, width = template.shape[:2]

        if width < 4 or height < 4:
            msg = (
                f"【模板验证】模板尺寸过小：{template_path}, "
                f"width={width}, height={height}"
            )
            self.logger.warning(msg)
            raise ValueError(msg)

        resized_template = cv2.resize(
            template,
            (width // 2, height // 2),
            interpolation=cv2.INTER_AREA,
        )

        screenshot = self.device.screenshot(scale_factor=0.5)

        if screenshot is None:
            self.logger.warning("【模板验证】页面截图失败")
            return False

        try:
            return TemplateMatchCapability.exists(
                image=screenshot,
                template=resized_template,
                threshold=score_threshold,
                downscale=1.0,
            )
        except Exception as error:
            msg = f"【模板验证】模板匹配异常：template={template_path}, error={error}"
            self.logger.warning(msg)
            raise

    def _check_activity(self, expected_activity: str) -> bool:
        """检查当前顶层 Activity 是否为目标 Activity。"""

        _, current_activity = self.device.top_activity()

        self.logger.debug(
            "Activity 检查：expected=%s，current=%s",
            expected_activity,
            current_activity,
        )

        return current_activity == expected_activity
