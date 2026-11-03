from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from exfw.aw.trace import TraceCollector
from exfw.pytest_framework.core.path import safe_path_name


class DynamicTraceCollector:
    """动态模型 TraceCollector 命名代理。

    AW TraceCollector 只负责按传入 name 采集 trace；本代理只在动态模型用例中
    自动补齐 trace 名称前缀：<case>_loop<round>_<name>。
    """

    def __init__(
        self,
        *,
        collector: TraceCollector,
        case_name: str,
        round_no: int,
    ) -> None:
        self._collector = collector
        self._case_name = safe_path_name(_normalize_case_name(case_name), max_length=80)
        self._round_no = round_no

    def build_trace_name(self, name: str | None) -> str | None:
        """生成动态模型 trace 名；name 为 None 时保留底层默认命名。"""

        if name is None:
            return None

        raw_name = str(name)
        prefix = f"{self._case_name}_loop{self._round_no}_"

        # 兼容已经按新规则写完整名称的旧/临时代码，避免重复加前缀。
        if raw_name.startswith(prefix):
            return safe_path_name(raw_name, max_length=120)

        short_name = safe_path_name(raw_name, max_length=80)
        return safe_path_name(f"{prefix}{short_name}", max_length=120)

    @contextmanager
    def collect(
        self,
        serial: str,
        name: str | None = None,
        *,
        description: str = "",
        delete_on_error: bool = True,
    ) -> Generator[str, None, None]:
        """采集 trace，并自动补齐动态模型 trace 名称前缀。"""

        with self._collector.collect(
            serial=serial,
            name=self.build_trace_name(name),
            description=description,
            delete_on_error=delete_on_error,
        ) as trace_path:
            yield trace_path

    def start_trace(
        self,
        serial: str,
        name: str | None = None,
        *,
        description: str = "",
    ) -> str | None:
        """启动 trace，并自动补齐动态模型 trace 名称前缀。"""

        return self._collector.start_trace(
            serial=serial,
            name=self.build_trace_name(name),
            description=description,
        )

    def __getattr__(self, name: str) -> Any:
        """未覆写的方法透传给底层 TraceCollector。"""

        return getattr(self._collector, name)


def _normalize_case_name(case_name: str) -> str:
    """转换用于 trace 文件名的用例名，去掉 pytest 方法名前缀 test_。"""

    if case_name.startswith("test_"):
        return case_name[5:]

    return case_name
