from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

import cv2

from exfw.aw.cv.template_match import TemplateMatchCapability
from exfw.aw.device import AdbDriver

VerifyFailedHandler = Callable[[], bool | None]
Verifier = Callable[[], bool]


class CommonWaiter:
    """通用页面等待与验证器，支持 UI 元素和模板图片验证。"""

    def __init__(
        self,
        device: AdbDriver,
        *,
        logger: logging.Logger | None = None,
    ):
        self.device = device
        self.logger = logger or logging.getLogger("exfw.PageWaiter")

    def wait_ui(
        self,
        judge_elements: dict,
        *,
        timeout: float = 5.0,
        interval: float = 1.0,
        on_failed: VerifyFailedHandler | None = None,
    ) -> bool:
        """
        等待 UI 元素满足预期。

        Args:
            judge_elements: 传给 device.check_page_elements() 的元素条件。
            timeout: 最大等待时长，单位：秒。
            interval: 每轮验证之间的等待间隔，单位：秒。
            on_failed: 单次 UI 验证失败后的回调。可用于处理弹窗、返回上一页、刷新页面等。
        """

        if not judge_elements:
            raise ValueError("judge_elements 不能为空")

        return self._wait(
            verifier=lambda: self.device.check_page_elements(**judge_elements),
            verify_name=f"UI元素验证 judge={judge_elements}",
            timeout=timeout,
            interval=interval,
            on_failed=on_failed,
        )

    def wait_template(
        self,
        template_path: str,
        *,
        timeout: float = 5,
        interval: float = 1,
        score_threshold: float = 0.7,
        on_failed: VerifyFailedHandler | None = None,
    ) -> bool:
        """
        等待模板图片匹配成功。

        Args:
            template_paths: 模板路径或模板路径列表。
            timeout: 最大等待时长，单位：秒。
            interval: 每轮验证之间的等待间隔，单位：秒。
            score_threshold: 模板匹配分数阈值。
            on_failed: 单次模板验证失败后执行的回调。
        """

        if not os.path.exists(template_path):
            msg = f"模板不存在：{template_path}"
            self.logger.warning(msg)
            raise ValueError(msg)

        return self._wait(
            verifier=lambda: self._match_template(
                template_path, score_threshold=score_threshold
            ),
            verify_name=f"模板验证: {template_path}",
            timeout=timeout,
            interval=interval,
            on_failed=on_failed,
        )

    def _wait(
        self,
        *,
        verifier: Verifier,
        verify_name: str,
        timeout: float,
        interval: float,
        on_failed: VerifyFailedHandler | None,
    ) -> bool:
        """
        通用等待流程：

        1. 验证目标是否满足；
        2. 若失败，执行调用方传入的回调；
        3. 回调执行后立即复检；
        4. 未成功则等待 interval 后重试。
        """

        if timeout <= 0:
            raise ValueError(f"timeout 必须大于 0，当前值：{timeout}")

        if interval <= 0:
            raise ValueError(f"interval 必须大于 0，当前值：{interval}")

        start_time = time.monotonic()
        attempt = 0

        while time.monotonic() - start_time < timeout:
            attempt += 1

            # 1. 优先验证目标是否已经满足。
            if verifier():
                self.logger.debug(f"页面验证通过：{verify_name}")
                return True

            # 2. 验证失败后，执行调用方传入的任意逻辑。
            if on_failed is not None:
                try:
                    on_failed()
                except Exception as error:
                    self.logger.warning(
                        "页面验证回调异常：%s，error=%s", verify_name, error
                    )
                    raise

            # 4. 等待时长。
            time.sleep(interval)

        self.logger.error(
            "页面验证失败：%s，timeout=%.2fs，attempt=%s", verify_name, timeout, attempt
        )
        return False

    def _match_template(self, template_path: str, *, score_threshold: float) -> bool:
        """检查当前页面是否匹配模板。"""

        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)

        if template is None:
            msg = f"【模板验证】模板加载失败：{template_path}"
            self.logger.warning(msg)
            raise ValueError(msg)

        height, width = template.shape[:2]

        if width < 4 or height < 4:
            msg = f"【模板验证】模板尺寸过小：{template_path}, width={width}, height={height}"
            self.logger.warning(msg)
            raise ValueError(msg)

        resized_template = cv2.resize(template, (width // 2, height // 2))

        screenshot = self.device.screenshot(scale_factor=0.5)

        if screenshot is None:
            self.logger.warning("页面验证截图失败")
            return False

        screen_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

        try:
            result = TemplateMatchCapability.exists(
                template=resized_template, image=screen_gray, threshold=score_threshold
            )
        except Exception as error:
            msg = f"页面验证模板匹配异常：template={template_path}, error={error}"
            self.logger.warning(msg)
            raise

        return result
