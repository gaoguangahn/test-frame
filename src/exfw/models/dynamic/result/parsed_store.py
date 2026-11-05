"""单个 pytest 子任务的设备级解析结果，集中并发合并和原子写入。"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from threading import RLock

from exfw.pytest_framework.result.store import atomic_write_json
from .models import ParsedCase, ParsedResults, ParsedRound


class ParsedResultStore:
    def __init__(self, output_dir: Path, local_run_id: str):
        self.path = Path(output_dir) / "parsed_results.json"
        self.data = ParsedResults(local_run_id=local_run_id)
        self._lock = RLock()
        atomic_write_json(self.path, asdict(self.data))

    def update(self, context: dict, log_results: list, trace_results: list):
        with self._lock:
            previous = deepcopy(self.data)
            try:
                round_no = context["round"]
                round_result = next((item for item in self.data.rounds if item.round == round_no), None)
                if round_result is None:
                    round_result = ParsedRound(round=round_no)
                    self.data.rounds.append(round_result)
                if context.get("case") == "__round_logs__":
                    round_result.round_logs = deepcopy(log_results)
                else:
                    record = ParsedCase(case_id=context["case_id"], nodeid=context["nodeid"],
                                        case_name=context["case"], log_results=deepcopy(log_results),
                                        trace_results=deepcopy(trace_results))
                    round_result.cases = [item for item in round_result.cases if item.case_id != record.case_id]
                    round_result.cases.append(record)
                atomic_write_json(self.path, asdict(self.data))
            except BaseException:
                self.data = previous
                raise
