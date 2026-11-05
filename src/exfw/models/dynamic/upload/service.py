"""上传只消费已落盘结果，保留现有 HTTP payload 协议。"""
from typing import Any

import requests

from exfw.common.http import AsyncHttpUploader, UploadRequest
from exfw.models.dynamic.server_config import CASE_RESULT_SERVER


def create_server_task_id() -> str:
    """上传启用时按现有服务协议申请子任务 ID。"""
    response = requests.post(CASE_RESULT_SERVER.task_id_url, timeout=10.0)
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    if body.get("code") != 200:
        raise RuntimeError(f"获取任务 ID 失败：response={body}")
    task_id = body.get("data", {}).get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise RuntimeError(f"服务端未返回有效 task_id：response={body}")
    return task_id


class DynamicUploadService:
    def __init__(self):
        self._uploader = AsyncHttpUploader()

    def submit(self, payload, on_success, on_failure):
        context = payload
        name = f"case-result:task_id={context.get('task_id')}:round={context.get('round')}:case={context.get('case')}"
        self._uploader.submit(UploadRequest(
            name=name, url=CASE_RESULT_SERVER.upload_url, payload=payload,
            timeout=10.0, retries=2, headers={"Content-Type": "application/json"},
            on_success=on_success, on_failure=on_failure,
        ))

    def close(self):
        self._uploader.close()
