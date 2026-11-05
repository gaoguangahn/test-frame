"""动态模型结果：采集元数据与解析明细独立于服务端协议。"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TraceArtifact:
    name: str
    path: str
    description: str
    start_time: float | None
    end_time: float | None
    duration_seconds: float | None
    time_source: str
    time_context: dict[str, Any] | None = None
    available: bool = False


@dataclass
class ParsedCase:
    case_id: str
    nodeid: str
    case_name: str
    log_results: list[dict[str, Any]] = field(default_factory=list)
    trace_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ParsedRound:
    round: int
    round_logs: list[dict[str, Any]] = field(default_factory=list)
    cases: list[ParsedCase] = field(default_factory=list)


@dataclass
class ParsedResults:
    local_run_id: str
    schema_version: int = 1
    rounds: list[ParsedRound] = field(default_factory=list)
