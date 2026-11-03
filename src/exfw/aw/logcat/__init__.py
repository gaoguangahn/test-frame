"""日志采集模块。

对外入口：
- LogCollectorFactory.get_collector(name)  按名取采集器实例（持续 / 单次统一入口）
- exfw.runtime.logcat.collectors            各具体采集器类
"""

from .collectors import BaseCollector, ContinuousCollector, InstantCollector
from .factory import LogCollectorFactory

__all__ = [
    "BaseCollector",
    "ContinuousCollector",
    "InstantCollector",
    "LogCollectorFactory",
]
