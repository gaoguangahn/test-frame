import time
from logging import Logger

from adbutils import AdbDevice

from .base_collector import InstantCollector


class DumpMemoryCollector(InstantCollector):
    """内存信息采集器"""

    name = "dumpsys_meminfo"

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger=logger)

    def collect(self, device: str | AdbDevice, context: dict):
        """采集内存信息

        期望的 context 字段：
            - loop: int/str，loop 编号
        """
        adb_dev = self._get_device(device)
        if not adb_dev:
            self.logger.error(f"[{self.name}] device is None or invalid, skip collect.")
            return None

        filename = "DumpsysMeminfo.txt"
        save_path = self.build_path(context, filename)

        start_time = time.time()
        try:
            output = adb_dev.shell("dumpsys -t 25 meminfo", timeout=30)

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(output)

            self.logger.debug(
                f"dumpsys meminfo finished, spend {time.time() - start_time:.2f}s"
            )
            return save_path

        except Exception as e:
            self.logger.error(f"dumpsys meminfo failed: {e}")
            return None


class IOMeasureCollector(InstantCollector):
    """IO测量采集器"""

    name = "io_measure"

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger=logger)

    def collect(self, device: str | AdbDevice, context: dict):
        """IO测量并重置"""
        adb_dev = self._get_device(device)
        if not adb_dev:
            self.logger.error(f"[{self.name}] device is None or invalid, skip collect.")
            return None

        filename = "io_measure.txt"
        save_path = self.build_path(context, filename)

        start_time = time.time()

        src_files = [
            "/proc/iomeasure/io_fs_scatter",
            "/proc/iomeasure/io_blk_scatter",
            "/proc/iomeasure/io_blk_sched_scatter",
            "/proc/iomeasure/io_scsi_scatter",
            "/proc/iomeasure/io_scsi_sched_scatter",
            "/proc/iomeasure/io_pagecache",
        ]

        try:
            cmd = "cat " + " ".join(src_files)
            output = adb_dev.shell(cmd, timeout=5)

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(output)

            self.logger.debug(
                f"IO measure finished, spend {time.time() - start_time:.2f}s"
            )
            adb_dev.shell("echo 1 > /proc/iomeasure/reset", timeout=10)
            self.logger.debug("reset io measure success")
            return save_path
        except Exception as e:
            self.logger.error(f"IO failed: {e}")
            return None


class IOStatCollector(InstantCollector):
    """IOStat采集器"""

    name = "io_stat"

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger=logger)

    def collect(self, device: str | AdbDevice, context: dict):
        """IOStat

        期望的 context 字段：
            - loop_num: int/str，loop 编号
            - stage: "start" / "end" / 其他字符串
        """
        adb_dev = self._get_device(device)
        if not adb_dev:
            self.logger.error(f"[{self.name}] device is None or invalid, skip collect.")
            return None

        stage = context.get("stage")
        if stage is not None:
            filename = "io_stat_" + stage + f"_{int(time.time())}.txt"
        else:
            filename = "io_stat_" + f"_{int(time.time())}.txt"

        save_path = self.build_path(context, filename)

        start_time = time.time()
        try:
            output = adb_dev.shell("cat /sys/block/sda/stat", timeout=20)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(output)

            self.logger.debug(f"IOStat finished, spend {time.time() - start_time:.2f}s")
            return save_path
        except Exception as e:
            self.logger.error(f"IOStat failed: {e}")
            return None


class RadarLogCollector(InstantCollector):
    """性能雷达采集器"""

    name = "radar"

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger=logger)
        self._bd_start_times = {}

    def reset(self, device: str | AdbDevice, context: dict):
        """开始阶段：重置性能雷达数据并记录时间"""
        adb_dev = self._get_device(device)
        if not adb_dev:
            self.logger.error(f"[{self.name}] device is None or invalid, skip collect.")
            return

        serial = adb_dev.serial
        if not serial:
            self.logger.error(f"[{self.name}] device serial is None, skip collect.")
            return

        try:
            adb_dev.shell("dumpsys jank -cbd", timeout=10)
            self._bd_start_times[serial] = time.time()
            self.logger.debug(f"[{serial}] radar reset success, timer started.")
        except Exception as e:
            self.logger.error(f"[{serial}] radar reset failed: {e}")

        return

    def collect(self, device: str | AdbDevice, context: dict):
        """结束阶段：生成数据、计算耗时并拉取文件"""
        adb_dev = self._get_device(device)
        if not adb_dev:
            return None

        serial = adb_dev.serial
        if not serial:
            return None

        phone_bd_file = "/data/log/jank/bd/actionstats.bd"

        try:
            adb_dev.shell("dumpsys jank -sbd", timeout=10)

            found = False
            for _ in range(8):
                file_info = adb_dev.sync.stat(phone_bd_file)
                if file_info.size > 0:
                    found = True
                    break
                time.sleep(1)

            if not found:
                self.logger.error(f"[{serial}] bd file not found: {phone_bd_file}")
                return None

            start_time = self._bd_start_times.pop(serial, time.time())
            expend_time = int(time.time() - start_time)

            filename = f"actionstats_{expend_time}.txt"
            local_path = self.build_path(context, filename)

            adb_dev.sync.pull(phone_bd_file, local_path, exist_ok=True)
            self.logger.debug(
                f"[{serial}] radar cat finished, expend time: {expend_time}s"
            )

            return local_path

        except Exception as e:
            self.logger.error(f"[{serial}] radar stop failed: {e}")
            return None


class BroadcastsHistoryCollector(InstantCollector):
    """广播历史采集器"""

    name = "broadcasts_history"

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger=logger)

    def collect(self, device: str | AdbDevice, context: dict):
        """采集广播历史"""
        adb_dev = self._get_device(device)
        if not adb_dev:
            self.logger.error(f"[{self.name}] device is None or invalid, skip collect.")
            return None

        filename = "broadcast.txt"
        file_path = self.build_path(context, filename)

        start_time = time.time()

        try:
            output = adb_dev.shell("dumpsys activity broadcasts history", timeout=5)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(output)

            self.logger.debug(
                f"broadcasts history finished, spend {time.time() - start_time:.2f}s"
            )
            return file_path
        except Exception as e:
            self.logger.error(f"broadcasts history failed: {e}")
            return None


class ProcMemoryCollector(InstantCollector):
    """进程内存采集器"""

    name = "proc_memory"

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger=logger)

    def collect(self, device: str | AdbDevice, context: dict):
        """采集进程内存信息"""
        adb_dev = self._get_device(device)
        if not adb_dev:
            self.logger.error(f"[{self.name}] device is None or invalid, skip collect.")
            return None

        filename = "proc_memory.txt"
        file_path = self.build_path(context, filename)

        start_time = time.time()
        src_paths = [
            "/proc/meminfo",
            "/proc/vmstat",
            "/proc/pressure/memory",
            "/dev/memcg/memory.psi_health_info",
        ]

        try:
            cmd = "cat " + " ".join(src_paths)
            output = adb_dev.shell(cmd, timeout=5)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(output)

            self.logger.debug(
                f"proc memory finished, spend {time.time() - start_time:.2f}s"
            )
            return file_path
        except Exception as e:
            self.logger.error(f"proc memory failed: {e}")
            return None


class SoftResourceCollector(InstantCollector):
    """soft resource采集"""

    name = "soft_resource"

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger=logger)

    def collect(self, device: str | AdbDevice, context: dict):
        """采集软资源相关日志"""
        adb_dev = self._get_device(device)
        if not adb_dev:
            self.logger.error(f"[{self.name}] device is None or invalid, skip collect.")
            return None

        filename = "soft_resource.txt"
        file_path = self.build_path(context, filename)
        src_path = "/data/log/iaware/broadcast/broadcast_policy_info.log"

        start_time = time.time()
        try:
            adb_dev.sync.pull(src_path, file_path, exist_ok=True)
            self.logger.debug(
                f"soft resource finished, spend {time.time() - start_time:.2f}s"
            )
            return file_path
        except Exception as e:
            self.logger.error(f"soft resource failed: {e}")
            return None
