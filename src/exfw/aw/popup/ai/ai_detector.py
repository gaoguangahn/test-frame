import base64
import logging
from logging import Logger

import cv2
import numpy as np
import requests


class ImageDetector:
    """图片检测有叉号的弹窗"""

    def __init__(
        self,
        logger: Logger | None = None,
        popup_rank_threshold: int = 64,
        click_rank_threshold: int = 10,
    ):
        self.server_url = "http://10.163.80.200:7766/check_popup"

        self.logger = logger or logging.getLogger("exfw.ImageDetector")
        self.popup_rank_threshold = popup_rank_threshold
        self.click_rank_threshold = click_rank_threshold

    def detect(self, image: np.ndarray, scale_factor: float = 1.0):
        """检测图片中是否有叉号弹窗
        Args:
            image: 图片, np.ndarray 格式
            scale_factor: 图片相对屏幕的缩放比例，默认为 1.0
        Returns:
            click_coord: 点击坐标[x, y], None 表示没有找到。
            max_popup_rank: 叉号弹窗排名
            max_click_rank: 点击叉号弹窗排名
        """

        if not isinstance(image, np.ndarray):
            image = np.asarray(image)

        # 1. base64 转换
        _, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        image_b64 = base64.b64encode(buf.tobytes()).decode("utf8")

        # 2. 拼接请求
        data = {
            "img": image_b64,
            "app_name": "bilibili",
            "image_name": "frame_1",
            "direction": "vertical",
            "anti_button_text_dict": {
                "✖": ["修复", "修复客户端"],
                "⊗": ["修复", "修复客户端"],
            },
            "simple_popup": False,
            "x_ox_list_from_client": None,
            "how_to_use_button_template": "auto",
            "check_mode": "auto",
        }

        try:
            resp = requests.post(url=self.server_url, json=data, timeout=10)
            if resp.status_code != 200:
                return None, 0, 0
            response = resp.json()
        except Exception:
            return None, 0, 0

        max_popup_rank = 0
        max_click_rank = 0
        click_coord = None

        for cross in response:
            coord = cross.get("click_coord")
            popup_rank = cross.get("popup_rank", 0)
            click_rank = cross.get("click_rank", 0)

            if (
                coord
                and popup_rank > self.popup_rank_threshold
                and click_rank > self.click_rank_threshold
                and popup_rank > max_popup_rank
            ):
                max_popup_rank = popup_rank
                max_click_rank = click_rank
                original_x = int(coord[0] / scale_factor)
                original_y = int(coord[1] / scale_factor)
                click_coord = [original_x, original_y]

        return click_coord, max_popup_rank, max_click_rank


if __name__ == "__main__":
    import os

    import cv2
    import uiautomator2 as u2

    d = u2.connect_usb()
    image = d.screenshot(format="opencv")
    image = cv2.imread(r"C:\Users\g00031637\Desktop\20261026-150416.png")

    if not isinstance(image, np.ndarray):
        image = np.asarray(image)

    image = cv2.resize(image, dsize=(0, 0), fx=0.5, fy=0.5)
    detector = ImageDetector()
    click_coord, max_popup_rank, max_click_rank = detector.detect(
        image, scale_factor=0.5
    )
    print(click_coord, max_popup_rank, max_click_rank)
    # obj = d(text="打车")
    # d(text="模拟导航").click()
    # if obj.exists(timeout=5):
    #     info = obj.info
    #     bounds = info["bounds"]

    #     left = bounds["left"]
    #     top = bounds["top"]
    #     right = bounds["right"]
    #     bottom = bounds["bottom"]

    #     center_x = (left + right) // 2
    #     center_y = (top + bottom) // 2

    #     print(f"控件边界: left={left}, top={top}, right={right}, bottom={bottom}")
    #     print(f"控件中心点: x={center_x}, y={center_y}")
    # else:
    #     print("未找到“打车”控件")
