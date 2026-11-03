import re
from collections import Counter, defaultdict
from datetime import datetime

# ====================== 常量与映射表 ====================== #

START_POLICY = {
    "S": "startService",
    "D": "bindService",
    "P": "provider拉起",
    "B": "三方应用广播",
    "b": "系统应用广播",
    "A": "启动Activity",
    "J": "jobSchedule",
    "Y": "账户同步",
    "R": "scheduleRestart",
    "M": "alarm",
    "MA": "alarm启动activity",
    "MB": "alarm广播",
    "MS": "alarm服务",
    "pA": "pending intent activity",
    "pB": "pending intent broadcast",
    "pS": "pending intent service",
}

START_POLICY_INDEX = {
    "U": "用户允许",
    "H": "系统应用拉起",
    "O": "同应用拉起",
    "E": "被拉起应用为系统应用",
    "F": "默认允许或禁止",
    "L": "白名单应用",
    "CL": "云推列表",
    "WP": "禁止WidgetProvider拉起其他应用",
    "ROP": "单次许可",
    "FBA": "省电精灵清理不再拉起",
    "SUB": "子账户控制",
    "SAS": "特殊允许",
    "GMS": "GMS拉起放行",
    "MS": "微软应用管家",
    "BLACK": "流氓应用",
    "WK": "近期杀死的桌面卡片",
}

# ====================== 公共辅助函数 ====================== #


def _parse_log_time_to_timestamp(time_str: str) -> float:
    """将 'MM-DD HH:MM:SS.mmm' 转换为时间戳。"""
    try:
        current_year = datetime.now().year
        return datetime.strptime(
            f"{current_year}-{time_str}", "%Y-%m-%d %H:%M:%S.%f"
        ).timestamp()
    except Exception:
        return 0.0


def _format_timestamp(ts: float) -> str:
    """将时间戳转回日志时间格式"""
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S.%f")[:-3]


def _find_high_freq_segments(timestamps: list, interval: int, max_num: int) -> list:
    """通用高频片段查找算法"""
    if len(timestamps) < max_num:
        return []

    timestamps.sort()
    segments = []
    current_segment = [timestamps[0]]

    for i in range(1, len(timestamps)):
        if timestamps[i] - timestamps[i - 1] <= interval:
            current_segment.append(timestamps[i])
        else:
            if len(current_segment) >= max_num:
                segments.append([_format_timestamp(t) for t in current_segment])
            current_segment = [timestamps[i]]

    if len(current_segment) >= max_num:
        segments.append([_format_timestamp(t) for t in current_segment])

    return segments


def _parse_kill_reason(s: str) -> str:
    """标准化杀进程原因"""
    if "iAware" in s:
        s1 = re.findall(r"\[(.*?)\]", s)[0] if re.findall(r"\[(.*?)\]", s) else s
        return "iAware " + re.sub(r"\(.*?\)", "", s1).strip()
    return "empty" if "empty" in s else s.strip()


# ====================== 单行日志解析函数 ====================== #


def _parse_kill_line(line: str) -> dict:
    parts = line.split()
    if len(parts) < 6:
        return {}
    try:
        kill_idx = parts.index("Killing")
        proc_field = parts[kill_idx + 1]
        proc_name = proc_field.split(":", 1)[1].split("/")[0]
        reason = _parse_kill_reason(line.split(":")[-1])
        return {
            "timestamp": _parse_log_time_to_timestamp(f"{parts[0]} {parts[1]}"),
            "process_name": proc_name,
            "reason": reason,
        }
    except Exception:
        return {}


def _parse_start_line(line: str) -> dict:
    parts = line.split()
    if len(parts) < 6:
        return {}
    try:
        start_idx = parts.index("ActivityManager:")
        proc_field = parts[start_idx + 3]
        pid, proc_name = proc_field.split(":", 1)
        proc_name = proc_name.split("/")[0]
        return {
            "timestamp": _parse_log_time_to_timestamp(f"{parts[0]} {parts[1]}"),
            "process_name": proc_name,
            "reason": line.split("for ")[1].split("{")[0].strip()
            if "for " in line
            else "",
        }
    except Exception:
        return {}


def _parse_iaware_line(line: str) -> dict:
    try:
        idx = line.find("I AwareLog: AppStart:")
        if idx == -1:
            return {}

        ts = _parse_log_time_to_timestamp(f"{line[:18]}")
        content = line[idx + 21 :].strip()
        parts = [p.strip() for p in content.split(",") if not p.startswith("state:")]

        req_code = parts[0].split(":")[-1]
        alw_field = parts[1].split(":")[-1]

        if not alw_field[0].isdigit():
            return {}

        if int(alw_field[0]) == 0:
            return {}

        return {
            "timestamp": ts,
            "req": START_POLICY.get(req_code, req_code),
            "allow": int(alw_field[0]),
            "reason": alw_field[2:-1],
            "flag": parts[2].split(":")[1] if int(alw_field[0]) != 0 else "",
            "target_name": parts[4] if int(alw_field[0]) != 0 else "",
            "caller": parts[6].split(" ")[0] if int(alw_field[0]) != 0 else "",
        }
    except Exception:
        return {}


# ====================== 核心汇总入口 ====================== #


def process_all_adb_log_data(adb_log_list: list):
    """整理 adb log 自启清理数据，返回表格输入和第 0 页汇总数据。"""

    kill_report_data, start_report_data = adb_log_summary(adb_log_list)

    return {
        "sheets_data": {
            "start_cleanup": _build_start_cleanup_data(
                kill_report_data, start_report_data
            ),
        },
        "summary_data": {},
    }



def _build_start_cleanup_data(kill_report_data, start_report_data):
    """构建自启清理 sheet 自定义布局所需的完整数据。"""

    start_summary = start_report_data.get("summary", {})
    kill_summary = kill_report_data.get("summary", {})
    cold_start_num = start_summary.get("cold_start_num", 0)
    warm_start_num = start_summary.get("warm_start_num", 0)

    total_start_num = start_summary.get("total_start_num", 0)
    multi_start_num = start_summary.get("multi_start_num", 0)
    single_start_num = total_start_num - multi_start_num
    single_percent = round(single_start_num * 100 / total_start_num, 2) if total_start_num else 0.0
    multi_percent = round(multi_start_num * 100 / total_start_num, 2) if total_start_num else 0.0

    return {
        "total_start_num": total_start_num,
        "single_start_num": single_start_num,
        "single_percent": f"{single_percent}%",
        "multi_start_num": multi_start_num,
        "multi_percent": f"{multi_percent}%",
        "cold_start_num": cold_start_num,
        "warm_start_num": warm_start_num,
        "total_iAware_num": cold_start_num + warm_start_num,
        "start_reasons": start_report_data.get("process_details", []),
        "start_high_freq_segments": start_report_data.get("high_freq_segments", []),
        "total_kill_num": kill_summary.get("total_kill_num", 0),
        "total_kill_num_repeat": kill_summary.get("total_kill_num_repeat", 0),
        "repeat_kill_percent": kill_summary.get("repeat_percent", "0%"),
        "kill_reason_stats": kill_summary.get("reason_stats", {}),
        "kill_process_reasons": kill_report_data.get("process_details", []),
        "high_freq_kill_segments": kill_report_data.get("high_freq_segments", []),
    }



def adb_log_summary(adb_log_list: list) -> tuple:
    """
    解析并汇总 ADB 日志数据
    :param adb_log_list: 包含各个文件解析结果的列表
    :return: (kill_report_data, start_report_data) 两个排版友好的字典
    """
    if not adb_log_list:
        # 返回两个基础的空字典结构，防止后续生成报表时找不到 key 报错
        empty_kill = {"summary": {}, "process_details": [], "high_freq_segments": []}
        empty_start = {"summary": {}, "process_details": [], "high_freq_segments": []}
        return empty_kill, empty_start

    all_kills = []
    all_starts = []
    all_iawares = []

    # 1. 提取并清洗所有原始日志行
    for file_data in adb_log_list:
        res = file_data.get("data", {})
        if not res:
            continue

        for line in res.get("kill_res", []):
            parsed = _parse_kill_line(line)
            if parsed:
                all_kills.append(parsed)

        for line in res.get("startup_res", []):
            parsed = _parse_start_line(line)
            if parsed:
                all_starts.append(parsed)

        for line in res.get("iaware_res", []):
            parsed = _parse_iaware_line(line)
            if parsed:
                all_iawares.append(parsed)

    # ====================== 2. 汇总杀进程数据 ====================== #
    kill_stats = defaultdict(
        lambda: {"kill_times": 0, "reasons": set(), "timestamps": []}
    )
    kill_reason_counter = Counter()

    for k in all_kills:
        pname = k["process_name"]
        kill_stats[pname]["kill_times"] += 1
        kill_stats[pname]["reasons"].add(k["reason"])
        kill_stats[pname]["timestamps"].append(k["timestamp"])
        kill_reason_counter[k["reason"]] += 1

    kill_process_details = []
    kill_high_freq = []
    total_kills = len(all_kills)
    repeat_kills = 0

    for pname, data in kill_stats.items():
        if data["kill_times"] > 1:
            repeat_kills += data["kill_times"]

        kill_process_details.append(
            {
                "process_name": pname,
                "kill_times": data["kill_times"],
                "reasons": list(data["reasons"]),
            }
        )

        segments = _find_high_freq_segments(data["timestamps"], 300, 5)
        if segments:
            kill_high_freq.append({"process_name": pname, "segments": segments})

    kill_process_details.sort(key=lambda x: x["kill_times"], reverse=True)

    kill_report_data = {
        "summary": {
            "total_kill_num": total_kills,
            "total_kill_num_repeat": repeat_kills,
            "repeat_percent": f"{round(repeat_kills / total_kills * 100, 2)}%"
            if total_kills
            else "0%",
            "reason_stats": {
                k: {"count": v, "percent": f"{round(v / total_kills * 100, 2)}%"}
                for k, v in kill_reason_counter.items()
            },
        },
        "process_details": kill_process_details,
        "high_freq_segments": kill_high_freq,
    }

    # ====================== 3. 汇总启动进程数据 ====================== #
    # 按进程名对 iAware 进行分组，优化匹配速度
    iaware_map = defaultdict(list)
    for ia in all_iawares:
        iaware_map[ia["target_name"]].append(ia)
    for k in iaware_map:
        iaware_map[k].sort(key=lambda x: x["timestamp"])

    start_stats = defaultdict(
        lambda: {
            "start_times": 0,
            "reqs": set(),
            "reasons": set(),
            "callers": set(),
            "timestamps": [],
        }
    )

    for st in all_starts:
        pname = st["process_name"]
        ts = st["timestamp"]

        # 寻找最近的 iAware 记录
        matched_ia = None
        if pname in iaware_map:
            for i, ia in enumerate(iaware_map[pname]):
                if ia["timestamp"] < ts:
                    matched_ia = ia
                    # 匹配到之后，立刻从列表中移除，防止被下一次启动重复使用
                    iaware_map[pname].pop(i)
                    break

        start_stats[pname]["start_times"] += 1
        start_stats[pname]["timestamps"].append(ts)

        if matched_ia:
            start_stats[pname]["reqs"].add(matched_ia["req"])
            reason_desc = START_POLICY_INDEX.get(
                matched_ia["reason"], matched_ia["reason"]
            )
            start_stats[pname]["reasons"].add(reason_desc)
            start_stats[pname]["callers"].add(matched_ia["caller"])
        else:
            start_stats[pname]["reqs"].add(st["reason"])

    start_process_details = []
    start_high_freq = []
    multi_starts = 0

    for pname, data in start_stats.items():
        if data["start_times"] > 1:
            multi_starts += data["start_times"]

        start_process_details.append(
            {
                "process_name": pname,
                "start_times": data["start_times"],
                "req": list(data["reqs"]),
                "reason": list(data["reasons"]),
                "caller": list(data["callers"]),
            }
        )

        segments = _find_high_freq_segments(data["timestamps"], 300, 5)
        if segments:
            start_high_freq.append({"process_name": pname, "segments": segments})

    start_process_details.sort(key=lambda x: x["start_times"], reverse=True)
    cold_starts = sum(1 for ia in all_iawares if ia.get("flag", "00")[1:2] == "1")
    warm_starts = len(all_iawares) - cold_starts

    start_report_data = {
        "summary": {
            "total_start_num": len(all_starts),
            "multi_start_num": multi_starts,
            "cold_start_num": cold_starts,
            "warm_start_num": warm_starts,
        },
        "process_details": start_process_details,
        "high_freq_segments": start_high_freq,
    }

    return kill_report_data, start_report_data
