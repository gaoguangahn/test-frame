from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DynamicModelStepConfig:
    """动态模型步骤记录配置。"""

    screenshot: bool = True
    picture_dir: str = "pictures"
    filename_max_length: int = 80


@dataclass(frozen=True)
class DynamicModelConfig:
    """动态模型 pytest 扩展配置。"""

    steps: DynamicModelStepConfig = DynamicModelStepConfig()
    upload_enabled: bool = True


def load_dynamic_model_config(project_config: dict[str, Any]) -> DynamicModelConfig:
    """从项目配置中解析动态模型专属配置。"""

    raw_dynamic_config = project_config.get("test_models", {}).get("dynamic_model", {})

    if raw_dynamic_config is None:
        raw_dynamic_config = {}

    if not isinstance(raw_dynamic_config, dict):
        raise TypeError("配置 test_models.dynamic_model 必须是映射对象。")

    raw_steps_config = raw_dynamic_config.get("steps", {})
    if raw_steps_config is None:
        raw_steps_config = {}

    if not isinstance(raw_steps_config, dict):
        raise TypeError("配置 test_models.dynamic_model.steps 必须是映射对象。")

    return DynamicModelConfig(
        upload_enabled=_get_upload_enabled(raw_dynamic_config),
        steps=DynamicModelStepConfig(
            screenshot=_get_bool(raw_steps_config, "screenshot", True),
            picture_dir=_get_str(raw_steps_config, "picture_dir", "pictures"),
            filename_max_length=_get_int(raw_steps_config, "filename_max_length", 80),
        )
    )


def _get_upload_enabled(config: dict[str, Any]) -> bool:
    upload = config.get("upload", {})
    if not isinstance(upload, dict):
        raise TypeError("配置 test_models.dynamic_model.upload 必须是映射对象。")
    enabled = upload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise TypeError("配置 test_models.dynamic_model.upload.enabled 必须是布尔值。")
    return enabled


def _get_bool(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)

    if not isinstance(value, bool):
        raise TypeError(f"配置 test_models.dynamic_model.steps.{key} 必须是布尔值。")

    return value


def _get_str(config: dict[str, Any], key: str, default: str) -> str:
    value = config.get(key, default)

    if not isinstance(value, str) or not value:
        raise TypeError(
            f"配置 test_models.dynamic_model.steps.{key} 必须是非空字符串。"
        )

    return value


def _get_int(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)

    if not isinstance(value, int) or value < 1:
        raise TypeError(f"配置 test_models.dynamic_model.steps.{key} 必须是正整数。")

    return value
