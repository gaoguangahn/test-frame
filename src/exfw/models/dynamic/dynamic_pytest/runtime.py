from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from exfw.models.dynamic.result import DynamicResultProcessor

from exfw.models.dynamic.capture.service import DynamicModelCaptureService
from .config import DynamicModelConfig


@dataclass
class DynamicModelRuntime:
    """动态模型 pytest 扩展运行期间共享的基础设施对象。"""

    task_id: str | None
    config: DynamicModelConfig
    capture_service: DynamicModelCaptureService
    case_result_reporter: DynamicResultProcessor | None
    recovery_required_serials: set[str] = field(default_factory=set)


DYNAMIC_MODEL_RUNTIME_KEY: pytest.StashKey[DynamicModelRuntime] = pytest.StashKey()


def get_dynamic_model_runtime(config: pytest.Config) -> DynamicModelRuntime:
    """获取已初始化的动态模型运行时对象。"""

    runtime = config.stash.get(DYNAMIC_MODEL_RUNTIME_KEY, None)

    if runtime is None:
        raise RuntimeError(
            "DynamicModelRuntime 未初始化。请确认动态模型 pytest 插件已加载。"
        )

    return runtime
