from __future__ import annotations

import logging
import time

import requests

from .types import UploadRequest


class HttpJsonClient:
    """提供带超时和重试的同步 JSON POST 请求能力。"""

    def __init__(
        self,
        logger: logging.Logger | None = None,
        retry_interval: float = 1.0,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._retry_interval = retry_interval

    def post_json(self, request: UploadRequest) -> bool:
        """
        执行上传任务。

        返回：
            True：上传成功。
            False：重试耗尽后仍失败。
        """
        total_attempts = request.retries + 1
        last_response: requests.Response | None = None
        last_error: Exception | None = None

        for attempt in range(1, total_attempts + 1):
            try:
                response = requests.post(
                    request.url,
                    json=request.payload,
                    headers=request.headers,
                    timeout=request.timeout,
                )
                last_response = response

                is_success = (
                    request.validator(response)
                    if request.validator is not None
                    else response.ok
                )

                if is_success:
                    self._logger.info(
                        "HTTP 上传成功：name=%s, status=%s, attempt=%s/%s",
                        request.name,
                        response.status_code,
                        attempt,
                        total_attempts,
                    )
                    if request.on_success is not None:
                        request.on_success(response)
                    return True

                self._logger.warning(
                    "HTTP 上传失败：name=%s, status=%s, attempt=%s/%s, response=%s",
                    request.name,
                    response.status_code,
                    attempt,
                    total_attempts,
                    response.text,
                )

            except requests.RequestException as error:
                last_error = error
                self._logger.warning(
                    "HTTP 上传异常：name=%s, attempt=%s/%s, error=%s",
                    request.name,
                    attempt,
                    total_attempts,
                    error,
                )

            if attempt < total_attempts:
                time.sleep(self._retry_interval)

        self._logger.error(
            "HTTP 上传最终失败：name=%s, url=%s",
            request.name,
            request.url,
        )

        if request.on_failure is not None:
            request.on_failure(last_response, last_error)

        return False
