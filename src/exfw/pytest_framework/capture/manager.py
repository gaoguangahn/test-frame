from __future__ import annotations

import logging
from typing import Any

import pytest

from exfw.aw.trace import TraceCollector
from exfw.pytest_framework.core.runtime import LOGCAT_MANAGER_KEY, TRACE_COLLECTOR_KEY


class LogcatManager:
    """
    pytest 会话内共享的 Logcat 管理服务。

    职责：
    - 缓存业务插件注册的 logcat collector；
    - 向 RoundTask、fixture 等调用方提供 logcat collector；
    - 保证同一 pytest 会话内的 logcat collector 可复用。
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("exfw.logcat")
        self._collectors: dict[str, Any] = {}

    def register(self, name: str, collector: Any, *, replace: bool = False) -> bool:
        """
        注册 logcat collector。

        返回 True 表示本次新增或替换；
        返回 False 表示同名 collector 已存在且未允许替换。
        """
        if name in self._collectors and not replace:
            self.logger.debug("logcat collector 已注册，跳过：%s", name)
            return False

        self._collectors[name] = collector
        self.logger.debug(
            "logcat collector 注册成功：name=%s, type=%s",
            name,
            type(collector).__name__,
        )
        return True

    def get(self, name: str) -> Any:
        """按名称获取已注册的 logcat collector。"""
        try:
            return self._collectors[name]
        except KeyError as error:
            available_names = ", ".join(sorted(self._collectors)) or "无"
            raise ValueError(
                f"未注册的 logcat collector：{name!r}；"
                f"可用 collector：{available_names}"
            ) from error

    def unregister(self, name: str) -> Any | None:
        """移除指定的 logcat collector，并返回原对象。"""
        return self._collectors.pop(name, None)

    @property
    def names(self) -> tuple[str, ...]:
        """返回当前已注册的 collector 名称。"""
        return tuple(sorted(self._collectors))


def get_or_create_trace_collector(config: pytest.Config) -> TraceCollector:
    """获取 pytest 会话共享的 TraceCollector；不存在时创建。"""
    collector = config.stash.get(TRACE_COLLECTOR_KEY, None)

    if collector is None:
        collector = TraceCollector()
        config.stash[TRACE_COLLECTOR_KEY] = collector

    return collector


def get_or_create_logcat_manager(config: pytest.Config) -> LogcatManager:
    """获取 pytest 会话共享的 LogcatManager；不存在时创建。"""
    manager = config.stash.get(LOGCAT_MANAGER_KEY, None)

    if manager is None:
        manager = LogcatManager()
        config.stash[LOGCAT_MANAGER_KEY] = manager

    return manager
