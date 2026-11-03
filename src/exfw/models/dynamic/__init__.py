from __future__ import annotations

__all__ = ["DynamicCase", "DynamicReplayCase"]


def __getattr__(name: str):
    if name == "DynamicCase":
        from .base_case import DynamicCase

        return DynamicCase

    if name == "DynamicReplayCase":
        from .replay_case import DynamicReplayCase

        return DynamicReplayCase

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
