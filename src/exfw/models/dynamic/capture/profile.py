"""动态模型内部采集 profile；只允许配置已实现且阶段匹配的采集项。"""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CaptureProfile:
    round_start: tuple[str, ...]
    round_end: tuple[str, ...]
    case_start: tuple[str, ...]
    case_end: tuple[str, ...]


_ALLOWED = {
    "round_start": {"jank_log", "events_log", "adb_log", "dmesg_log"},
    "round_end": {"dumpsys_meminfo"},
    "case_start": {"io_stat", "proc_memory", "radar"},
    "case_end": {"io_measure", "io_stat", "radar", "proc_memory"},
}


def load_capture_profile(path: Path | None = None) -> CaptureProfile:
    path = path or Path(__file__).with_name("profile.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != set(_ALLOWED):
        raise ValueError(f"采集 profile 必须包含且仅包含 {sorted(_ALLOWED)}：{path}")
    values = {}
    for stage, allowed in _ALLOWED.items():
        names = data[stage]
        if not isinstance(names, list) or any(not isinstance(name, str) or name not in allowed for name in names) or len(names) != len(set(names)):
            raise ValueError(f"采集 profile 阶段 {stage} 包含无效或重复的采集项：{names}")
        values[stage] = tuple(names)
    if "jank_log" in values["round_start"] and values["round_start"][0] != "jank_log":
        raise ValueError("jank_log 会清除 logcat，必须在其他持续日志之前启动")
    if ("radar" in values["case_start"]) != ("radar" in values["case_end"]):
        raise ValueError("radar 需要同时配置用例开始重置和用例结束采集")
    return CaptureProfile(**values)
