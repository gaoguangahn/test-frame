from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CASE_TIME_CONTEXT_ATTR = "_exfw_case_time_context"


@dataclass(frozen=True)
class CaseTimeContext:
    """当前 pytest 用例的时间戳转换上下文。

    通用框架默认使用 PC wall-clock 写 result.json；其他模型可以在
    pytest item 上设置该上下文，让 result.json 的绝对时间戳转换到
    指定时间源，例如 Android 设备 wall-clock。
    """

    time_source: str
    offset_seconds: float = 0.0
    device_serial: str | None = None

    def convert_timestamp(self, value: Any) -> Any:
        """转换绝对时间戳；非数字和 bool 原样返回。"""

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return value + self.offset_seconds

        return value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def set_case_time_context(item: Any, context: CaseTimeContext) -> None:
    """为当前 pytest item 设置用例时间戳转换上下文。"""

    setattr(item, CASE_TIME_CONTEXT_ATTR, context)


def get_case_time_context(item: Any) -> CaseTimeContext | None:
    """获取当前 pytest item 的用例时间戳转换上下文。"""

    context = getattr(item, CASE_TIME_CONTEXT_ATTR, None)
    return context if isinstance(context, CaseTimeContext) else None
