"""动态模型解析 profile：映射仅调用解析库中已存在的方法。"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from metric_parser import LogParser, TraceParser


@dataclass(frozen=True)
class AnalysisProfile:
    trace: dict[str, list[dict[str, Any]]]
    log: dict[str, list[str]]


def load_analysis_profile(path: Path | None = None) -> AnalysisProfile:
    path = path or Path(__file__).with_name("profile.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"trace", "log"}:
        raise ValueError(f"解析 profile 须包含 trace 和 log：{path}")
    for category, parser in (("trace", TraceParser), ("log", LogParser)):
        mapping = raw[category]
        if not isinstance(mapping, dict):
            raise ValueError(f"解析 profile {category} 必须是映射")
        for key, metrics in mapping.items():
            if not isinstance(key, str) or not key or not isinstance(metrics, list):
                raise ValueError(f"解析 profile {category} 条目无效：{key!r}")
            for item in metrics:
                if category == "trace":
                    if not isinstance(item, dict) or set(item) - {"metric", "params"} or not isinstance(item.get("params", {}), dict):
                        raise ValueError(f"Trace 指标配置无效：{item!r}")
                    metric = item.get("metric")
                else:
                    metric = item
                if not isinstance(metric, str) or metric.startswith("_") or not callable(getattr(parser, metric, None)):
                    raise ValueError(f"解析器不支持指标：{metric!r}")
    return AnalysisProfile(trace=raw["trace"], log=raw["log"])
