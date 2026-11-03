from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import requests

JsonPayload = dict[str, Any] | list[Any]
ResponseValidator = Callable[[requests.Response], bool]
SuccessCallback = Callable[[requests.Response], None]
FailureCallback = Callable[[requests.Response | None, Exception | None], None]


@dataclass(frozen=True)
class UploadRequest:
    """通用的 JSON 上传任务。"""

    name: str
    url: str
    payload: JsonPayload

    timeout: float = 5.0
    retries: int = 1
    headers: Mapping[str, str] | None = None

    # 业务方可按自己的服务端协议定义成功标准。
    # 不传时默认使用 HTTP 2xx。
    validator: ResponseValidator | None = None

    # 用于业务方记录成功或失败信息，不在 common 层写业务日志。
    on_success: SuccessCallback | None = None
    on_failure: FailureCallback | None = None
