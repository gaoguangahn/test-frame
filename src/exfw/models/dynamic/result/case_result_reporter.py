from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from logging import Logger
from pathlib import Path
from typing import Any

from exfw.common.http import AsyncHttpUploader, UploadRequest
from exfw.models.dynamic.analyse.log_parser_dispatcher import LogParserDispatcher
from exfw.models.dynamic.analyse.trace_parser_dispatcher import TraceParserDispatcher
from exfw.models.dynamic.server_config import CASE_RESULT_SERVER


class CaseResultReporter:
    """
    用例完整结果上报器。

    负责在后台完成：
    1. Log 解析；
    2. Trace 解析；
    3. 汇总用例执行结果、原始日志、Log 解析结果和 Trace 解析结果；
    4. 将完整 payload 提交至异步上传队列。

    测试主线程只调用 submit_case_result()，不会等待解析或网络上传。
    """

    def __init__(
        self,
        max_workers: int = 2,
        parse_max_workers: int = 8,
        logger: Logger | None = None,
    ) -> None:
        self._async_uploader = AsyncHttpUploader()
        self._upload_url = CASE_RESULT_SERVER.upload_url
        self._logger = logger or logging.getLogger("exfw.CaseResultReporter")

        # 用例级编排：
        # 一个任务负责当前 case 的 Log 解析、Trace 解析、汇总与上传提交。
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="case-result-reporter",
        )

        # 文件级解析：
        # Log 与 Trace 共用，限制整个进程的总解析并发数。
        self._parse_executor = ThreadPoolExecutor(
            max_workers=max(1, parse_max_workers),
            thread_name_prefix="artifact-parser",
        )

        self._log_parser = LogParserDispatcher(
            executor=self._parse_executor,
        )
        self._trace_parser = TraceParserDispatcher(
            executor=self._parse_executor,
        )
        self._closed = False

    def submit_case_result(
        self,
        task_context: dict[str, Any],
        *,
        log_path: str | Path | None,
        trace_path: str | Path | None,
        brand: str = "Honor",
    ) -> Future[None]:
        """
        提交一个用例的后台解析与上报任务。

        log_path 与 trace_path 至少可传一个：
        - 仅传 log_path：只解析 Log；
        - 仅传 trace_path：只解析 Trace；
        - 两者都传：同时解析 Log 与 Trace；
        - 两者都不传：上传空列表。
        """
        if self._closed:
            raise RuntimeError("CaseResultReporter 已关闭，不能继续提交用例结果")

        # 防止测试主线程后续复用或修改这些对象，导致后台数据串用。
        task_context_snapshot = dict(task_context)

        return self._executor.submit(
            copy_context().run, self._parse_and_upload, task_context_snapshot, log_path, trace_path, brand
        )

    def _parse_and_upload(
        self,
        task_context: dict[str, Any],
        log_path: str | Path | None,
        trace_path: str | Path | None,
        brand: str,
    ) -> None:
        """运行于 Report 后台线程：解析、汇总并提交上传。"""
        try:
            # 解析日志
            log_results = self._parse_logs(
                task_context=task_context,
                log_path=log_path,
                brand=brand,
            )

            # 解析 Trace
            trace_results = self._parse_traces(
                task_context=task_context,
                trace_path=trace_path,
                brand=brand,
            )

            payload = {
                **task_context,
                "log_result": log_results,
                "trace_result": trace_results,
            }

            request = UploadRequest(
                name=self._build_request_name(task_context),
                url=self._upload_url,
                payload=payload,
                timeout=10.0,
                retries=2,
                headers={
                    "Content-Type": "application/json",
                },
            )

            self._async_uploader.submit(request)

            self._logger.info(
                "用例完整结果已进入上传队列："
                "task_id=%s, round=%s, case=%s, "
                "log_count=%s, trace_count=%s",
                task_context.get("task_id"),
                task_context.get("round"),
                task_context.get("case"),
                len(log_results),
                len(trace_results),
            )

        except Exception:
            self._logger.exception(
                "用例完整结果提交上传队列失败：task_id=%s, round=%s, case=%s",
                task_context.get("task_id"),
                task_context.get("round"),
                task_context.get("case"),
            )

    def _parse_logs(
        self, task_context: dict[str, Any], log_path: str | Path | None, brand: str
    ) -> list[dict[str, Any]]:
        """解析当前用例的 Log；失败时返回包含错误信息的结果列表。"""

        if log_path is None:
            return []

        try:
            return self._log_parser.parse(
                log_path=log_path,
                brand=brand,
            )

        except Exception as error:
            self._logger.exception(
                "Log 解析失败：task_id=%s, round=%s, case=%s, path=%s",
                task_context.get("task_id"),
                task_context.get("round"),
                task_context.get("case"),
                log_path,
            )

            return [{"success": False, "error": f"Log 解析汇总异常: {error}"}]

    def _parse_traces(
        self, task_context: dict[str, Any], trace_path: str | Path | None, brand: str
    ) -> list[dict[str, Any]]:
        """解析当前用例的 Trace；失败时返回包含错误信息的结果列表。"""

        if trace_path is None:
            return []

        try:
            return self._trace_parser.parse(trace_path=trace_path, brand=brand)

        except Exception as error:
            self._logger.exception(
                "Trace 解析失败：task_id=%s, round=%s, case=%s, path=%s",
                task_context.get("task_id"),
                task_context.get("round"),
                task_context.get("case"),
                trace_path,
            )

            return [{"success": False, "error": f"Trace 解析汇总异常: {error}"}]

    @staticmethod
    def _build_request_name(
        task_context: dict[str, Any],
    ) -> str:
        """构造用于日志排查的上传请求名称。"""

        return (
            "case-result:"
            f"task_id={task_context.get('task_id')}:"
            f"round={task_context.get('round')}:"
            f"case={task_context.get('case')}"
        )

    def shutdown(self, wait: bool = True) -> None:
        """关闭上报编排、解析及上传资源。"""

        if self._closed:
            return

        self._closed = True

        # 先等待当前 case 的编排任务结束。
        # 此时不会再向 _parse_executor 提交新的文件解析任务。
        self._executor.shutdown(wait=wait)

        # 再等待已提交的 Log / Trace 文件解析任务结束。
        self._parse_executor.shutdown(wait=wait)

        # 最后处理上传队列中剩余请求。
        self._async_uploader.close()

        self._logger.info("用例结果上报器已关闭：wait=%s", wait)
