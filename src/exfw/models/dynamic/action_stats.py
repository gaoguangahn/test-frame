from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from functools import wraps
from types import MethodType
from typing import Any

from exfw.aw.device import AdbDriver

_TRACKED_ACTION_METHODS = {
    "start_app",
    "start_pkg",
    "click",
    "double_click",
    "long_click",
    "swipe",
    "home",
    "open_control",
    "open_notification",
}


class ActionStatsRecorder:
    """记录动态模型用例执行过程中的设备动作统计。"""

    def __init__(
        self,
        on_change: Callable[[dict[str, int]], None] | None = None,
    ) -> None:
        self._stats: Counter[str] = Counter()
        self._on_change = on_change

    def record(self, method_name: str, count: int = 1) -> None:
        """记录一次成功执行的设备动作。"""

        self._stats[method_name] += count
        self._notify()

    def snapshot(self) -> dict[str, int]:
        """返回当前动作统计快照。"""

        return dict(self._stats)

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change(self.snapshot())


class DeviceActionInstrumentation:
    """临时包装 AdbDriver 动作方法，用例结束后恢复。"""

    def __init__(self, device: AdbDriver, recorder: ActionStatsRecorder) -> None:
        self._device = device
        self._recorder = recorder
        self._original_attrs: dict[str, tuple[bool, Any]] = {}

    def __enter__(self) -> AdbDriver:
        instance_attrs = vars(self._device)

        for method_name in _TRACKED_ACTION_METHODS:
            if not hasattr(self._device, method_name):
                continue

            original = getattr(self._device, method_name)
            if not callable(original):
                continue

            self._original_attrs[method_name] = (
                method_name in instance_attrs,
                instance_attrs.get(method_name),
            )

            wrapped = self._build_wrapper(
                method_name=method_name,
                original=original,
            )
            setattr(self._device, method_name, MethodType(wrapped, self._device))

        return self._device

    def __exit__(self, exc_type, exc, traceback) -> None:
        for method_name, (had_attr, original_value) in self._original_attrs.items():
            if had_attr:
                setattr(self._device, method_name, original_value)
            else:
                delattr(self._device, method_name)

        self._original_attrs.clear()

    def _build_wrapper(self, *, method_name: str, original: Callable[..., Any]):
        @wraps(original)
        def wrapper(_device_self, *args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            self._recorder.record(
                method_name,
                count=_get_action_count(method_name, kwargs),
            )
            return result

        return wrapper


def instrument_device_actions(
    device: AdbDriver,
    recorder: ActionStatsRecorder,
) -> DeviceActionInstrumentation:
    """创建设备动作统计包装上下文。"""

    return DeviceActionInstrumentation(device=device, recorder=recorder)


def _get_action_count(method_name: str, kwargs: dict[str, Any]) -> int:
    if method_name != "swipe":
        return 1

    times = kwargs.get("times", 1)
    if isinstance(times, int) and times > 0:
        return times

    return 1
