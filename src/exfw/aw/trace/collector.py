import logging
import shlex
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from logging import Logger

import adbutils

from .utils import *


@dataclass(frozen=True)
class TraceRecord:
    """一份 Perfetto Trace 的采集记录及其描述。"""

    trace_path: str
    perfetto_pid: int
    serial: str
    description: str
    start_time: float
    end_time: float | None = None
    duration_seconds: float | None = None


class TraceCollector:
    """
    Perfetto Trace 采集控制器。

    约束：
    1. 同一采集器实例中，同一设备同一时刻只允许一份活跃 Trace。
    2. 不同设备可以并行抓取 Trace。
    3. 本类只负责 Trace 的启动和停止，不关心测试步骤。
    同一设备若由多个采集器实例操作，调用方需避免并发采集。
    """

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or logging.getLogger("exfw.TraceCollector")

        # 保护 _active_traces。
        self._state_lock = threading.Lock()

        # 保护 _device_locks 的创建过程。
        self._device_locks_lock = threading.Lock()

        # 格式：{serial: RLock}
        # 同一设备上的 start / stop 必须串行。
        self._device_locks: dict[str, threading.Lock] = {}

        # 当前正在采集的 Trace：{serial: TraceRecord}
        self._active_traces: dict[str, TraceRecord] = {}

        # 当前进程中已成功停止的 Trace：{serial: [TraceRecord, ...]}
        self._completed_traces: dict[str, list[TraceRecord]] = {}

        # 本次 Python 进程生命周期内，已成功完成 Trace 环境准备的设备。
        self._environment_ready_devices: set[str] = set()

    def _get_device_lock(self, serial: str) -> threading.Lock:
        """获取指定设备的独立操作锁。"""

        with self._device_locks_lock:
            if serial not in self._device_locks:
                self._device_locks[serial] = threading.Lock()

            return self._device_locks[serial]

    def _ensure_environment(self, serial: str) -> None:
        """
        确保指定设备的 Trace 环境已准备完成。

        调用方必须已经持有该设备对应的 device_lock。

        Raises:
            RuntimeError: Trace 环境准备失败。
        """

        with self._state_lock:
            if serial in self._environment_ready_devices:
                return

        try:
            setup_trace_environment(serial)
        except Exception as e:
            raise RuntimeError(f"[{serial}] Trace 环境设置失败") from e

        with self._state_lock:
            self._environment_ready_devices.add(serial)

        self.logger.info("[%s] Trace 环境设置成功", serial)

    def start_trace(
        self, serial: str, name: str | None = None, *, description: str = ""
    ) -> str | None:
        """
        启动指定设备的 Perfetto Trace。

        同一设备已有活跃 Trace 时，不允许重复启动。

        Args:
            serial: 设备序列号。

        Returns:
            成功时返回设备端 Trace 文件路径，例如：
            /data/misc/perfetto-traces/123456.789.pftrace

            已有 Trace 或启动失败时返回 None。
        """

        device_lock = self._get_device_lock(serial)

        with device_lock:
            with self._state_lock:
                active_trace = self._active_traces.get(serial)

            if active_trace is not None:
                self.logger.warning(
                    "[%s] 已有活跃 Trace，拒绝重复启动：path=%s, pid=%s",
                    serial,
                    active_trace.trace_path,
                    active_trace.perfetto_pid,
                )
                return None

            try:
                self._ensure_environment(serial)

                adb_dev = adbutils.adb.device(serial)

                if name is None:
                    name = f"{time.time_ns()}"
                trace_path = f"{PHONE_TRACE_DIR}/{name}.pftrace"

                start_time = time.time()

                perfetto_pid = start_perfetto(adb_dev, trace_path)

                trace_record = TraceRecord(
                    trace_path=trace_path,
                    perfetto_pid=perfetto_pid,
                    serial=serial,
                    description=description,
                    start_time=start_time,
                )

                with self._state_lock:
                    self._active_traces[serial] = trace_record

                self.logger.info(
                    "[%s] Trace 启动成功：path=%s, pid=%s",
                    serial,
                    trace_path,
                    perfetto_pid,
                )

                return trace_path

            except Exception:
                self.logger.exception(
                    "[%s] Trace 启动失败",
                    serial,
                )

                return None

    def stop_trace(self, serial: str) -> str | None:
        """
        停止指定设备当前正在采集的 Trace。

        只有 stop_perfetto 成功后，才会清理活跃状态。
        停止失败时保留活跃状态，避免错误启动第二份 Trace。

        Args:
            serial: 设备序列号。

        Returns:
            成功停止时返回设备端 Trace 路径；
            无活跃 Trace 或停止失败时返回 None。
        """

        device_lock = self._get_device_lock(serial)

        with device_lock:
            with self._state_lock:
                active_trace = self._active_traces.get(serial)

            if active_trace is None:
                self.logger.warning("[%s] 当前没有活跃 Trace，无需停止。", serial)
                return None

            try:
                adb_dev = adbutils.adb.device(serial)

                stop_perfetto(
                    device=adb_dev,
                    perfetto_pid=active_trace.perfetto_pid,
                )

                end_time = time.time()

                completed_trace = replace(
                    active_trace,
                    end_time=end_time,
                    duration_seconds=round(end_time - active_trace.start_time, 3),
                )

                with self._state_lock:
                    self._active_traces.pop(serial, None)
                    self._completed_traces.setdefault(serial, []).append(
                        completed_trace
                    )

                self.logger.info(
                    "[%s] Trace 停止成功：path=%s, pid=%s",
                    serial,
                    active_trace.trace_path,
                    active_trace.perfetto_pid,
                )

                return active_trace.trace_path

            except Exception:
                self.logger.exception(
                    "[%s] Trace 停止失败，保留活跃状态：path=%s, pid=%s",
                    serial,
                    active_trace.trace_path,
                    active_trace.perfetto_pid,
                )
                return None

    def is_trace_active(self, serial: str) -> bool:
        """判断指定设备是否存在框架管理中的活跃 Trace。"""

        with self._state_lock:
            return serial in self._active_traces

    def get_active_trace_path(self, serial: str) -> str | None:
        """获取指定设备当前活跃 Trace 的设备端路径。"""

        with self._state_lock:
            active_trace = self._active_traces.get(serial)
            return active_trace.trace_path if active_trace else None

    def get_active_trace_pid(self, serial: str) -> int | None:
        """获取指定设备当前活跃 Perfetto 的 PID。"""

        with self._state_lock:
            active_trace = self._active_traces.get(serial)
            return active_trace.perfetto_pid if active_trace else None

    def stop_all(self) -> None:
        """停止当前框架管理的所有设备 Trace。"""

        with self._state_lock:
            serials = list(self._active_traces.keys())

        for serial in serials:
            self.stop_trace(serial)

        self.logger.info("所有设备的 Trace 停止操作已执行。")

    def pull_trace_directory(self, serial: str, local_dir: str | Path) -> Path | None:
        """
        将设备端 Perfetto Trace 目录整体拉取到本地。

        注意：
        - 本方法不停止正在运行的 Perfetto。
        - 调用方应先确保当前设备的 Trace 已停止，
        否则可能拉取到未写入完成的文件。

        Args:
            serial: 设备序列号。
            local_dir: 本地 Trace 保存目录。

        Returns:
            成功时返回本地实际保存 Trace 的目录；
            失败时返回 None。
        """

        device_lock = self._get_device_lock(serial)

        with device_lock:
            try:
                local_dir = Path(local_dir)
                local_dir.mkdir(parents=True, exist_ok=True)

                adb_dev = adbutils.adb.device(serial)

                # 拉取 PHONE_TRACE_DIR 整个目录。
                # 通常结果为：
                # local_dir / <PHONE_TRACE_DIR 最后一层目录名>
                adb_dev.sync.pull(f"{PHONE_TRACE_DIR}/.", str(local_dir), exist_ok=True)

                self.logger.info(
                    "[%s] Trace 文件拉取成功：remote=%s, local=%s",
                    serial,
                    PHONE_TRACE_DIR,
                    local_dir,
                )

                return local_dir

            except Exception:
                self.logger.exception(
                    "[%s] Trace 目录拉取失败：remote=%s, local=%s",
                    serial,
                    PHONE_TRACE_DIR,
                    local_dir,
                )
                return None

    def clean_device_traces(self, serial: str) -> bool:
        """
        清理设备端 Perfetto Trace 目录中的 .pftrace 文件。

        注意：
        调用前应确保当前设备没有仍在写入的 Perfetto Trace，
        否则可能影响正在执行的 Trace。

        Args:
            serial: 设备序列号。

        Returns:
            清理成功返回 True，失败返回 False。
        """

        device_lock = self._get_device_lock(serial)

        with device_lock:
            try:
                adb_dev = adbutils.adb.device(serial)

                # PHONE_TRACE_DIR 是框架内部固定目录，不来自外部请求。
                command = f"rm -f {PHONE_TRACE_DIR}/*.pftrace"

                output = adb_dev.shell(command)

                self.logger.info(
                    "[%s] Trace 目录清理完成：dir=%s, output=%s",
                    serial,
                    PHONE_TRACE_DIR,
                    output.strip() if output else "",
                )

                return True

            except Exception:
                self.logger.exception(
                    "[%s] Trace 目录清理失败：dir=%s", serial, PHONE_TRACE_DIR
                )
                return False

    def delete_trace(self, serial: str, trace_path: str) -> bool:
        """删除指定设备上的单个 Trace 文件。"""

        device_lock = self._get_device_lock(serial)

        with device_lock:
            try:
                # trace_path 由 start_trace 内部生成；此处仍使用 quote 避免 shell 解析风险。
                command = f"rm -f {shlex.quote(trace_path)}"

                adb_dev = adbutils.adb.device(serial)
                adb_dev.shell(command)

                self.logger.info("[%s] Trace 文件删除成功：path=%s", serial, trace_path)
                return True

            except Exception:
                self.logger.exception(
                    "[%s] Trace 文件删除失败：path=%s", serial, trace_path
                )
                return False

    def completed_trace_records(self, serial: str) -> tuple[TraceRecord, ...]:
        """返回设备已完成记录的快照；调用方持久化成功后再确认清理。"""
        with self._state_lock:
            return tuple(self._completed_traces.get(serial, ()))

    def acknowledge_trace_records(self, serial: str, records: tuple[TraceRecord, ...]) -> None:
        """只移除已成功持久化的快照，保留之后新完成的记录。"""
        with self._state_lock:
            remaining = list(self._completed_traces.get(serial, ()))
            for record in records:
                if record in remaining:
                    remaining.remove(record)
            if remaining:
                self._completed_traces[serial] = remaining
            else:
                self._completed_traces.pop(serial, None)

    @contextmanager
    def collect(
        self,
        serial: str,
        name: str | None = None,
        *,
        description: str = "",
        delete_on_error: bool = True,
    ) -> Generator[str, None, None]:
        """
        在 with 进入时启动 Trace，退出时停止 Trace。

        Args:
            serial: 设备序列号。
            name: Trace 文件名，不包含 .pftrace 后缀。
            delete_on_error: with 内发生异常时，停止并删除本次 Trace。
        """

        trace_path = self.start_trace(serial=serial, name=name, description=description)

        if trace_path is None:
            raise RuntimeError(f"[{serial}] Trace 启动失败，或已有活跃 Trace")

        try:
            yield trace_path

        except BaseException:
            # 先停止，避免 Perfetto 仍在写入时就删除文件。
            stopped_trace_path = self.stop_trace(serial)

            if delete_on_error and stopped_trace_path is not None:
                self.delete_trace(serial=serial, trace_path=stopped_trace_path)

            # 必须继续抛出原始异常，确保 pytest 正确标记用例失败。
            raise

        else:
            self.stop_trace(serial)
