from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, Literal

import cv2
import numpy as np
import requests


@dataclass(frozen=True)
class OcrResult:
    """单条 OCR 识别结果。"""

    text: str
    score: float
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center_x(self) -> float:
        """文本区域中心点 X 坐标。"""
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        """文本区域中心点 Y 坐标。"""
        return (self.top + self.bottom) / 2


class OcrRecognizer:
    """OCR 识别与文字坐标定位能力。"""

    OCR_SERVER_URL = "http://10.163.75.254:5555/predict"

    logger = logging.getLogger("exfw.OcrRecognizer")

    @classmethod
    def recognize(
        cls, image: np.ndarray, *, scale_factor: float = 1.0, timeout: float = 10
    ) -> list[OcrResult]:
        """
        识别 OpenCV 图片中的全部文字。

        Args:
            image: OpenCV 图片，通常是 BGR 格式的 numpy.ndarray。
            scale_factor: 图片相对原始设备截图的缩放比例。
            timeout: OCR 服务请求超时时间，单位秒。

        Returns:
            返回已还原至原始设备坐标系的 OCR 结果列表。
        """

        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            cls.logger.warning("【OCR】传入图片为空，跳过识别")
            return []

        if scale_factor <= 0:
            raise ValueError(f"scale_factor 必须大于 0，当前值：{scale_factor}")

        image_base64 = cls._encode_image(image)

        if image_base64 is None:
            return []

        try:
            response = requests.post(
                cls.OCR_SERVER_URL,
                json={"img": image_base64},
                timeout=timeout,
            )
            response.raise_for_status()
            raw_results = response.json()

        except requests.RequestException as error:
            cls.logger.warning("【OCR】请求失败：%s", error)
            return []

        except ValueError as error:
            cls.logger.warning("【OCR】响应 JSON 解析失败：%s", error)
            return []

        if not isinstance(raw_results, list):
            cls.logger.warning(
                "【OCR】响应格式异常，期望 list，实际：%s",
                type(raw_results).__name__,
            )
            return []

        results = []

        for item in raw_results:
            result = cls._parse_result(
                item,
                scale_factor=scale_factor,
            )

            if result is not None:
                results.append(result)

        cls.logger.debug("【OCR】识别完成，结果数量：%s", len(results))
        return results

    @classmethod
    def locate_text(
        cls,
        text: str,
        *,
        image: np.ndarray,
        scale_factor: float = 1.0,
        match_mode: Literal["exact", "contains"] = "exact",
        score_threshold: float = 0.85,
        timeout: float = 10,
    ) -> OcrResult | None:
        """
        在 OpenCV 图片中查找目标文字，返回置信度最高的结果。

        Args:
            text: 要查找的目标文本。
            image: OpenCV 图片。
            scale_factor: 图片相对设备原图的缩放比例。
            match_mode:
                - exact：OCR 文本与目标文本完全一致；
                - contains：OCR 文本包含目标文本。
            score_threshold: OCR 文本的最低置信度。
            timeout: OCR 请求超时时间，单位秒。
        """

        target_text = text.strip()

        if not target_text:
            cls.logger.warning("【OCR】目标文本为空，无法定位")
            return None

        if match_mode not in {"exact", "contains"}:
            raise ValueError(
                f"不支持的 match_mode：{match_mode}，仅支持 exact / contains"
            )

        results = cls.recognize(
            image,
            scale_factor=scale_factor,
            timeout=timeout,
        )

        matched_results = [
            result
            for result in results
            if result.score >= score_threshold
            and cls._is_text_matched(
                target_text=target_text,
                recognized_text=result.text,
                match_mode=match_mode,
            )
        ]

        if not matched_results:
            cls.logger.debug(
                "【OCR】未找到目标文字：text=%r，mode=%s，threshold=%.2f",
                target_text,
                match_mode,
                score_threshold,
            )
            return None

        best_result = max(matched_results, key=lambda result: result.score)

        cls.logger.debug(
            "【OCR】定位成功：text=%r，recognized=%r，score=%.3f，center=(%.1f, %.1f)",
            target_text,
            best_result.text,
            best_result.score,
            best_result.center_x,
            best_result.center_y,
        )

        return best_result

    @classmethod
    def _encode_image(cls, image: np.ndarray) -> str | None:
        """将 OpenCV 图片编码为 JPEG Base64。"""

        try:
            success, buffer = cv2.imencode(
                ".jpg",
                image,
                [cv2.IMWRITE_JPEG_QUALITY, 90],
            )

            if not success:
                cls.logger.warning("【OCR】图片 JPEG 编码失败")
                return None

            return base64.b64encode(buffer.tobytes()).decode("utf-8")

        except cv2.error as error:
            cls.logger.warning("【OCR】图片编码异常：%s", error)
            return None

    @classmethod
    def _parse_result(
        cls,
        item: Any,
        *,
        scale_factor: float,
    ) -> OcrResult | None:
        """解析 OCR 服务返回的单条结果。"""

        try:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                return None

            text = str(item[0]).strip()
            score = float(item[1])

            # 服务格式兼容：
            # item[-1][0] = [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
            points = item[-1]
            if not text or not isinstance(points, list) or len(points) < 3:
                return None

            point0 = points[0]
            point2 = points[2]

            left = min(point0[0], point2[0]) / scale_factor
            top = min(point0[1], point2[1]) / scale_factor
            right = max(point0[0], point2[0]) / scale_factor
            bottom = max(point0[1], point2[1]) / scale_factor

            return OcrResult(
                text=text,
                score=score,
                left=left,
                top=top,
                right=right,
                bottom=bottom,
            )

        except (TypeError, ValueError, IndexError):
            return None

    @staticmethod
    def _is_text_matched(
        *,
        target_text: str,
        recognized_text: str,
        match_mode: Literal["exact", "contains"],
    ) -> bool:
        """判断识别文本是否符合匹配规则。"""

        normalized_text = recognized_text.strip()

        if match_mode == "exact":
            return normalized_text == target_text

        return target_text in normalized_text


if __name__ == "__main__":
    import cv2
    import uiautomator2 as u2

    d = u2.connect_usb()
    image = d.screenshot(format="opencv")

    if not isinstance(image, np.ndarray):
        image = np.asarray(image)

    image = cv2.resize(image, dsize=(0, 0), fx=0.5, fy=0.5)
    result = OcrRecognizer.locate_text(
        text="确认协议并开通", image=image, match_mode="contains"
    )
