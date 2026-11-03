from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CaseResultServerConfig:
    """动态模型用例结果服务地址。"""

    base_url: str = "http://10.163.5.3:7001"
    task_id_path: str = "/api/v1/case-results/task-id"
    upload_path: str = "/api/v1/case-results"

    @property
    def task_id_url(self) -> str:
        return self._join_url(self.task_id_path)

    @property
    def upload_url(self) -> str:
        return self._join_url(self.upload_path)

    def _join_url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"


CASE_RESULT_SERVER = CaseResultServerConfig()
