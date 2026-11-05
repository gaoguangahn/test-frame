"""分析服务只解析产物；结果保存和网络上报由调用方负责。"""
import logging
from concurrent.futures import ThreadPoolExecutor

from .log_parser_dispatcher import LogParserDispatcher
from .profile import load_analysis_profile
from .trace_parser_dispatcher import TraceParserDispatcher


class AnalysisService:
    def __init__(self, executor: ThreadPoolExecutor):
        profile = load_analysis_profile()
        self.log = LogParserDispatcher(executor=executor, metric_map=profile.log)
        self.trace = TraceParserDispatcher(executor=executor, metric_map=profile.trace)
        self.logger = logging.getLogger("exfw.dynamic.analysis")

    def parse(self, log_path, trace_path, brand):
        def run(parser, path, **kwargs):
            if path is None:
                return []
            try:
                return parser.parse(path, brand=brand, **kwargs)
            except Exception as error:
                self.logger.exception("产物解析失败：path=%s", path)
                return [{"success": False, "error": str(error)}]
        return run(self.log, log_path), run(self.trace, trace_path)
