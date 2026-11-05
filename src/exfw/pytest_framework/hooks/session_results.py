"""连接 pytest 会话生命周期与通用 session 结果存储。"""
import pytest

from exfw.pytest_framework.result.store import get_session_result_store


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    get_session_result_store(session.config).initialize()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus) -> None:
    get_session_result_store(session.config).finish(int(exitstatus))
