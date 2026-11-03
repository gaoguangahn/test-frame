from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DynamicReportTask:
    """dynamic runner 下一个 pytest 子任务的报告上下文。"""

    task_dir: Path
    task_id: str
    main_serial: str | None
    session_data: dict[str, Any]
    device_info: dict[str, Any]
    runner_task: dict[str, Any]


@dataclass(frozen=True)
class ActionStatsSummary:
    """从 case_results.action_stats 汇总出的操作统计。"""

    total_clicks: int = 0
    total_swipes: int = 0
    total_start_app: int = 0
    total_home: int = 0
    total_start_exit: int = 0
    case_actions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def case_swipes(self) -> list[dict[str, Any]]:
        """兼容旧字段：从 case_actions 中提取每个用例的滑动次数。"""

        return [
            {
                "serial": item.get("serial"),
                "round": item.get("round"),
                "case": item.get("case"),
                "swipe": item.get("swipe", 0),
            }
            for item in self.case_actions
        ]


@dataclass(frozen=True)
class ReportDataset:
    """报表生成前已经读取、整理、路由完成的数据集合。"""

    # API 查询得到的原始用例结果。
    case_results: list[dict[str, Any]]

    # 报告公共上下文，只保留报告会用到的测试信息。
    test_info: dict[str, Any]

    # 从 case_results.trace_result / log_result 展开并按指标路由后的数据。
    trace_data: dict[str, list[dict[str, Any]]]
    log_data: dict[str, list[dict[str, Any]]]
    report_tasks: list[DynamicReportTask] = field(default_factory=list)
    selected_round: int | None = None

