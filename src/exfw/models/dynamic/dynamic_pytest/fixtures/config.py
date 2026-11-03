from __future__ import annotations

from pathlib import Path

import pytest

from exfw.models.dynamic.dynamic_pytest.config import DynamicModelConfig
from exfw.models.dynamic.dynamic_pytest.runtime import get_dynamic_model_runtime
from exfw.pytest_framework.core.runtime import EXFW_RUN_CONFIG_KEY


@pytest.fixture(scope="session")
def dynamic_model_config(pytestconfig: pytest.Config) -> DynamicModelConfig:
    """获取动态模型 pytest 扩展配置。"""

    return get_dynamic_model_runtime(pytestconfig).config
