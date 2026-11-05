"""为每次用例运行绑定通用日志上下文。"""
import pytest
from exfw.pytest_framework.core.runtime import EXFW_CURRENT_ROUND_KEY
from exfw.pytest_framework.core.logging_setup import log_context


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    token = log_context.set({"case": item.nodeid, "round": item.config.stash.get(EXFW_CURRENT_ROUND_KEY, 1)})
    try:
        yield
    finally:
        log_context.reset(token)
