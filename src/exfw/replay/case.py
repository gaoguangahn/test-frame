from __future__ import annotations

import pytest

from .context import reset_current_replay_engine, set_current_replay_engine
from .engine import ReplayEngine


class ReplayCase:
    """pytest 用例回放基类：每个测试方法一个 ReplayEngine。"""

    replay_enabled = True
    max_recover = 4
    max_probe_per_recover = 4

    @pytest.fixture(autouse=True)
    def _replay_case_context(self):
        engine = self.create_replay_engine()
        self._activate_replay_engine(engine)

        try:
            yield
        finally:
            self._deactivate_replay_engine()

    def create_replay_engine(self) -> ReplayEngine:
        """创建当前测试方法使用的回放引擎。"""
        return ReplayEngine(
            recovery_step=self.recovery_step,
            max_recover=self.max_recover,
            max_probe_per_recover=self.max_probe_per_recover,
        )

    def recovery_step(self, attempt: int) -> None:
        """
        执行一次恢复动作。

        子类可按 attempt 编排恢复动作。
        基类默认不执行设备操作，但引擎仍会继续探测历史检查点。
        """
        del attempt

    def _activate_replay_engine(self, engine: ReplayEngine) -> None:
        engine.replay_enabled = self.replay_enabled
        self.replay_engine = engine
        self._replay_token = set_current_replay_engine(engine)

    def _deactivate_replay_engine(self) -> None:
        reset_current_replay_engine(self._replay_token)
