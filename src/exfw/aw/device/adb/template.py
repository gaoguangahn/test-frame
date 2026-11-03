from pathlib import Path
from typing import ClassVar

import numpy as np

from exfw.aw.cv.template_match import TemplateMatchCapability

from .base.mixin_base import AdbMixinBase


class AdbTemplateMatchMixin(AdbMixinBase):
    """ADB 设备模板匹配能力。"""

    _template_cache: ClassVar[dict[str, np.ndarray]] = {}

    def locate_template(
        self,
        template_path: str | Path,
        *,
        threshold: float = 0.45,
        downscale: float = 0.7,
        match_score: float = 0.95,
        multi_scale: bool = False,
    ) -> dict[str, int | float | bool]:
        """
        在当前设备截图中定位指定模板。

        模板会按绝对路径缓存，同一个模板文件只会读取一次。

        Args:
            template_path: 模板文件路径。
            threshold: 最低匹配分数，低于该值表示未找到。
            downscale: 截图缩放比例，用于加速匹配。
            match_score: 多尺度匹配提前结束阈值。
            multi_scale: 是否启用多尺度匹配。

        Returns:
            模板匹配结果，例如：

            {
                "found": True,
                "center_x": 500,
                "center_y": 800,
                "score": 0.98,
                "scale": 1.0,
                "template_width": 120,
                "template_height": 80,
            }
        """
        screenshot = self.screenshot()
        template = self._get_template(template_path)

        return TemplateMatchCapability.locate_exist(
            image=screenshot,
            template=template,
            threshold=threshold,
            downscale=downscale,
            match_score=match_score,
            multi_scale=multi_scale,
        )

    def template_exists(
        self,
        template_path: str | Path,
        *,
        threshold: float = 0.45,
        downscale: float = 0.7,
        match_score: float = 0.95,
        multi_scale: bool = False,
    ) -> bool:
        """判断当前截图中是否存在指定模板。"""
        result = self.locate_template(
            template_path,
            threshold=threshold,
            downscale=downscale,
            match_score=match_score,
            multi_scale=multi_scale,
        )

        return bool(result["found"])

    @classmethod
    def clear_template_cache(cls) -> None:
        """清空模板缓存。通常仅在模板文件被动态修改时使用。"""
        cls._template_cache.clear()

    @classmethod
    def _get_template(
        cls,
        template_path: str | Path,
    ) -> np.ndarray:
        """获取缓存模板；缓存不存在时从磁盘加载。"""
        path = str(Path(template_path).resolve())

        if path not in cls._template_cache:
            cls._template_cache[path] = TemplateMatchCapability.load_template(path)

        return cls._template_cache[path]
