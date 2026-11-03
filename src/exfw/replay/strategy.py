"""恢复策略协议。

引擎找不到匹配检查点时，调用策略做一步兜底动作改变当前状态，
再重新探测历史检查点。具体恢复动作由用例基类或业务侧实现。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RecoveryStrategy(Protocol):
    """设备恢复策略。

    attempt 从 0 开始，表示当前恢复周期内的第几步。
    每执行一步后，引擎会自动探测可用检查点。
    """

    def step(self, attempt: int) -> None: ...
