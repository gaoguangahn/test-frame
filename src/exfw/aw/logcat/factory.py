from .collectors.base_collector import BaseCollector


class LogCollectorFactory:
    _instances = {}  # 用来缓存实例，确保单例（如果需要的话）

    @classmethod
    def get_collector(cls, name: str, logger=None):
        """根据名字获取对应的采集器实例"""
        cache_key = (name, id(logger) if logger else None)

        if cache_key in cls._instances:
            return cls._instances[cache_key]

        collector_class = BaseCollector.registry.get(name)
        if not collector_class:
            raise ValueError(f"找不到名为 '{name}' 的日志采集器！")

        instance = collector_class(logger=logger)
        cls._instances[cache_key] = instance
        return instance
