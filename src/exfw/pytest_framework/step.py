from __future__ import annotations

import logging
import time
from contextvars import ContextVar, Token
from copy import deepcopy
from typing import Any

_CURRENT_RECORDER: ContextVar[StepRecorder | None] = ContextVar(
    "exfw_step_recorder", default=None
)


class StepRecorder:
    """记录当前 pytest 用例执行过程中的步骤标记。"""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("exfw.step")
        self._records: list[dict[str, Any]] = []

    @property
    def records(self) -> list[dict[str, Any]]:
        """返回当前已记录步骤的深拷贝。"""

        return deepcopy(self._records)

    def record(self, description: str, **extra: Any) -> dict[str, Any]:
        """记录一条步骤日志。"""

        timestamp = time.time()

        record: dict[str, Any] = {
            "index": len(self._records) + 1,
            "description": description,
            "timestamp": timestamp,
            **extra,
        }

        self._records.append(record)

        self._logger.info("[STEP %03d] %s", record["index"], description)
        return deepcopy(record)


def set_current_step_recorder(recorder: StepRecorder) -> Token[StepRecorder | None]:
    """绑定当前执行上下文的步骤记录器。"""

    return _CURRENT_RECORDER.set(recorder)


def reset_current_step_recorder(token: Token[StepRecorder | None]) -> None:
    """恢复当前执行上下文的步骤记录器。"""

    _CURRENT_RECORDER.reset(token)


def get_current_step_recorder() -> StepRecorder | None:
    """获取当前执行上下文的步骤记录器。"""

    return _CURRENT_RECORDER.get()


def Step(description: str, **extra: Any) -> dict[str, Any]:
    """
    标记当前用例执行步骤。

    示例：
        Step("启动微信")
        Step("点击发送", op_type="click", target="发送按钮")
    """

    recorder = get_current_step_recorder()
    if recorder is None:
        logging.getLogger("exfw.step").warning(
            "Step 在 pytest 用例上下文外被调用：%s", description
        )
        return {
            "index": 0,
            "description": description,
            "timestamp": time.time(),
            **extra,
        }

    return recorder.record(description, **extra)
