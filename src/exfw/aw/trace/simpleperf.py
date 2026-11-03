import logging
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from logging import Logger

import adbutils

from .utils import (
    PHONE_SIMPLEPERF_DIR,
    record_simpleperf,
    start_simpleperf,
    stop_simpleperf,
)


@dataclass(frozen=True)
class ActiveSimpleperf:
    """框架管理的一份活跃 Simpleperf 采集。"""

    simpleperf_path: str
    process: subprocess.Popen


class SimpleperfCollector:
    """
    Simpleperf 采集控制器。

    约束：
    1. 同一设备同一时刻只允许一份框架管理的 Simpleperf 采集。
    2. 不同设备可并行采集。
    3. 仅管理由本控制器启动的 Simpleperf 会话。
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self, logger: Logger | None = None):
        if getattr(self, "_initialized", False):
            return

        self.logger = logger or logging.getLogger("exfw.SimpleperfCollector")

        # 保护 _active_sessions。
        self._state_lock = threading.Lock()

        # 保护 _device_locks 的创建过程。
        self._device_locks_lock = threading.Lock()

        # 格式：{serial: RLock}
        # 同一设备上的 start / stop 必须串行。
        self._device_locks: dict[str, threading.RLock] = {}

        # 格式：{serial: ActiveSimpleperf}
        # 仅保存成功启动、尚未成功停止的 Simpleperf。
        self._active_sessions: dict[str, ActiveSimpleperf] = {}

        self._initialized = True

    def _get_device_lock(self, serial: str) -> threading.RLock:
        """获取指定设备的独立操作锁。"""

        with self._device_locks_lock:
            if serial not in self._device_locks:
                self._device_locks[serial] = threading.RLock()

            return self._device_locks[serial]

    def start(self, serial: str, pid_list: Sequence[int]) -> str | None:
        """
        启动指定设备的持续 Simpleperf 采集。

        Args:
            serial: 设备序列号。
            pid_list: 需要采集的 PID 列表。

        Returns:
            成功时返回设备端 .data 文件路径；
            已有活跃采集、未指定 PID 或启动失败时返回 None。
        """

        if not pid_list:
            self.logger.warning("[%s] 未指定 PID，跳过启动 Simpleperf。", serial)
            return None

        device_lock = self._get_device_lock(serial)

        with device_lock:
            active_session = self._get_live_session(serial)

            if active_session is not None:
                self.logger.warning(
                    "[%s] 已有活跃 Simpleperf，拒绝重复启动：path=%s",
                    serial,
                    active_session.simpleperf_path,
                )
                return None

            try:
                adb_dev = adbutils.adb.device(serial)

                # 由电脑端纳秒时间戳保证文件名足够唯一。
                simpleperf_path = f"{PHONE_SIMPLEPERF_DIR}/{time.time_ns()}.data"

                process = start_simpleperf(
                    device=adb_dev,
                    pid_list=list(pid_list),
                    simpleperf_path=simpleperf_path,
                )

                active_session = ActiveSimpleperf(
                    simpleperf_path=simpleperf_path, process=process
                )

                with self._state_lock:
                    self._active_sessions[serial] = active_session

                self.logger.info(
                    "[%s] Simpleperf 启动成功：path=%s, pids=%s",
                    serial,
                    simpleperf_path,
                    list(pid_list),
                )

                return simpleperf_path

            except Exception:
                self.logger.exception("[%s] Simpleperf 启动失败", serial)
                return None

    def stop(self, serial: str) -> str | None:
        """
        停止指定设备当前活跃的 Simpleperf 采集。

        仅在底层停止成功后清理活跃状态。

        Returns:
            成功时返回设备端 .data 文件路径；
            无活跃采集或停止失败时返回 None。
        """

        device_lock = self._get_device_lock(serial)

        with device_lock:
            active_session = self._get_live_session(serial)

            if active_session is None:
                self.logger.warning("[%s] 当前没有活跃 Simpleperf，无需停止。", serial)
                return None

            try:
                adb_dev = adbutils.adb.device(serial)

                stop_simpleperf(device=adb_dev, simpleperf_proc=active_session.process)

                with self._state_lock:
                    self._active_sessions.pop(serial, None)

                self.logger.info(
                    "[%s] Simpleperf 停止成功：path=%s",
                    serial,
                    active_session.simpleperf_path,
                )

                return active_session.simpleperf_path

            except Exception:
                self.logger.exception(
                    "[%s] Simpleperf 停止失败，保留活跃状态：path=%s",
                    serial,
                    active_session.simpleperf_path,
                )
                return None

    def record(
        self, serial: str, pid_list: Sequence[int], duration_s: int
    ) -> str | None:
        """异步启动指定时长的 Simpleperf 采集。"""

        if not pid_list:
            self.logger.warning("[%s] 未指定 PID，跳过定时 Simpleperf 采集。", serial)
            return None

        if duration_s <= 0:
            self.logger.warning(
                "[%s] Simpleperf 采集时长必须大于 0，当前值：%s", serial, duration_s
            )
            return None

        device_lock = self._get_device_lock(serial)

        # 用于在锁外启动后台监控线程。
        active_session: ActiveSimpleperf | None = None

        with device_lock:
            active_session = self._get_live_session(serial)

            if active_session is not None:
                self.logger.warning(
                    "[%s] 已有活跃 Simpleperf，拒绝启动定时采集：path=%s",
                    serial,
                    active_session.simpleperf_path,
                )
                return None

            try:
                adb_dev = adbutils.adb.device(serial)

                simpleperf_path = f"{PHONE_SIMPLEPERF_DIR}/{time.time_ns()}.data"

                process = record_simpleperf(
                    device=adb_dev,
                    pid_list=list(pid_list),
                    duration_s=duration_s,
                    simpleperf_path=simpleperf_path,
                )

                active_session = ActiveSimpleperf(
                    simpleperf_path=simpleperf_path,
                    process=process,
                )

                # 必须先注册状态，再释放设备锁。
                # 否则其他线程可能在这期间再次启动 Simpleperf。
                with self._state_lock:
                    self._active_sessions[serial] = active_session

            except Exception:
                self.logger.exception(
                    "[%s] 启动定时 Simpleperf 失败：duration=%ss",
                    serial,
                    duration_s,
                )
                return None

        # 已退出 device_lock：
        # 此时会话已注册，其他 start/record 会被正确拒绝。
        # 后台线程只负责等待自然结束并清理状态。
        threading.Thread(
            target=self._wait_and_cleanup,
            args=(serial, active_session),
            name=f"simpleperf-wait-{serial}",
            daemon=True,
        ).start()

        self.logger.info(
            "[%s] 定时 Simpleperf 启动成功：path=%s, duration=%ss, pids=%s",
            serial,
            active_session.simpleperf_path,
            duration_s,
            list(pid_list),
        )

        return active_session.simpleperf_path

    def _wait_and_cleanup(self, serial: str, active_session: ActiveSimpleperf) -> None:
        """等待定时 Simpleperf 自然结束，并清理活跃状态。"""

        try:
            return_code = active_session.process.wait()

            if return_code == 0:
                self.logger.info(
                    "[%s] 定时 Simpleperf 自动结束：path=%s",
                    serial,
                    active_session.simpleperf_path,
                )
            else:
                self.logger.warning(
                    "[%s] 定时 Simpleperf 异常退出：path=%s, return_code=%s",
                    serial,
                    active_session.simpleperf_path,
                    return_code,
                )

        except Exception:
            self.logger.exception(
                "[%s] 等待定时 Simpleperf 结束失败：path=%s",
                serial,
                active_session.simpleperf_path,
            )

        finally:
            with self._state_lock:
                current_session = self._active_sessions.get(serial)

                # 只能清理自己对应的那一份会话。
                if current_session is active_session:
                    self._active_sessions.pop(serial, None)

    def is_active(self, serial: str) -> bool:
        """判断指定设备是否存在框架管理中的活跃 Simpleperf。"""

        with self._state_lock:
            return serial in self._active_sessions

    def _get_live_session(self, serial: str) -> ActiveSimpleperf | None:
        """获取仍在运行的会话，并清理已退出的残留会话。"""

        with self._state_lock:
            active_session = self._active_sessions.get(serial)

            if active_session is not None and active_session.process.poll() is not None:
                self._active_sessions.pop(serial, None)
                return None

            return active_session

    def get_active_path(self, serial: str) -> str | None:
        """获取指定设备当前活跃 Simpleperf 的设备端输出路径。"""

        with self._state_lock:
            active_session = self._active_sessions.get(serial)

            return (
                active_session.simpleperf_path if active_session is not None else None
            )

    def stop_all(self) -> None:
        """停止框架管理的全部 Simpleperf 采集。"""

        with self._state_lock:
            serials = list(self._active_sessions.keys())

        for serial in serials:
            self.stop(serial)

        self.logger.info("所有设备的 Simpleperf 停止操作已执行。")

    def get_pid_list(
        self,
        serial: str,
        process_names: Sequence[str],
    ) -> list[int]:
        """根据进程名获取设备上的 PID 列表。"""

        if not process_names:
            return []

        adb_dev = adbutils.adb.device(serial)
        pid_list: list[int] = []

        for process_name in process_names:
            try:
                output = adb_dev.shell(f"pidof {process_name}").strip()

                if not output:
                    self.logger.warning(
                        "[%s] 未找到进程 PID：%s",
                        serial,
                        process_name,
                    )
                    continue

                pid_list.extend(int(pid) for pid in output.split())

            except Exception:
                self.logger.exception(
                    "[%s] 获取进程 PID 失败：%s",
                    serial,
                    process_name,
                )

        return pid_list
