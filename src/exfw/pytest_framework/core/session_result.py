from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class SessionResultCollector:
    """收集本次 pytest session 的汇总结果。"""

    started_at: float = field(default_factory=time.time)
    cases: list[dict[str, Any]] = field(default_factory=list)
    extensions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_case(self, case_result: dict[str, Any]) -> None:
        """登记一条用例结果索引。"""

        artifacts = case_result.get("artifacts", {})
        result_path = artifacts.get("result_file", "result.json")
        artifact_dir = artifacts.get("case_dir", ".")

        case_index = {
            "nodeid": case_result["nodeid"],
            "case_id": case_result["case_id"],
            "case_name": case_result["case_name"],
            "round": case_result["round"],
            "outcome": case_result["outcome"],
            "duration": case_result["duration"],
            "result_path": result_path,
            "artifact_dir": artifact_dir,
        }

        for index, existing_case in enumerate(self.cases):
            if (
                existing_case["nodeid"] == case_index["nodeid"]
                and existing_case["round"] == case_index["round"]
            ):
                self.cases[index] = case_index
                return

        self.cases.append(case_index)

    def update_extension(self, name: str, value: dict[str, Any]) -> None:
        """合并登记业务插件扩展的 session 结果信息。"""

        extension = self.extensions.setdefault(name, {})
        extension.update(value)


EXFW_SESSION_RESULT_KEY: pytest.StashKey[SessionResultCollector] = pytest.StashKey()


def get_or_create_session_result_collector(
    config: pytest.Config,
) -> SessionResultCollector:
    """获取本次 pytest session 的结果收集器。"""

    collector = config.stash.get(EXFW_SESSION_RESULT_KEY, None)

    if collector is None:
        collector = SessionResultCollector()
        config.stash[EXFW_SESSION_RESULT_KEY] = collector

    return collector
