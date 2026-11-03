# pytest_ext/fixtures/logging.py

from __future__ import annotations

import logging
from pathlib import Path

import pytest


def _logger_name_from_nodeid(nodeid: str) -> str:
    """从 Pytest nodeid 提取简短、易读的 Logger 名称。"""
    parts = nodeid.split("::")

    # tests/test_login.py -> test_login
    test_file = Path(parts[0]).stem

    # TestLogin::test_password_login 或 test_password_login
    test_target = ".".join(parts[1:]) if len(parts) > 1 else "unknown"

    return f"{test_file}.{test_target}"


@pytest.fixture
def test_logger(request: pytest.FixtureRequest) -> logging.Logger:
    """
    返回当前测试用例专属的 Logger。

    前提：pytest_configure 已完成 configure_logging()，
    所以该 Logger 会继承 exfw 的 Handler 配置。
    """
    logger_name = _logger_name_from_nodeid(request.node.nodeid)

    return logging.getLogger(f"exfw.test.{logger_name}")
