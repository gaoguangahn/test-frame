from __future__ import annotations

import logging
from typing import Any

from metric_parser import LogParser


class LogAnalysis:
    """调用解析脚本，解析性能 Log 文件"""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("exfw.LogAnalysis")

    def analysis_log(
        self, log_file: str, metric_names: list[str], brand: str = "Honor"
    ) -> dict[str, Any]:
        """
        根据 metric_names 动态调用对应的解析方法。

        Args:
            log_file (str): Log 文件路径。
            metric_names (str): 日志类型，需严格对应解析方法名。
            brand (str): 设备品牌。

        Returns:
            result: 解析结果的字典，格式为 {metric: value}。
        """
        result: dict[str, Any] = {
            "success": False,
            "data": None,
            "error": None,
        }

        try:
            with LogParser(file_path=log_file, device_brand=brand) as parser:
                analyse_results = {}
                for metric in metric_names:
                    method = getattr(parser, metric, None)

                    if not callable(method):
                        error = f"未找到支持的解析方法: {metric}"
                        self.logger.warning(error)
                        result["error"] = error
                        continue

                    # 3. 直接调用解析方法
                    analyse_result = method()

                    if not analyse_result.success:
                        error = analyse_result.error or "Log 解析失败"
                        self.logger.warning(
                            "Log 解析失败: metric=%s, error=%s", metric, error
                        )
                        result["error"] = error
                        continue

                    # 4. 直接提取结果（data 已经是原生 dict/list，无需序列化处理）
                    analyse_results[metric] = analyse_result.data

                result["success"] = bool(analyse_results)
                result["data"] = analyse_results

                if not analyse_results:
                    result["error"] = "所有 metric 均解析失败"

                return result

        except TypeError as error:
            message = f"指标 [{metric}] 参数错误: {error}"
            self.logger.exception(message)
            result["error"] = message
            return result

        except Exception as error:
            message = f"Log 解析异常: {error}"
            self.logger.exception(
                "Log 解析异常: log=%s, metrics=%s", log_file, metric_names
            )
            result["error"] = message
            return result

        return result
