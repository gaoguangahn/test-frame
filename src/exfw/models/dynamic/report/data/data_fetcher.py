from __future__ import annotations

from typing import Any, Optional, Self

import requests


class ReportDataFetcher:
    """从服务端拉取报告生成所需的用例结果数据。"""

    def __init__(
        self,
        base_url: str = "http://10.163.5.3:7001/api",
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    @staticmethod
    def _build_params(**kwargs: Any) -> dict[str, Any]:
        """过滤值为 None 的查询参数。"""
        return {key: value for key, value in kwargs.items() if value is not None}

    def fetch_case_results(
        self,
        task_id: str | None = None,
        serial: str | None = None,
        round: int | None = None,
        case: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        查询用例结果列表。

        对应服务端接口：
        GET /v1/case-results

        服务端使用游标分页：
        - limit：单页数量；
        - last_id：上一页最后一条记录 ID；
        - 返回空列表或返回数量小于 limit 时表示没有下一页。

        参数：
        - task_id：任务 ID
        - serial：设备序列号
        - round：测试轮次
        - case：用例名称
        - limit：单页数量，服务端当前支持 1~1000。
        """
        url = f"{self.base_url}/v1/case-results"
        base_params = self._build_params(
            task_id=task_id,
            serial=serial,
            round=round,
            case=case,
        )
        limit = max(1, min(limit, 1000))

        records: list[dict[str, Any]] = []
        last_id: int | None = None

        while True:
            params = self._build_params(
                **base_params,
                limit=limit,
                last_id=last_id,
            )

            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()

                result = response.json()

                if not isinstance(result, list):
                    raise TypeError(
                        f"接口返回格式异常，预期为 list，实际为 {type(result).__name__}"
                    )

                if not result:
                    break

                page_records: list[dict[str, Any]] = []

                for item in result:
                    if not isinstance(item, dict):
                        raise TypeError(
                            f"接口返回列表元素格式异常，预期为 dict，实际为 {type(item).__name__}"
                        )

                    page_records.append(item)

                records.extend(page_records)

                last_item_id = page_records[-1].get("id")
                if not isinstance(last_item_id, int):
                    raise TypeError("接口返回数据缺少有效 id，无法继续游标分页。")

                last_id = last_item_id

                if len(page_records) < limit:
                    break

            except requests.RequestException as error:
                raise RuntimeError(f"获取用例结果失败：{error}") from error

            except ValueError as error:
                raise RuntimeError(f"解析用例结果失败：{error}") from error

            except TypeError as error:
                raise RuntimeError(f"用例结果格式异常：{error}") from error

        return records

    def fetch_case_result_by_id(
        self,
        result_id: int,
    ) -> dict[str, Any] | None:
        """
        按主键 ID 查询单条用例结果。

        对应服务端接口：
        GET /v1/case-results/{result_id}
        """
        url = f"{self.base_url}/v1/case-results/{result_id}"

        try:
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 404:
                return None

            response.raise_for_status()

            result = response.json()

            if not isinstance(result, dict):
                raise TypeError(
                    f"接口返回格式异常，预期为 dict，实际为 {type(result).__name__}"
                )

            return result

        except requests.RequestException as error:
            print(f"获取用例结果失败，result_id={result_id}：{error}")
            return None

        except ValueError as error:
            print(f"解析用例结果失败，result_id={result_id}：{error}")
            return None

    def close(self) -> None:
        """关闭 HTTP 连接池。"""
        self.session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
