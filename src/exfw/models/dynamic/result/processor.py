"""动态结果流水线：解析、持久化、可选上传；执行状态由通用 session store 保存。"""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import RLock
from uuid import uuid4
import logging

from exfw.models.dynamic.analyse.service import AnalysisService
from exfw.models.dynamic.result.parsed_store import ParsedResultStore
from exfw.models.dynamic.upload.service import DynamicUploadService


class DynamicResultProcessor:
    def __init__(self, output_dir, session_store, max_workers=2, parse_max_workers=8, *, upload_enabled=True, local_run_id=None):
        self._logger = logging.getLogger("exfw.dynamic.result")
        self.local_run_id = local_run_id or uuid4().hex
        self._session = session_store
        self._parsed = ParsedResultStore(output_dir, self.local_run_id)
        self._executor = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="case-result-reporter")
        self._parse_executor = ThreadPoolExecutor(max_workers=max(1, parse_max_workers), thread_name_prefix="artifact-parser")
        try:
            self._analysis = AnalysisService(self._parse_executor)
            self._upload = DynamicUploadService() if upload_enabled else None
        except Exception:
            self._executor.shutdown(wait=True)
            self._parse_executor.shutdown(wait=True)
            raise
        self._states = {}
        self._lock = RLock()
        self._closed = False

    def _update(self, context, changes):
        key = (context["round"], context.get("case_id") or "__round_logs__")
        with self._lock:
            if context.get("case") == "__round_logs__":
                self._session.update_round_extension(context["round"], "dynamic_model", changes)
            else:
                self._session.update_case_extension(context["round"], context["case_id"], context["nodeid"], "dynamic_model", changes)
            state = self._states.setdefault(key, {})
            for phase in ("capture", "analysis", "upload"):
                if phase in changes:
                    state[phase] = changes[phase]

    def submit_case_result(self, task_context, *, log_path, trace_path, brand="Honor", capture_status=None):
        if self._closed:
            raise RuntimeError("动态结果处理器已关闭")
        context = dict(task_context)
        self._update(context, {"capture": capture_status or {"status": "unknown"},
                               "analysis": {"status": "pending"},
                               "upload": {"status": "pending" if self._upload else "disabled"}})
        return self._executor.submit(copy_context().run, self._process, context, log_path, trace_path, brand)

    def _process(self, context, log_path, trace_path, brand):
        saved = False
        try:
            log_results, trace_results = self._analysis.parse(log_path, trace_path, brand)
            self._parsed.update(context, log_results, trace_results)
            results = log_results + trace_results
            failed = sum(1 for result in results if result.get("success") is False or result.get("error"))
            succeeded = sum(1 for result in results if result.get("success") is True)
            status = "skipped" if not results else ("completed" if not failed else ("partial" if succeeded else "failed"))
            self._update(context, {"analysis": {"status": status, "failed": failed}})
            saved = True
            if self._upload is None:
                return
            # 服务端沿用原有协议，模型内部标识不混入上传 payload。
            payload = {key: value for key, value in context.items() if key not in ("case_id", "nodeid")}
            payload.update(log_result=log_results, trace_result=trace_results)
            def success(response):
                self._update(context, {"upload": {"status": "completed", "http_status": response.status_code}})
            def failure(response, error):
                self._update(context, {"upload": {"status": "failed", "http_status": getattr(response, "status_code", None), "error": str(error) if error else "HTTP 上传失败"}})
            self._upload.submit(payload, success, failure)
        except Exception as error:
            self._logger.exception("解析或提交上传失败：case=%s", context.get("case"))
            try:
                changes = {"upload": {"status": "failed" if self._upload else "disabled", "error": str(error)}}
                if not saved:
                    changes["analysis"] = {"status": "failed", "error": str(error)}
                self._update(context, changes)
            except Exception:
                self._logger.exception("写入处理状态失败")

    def record_capture_failure(self, task_context, error):
        self._update(dict(task_context), {"capture": {"status": "failed", "error": str(error)},
                    "analysis": {"status": "not_run"},
                    "upload": {"status": "not_run" if self._upload else "disabled"}})

    def summary(self):
        with self._lock:
            result = {"total": len(self._states), "capture": {}, "analysis": {}, "upload": {}}
            for state in self._states.values():
                for phase in ("capture", "analysis", "upload"):
                    status = state.get(phase, {}).get("status", "pending")
                    result[phase][status] = result[phase].get(status, 0) + 1
            return result

    def shutdown(self, wait=True):
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=wait)
        self._parse_executor.shutdown(wait=wait)
        if self._upload is not None:
            self._upload.close()
