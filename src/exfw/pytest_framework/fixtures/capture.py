from __future__ import annotations

import pytest

from exfw.aw.trace import TraceCollector
from exfw.pytest_framework.capture.manager import (
    LogcatManager,
    get_or_create_logcat_manager,
    get_or_create_trace_collector,
)


@pytest.fixture(scope="session")
def logcat_manager(pytestconfig: pytest.Config) -> LogcatManager:
    """获取 pytest 会话共享的 LogcatManager。"""
    return get_or_create_logcat_manager(pytestconfig)


@pytest.fixture(scope="session")
def trace_collector(pytestconfig: pytest.Config) -> TraceCollector:
    """获取 pytest 会话共享的 TraceCollector。"""
    return get_or_create_trace_collector(pytestconfig)
