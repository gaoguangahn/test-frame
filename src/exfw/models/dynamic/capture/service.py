from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import asdict
from pathlib import Path

from exfw.aw.trace import TraceCollector
from .profile import CaptureProfile, load_capture_profile
from .registry import DynamicCollectorRegistry
from .trace import DynamicTraceCollector
from exfw.models.dynamic.result.models import TraceArtifact


@dataclass
class RoundCaptureState:
    """一个设备在某个 round 中的持续采集状态。"""

    context: dict[str, str]
    results: list[dict]


class DynamicModelCaptureService:
    """统一编排动态模型的 round 级与 case 级日志采集。"""

    def __init__(self, registry=None, profile: CaptureProfile | None = None, trace_collector=None) -> None:
        self._collectors = registry if registry is not None else DynamicCollectorRegistry()
        # 操作级 tracer、用例结束时拉取和记录必须使用同一个实例。
        self._trace_collector = trace_collector if trace_collector is not None else TraceCollector()
        self._logger = logging.getLogger("exfw.dynamic_model_capture")
        self.profile = profile or load_capture_profile()

        # key: (round_no, serial)
        self._round_states: dict[tuple[int, str], RoundCaptureState] = {}
        self._case_results: dict[str, list[dict]] = {}
        self.last_round_results: dict[tuple[int, str], dict] = {}

    def start_round_capture(
        self, *, serial: str, round_no: int, logs_dir: Path
    ) -> None:
        """启动 round 级持续日志采集。"""

        logs_dir.mkdir(parents=True, exist_ok=True)

        context = {"root_dir": str(logs_dir), "loop": f"round_{round_no:03d}"}
        state_key = (round_no, serial)

        if state_key in self._round_states:
            raise RuntimeError(f"设备 {serial} 的第 {round_no} 轮持续日志采集已启动。")

        # 先登记，保证即使部分启动失败，也能在 round 结束时尽力清理。
        self._round_states[state_key] = RoundCaptureState(context=context, results=[])

        try:
            # jank_log 会清空 logcat buffer，必须最先启动。
            for collector_name in self.profile.round_start:
                path = self._collectors.get(collector_name).start(
                    serial,
                    context,
                )
                self._record(self._round_states[state_key].results, collector_name, "start", path is not None, path)

            self._logger.info(
                "启动动态模型 round 日志采集：round=%03d, serial=%s, logs_dir=%s",
                round_no,
                serial,
                logs_dir,
            )

        except Exception:
            self._logger.exception(
                "启动动态模型 round 日志采集失败：round=%03d, serial=%s",
                round_no,
                serial,
            )
            raise

    def stop_round_capture(
        self,
        *,
        serial: str,
        round_no: int,
    ) -> dict[str, str]:
        """停止 round 级持续日志采集，并采集结束快照。"""

        state_key = (round_no, serial)
        state = self._round_states.pop(state_key, None)

        if state is None:
            return {}

        artifacts: dict[str, str] = {}

        try:
            for name in self.profile.round_end:
                path = self._collectors.get(name).collect(serial, {**state.context, "stage": "end"})
                self._record(state.results, name, "collect", path is not None, path)
                if path:
                    artifacts[name] = str(path)

        except Exception:
            self._record(state.results, name, "collect", False)
            self._logger.exception(
                "动态模型 round 结束快照采集失败：round=%03d, serial=%s",
                round_no,
                serial,
            )

        finally:
            # 严格按启动反序停止。
            for collector_name in reversed(self.profile.round_start):
                self._stop_collector(
                    name=collector_name,
                    serial=serial,
                    context=state.context,
                    round_no=round_no,
                    artifacts=artifacts,
                    results=state.results,
                )

        self._logger.info(
            "结束动态模型 round 日志采集：round=%03d, serial=%s, artifacts=%s",
            round_no,
            serial,
            artifacts,
        )

        self.last_round_results[state_key] = self._summarize(state.results)
        return artifacts

    def start_case_capture(self, *, serial: str, logs_dir: Path) -> dict[str, str]:
        """执行 case 前置快照采集，并返回后续可复用的采集上下文。"""

        logs_dir.mkdir(parents=True, exist_ok=True)

        context = {"root_dir": str(logs_dir), "stage": "start"}
        self._case_results.setdefault(serial, [])

        for name in self.profile.case_start:
            collector = self._collectors.get(name)
            if name == "radar":
                result = collector.reset(serial, context)
            else:
                result = collector.collect(serial, context)
            self._record(self._case_results[serial], name, "start", bool(result), result if isinstance(result, str) else None)

        return context

    def stop_case_capture(self, *, serial: str, logs_dir: Path) -> None:
        """执行 case 后置快照采集。"""

        logs_dir.mkdir(parents=True, exist_ok=True)

        context = {"root_dir": str(logs_dir), "stage": "end"}

        for collector_name in self.profile.case_end:
            try:
                result = self._collectors.get(collector_name).collect(serial, context)
                self._record(self._case_results[serial], collector_name, "end", result is not None, result)

            except Exception:
                self._record(self._case_results[serial], collector_name, "end", False)
                self._logger.exception(
                    "动态模型用例后置日志采集失败：serial=%s, collector=%s",
                    serial,
                    collector_name,
                )

    def create_tracer(self, *, case_name: str, round_no: int) -> DynamicTraceCollector:
        """构造动态模型操作级 Trace 入口，共享本次运行的底层采集器。"""
        return DynamicTraceCollector(collector=self._trace_collector, case_name=case_name, round_no=round_no)

    def prepare_case(self, *, serial, logs_dir):
        """用例采集开始：清除旧 Trace，按 profile 采集前置快照。"""
        self._case_results[serial] = []
        cleaned = self._trace_collector.clean_device_traces(serial=serial)
        self._record(self._case_results[serial], "trace", "clean", cleaned is True)
        self.start_case_capture(serial=serial, logs_dir=logs_dir)

    def finish_case(self, *, serial, logs_dir, traces_dir, root_dir, time_context):
        """结束快照和 Trace 收集，供解析服务处理本地产物。"""
        self.stop_case_capture(serial=serial, logs_dir=logs_dir)
        pulled = self._trace_collector.pull_trace_directory(serial=serial, local_dir=traces_dir)
        self._record(self._case_results[serial], "trace", "pull", pulled is not None, pulled)
        snapshot = self._trace_collector.completed_trace_records(serial)
        traces = []
        for record in snapshot:
            name = Path(record.trace_path).name
            local_file = traces_dir / name
            convert = time_context.convert_timestamp if time_context else lambda value: value
            traces.append(asdict(TraceArtifact(
                name=name, path=local_file.relative_to(root_dir).as_posix(),
                description=record.description, start_time=convert(record.start_time),
                end_time=convert(record.end_time), duration_seconds=record.duration_seconds,
                time_source=time_context.time_source if time_context else "pc_realtime",
                time_context=time_context.to_dict() if time_context else None,
                available=pulled is not None and local_file.is_file(),
            )))
        return self._summarize(self._case_results.pop(serial, [])), traces, snapshot

    def acknowledge_traces(self, serial, snapshot):
        self._trace_collector.acknowledge_trace_records(serial, snapshot)

    @staticmethod
    def _record(results, name, stage, success, path=None):
        results.append({"name": name, "stage": stage, "status": "completed" if success else "failed", "path": str(path) if path else None})

    @staticmethod
    def _summarize(results):
        failures = sum(item["status"] == "failed" for item in results)
        return {"status": "completed" if not failures else ("failed" if failures == len(results) else "partial"), "items": results}

    def _stop_collector(
        self,
        *,
        name: str,
        serial: str,
        context: dict[str, str],
        round_no: int,
        artifacts: dict[str, str],
        results: list[dict],
    ) -> None:
        """停止一个持续采集器；失败时仅记录异常。"""

        try:
            path = self._collectors.get(name).stop(
                serial,
                context,
            )
            self._record(results, name, "stop", path is not None, path)
            if path:
                artifacts[name] = str(path)

        except Exception:
            self._record(results, name, "stop", False)
            self._logger.exception(
                "停止采集器失败：round=%03d, serial=%s, collector=%s",
                round_no,
                serial,
                name,
            )
