import re
import subprocess
import time
from pathlib import Path

import adbutils
from adbutils import AdbDevice

BASE_DIR = Path(__file__).resolve().parent
TRACE_CONFIG_PATH = BASE_DIR / "config" / "trace_config.txt"

PHONE_TRACE_CONFIG = "/data/misc/perfetto-configs/trace_config.txt"
PHONE_TRACE_DIR = "/data/misc/perfetto-traces"

PREPARE_TRACE_CMDS = [
    "setprop persist.traced.enable 1",
    "setenforce 0",
    "echo sched_waking irq > /sys/kernel/tracing/set_event",
    "am trace-ipc start",
]

PHONE_SIMPLEPERF_DIR = "/data/misc/simpleperf"


def get_device(serial_or_dev: str | AdbDevice) -> AdbDevice:
    """内部辅助函数：统一获取 AdbDevice 实例"""
    if isinstance(serial_or_dev, str):
        return adbutils.adb.device(serial_or_dev)
    return serial_or_dev


def get_monotonic_time_s(device: str | AdbDevice) -> float:
    """获取手机的单调时间（秒）"""
    try:
        adb_dev = get_device(device)
        result = adb_dev.shell("cat /proc/uptime", timeout=1).rstrip()
        if not result:
            return 0.0
        return float(result.split()[0])
    except Exception:
        return 0.0


def setup_trace_environment(
    device: str | AdbDevice, trace_config_path: str | None = None
):
    """设置trace环境"""
    if not trace_config_path:
        trace_config_path = str(
            Path(__file__).resolve().parent / "config" / "trace_config.txt"
        )

    adb_dev = get_device(device)
    try:
        adb_dev.sync.push(trace_config_path, PHONE_TRACE_CONFIG)
    except Exception as e:
        raise RuntimeError(f"push trace_config 失败: {e}")

    for cmd in PREPARE_TRACE_CMDS:
        try:
            adb_dev.shell(cmd)
        except Exception:
            continue


def _parse_perfetto_pid(output: str) -> int:
    """
    从 `perfetto -D` 输出中提取后台 Perfetto 进程 PID。

    正常情况下，Perfetto 会单独输出一行 PID，例如：
    12345
    """

    matches = re.findall(r"(?m)^\s*(\d+)\s*$", output)

    if not matches:
        raise RuntimeError(
            f"Perfetto 启动命令已返回，但无法从输出中解析后台 PID：{output!r}"
        )

    return int(matches[-1])


def start_perfetto(device: str | AdbDevice, trace_path: str):
    """
    使用 -D 后台模式启动 Perfetto，并返回 Perfetto 进程 PID。

    设备端命令类似：

    perfetto -D --txt \
      -c /data/local/tmp/trace_config.txt \
      -o /data/misc/perfetto-traces/xxx.pftrace

    Args:
        device: 设备序列号或 AdbDevice。
        trace_path: 设备端 Trace 输出文件路径。

    Returns:
        后台 Perfetto 进程 PID。

    Raises:
        RuntimeError: 启动失败或无法从命令输出中解析 PID。
    """
    adb_dev = get_device(device)
    cmd = f"perfetto -D --txt -c {PHONE_TRACE_CONFIG} -o {trace_path}"

    try:
        output = adb_dev.shell(cmd, timeout=10).strip()
    except Exception as e:
        raise RuntimeError(f"启动 perfetto 失败: {e}")

    # perfetto -D 正常情况下会输出后台进程 PID。
    # 为兼容输出中包含额外日志的场景，提取最后一个纯数字行。
    return _parse_perfetto_pid(output)


def is_process_alive(device: str | AdbDevice, pid: int) -> bool:
    """
    检查设备端指定 PID 是否存在。

    `kill -0` 不会真正发送信号，只用于检查：
    - 返回码为 0：进程存在，且当前用户有权限操作；
    - 返回码非 0：进程已退出或无权限操作。
    """

    if pid <= 0:
        return False

    adb_dev = get_device(device)
    exit_code_marker = "__PROCESS_EXIT_CODE__"

    # adbutils.shell() 不一定能拿到远端命令的退出码，
    # 因此通过 echo $?... 显式输出退出码。
    cmd = f"kill -0 {pid} >/dev/null 2>&1; echo {exit_code_marker}:$?"

    try:
        output = adb_dev.shell(cmd, timeout=5).strip()
    except Exception as e:
        raise RuntimeError(f"检查 Perfetto 进程状态失败，PID={pid}: {e}") from e

    match = re.search(rf"{exit_code_marker}:(\d+)", output)

    if not match:
        raise RuntimeError(f"无法解析进程状态检查结果，PID={pid}，输出：{output!r}")

    return match.group(1) == "0"


def stop_perfetto(
    device: str | AdbDevice,
    perfetto_pid: int,
    max_retry: int = 3,
) -> None:
    """
    停止 Perfetto 进程。

    停止策略：
    1. 优先发送 SIGTERM，让 Perfetto 正常停止、flush 缓冲区并写完 Trace；
    2. 多次 SIGTERM 后仍未退出时，可选发送 SIGKILL 强制结束；
    3. SIGKILL 成功后仍会抛出 RuntimeError，提示 Trace 可能不完整。

    Args:
        device: 设备序列号或 AdbDevice。
        perfetto_pid: start_perfetto() 返回的 Perfetto 进程 PID。
        max_retry: 最多发送 SIGTERM 的次数。

    Raises:
        RuntimeError: 优雅停止失败；即使强制结束成功，也会抛出异常提示。
    """

    if perfetto_pid <= 0:
        raise ValueError(f"非法 Perfetto PID: {perfetto_pid}")

    if max_retry <= 0:
        raise ValueError(f"max_retry 必须大于 0，当前值: {max_retry}")

    adb_dev = get_device(device)

    # 进程已经自然退出，无需再发送停止信号。
    if not is_process_alive(adb_dev, perfetto_pid):
        return

    for attempt in range(1, max_retry + 1):
        try:
            adb_dev.shell(
                f"kill -TERM {perfetto_pid}",
                timeout=3,
            )
        except Exception:
            pass

        if not is_process_alive(adb_dev, perfetto_pid):
            return

        if attempt < max_retry:
            time.sleep(0.1)

    try:
        adb_dev.shell(f"kill -KILL {perfetto_pid}", timeout=3)
    except Exception as e:
        raise RuntimeError(
            f"Perfetto 停止失败，且发送 SIGKILL 失败：PID={perfetto_pid}，错误：{e}"
        ) from e

    # SIGKILL 执行后立即检查；若设备调度略慢，短暂等待一次。
    time.sleep(0.1)

    if is_process_alive(adb_dev, perfetto_pid):
        raise RuntimeError(
            f"Perfetto 无法停止：PID={perfetto_pid} 在发送 "
            f"{max_retry} 次 SIGTERM 和 SIGKILL 后仍存在"
        )

    raise RuntimeError(
        f"Perfetto 已被强制停止：PID={perfetto_pid}。"
        "SIGTERM 未能正常结束进程，当前 Trace 文件可能不完整。"
    )


def start_simpleperf(
    device: str | AdbDevice, simpleperf_path: str, pid_list: list[int] | None
) -> subprocess.Popen:
    """开始 simpleperf 抓取(持续采集)

    Args:
        device (Union[str, u2.Device]): _description_
        simpleperf_path (str): 保存 perf 数据的路径
        pid_list (list, optional): 需要采集 perf 数据的 pid 列表. Defaults to None.

    Raises:
        RuntimeError: _description_

    Returns:
        subprocess.Popen: 已经启动的simpleperf 进程
    """
    adb_dev = get_device(device)
    try:
        adb_dev.shell("pkill -2 simpleperf")
    except Exception:
        pass

    if not pid_list:
        raise RuntimeError("启动simpleperf失败, 未指定需要采集的pid")

    pid_str = ",".join(map(str, pid_list))

    cmd = [
        "adb",
        "-s",
        adb_dev.serial,
        "shell",
        f"simpleperf record -p {pid_str} -g -o {simpleperf_path}",
    ]
    try:
        simpleperf_proc = subprocess.Popen(
            cmd,
            startupinfo=subprocess.STARTUPINFO(),
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        raise RuntimeError(f"启动simpleperf失败, 执行命令失败: {e}")
    return simpleperf_proc


def stop_simpleperf(device: str | AdbDevice, simpleperf_proc: subprocess.Popen):
    """停止 simpleperf 抓取"""
    if not simpleperf_proc:
        return

    adb_dev = get_device(device)

    try:
        # 优先使用 SIGINT，让 simpleperf 正常收尾并写入 data 文件。
        adb_dev.shell("pkill -2 simpleperf")
    except Exception as e:
        raise RuntimeError(f"发送 Simpleperf 停止信号失败: {e}") from e

    try:
        simpleperf_proc.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        # 设备端进程仍未退出时，使用默认终止信号兜底。
        adb_dev.shell("pkill -2 simpleperf")
        simpleperf_proc.wait(timeout=5)
        return
    except Exception as e:
        raise RuntimeError("Simpleperf 未在预期时间内停止") from e


def record_simpleperf(
    device: str | AdbDevice, pid_list: list[int], duration_s: int, simpleperf_path: str
) -> subprocess.Popen:
    """异步启动指定时长的 Simpleperf 采集。"""

    if not pid_list:
        raise ValueError("未指定需要采集的 PID")

    if duration_s <= 0:
        raise ValueError(f"采集时长必须大于 0，当前值：{duration_s}")

    adb_dev = get_device(device)
    pid_str = ",".join(map(str, pid_list))

    cmd = [
        "adb",
        "-s",
        adb_dev.serial,
        "shell",
        (
            f"simpleperf record "
            f"-p {pid_str} "
            f"-g "
            f"--duration {duration_s} "
            f"-o {simpleperf_path}"
        ),
    ]

    try:
        return subprocess.Popen(
            cmd,
            startupinfo=subprocess.STARTUPINFO(),
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        raise RuntimeError(f"启动定时 Simpleperf 采集失败：{e}") from e


if __name__ == "__main__":
    result = is_process_alive(device="ASPS015928000498", pid=1234111)
    print(result)
