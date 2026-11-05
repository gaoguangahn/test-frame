from __future__ import annotations

import logging
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger
from pathlib import Path
from typing import Any, ClassVar

from .log_analysis import LogAnalysis


class LogParserDispatcher:
    """
    根据日志文件名，调度对应的日志解析方法。

    一个日志文件可能对应多个 metric；
    不同日志文件可并行解析。

    对外使用 parse()：
    - 传入单个日志文件：解析该文件；
    - 传入目录：解析目录下全部支持的日志文件；
    - 始终返回 list[dict[str, Any]]。
    """

    LOG_METRIC_MAP: ClassVar[dict[str, list[str]]] = {
        "DumpsysMeminfo": [
            "parse_dumpsys_meminfo",
        ],
        "io_measure": [
            "parse_io_measure",
        ],
        "io_stat": [
            "parse_io_stat",
        ],
        "actionstats": [
            "parse_animation_jank",
            "parse_fling_jank",
            "parse_fluency_fling_jank",
        ],
        "JankRaw": [
            "parse_jank_log",
        ],
        # "EventsLog": [
        #     "parse_events_log",
        # ],
        "AdbLog": [
            "parse_adb_log",
        ],
        "proc_memory": [
            "parse_proc_memory",
        ],
    }

    ALLOWED_SUFFIXES: ClassVar[set[str]] = {
        ".txt",
        ".log",
        ".bd",
    }

    def __init__(
        self, executor: ThreadPoolExecutor, logger: Logger | None = None, metric_map: dict | None = None
    ) -> None:
        self.log_analysis = LogAnalysis()
        self.logger = logger or logging.getLogger("exfw.LogParserDispatcher")
        self._executor = executor
        self.LOG_METRIC_MAP = metric_map if metric_map is not None else self.LOG_METRIC_MAP

    def parse(self, log_path: str | Path, brand: str = "Honor") -> list[dict[str, Any]]:
        """
        解析一个日志文件，或一个目录下的全部支持日志文件。

        规则：
        - log_path 为文件时：仅解析该文件；
        - log_path 为目录时：扫描当前目录下全部支持的日志文件；
        - 多个日志文件在线程池中并发解析；
        - 当前方法等待全部解析完成后，统一返回结果。

        注意：
        - 本方法是同步阻塞方法；
        - 应由外层 Report 的后台任务调用，避免阻塞测试主线程。

        Returns:
            所有日志解析结果，按 log_file 路径排序。
            即使只有一个文件，也始终返回列表。
        """

        log_path = Path(log_path)

        if not log_path.exists():
            self.logger.error(
                "Log 路径不存在：path=%s",
                log_path,
            )
            return []

        if log_path.is_file():
            if log_path.suffix.lower() not in self.ALLOWED_SUFFIXES:
                self.logger.warning(
                    "不支持的日志文件类型，跳过解析：path=%s",
                    log_path,
                )
                return []

            log_files = [log_path]

        elif log_path.is_dir():
            log_files = sorted(
                (
                    file_path
                    for file_path in log_path.glob("*")
                    if file_path.is_file()
                    and file_path.suffix.lower() in self.ALLOWED_SUFFIXES
                ),
                key=lambda file_path: str(file_path),
            )

        else:
            self.logger.warning(
                "Log 路径既不是普通文件也不是目录，跳过解析：path=%s", log_path
            )
            return []

        if not log_files:
            self.logger.info("未发现可解析日志文件：path=%s", log_path)
            return []

        matched_log_files = []
        skipped_log_files = []

        for log_file in log_files:
            metric_names = self._get_metric_names(log_file)

            if metric_names:
                matched_log_files.append(log_file)
            else:
                skipped_log_files.append(log_file)

        if not matched_log_files:
            self.logger.info(
                "未发现可解析日志文件：path=%s, total=%s, skipped=%s",
                log_path,
                len(log_files),
                len(skipped_log_files),
            )
            return []

        self.logger.info("开始解析 Log：path=%s, count=%s", log_path, len(log_files))

        future_to_file = {
            self._executor.submit(copy_context().run, self.parse_file, log_file, brand): log_file
            for log_file in matched_log_files
        }

        results: list[dict[str, Any]] = []

        for future in as_completed(future_to_file):
            log_file = future_to_file[future]

            try:
                result = future.result()

            except Exception as error:
                self.logger.exception("日志后台解析任务异常：file=%s", log_file)

                result = self._build_failed_result(
                    log_file=log_file, error=error, stage="日志后台解析任务异常"
                )

            results.append(result)

        results.sort(key=lambda item: item["log_file"])

        success_count = sum(item["success"] for item in results)

        self.logger.info(
            "Log 批次解析完成：path=%s, total=%s, success=%s, failed=%s",
            log_path,
            len(results),
            success_count,
            len(results) - success_count,
        )

        return results

    def parse_file(
        self, log_file: str | Path, device_brand: str = "Honor"
    ) -> dict[str, Any]:
        """同步解析单份日志文件。"""

        log_file = Path(log_file)

        result: dict[str, Any] = {
            "log_file": str(log_file),
            "log_name": log_file.name,
            "success": False,
            "metrics": None,
            "data": None,
            "error": None,
        }

        if not log_file.exists():
            result["error"] = f"日志文件不存在: {log_file}"
            self.logger.warning(result["error"])
            return result

        if not log_file.is_file():
            result["error"] = f"日志路径不是文件: {log_file}"
            self.logger.warning(result["error"])
            return result

        if log_file.suffix.lower() not in self.ALLOWED_SUFFIXES:
            result["error"] = f"不支持的日志文件类型: {log_file.suffix}"
            self.logger.warning(result["error"])
            return result

        metric_names = self._get_metric_names(log_file)

        if not metric_names:
            result["error"] = f"未配置该日志文件的解析规则: {log_file.name}"
            self.logger.debug(result["error"])
            return result

        result["metrics"] = metric_names

        try:
            analysis_result = self.log_analysis.analysis_log(
                log_file=str(log_file), metric_names=metric_names, brand=device_brand
            )

            result.update(analysis_result)

            self.logger.debug(
                "日志解析完成：file=%s, metrics=%s, success=%s",
                log_file,
                metric_names,
                result["success"],
            )

        except Exception as error:
            result["error"] = f"日志调度解析异常: {error}"

            self.logger.exception(
                "日志调度解析异常：file=%s, metrics=%s",
                log_file,
                metric_names,
            )

        return result

    def _get_metric_names(
        self,
        log_file: Path,
    ) -> list[str]:
        """根据日志文件名中包含的关键字，获取对应解析方法。"""

        filename = log_file.name.lower()

        for keyword, metric_names in self.LOG_METRIC_MAP.items():
            if keyword.lower() in filename:
                return metric_names

        return []

    @staticmethod
    def _build_failed_result(
        log_file: Path,
        error: Exception,
        stage: str,
    ) -> dict[str, Any]:
        """构造单份日志的失败结果。"""

        return {
            "log_file": str(log_file),
            "log_name": log_file.name,
            "success": False,
            "metrics": [],
            "data": None,
            "error": f"{stage}: {error}",
        }

    def shutdown(self, wait: bool = True) -> None:
        """线程池由 CaseResultReporter 统一管理，此处无需关闭。"""
