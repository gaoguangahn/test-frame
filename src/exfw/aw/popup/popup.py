import logging
from logging import Logger

import numpy as np
import uiautomator2 as u2

from .ai.ai_detector import ImageDetector
from .watcher.watcher_detector import WatcherDetector


class PopupDetector:
    def __init__(self, logger: Logger | None = None):
        self.logger = logger or logging.getLogger("exfw.PopupDetector")
        self.watcher_detector = WatcherDetector(self.logger)
        self.image_detector = ImageDetector(self.logger)

    def detect_watcher(self, device: u2.Device, watcher: list[dict] | None = None):
        """检测弹窗并返回动作
        Args:
            device: u2.Device, 设备对象
            watcher: list[dict], 要匹配的弹窗规则. Defaults to None.
            例子:[{"text":"升级", "action":{"type": "click", "target": {"text": "确定"}}}, {"description": "登录", "action": {"type": "back"}}]
        Returns:
            tuple[str, tuple[int, int]]
            返回动作类型和坐标, 类型 back/click/unknown, 坐标 (-1, -1)
        """

        return self.watcher_detector.detect(device=device, watcher=watcher)

    def detect_image(self, image: np.ndarray, scale_factor: float = 1.0):
        """检测图片中是否有叉号弹窗
        Args:
            image: 图片, np.ndarray 格式
            scale_factor: 图片相对屏幕的缩放比例，默认为 1.0
        Returns:
            click_coord: 点击坐标[x, y], None 表示没有找到。
            max_popup_rank: 叉号弹窗排名
            max_click_rank: 点击叉号弹窗排名
        """

        result = self.image_detector.detect(image=image, scale_factor=scale_factor)
        return result

    def detect(
        self,
        device: u2.Device,
        watcher: list[dict] | None = None,
        image: np.ndarray | None = None,
        scale_factor: float = 1.0,
    ):
        """统一检测入口

        优先使用 watcher 检测，失败后再使用图像检测。
        返回格式统一为:
        - back, (-1, -1)
        - click, (x, y)
        - unknown, (-1, -1)
        """

        result = self.detect_watcher(device=device, watcher=watcher)

        if result[0] != "unknown":
            return result

        if image is not None:
            click_coord, _, _ = self.detect_image(
                image=image, scale_factor=scale_factor
            )
            if click_coord is not None:
                return "click", tuple(click_coord)

        return "unknown", (-1, -1)
