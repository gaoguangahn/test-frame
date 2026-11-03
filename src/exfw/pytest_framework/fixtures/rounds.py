from __future__ import annotations

import pytest

from exfw.pytest_framework.core.runtime import EXFW_CURRENT_ROUND_KEY


@pytest.fixture(scope="function")
def current_round(pytestconfig: pytest.Config) -> int:
    """
    获取当前执行轮次。

    未启用多轮执行时，默认使用第 1 轮。
    """
    return pytestconfig.stash.get(EXFW_CURRENT_ROUND_KEY, 1)
