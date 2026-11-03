from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from exfw.pytest_framework.capture.manager import LogcatManager


@dataclass
class RoundCaptureState:
    """一个设备在某个 round 中的持续采集状态。"""

    context: dict[str, str]


class DynamicModelCaptureService:
    """统一编排动态模型的 round 级与 case 级日志采集。"""

    def __init__(self, logcat_manager: LogcatManager) -> None:
        self._logcat_manager = logcat_manager
        self._logger = logging.getLogger("exfw.dynamic_model_capture")

        # key: (round_no, serial)
        self._round_states: dict[tuple[int, str], RoundCaptureState] = {}

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
        self._round_states[state_key] = RoundCaptureState(context=context)

        try:
            # jank_log 会清空 logcat buffer，必须最先启动。
            for collector_name in ("jank_log", "events_log", "adb_log", "dmesg_log"):
                self._logcat_manager.get(collector_name).start(
                    serial,
                    context,
                )

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
            path = self._logcat_manager.get("dumpsys_meminfo").collect(
                serial,
                {**state.context, "stage": "end"},
            )
            if path:
                artifacts["dumpsys_meminfo"] = str(path)

        except Exception:
            self._logger.exception(
                "动态模型 round 结束快照采集失败：round=%03d, serial=%s",
                round_no,
                serial,
            )

        finally:
            # 严格按启动反序停止。
            for collector_name in (
                "dmesg_log",
                "adb_log",
                "events_log",
                "jank_log",
            ):
                self._stop_collector(
                    name=collector_name,
                    serial=serial,
                    context=state.context,
                    round_no=round_no,
                    artifacts=artifacts,
                )

        self._logger.info(
            "结束动态模型 round 日志采集：round=%03d, serial=%s, artifacts=%s",
            round_no,
            serial,
            artifacts,
        )

        return artifacts

    def start_case_capture(self, *, serial: str, logs_dir: Path) -> dict[str, str]:
        """执行 case 前置快照采集，并返回后续可复用的采集上下文。"""

        logs_dir.mkdir(parents=True, exist_ok=True)

        context = {"root_dir": str(logs_dir), "stage": "start"}

        self._logcat_manager.get("io_stat").collect(
            serial,
            context,
        )
        self._logcat_manager.get("proc_memory").collect(
            serial,
            context,
        )
        self._logcat_manager.get("radar").reset(
            serial,
            context,
        )

        return context

    def stop_case_capture(self, *, serial: str, logs_dir: Path) -> None:
        """执行 case 后置快照采集。"""

        logs_dir.mkdir(parents=True, exist_ok=True)

        context = {"root_dir": str(logs_dir), "stage": "end"}

        for collector_name in ("io_measure", "io_stat", "radar", "proc_memory"):
            try:
                self._logcat_manager.get(collector_name).collect(serial, context)

            except Exception:
                self._logger.exception(
                    "动态模型用例后置日志采集失败：serial=%s, collector=%s",
                    serial,
                    collector_name,
                )

    def _stop_collector(
        self,
        *,
        name: str,
        serial: str,
        context: dict[str, str],
        round_no: int,
        artifacts: dict[str, str],
    ) -> None:
        """停止一个持续采集器；失败时仅记录异常。"""

        try:
            path = self._logcat_manager.get(name).stop(
                serial,
                context,
            )
            if path:
                artifacts[name] = str(path)

        except Exception:
            self._logger.exception(
                "停止采集器失败：round=%03d, serial=%s, collector=%s",
                round_no,
                serial,
                name,
            )
