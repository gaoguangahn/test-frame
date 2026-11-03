import json
import os
from pathlib import Path
from typing import Any, Optional

import requests


def format_duration(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}小时{m}分钟{s}秒"


def download_file(url: str, save_dir: str = ".", filename: Optional[str] = None) -> str:
    """
    从 url 下载文件到 save_dir 目录
    """
    os.makedirs(save_dir, exist_ok=True)

    # 如果没指定文件名，就从 url 里截取
    if filename is None:
        filename = url.split("?")[0].rstrip("/").split("/")[-1] or "download.bin"

    save_path = os.path.join(save_dir, filename)

    # 直接 GET 即可，这种 json 链接一般不需要特殊头
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()  # 不是 2xx 会抛异常

    with open(save_path, "wb") as f:
        f.write(resp.content)

    return save_path


def safe_int(value):
    """安全转 int，无法转换返回 None"""
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def _avg_and_std(numbers):
    """计算平均值和标准差"""
    if not numbers:
        return 0, 0.0
    mean = sum(numbers) / len(numbers)
    variance = sum((x - mean) ** 2 for x in numbers) / len(numbers)
    std_dev = variance**0.5
    return round(mean, 2), round(std_dev, 2)


def _counts_in_range(numbers, lower=None, upper=None):
    """计算给定范围内出现的次数"""
    count = 0
    for number in numbers:
        if lower is not None and upper is not None:
            if lower <= number < upper:
                count += 1
        elif lower is not None:
            if number >= lower:
                count += 1
        elif upper is not None:
            if number < upper:
                count += 1
    return count


def _get_range_percent(values, lower, upper, multiple, total, digits=2):
    """计算给定范围内出现的百分比"""
    if total == 0:
        return "-", "-"
    cnt = _counts_in_range(values, lower, upper)
    percent = round(cnt * multiple / total, digits)
    return percent, f"{cnt} / {total}"


def _gen_count_and_label2(numerator, denominator, multiplier=1, ndigits=2):
    """剩下的百分比计算"""
    if denominator == 0:
        return 0, 0
    value = round(numerator * multiplier / denominator, ndigits)
    label = f"{numerator} / {round(denominator, 2)}"
    return value, label


def get_op_dict(steps_info):
    """获取整个任务中，各个开始时间对应的操作描述"""
    desc_dict = {}

    try:
        for step_info in steps_info:
            time_str = step_info.get("monotonic_start")
            desc_str = step_info.get("description")
            time_key = int(float(time_str) * 1000_000_000)
            desc_dict[time_key] = desc_str
    except Exception as e:
        print(f"获取操作描述字典失败: {e}")

    return desc_dict


def get_steps_dict(task_folder, sn=None) -> dict:
    """获取整个任务中，各个开始时间对应的操作描述"""

    desc_dict = {}
    task_folder = Path(task_folder)

    steps_files = []

    # 1 有 SN
    if sn:
        steps_path = task_folder / sn / "steps_file.json"
        if steps_path.exists():
            steps_files.append(steps_path)

    # 2 没有 SN，遍历所有 SN 目录
    else:
        for sn_dir in task_folder.iterdir():
            if not sn_dir.is_dir():
                continue

            steps_path = sn_dir / "steps_file.json"
            if steps_path.exists():
                steps_files.append(steps_path)

    # 3 解析所有 steps_file
    for steps_file in steps_files:
        try:
            steps_info = json.loads(steps_file.read_text(encoding="utf-8"))

            for step_info in steps_info:
                time_str = step_info.get("monotonic_start")

                if time_str is None:
                    continue

                time_key = int(float(time_str) * 1_000_000_000)

                desc_dict[time_key] = {
                    "monotonic_start": step_info.get("monotonic_start"),
                    "absolute_start": step_info.get("absolute_start"),
                    "absolute_end": step_info.get("absolute_end"),
                    "description": step_info.get("description"),
                    "op_type": step_info.get("op_type"),
                    "step_result": step_info.get("step_result"),
                }

        except Exception as e:
            print(f"解析 {steps_file} 失败: {e}")

    return desc_dict


def aggregate_case_results(task_path, sn, loop, test_dur):
    """聚合不同case的结果"""

    case_files = list(Path(task_path).glob("*/case_results.json"))

    device_set = set()
    loops = set()

    total_cases = 0
    passed = 0
    failed = 0
    blocked = 0
    unavailable = 0
    total_trace_len = 0

    # 初始化操作统计变量
    total_clicks = 0
    total_swipes = 0
    total_app_starts = 0

    device_info_dict = {}

    for file in case_files:
        if file.stat().st_size == 0:
            print(f"警告: 发现空文件，跳过读取 -> {file}")
            continue

        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"错误: JSON 文件格式损坏，跳过读取 -> {file} (原因: {e})")
            continue
        except Exception as e:
            print(f"错误: 读取文件失败，跳过读取 -> {file} (原因: {e})")
            continue

        serial = data.get("serial")

        # SN过滤
        if sn and serial != sn:
            continue

        device_set.add(serial)

        device_info = data.get("device_info", {})
        if serial:
            device_info_dict[serial] = device_info

        # ✅ 2. 新增：提取并累加当前设备的操作统计数据
        summary = data.get("summary", {})
        action_stats = summary.get("action_stats", {})

        if loop is not None:
            loop_stats = action_stats.get(str(loop), {})
            total_clicks += loop_stats.get("click", 0)
            total_swipes += loop_stats.get("swipe", 0)
            total_app_starts += loop_stats.get("app_start", 0)
        else:
            for l_key, l_stats in action_stats.items():
                total_clicks += l_stats.get("click", 0)
                total_swipes += l_stats.get("swipe", 0)
                total_app_starts += l_stats.get("app_start", 0)

        cases = data.get("cases", [])

        for c in cases:
            case_loop = c.get("loop")

            # loop过滤
            if loop is not None and case_loop != loop:
                continue

            loops.add(case_loop)

            total_cases += 1
            total_trace_len += c.get("duration", 0)

            result = c.get("result")

            if result == "Passed":
                passed += 1
            elif result == "Failed":
                failed += 1
            elif result == "Blocked":
                blocked += 1
            elif result == "Unavailable":
                unavailable += 1

    device_count = len(device_set)
    loop_count = len(loops)

    pass_rate = 0
    if total_cases:
        pass_rate = round(passed / total_cases, 4)

    if test_dur:
        test_time = format_duration(test_dur)
    else:
        test_time = (
            format_duration(int(total_trace_len / device_count))
            if device_count
            else "0s"
        )

    case_results_dict = {
        "设备数": device_count,
        "循环数": loop_count,
        "总用例数": total_cases,
        "通过": passed,
        "失败": failed,
        "blocked": blocked,
        "unavailable": unavailable,
        "通过率": pass_rate,
        "总测试时长": test_time,
        "devices": device_info_dict,
        "total_clicks": total_clicks,
        "total_swipes": total_swipes,
        "total_app_starts": total_app_starts,
    }
    return case_results_dict


def collect_jsonl_paths(task_path, sn, trace_result, log_result):
    """收集task下所有trace/log jsonl路径"""

    trace_files = []
    log_files = []

    task_dir = Path(task_path)

    for sub in task_dir.iterdir():
        if not sub.is_dir():
            continue

        device_sn = sub.name

        # SN过滤
        if sn and device_sn != sn:
            continue

        # 使用传入的自定义文件名
        trace_file = sub / trace_result
        log_file = sub / log_result

        if trace_file.exists():
            trace_files.append(str(trace_file))

        if log_file.exists():
            log_files.append(str(log_file))

    return trace_files, log_files


def process_step_analysis_data(step_records: list) -> tuple[dict, dict]:
    """
    处理从 API 拉取的测试步骤数据，同时返回：
    1. desc_dict: 以纳秒时间戳为 Key 的步骤详情字典
    2. case_results_dict: 用例聚合统计结果
    """
    desc_dict = {}

    # 初始化聚合统计变量
    device_set = set()
    loops = set()
    unique_cases = {}  # 用于记录唯一用例 (sn, loop, case_name)

    total_clicks = 0
    total_swipes = 0
    total_app_starts = 0

    # 遍历 API 返回的字典列表
    for data in step_records:
        # ================= 任务一：构建 desc_dict =================
        m_start = data.get("monotonic_start")
        if m_start is not None:
            time_key = int(float(m_start) * 1_000_000_000)
            desc_dict[time_key] = {
                "monotonic_start": m_start,
                "absolute_start": data.get("absolute_start"),
                "absolute_end": data.get("absolute_end"),
                "description": data.get("description"),
                "op_type": data.get("op_type"),
                "step_result": data.get("step_result"),
            }

        # ================= 任务二：聚合统计 =================
        current_sn = data.get("device_sn")
        current_loop = data.get("loop_num")
        current_case = data.get("case_name")

        if current_sn:
            device_set.add(current_sn)
        if current_loop is not None:
            loops.add(current_loop)

        # 统计用例结果 (去重：一个用例有多个步骤，只算一次)
        case_key = (current_sn, current_loop, current_case)
        if case_key not in unique_cases:
            unique_cases[case_key] = data.get("case_result")

        # 统计操作类型
        stats = data.get("action_stats") or {}

        total_clicks += stats.get("click", 0)
        total_swipes += stats.get("swipe", 0)
        total_app_starts += stats.get("app_start", 0)

    # 3. 计算最终的聚合指标
    case_results = list(unique_cases.values())
    total_cases = len(case_results)
    passed = case_results.count("Passed")
    failed = case_results.count("Failed")
    blocked = case_results.count("Blocked")
    unavailable = case_results.count("Unavailable")

    pass_rate = round(passed / total_cases, 4) if total_cases > 0 else 0

    device_count = len(device_set)

    case_results_dict = {
        "设备数": device_count,
        "循环数": len(loops),
        "总用例数": total_cases,
        "通过": passed,
        "失败": failed,
        "blocked": blocked,
        "unavailable": unavailable,
        "通过率": pass_rate,
        "total_clicks": total_clicks,
        "total_swipes": total_swipes,
        "total_app_starts": total_app_starts,
    }

    return desc_dict, case_results_dict


def build_summary_info(task_info: dict):

    if not task_info:
        return {}
    duration_ms = int(task_info.get("duration_ms", 0) / 1000)

    summary = {
        "任务耗时": format_duration(duration_ms),
        "devices": {},
    }

    for device in task_info.get("device_infos", []):
        sn = device.get("serial", "unknown")

        summary["devices"][sn] = {
            "brand": device.get("brand", ""),
            "model": device.get("model", ""),
            "system_version": device.get("system_version", ""),
            "mem_total": device.get("mem_total", ""),
            "storage_size": device.get("storage_size", ""),
        }

    return summary
