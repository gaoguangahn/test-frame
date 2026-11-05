"""动态模型自行维护日志采集器，实例生命周期与本次测试运行一致。"""
from .collectors import continuous_collector, instant_collector

_COLLECTOR_TYPES = {
    cls.name: cls for cls in (
        continuous_collector.JankLogCollector,
        continuous_collector.EventLogCollector,
        continuous_collector.CommonLogcatCollector,
        continuous_collector.DmesgLogcatCollector,
        instant_collector.DumpMemoryCollector,
        instant_collector.IOMeasureCollector,
        instant_collector.IOStatCollector,
        instant_collector.RadarLogCollector,
        instant_collector.BroadcastsHistoryCollector,
        instant_collector.ProcMemoryCollector,
        instant_collector.SoftResourceCollector,
    )
}


class DynamicCollectorRegistry:
    """为一次动态模型运行创建独立采集器，避免跨 session 共享状态。"""

    def __init__(self):
        self._collectors = {name: cls() for name, cls in _COLLECTOR_TYPES.items()}

    def get(self, name):
        try:
            return self._collectors[name]
        except KeyError as error:
            raise ValueError(f"动态模型采集器不存在：{name}") from error
