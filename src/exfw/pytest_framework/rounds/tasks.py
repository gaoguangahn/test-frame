from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from exfw.pytest_framework.core.runtime import RunConfig


@dataclass(frozen=True)
class RoundContext:
    """Round 生命周期任务的运行上下文。"""

    run_config: RunConfig
    round_no: int
    rounds: int


class RoundTask(Protocol):
    """Round 生命周期任务接口。"""

    @property
    def name(self) -> str:
        """任务名称，用于日志和排查。"""
        ...

    def before_round(self, context: RoundContext) -> None:
        """在一个 round 的全部测试开始前执行。"""
        ...

    def after_round(self, context: RoundContext) -> None:
        """
        在一个 round 的全部测试结束后执行。

        即使 round 内有测试失败，也应执行。
        """
        ...
