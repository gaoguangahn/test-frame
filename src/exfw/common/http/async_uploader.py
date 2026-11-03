from __future__ import annotations

import logging
import queue
import threading
from contextvars import Context, copy_context

from .client import HttpJsonClient
from .types import UploadRequest


class AsyncHttpUploader:
    """基于队列和后台线程的异步 JSON 上传器。"""

    _STOP = object()

    def __init__(
        self,
        client: HttpJsonClient | None = None,
        logger: logging.Logger | None = None,
        queue_size: int = 10,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._client = client or HttpJsonClient(logger=self._logger)
        self._queue: queue.Queue[tuple[Context, UploadRequest] | object] = queue.Queue(
            maxsize=queue_size
        )
        self._closed = False
        self._close_lock = threading.Lock()

        self._thread = threading.Thread(
            target=self._worker,
            name="async-http-uploader",
            daemon=False,
        )
        self._thread.start()

    def submit(self, request: UploadRequest) -> None:
        """提交异步上传任务。"""
        with self._close_lock:
            if self._closed:
                raise RuntimeError("上传器已经关闭，不能继续提交上传任务。")

            self._queue.put((copy_context(), request))

    def flush(self) -> None:
        """等待当前已提交的上传任务全部处理完成。"""
        self._queue.join()

    def close(self) -> None:
        """
        优雅关闭上传器。

        已提交的任务仍会继续执行；
        close 后禁止继续提交新任务。
        """
        with self._close_lock:
            if self._closed:
                return

            self._closed = True
            self._queue.put(self._STOP)

        self._thread.join()

    def _worker(self) -> None:
        while True:
            task = self._queue.get()

            try:
                if task is self._STOP:
                    return

                assert isinstance(task, tuple)
                context, request = task
                context.run(self._client.post_json, request)

            except Exception:
                self._logger.exception("异步上传任务执行异常。")

            finally:
                self._queue.task_done()
