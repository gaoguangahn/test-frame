"""pytest 结果数据结构；业务模型数据只放在 extensions 中。"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseResult:
    case_id: str
    nodeid: str
    case_name: str
    outcome: str = "pending"
    duration: float = 0.0
    started_at: float | None = None
    stopped_at: float | None = None
    longrepr: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    time_source: str | None = None
    time_context: dict[str, Any] | None = None
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoundResult:
    round: int
    cases: list[CaseResult] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionResult:
    testbed: str | None
    config_path: str
    output_dir: str
    artifact_layout: str
    started_at: float
    devices: list[dict[str, Any]] = field(default_factory=list)
    stopped_at: float | None = None
    duration: float | None = None
    exitstatus: int | None = None
    schema_version: int = 2
    summary: dict[str, int] = field(default_factory=dict)
    rounds: list[RoundResult] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)
