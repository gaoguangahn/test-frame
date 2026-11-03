from __future__ import annotations

from contextvars import ContextVar, Token

from .engine import ReplayEngine

_CURRENT_REPLAY_ENGINE: ContextVar[ReplayEngine | None] = ContextVar(
    "current_replay_engine",
    default=None,
)


def get_current_replay_engine() -> ReplayEngine | None:
    """获取当前执行上下文绑定的回放引擎。"""
    return _CURRENT_REPLAY_ENGINE.get()


def set_current_replay_engine(engine: ReplayEngine) -> Token[ReplayEngine | None]:
    """绑定当前执行上下文的回放引擎，并返回可恢复 token。"""
    return _CURRENT_REPLAY_ENGINE.set(engine)


def reset_current_replay_engine(token: Token[ReplayEngine | None]) -> None:
    """恢复进入用例前的回放引擎上下文。"""
    _CURRENT_REPLAY_ENGINE.reset(token)
