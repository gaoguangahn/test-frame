import os
import re
import subprocess
import time

import uiautomator2 as u2
import uiautomator2.exceptions as u2_exceptions

ADB_SERVER_PORT = os.environ.get("ADB_SERVER_PORT")  # 复用已有配置


def _to_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _build_exact_regex(values):
    patterns = [re.escape(str(v)) for v in values]
    if not patterns:
        return None
    if len(patterns) == 1:
        return f"^{patterns[0]}$"
    return f"^({'|'.join(patterns)})$"


def _build_contains_regex(values):
    patterns = [re.escape(str(v)) for v in values]
    if not patterns:
        return None
    if len(patterns) == 1:
        return f".*{patterns[0]}.*"
    return f".*({'|'.join(patterns)}).*"


def run_cmd_with_adb(cmd: list[str], timeout=10):
    """简单封装命令行调用，自动继承 ADB_SERVER_PORT"""
    env = os.environ.copy()
    if ADB_SERVER_PORT:
        env["ADB_SERVER_PORT"] = ADB_SERVER_PORT

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            env=env,
            check=True,
        )
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"adb cmd failed: {e.stderr or e.stdout or e}")


def wait_for_device_online(
    serial: str, timeout: float = 180, interval: int = 3
) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        out, _ = run_cmd_with_adb(["adb", "-s", serial, "get-state"])
        if out.strip() == "device":
            return True
        time.sleep(interval)
    return False


def wait_for_u2_ready(serial_or_ip: str, timeout: float = 30, interval: int = 3):
    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            d = u2.connect(serial_or_ip)
            _ = d.window_size()
            return d
        except (u2_exceptions.UiObjectNotFoundError, Exception) as e:
            last_err = e
            time.sleep(interval)

    raise RuntimeError(f"uiautomator2 连接超时: {last_err}")


def get_center(bound):
    """
    Get the center of the bound.
    """
    # bounds 格式: [x1,y1][x2,y2]
    nums = list(map(int, re.findall(r"\d+", bound)))
    x1, y1, x2, y2 = nums
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return cx, cy
