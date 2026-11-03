from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeAlias

import cv2
import numpy as np

ImageSource: TypeAlias = str | Path | bytes | np.ndarray


@dataclass(frozen=True)
class TemplateMatchResult:
    """模板匹配结果。"""

    found: bool
    center_x: int
    center_y: int
    score: float
    scale: float
    template_width: int
    template_height: int

    def to_dict(self) -> dict[str, int | float | bool]:
        return asdict(self)


class TemplateMatchCapability:
    """AW 图像模板定位能力。"""

    @classmethod
    def load_template(
        cls,
        template_path: str | Path,
    ) -> np.ndarray:
        """
        从固定模板路径加载灰度图片。

        建议业务层在初始化时加载一次并缓存模板，
        后续直接将 ndarray 传入 locate_exist()。
        """
        return cls._read_image(template_path)

    @classmethod
    def exists(
        cls,
        *,
        image: ImageSource,
        template: ImageSource,
        threshold: float = 0.45,
        downscale: float = 0.7,
        match_score: float = 0.95,
        multi_scale: bool = False,
    ) -> bool:
        """
        判断待匹配图片中是否存在目标模板。

        Args:
            image: 待匹配图片，支持路径、bytes 或 np.ndarray。
            template: 模板图片，支持路径、bytes 或 np.ndarray。
            threshold: 最低匹配分数，低于该值视为不存在。
            downscale: 待匹配图片缩放比例，用于加速。
            match_score: 多尺度匹配提前结束分数。
            multi_scale: 是否启用多尺度匹配。

        Returns:
            模板匹配分数达到 threshold 时返回 True，否则返回 False。
        """

        result = cls.locate(
            image=image,
            template=template,
            threshold=threshold,
            downscale=downscale,
            match_score=match_score,
            multi_scale=multi_scale,
        )

        return bool(result["found"])

    @classmethod
    def locate(
        cls,
        *,
        image: ImageSource,
        template: ImageSource,
        threshold: float = 0.45,
        downscale: float = 0.7,
        match_score: float = 0.95,
        multi_scale: bool = False,
    ) -> dict[str, int | float | bool]:
        """
        在待匹配图片中定位模板。

        Args:
            image:
                待匹配图片，支持图片路径、图片 bytes 或 np.ndarray。

            template:
                模板图片，支持图片路径、图片 bytes 或 np.ndarray。

            threshold:
                最低匹配分数，低于该值视为未找到。

            downscale:
                待匹配图片缩放比例，用于加速。

            match_score:
                多尺度匹配时，达到该分数即提前结束。

            multi_scale:
                是否启用多尺度匹配。

        Returns:
            包含 found、center_x、center_y、score、scale 等字段。
        """
        cls._validate_args(
            threshold=threshold,
            downscale=downscale,
            match_score=match_score,
        )

        image_gray = cls._to_gray_image(
            image,
            source_name="待匹配图片",
        )

        template_gray = cls._to_gray_image(
            template,
            source_name="模板图片",
        )

        result = cls._locate(
            template=template_gray,
            image=image_gray,
            multi_scale=multi_scale,
            threshold=threshold,
            downscale=downscale,
            match_score=match_score,
        )

        return result.to_dict()

    @staticmethod
    def _read_image(
        path: str | Path,
    ) -> np.ndarray:
        """从本地路径读取灰度图片。"""
        image_path = Path(path)

        if not image_path.is_file():
            raise FileNotFoundError(f"文件不存在：{image_path}")

        image = cv2.imread(
            str(image_path),
            cv2.IMREAD_GRAYSCALE,
        )

        if image is None or image.size == 0:
            raise ValueError(f"无法读取图片：{image_path}")

        return image

    @classmethod
    def _to_gray_image(
        cls,
        source: ImageSource,
        source_name: str,
    ) -> np.ndarray:
        """
        将路径、二进制图片或 ndarray 统一转换为灰度图。

        支持：
        - str / Path；
        - bytes；
        - np.ndarray。
        """
        if isinstance(source, (str, Path)):
            return cls._read_image(source)

        if isinstance(source, bytes):
            return cls._decode_image_bytes(
                image_bytes=source,
                source_name=source_name,
            )

        if isinstance(source, np.ndarray):
            return cls._convert_to_gray(
                image=source,
                source_name=source_name,
            )

        raise TypeError(
            f"{source_name}类型不支持："
            f"{type(source).__name__}。"
            "仅支持 str、Path、bytes 或 np.ndarray。"
        )

    @staticmethod
    def _decode_image_bytes(
        image_bytes: bytes,
        source_name: str,
    ) -> np.ndarray:
        """将 PNG/JPEG 等图片二进制数据解码为灰度图。"""
        if not image_bytes:
            raise ValueError(f"{source_name}二进制数据为空。")

        image_buffer = np.frombuffer(
            image_bytes,
            dtype=np.uint8,
        )

        image = cv2.imdecode(
            image_buffer,
            cv2.IMREAD_GRAYSCALE,
        )

        if image is None or image.size == 0:
            raise ValueError(f"无法解码{source_name}二进制数据。")

        return image

    @staticmethod
    def _convert_to_gray(
        image: np.ndarray,
        source_name: str,
    ) -> np.ndarray:
        """将 OpenCV ndarray 图片统一转换为灰度图。"""
        if image.size == 0:
            raise ValueError(f"{source_name}不能为空图片。")

        if image.ndim == 2:
            return image

        if image.ndim != 3:
            raise ValueError(
                f"{source_name}维度不支持：shape={image.shape}。"
                "仅支持二维灰度图或三维彩色图。"
            )

        channel_count = image.shape[2]

        if channel_count == 1:
            return image[:, :, 0]

        if channel_count == 3:
            return cv2.cvtColor(
                image,
                cv2.COLOR_BGR2GRAY,
            )

        if channel_count == 4:
            return cv2.cvtColor(
                image,
                cv2.COLOR_BGRA2GRAY,
            )

        raise ValueError(
            f"{source_name}通道数不支持："
            f"channels={channel_count}。"
            "仅支持 1、3、4 通道图片。"
        )

    @staticmethod
    def _validate_args(
        *,
        threshold: float,
        downscale: float,
        match_score: float,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold 必须在 [0, 1] 范围内。")

        if not 0.0 < downscale <= 1.0:
            raise ValueError("downscale 必须在 (0, 1] 范围内。")

        if not 0.0 <= match_score <= 1.0:
            raise ValueError("match_score 必须在 [0, 1] 范围内。")

    @staticmethod
    def _sobel_edge(
        image: np.ndarray,
    ) -> np.ndarray:
        """提取 Sobel 边缘图。"""
        gx = cv2.Sobel(
            image,
            cv2.CV_32F,
            1,
            0,
            ksize=3,
        )

        gy = cv2.Sobel(
            image,
            cv2.CV_32F,
            0,
            1,
            ksize=3,
        )

        magnitude = cv2.magnitude(gx, gy)

        normalized = np.empty(
            magnitude.shape,
            dtype=np.uint8,
        )

        cv2.normalize(
            magnitude,
            normalized,
            alpha=0,
            beta=255,
            norm_type=cv2.NORM_MINMAX,
            dtype=cv2.CV_8U,
        )

        return normalized

    @staticmethod
    def _build_scales(
        *,
        multi_scale: bool,
    ) -> list[float]:
        """构造模板缩放比例列表。"""
        if not multi_scale:
            return [1.0]

        return [
            1.0,
            0.95,
            1.05,
            0.9,
            1.1,
            0.85,
            1.15,
            0.8,
            1.2,
        ]

    @classmethod
    def _locate(
        cls,
        *,
        template: np.ndarray,
        image: np.ndarray,
        multi_scale: bool,
        threshold: float,
        downscale: float,
        match_score: float,
    ) -> TemplateMatchResult:
        """执行模板匹配。"""
        image_height, image_width = image.shape[:2]
        template_height, template_width = template.shape[:2]

        if downscale < 1.0:
            image_resized = cv2.resize(
                image,
                None,
                fx=downscale,
                fy=downscale,
                interpolation=cv2.INTER_AREA,
            )
        else:
            image_resized = image

        resized_height, resized_width = image_resized.shape[:2]

        # 使用实际缩放后的图片尺寸，规避 resize 的取整误差。
        scale_x = resized_width / image_width
        scale_y = resized_height / image_height

        image_edge = cls._sobel_edge(image_resized)
        scales = cls._build_scales(multi_scale=multi_scale)

        best_result: TemplateMatchResult | None = None

        for scale in scales:
            scaled_width = max(
                1,
                round(template_width * scale * scale_x),
            )

            scaled_height = max(
                1,
                round(template_height * scale * scale_y),
            )

            if scaled_width > resized_width or scaled_height > resized_height:
                continue

            interpolation = (
                cv2.INTER_AREA
                if (scaled_width <= template_width and scaled_height <= template_height)
                else cv2.INTER_LINEAR
            )

            template_scaled = cv2.resize(
                template,
                (scaled_width, scaled_height),
                interpolation=interpolation,
            )

            template_edge = cls._sobel_edge(template_scaled)

            min_edge_pixel_count = min(
                10,
                max(1, template_edge.size // 20),
            )

            if cv2.countNonZero(template_edge) < min_edge_pixel_count:
                continue

            matched = cv2.matchTemplate(
                image_edge,
                template_edge,
                cv2.TM_CCOEFF_NORMED,
            )

            _, max_score, _, max_location = cv2.minMaxLoc(matched)

            if max_score < threshold:
                continue

            x_left, y_top = max_location

            center_x = round((x_left + scaled_width / 2) / scale_x)

            center_y = round((y_top + scaled_height / 2) / scale_y)

            center_x = max(
                0,
                min(center_x, image_width - 1),
            )

            center_y = max(
                0,
                min(center_y, image_height - 1),
            )

            candidate = TemplateMatchResult(
                found=True,
                center_x=center_x,
                center_y=center_y,
                score=float(max_score),
                scale=scale,
                template_width=max(
                    1,
                    round(template_width * scale),
                ),
                template_height=max(
                    1,
                    round(template_height * scale),
                ),
            )

            if multi_scale and max_score >= match_score:
                return candidate

            if best_result is None or candidate.score > best_result.score:
                best_result = candidate

        if best_result is not None:
            return best_result

        return TemplateMatchResult(
            found=False,
            center_x=-1,
            center_y=-1,
            score=-1.0,
            scale=-1.0,
            template_width=0,
            template_height=0,
        )
