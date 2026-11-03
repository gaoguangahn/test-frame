import inspect
import logging
from logging import Logger
from typing import Any

from metric_parser import AnalyseResult, TraceParser


class TraceAnalysis:
    """调用解析库，解析 trace 文件"""

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or logging.getLogger("exfw.TraceAnalysis")

    def analysis_trace(
        self,
        trace_file: str,
        metric: str,
        params: dict[str, Any] | None = None,
        brand: str = "Honor",
    ):
        """解析 trace 文件并返回结果。

        Args:
            trace_file (str): Trace 文件路径。
            metric (str): 需要解析的指标。
            params (dict[str, Any] | None): 指标解析方法的参数。
            brand (str): 设备品牌型号。

        Returns:
            result: 解析结果的字典，格式为 {metric: value}。
            trace_length: trace的长度。
        """

        result: dict[str, Any] = {
            "success": False,
            "metric": metric,
            "trace_info": {
                "trace_length": 0.0,
                "trace_start": 0,
                "trace_end": 0,
            },
            "data": None,
            "error": None,
        }
        # None 表示调用方不传任何指标参数。
        params = params or {}

        try:
            with TraceParser(trace_file=trace_file, device_brand=brand) as parser:
                # 1. 加载 trace 文件，并获取 trace 长度
                result["trace_info"] = {
                    "trace_length": parser.trace_length,
                    "trace_start": parser.trace_start,
                    "trace_end": parser.trace_end,
                }

                # 2. 获取解析方法
                method = getattr(parser, metric, None)
                if not callable(method):
                    error = f"未找到支持的解析方法: {metric}"
                    self.logger.warning(error)
                    result["error"] = error
                    return result

                # 过滤调用方传入的多余参数，避免无效字段导致 TypeError。
                signature = inspect.signature(method)
                valid_params = set(signature.parameters)

                filtered_params = {
                    key: value for key, value in params.items() if key in valid_params
                }

                ignored_params = set(params) - valid_params
                if ignored_params:
                    self.logger.warning(
                        "指标 [%s] 忽略不支持的参数: %s",
                        metric,
                        sorted(ignored_params),
                    )

                # 当 params 为空时，就是 method()，
                # 会自动使用 TraceParser 中定义的默认参数。
                analyse_result: AnalyseResult = method(**filtered_params)

                if not analyse_result.success:
                    error = analyse_result.error or "Trace 解析失败"
                    self.logger.warning(
                        "Trace 解析失败: metric=%s, error=%s",
                        metric,
                        error,
                    )
                    result["error"] = error
                    return result

                result["success"] = True
                result["data"] = self._serialize_data(analyse_result.data)
                self.logger.info(
                    "Trace 解析成功: trace=%s, metric=%s", trace_file, metric
                )

                return result

        except TypeError as error:
            message = f"指标 [{metric}] 参数错误: {error}"
            self.logger.exception(message)
            result["error"] = message
            return result

        except Exception as error:
            message = f"Trace 解析异常: {error}"
            self.logger.exception(
                "Trace 解析异常: trace=%s, metric=%s", trace_file, metric
            )
            result["error"] = message
            return result

    @staticmethod
    def _serialize_data(data: Any) -> Any:
        """将解析结果转换为可 JSON 序列化的数据结构。"""

        if isinstance(data, list):
            return [
                item.to_dict() if hasattr(item, "to_dict") else item for item in data
            ]

        return data.to_dict() if hasattr(data, "to_dict") else data
