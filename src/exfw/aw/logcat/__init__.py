"""日志采集基础接口；具体采集器由各测试模型提供。"""
from .base_collector import BaseCollector, ContinuousCollector, InstantCollector
from .cmd_runner import CmdRunner

__all__ = ["BaseCollector", "ContinuousCollector", "InstantCollector", "CmdRunner"]
