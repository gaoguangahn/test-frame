import logging
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger
from pathlib import Path
from typing import Any, ClassVar

from .trace_analysis import TraceAnalysis


class TraceParserDispatcher:
    """
    根据 Trace 文件名中的 code，调度对应 metric 的解析逻辑。

    文件名约定：
    - {任意名称}__{metric_code}.pftrace

    示例：
    - 123456789__AppLaunch.pftrace
    - case_001__step_01__CameraPhoto.pftrace

    对外使用 parse()：
    - 传入 .pftrace 文件：解析单个 Trace；
    - 传入目录：递归解析目录下所有 .pftrace 文件；
    - 始终返回 list[dict[str, Any]]。
    """

    METRIC_MAP: ClassVar[dict[str, list[dict[str, Any]]]] = {
        "AppLaunch": [{"metric": "startup_transition"}],
        "AppExit": [{"metric": "exit_animation"}],
        "AppClick": [{"metric": "click_transition"}],
        # "AppSwipe": [{"metric": "swipe_offscreen"}],
        # "ControlCenter": [{"metric": "control_center"}],
        # "MultiTask": [{"metric": "multi_task"}],
        # "KbdPopup": [
        #     {"metric": "keyboard_popup"},
        #     {"metric": "click_transition"},
        # ],
        # "KbdInput": [{"metric": "keyboard_input"}],
        "CameraPhoto": [
            {
                "metric": "startup_transition",
                "params": {"from_app": "com.hihonor.camera"},
            }
        ],
    }

    def __init__(
        self, executor: ThreadPoolExecutor, logger: Logger | None = None
    ) -> None:
        self.trace_analysis = TraceAnalysis()
        self.logger = logger or logging.getLogger("exfw.TraceParserDispatcher")
        self._executor = executor

    @classmethod
    def get_metric_configs(cls, trace_file: str | Path) -> list[dict[str, Any]]:
        """
        根据 Trace 文件名的包含关系，获取对应的指标配置列表。

        文件名只要包含 METRIC_MAP 中任意 key，即认为匹配成功。
        一个 key 可配置一个或多个指标；返回值始终是列表。

        示例：
        - 123456789__AppLaunch.pftrace
        -> [{"metric": "startup_transition"}]

        - case_001__step_01__KbdPopup.pftrace
        -> [{"metric": "keyboard_popup"}, {"metric": "click_transition"}]

        - manual_trace.pftrace
        -> []
        """
        trace_file = Path(trace_file)

        if trace_file.suffix.lower() != ".pftrace":
            return []

        trace_file_stem = trace_file.stem

        # 按 key 长度倒序匹配，避免未来存在包含关系时短 key 优先命中。
        metric_codes = sorted(cls.METRIC_MAP.keys(), key=len, reverse=True)

        for metric_code in metric_codes:
            if metric_code in trace_file_stem:
                return cls.METRIC_MAP[metric_code]

        return []

    @classmethod
    def get_metric_config(cls, trace_file: str | Path) -> dict[str, Any] | None:
        """
        根据 Trace 文件名的包含关系，获取首个指标配置。

        保留该方法用于兼容旧调用方；多指标场景请使用 get_metric_configs()。
        """
        metric_configs = cls.get_metric_configs(trace_file)
        return metric_configs[0] if metric_configs else None

    def parse(
        self, trace_path: str | Path, brand: str = "Honor"
    ) -> list[dict[str, Any]]:
        """
        解析一个 Trace 文件，或一个目录下的全部 Trace 文件。

        规则：
        - trace_path 为 .pftrace 文件时：仅解析该文件；
        - trace_path 为目录时：递归查找全部 .pftrace 文件并解析；
        - 多个 Trace 会在线程池中并发解析；
        - 当前方法会等待该批次全部解析完成后，统一返回结果。

        注意：
        - 此方法是同步阻塞方法；
        - 建议由外层的后台任务调用，避免阻塞测试主线程。

        Returns:
            所有 Trace 的解析结果，按 trace_file 路径和 metric 排序。
            即使仅解析一个文件，返回值仍然是列表；多指标 Trace 会返回多条结果。
        """

        trace_path = Path(trace_path)

        if not trace_path.exists():
            self.logger.error("Trace 路径不存在：path=%s", trace_path)
            return []

        if trace_path.is_file():
            if trace_path.suffix.lower() != ".pftrace":
                self.logger.warning(
                    "输入文件不是 .pftrace，跳过解析：path=%s", trace_path
                )
                return []

            trace_files = [trace_path]

        elif trace_path.is_dir():
            # 递归扫描目录及其子目录。
            trace_files = sorted(
                trace_path.rglob("*.pftrace"), key=lambda file_path: str(file_path)
            )

        else:
            self.logger.warning(
                "Trace 路径既不是普通文件也不是目录，跳过解析：path=%s", trace_path
            )
            return []

        if not trace_files:
            self.logger.warning("未发现 .pftrace 文件：path=%s", trace_path)
            return []

        # 按文件名匹配指标，过滤掉不匹配的文件。
        matched_trace_tasks: list[tuple[Path, dict[str, Any]]] = []
        skipped_trace_files = []

        for trace_file in trace_files:
            metric_configs = self.get_metric_configs(trace_file)

            if not metric_configs:
                skipped_trace_files.append(trace_file)
                continue

            matched_trace_tasks.extend(
                (trace_file, metric_config) for metric_config in metric_configs
            )

        if skipped_trace_files:
            self.logger.info(
                "已跳过未匹配指标的 Trace 文件：count=%s", len(skipped_trace_files)
            )

        if not matched_trace_tasks:
            self.logger.warning(
                "未发现可解析的 Trace 文件：path=%s, total=%s, skipped=%s",
                trace_path,
                len(trace_files),
                len(skipped_trace_files),
            )
            return []

        self.logger.info(
            "开始解析 Trace：path=%s, total=%s, matched_files=%s, matched_metrics=%s, skipped=%s",
            trace_path,
            len(trace_files),
            len({trace_file for trace_file, _ in matched_trace_tasks}),
            len(matched_trace_tasks),
            len(skipped_trace_files),
        )

        future_to_task = {
            self._executor.submit(copy_context().run, self.parse_trace, trace_file, brand, metric_config): (
                trace_file,
                metric_config,
            )
            for trace_file, metric_config in matched_trace_tasks
        }

        results: list[dict[str, Any]] = []

        for future in as_completed(future_to_task):
            trace_file, metric_config = future_to_task[future]

            try:
                result = future.result()

            except Exception as error:
                self.logger.exception(
                    "Trace 后台解析任务异常：file=%s, metric=%s",
                    trace_file,
                    metric_config.get("metric"),
                )

                result = self._build_failed_result(
                    trace_file=trace_file,
                    error=error,
                    stage="Trace 后台解析任务异常",
                    metric_config=metric_config,
                )

            results.append(result)

        results.sort(key=lambda item: (item["trace_file"], item.get("metric") or ""))

        success_count = sum(item["success"] for item in results)

        self.logger.info(
            "Trace 批次解析完成：path=%s, total=%s, success=%s, failed=%s",
            trace_path,
            len(results),
            success_count,
            len(results) - success_count,
        )

        return results

    def parse_trace(
        self,
        trace_file: str | Path,
        brand: str = "Honor",
        metric_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        同步解析一份 Trace 的一个指标。

        根据 Trace 文件名是否包含 METRIC_MAP 的 key，
        自动识别对应的 metric 和 params。调用方也可以传入 metric_config，
        用于同一份 Trace 解析多个指标。

        该方法一般由 parse() 在线程池中调用。
        """
        trace_file = Path(trace_file)

        result: dict[str, Any] = {
            "trace_file": str(trace_file),
            "trace_name": trace_file.name,
            "metric": None,
            "success": False,
            "trace_info": None,
            "data": None,
            "error": None,
        }

        metric_config = metric_config or self.get_metric_config(trace_file)

        if metric_config is None:
            result["error"] = (
                "无法根据文件名匹配 Trace 类型，"
                "文件名应包含以下任一标识："
                f"{'、'.join(self.METRIC_MAP.keys())}"
            )

            self.logger.warning(
                "跳过 Trace：file=%s, reason=%s",
                trace_file,
                result["error"],
            )

            return result

        metric = metric_config["metric"]
        params = metric_config.get("params")

        result["metric"] = metric

        try:
            analysis_result = self.trace_analysis.analysis_trace(
                trace_file=str(trace_file),
                metric=metric,
                params=params,
                brand=brand,
            )

            result.update(analysis_result)

            self.logger.info(
                "Trace 解析完成：file=%s, metric=%s, success=%s",
                trace_file,
                metric,
                result["success"],
            )

        except Exception as error:
            self.logger.exception(
                "Trace 调度解析异常：file=%s, metric=%s",
                trace_file,
                metric,
            )

            result["error"] = f"Trace 调度解析异常: {error}"

        return result

    def _build_failed_result(
        self,
        trace_file: Path,
        error: Exception,
        stage: str,
        metric_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """构造单份 Trace 单个指标的失败结果。"""
        metric_config = metric_config or self.get_metric_config(trace_file)

        return {
            "trace_file": str(trace_file),
            "trace_name": trace_file.name,
            "metric": (metric_config["metric"] if metric_config is not None else None),
            "success": False,
            "trace_info": None,
            "data": None,
            "error": f"{stage}: {error}",
        }

    def shutdown(self, wait: bool = True) -> None:
        """线程池由 CaseResultReporter 统一管理，此处无需关闭。"""
