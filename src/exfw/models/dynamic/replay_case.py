from __future__ import annotations

import pytest

from exfw.replay import ReplayCase


class DynamicReplayCase(ReplayCase):
    """
    动态模型回放用例基类。

    普通动态模型用例应继承 DynamicCase；只有需要接入 replay 恢复能力的用例
    才继承本类。
    """

    @pytest.fixture(autouse=True)
    def _replay_case_context(self, primary_device):
        self.replay_device = primary_device

        engine = self.create_replay_engine()
        self._activate_replay_engine(engine)

        try:
            yield
        finally:
            self._deactivate_replay_engine()

    def recovery_step(self, attempt: int):
        del attempt

        try:
            self.replay_device.back()
        except Exception as error:
            raise RuntimeError("无法按返回键") from error
