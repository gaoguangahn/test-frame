import adbutils

from exfw.aw.logcat import CmdRunner, ContinuousCollector


class JankLogCollector(ContinuousCollector):
    """jank日志采集器"""

    name = "jank_log"

    def __init__(self, logger=None):
        super().__init__(logger=logger)
        self._collectors = {}

    def start(self, serial: str, context: dict):
        self._stop_collector(serial)  # 防止重复调用

        filename = "JankRaw.log"
        path = self.build_path(context, filename)

        try:
            d = adbutils.adb.device(serial)
            d.shell("logcat -b all -c", timeout=10)
        except Exception as e:
            self.logger.error(f"clean adb log error: {e}")
            return None

        cmd = ["adb", "-s", serial, "logcat", "-b", "jank"]
        collector = CmdRunner(path, cmd, f"{self.name}_{serial}", logger=self.logger)
        collector.start()

        self._collectors[serial] = collector
        return path

    def stop(self, serial: str, context: dict):
        return self._stop_collector(serial)

    def _stop_collector(self, serial: str):
        """安全的停止指定设备的采集并返回路径"""
        collector = self._collectors.pop(serial, None)
        if collector:
            path = collector.output_path
            collector.stop()
            return path
        return None


class EventLogCollector(ContinuousCollector):
    """events日志采集器"""

    name = "events_log"

    def __init__(self, logger=None):
        super().__init__(logger=logger)
        self._collectors = {}

    def start(self, serial: str, context: dict):
        # 确保之前的 collector 已停止
        self._stop_collector(serial)

        filename = "EventsLog.log"
        path = self.build_path(context, filename)

        cmd = ["adb", "-s", serial, "logcat", "-b", "events"]
        collector = CmdRunner(path, cmd, f"{self.name}_{serial}", logger=self.logger)
        collector.start()

        self._collectors[serial] = collector
        return path

    def stop(self, serial: str, context: dict):
        return self._stop_collector(serial)

    def _stop_collector(self, serial: str):
        collector = self._collectors.pop(serial, None)
        if collector:
            path = collector.output_path
            collector.stop()
            return path
        return None


class CommonLogcatCollector(ContinuousCollector):
    """ADB日志采集器包装类"""

    name = "adb_log"

    def __init__(self, logger=None):
        super().__init__(logger=logger)
        self._collectors = {}

    def start(self, serial: str, context: dict):
        # 确保之前的 collector 已停止
        self._stop_collector(serial)

        filename = "AdbLog.log"
        path = self.build_path(context, filename)

        cmd = ["adb", "-s", serial, "logcat"]
        collector = CmdRunner(path, cmd, f"{self.name}_{serial}", logger=self.logger)
        collector.start()

        self._collectors[serial] = collector
        return path

    def stop(self, serial: str, context: dict):
        return self._stop_collector(serial)

    def _stop_collector(self, serial: str):
        collector = self._collectors.pop(serial, None)
        if collector:
            path = collector.output_path
            collector.stop()
            return path
        return None


class DmesgLogcatCollector(ContinuousCollector):
    """内核日志采集器包装类"""

    name = "dmesg_log"

    def __init__(self, logger=None):
        super().__init__(logger=logger)
        self._collectors = {}

    def start(self, serial: str, context: dict):
        self._stop_collector(serial)

        filename = "DmesgLog.log"
        path = self.build_path(context, filename)

        try:
            d = adbutils.adb.device(serial)
            d.shell("dmesg -c", timeout=10.0)
        except Exception as e:
            self.logger.error(f"clean dmesg log error: {e}")
            return None

        cmd = ["adb", "-s", serial, "shell", "dmesg", "-w"]
        collector = CmdRunner(path, cmd, f"{self.name}_{serial}", logger=self.logger)
        collector.start()

        self._collectors[serial] = collector
        return path

    def stop(self, serial: str, context: dict):
        return self._stop_collector(serial)

    def _stop_collector(self, serial: str):
        collector = self._collectors.pop(serial, None)
        if collector:
            path = collector.output_path
            collector.stop()
            return path
        return None
