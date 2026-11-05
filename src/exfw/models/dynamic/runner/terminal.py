"""动态 runner 的实时状态与最终汇总。"""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import sys


@dataclass
class DeviceProgress:
    serial: str
    total: int | None = None
    completed: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    current: str = "等待收集用例"
    round_no: int = 0
    done: bool = False
    exit_code: int | None = None
    failures: list[tuple[int, str]] = field(default_factory=list)

    def update(self, event):
        kind = event.get("event")
        if kind == "collected":
            self.total = event["total"]
            self.current = "等待执行"
        elif kind == "start":
            self.current = event["nodeid"]
            self.round_no = event["round"]
        elif kind == "finish":
            self.completed += 1
            result = event.get("outcome")
            if result == "PASSED":
                self.passed += 1
            elif result == "FAILED":
                self.failed += 1
                self.failures.append((event["round"], event["nodeid"]))
            elif result == "SKIPPED":
                self.skipped += 1
            self.current = ("用例已结束，等待收尾" if self.total is not None and
                            self.completed >= self.total else "等待下一用例")


def _supports_refresh(stream):
    if not stream.isatty() or os.environ.get("TERM") == "dumb":
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)) and
                    ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 4))
    except (AttributeError, OSError):
        return False


class Terminal:
    def __init__(self, tasks, stream=None):
        self.stream = stream or sys.stdout
        self.states = {task.main_serial: DeviceProgress(task.main_serial) for task in tasks}
        self.refresh = _supports_refresh(self.stream)
        self._lines = 0
        self._latest_failure = None

    def event(self, serial, event):
        state = self.states[serial]
        state.update(event)
        kind = event.get("event")
        if kind == "finish" and event.get("outcome") == "FAILED":
            self._latest_failure = (serial, event["round"], event["nodeid"])
        if self.refresh:
            self.render()
        elif kind in ("start", "finish"):
            result = "RUNNING" if kind == "start" else event.get("outcome", "UNKNOWN")
            print(f"[{serial}] round {event['round']} | {event['nodeid']} | {result}", file=self.stream, flush=True)
        elif kind == "collected":
            print(f"[{serial}] 计划执行 {state.total} 次用例", file=self.stream, flush=True)

    def finish(self, serial, exit_code, *, interrupted=False):
        state = self.states[serial]
        state.done, state.exit_code = True, exit_code
        state.current = (f"任务异常 (exit={exit_code})" if interrupted else
                         "已完成" if exit_code == 0 else
                         "已完成（存在失败用例）" if exit_code == 1 and state.failed else
                         f"任务异常 (exit={exit_code})")
        if self.refresh:
            self.render()
        else:
            print(f"[{serial}] {state.current}", file=self.stream, flush=True)

    def render(self):
        if not self.refresh:
            return
        if self._lines:
            self.stream.write(f"\x1b[{self._lines}A")
        lines = []
        for state in self.states.values():
            if state.total is None:
                progress = "[等待收集]"
            else:
                ratio = min(state.completed / state.total, 1) if state.total else 0
                width = 16
                filled = int(ratio * width)
                progress = f"[{'#' * filled}{'-' * (width - filled)}] {ratio:5.0%} {state.completed}/{state.total}"
            lines.append(f"{state.serial} {progress} 通过:{state.passed} 失败:{state.failed} 跳过:{state.skipped} | 轮次:{state.round_no} {state.current}")
        if self._latest_failure:
            serial, round_no, nodeid = self._latest_failure
            lines.append(f"最近失败: {serial} 第 {round_no} 轮 {nodeid}")
        else:
            lines.append("最近失败: 无")
        # 防止自动换行导致光标回移行数不正确（中文字符可能占两列）。
        columns = max(20, shutil.get_terminal_size((100, 24)).columns)
        for line in lines:
            visible = ''
            size = 0
            for char in line:
                char_width = 2 if ord(char) > 0x2fff else 1
                if size + char_width >= columns:
                    break
                visible += char
                size += char_width
            self.stream.write("\r\x1b[2K" + visible + "\n")
        self.stream.flush()
        self._lines = len(lines)

    def summary(self, results, output_dir):
        print("\n================ 测试汇总 ================", file=self.stream)
        for result in results:
            serial = result["main_serial"]
            task_dir = Path(output_dir) / result["output_dir"]
            try:
                data = json.loads((task_dir / "session_result.json").read_text(encoding="utf-8"))
                summary = data.get("summary") or {}
                cases = [(r.get("round"), case) for r in data.get("rounds", []) for case in r.get("cases", []) if case.get("outcome") == "failed"]
                print(f"设备 {serial}  通过 {summary.get('passed', 0)}  失败 {summary.get('failed', 0)}  跳过 {summary.get('skipped', 0)}", file=self.stream)
                for round_no, case in cases:
                    print(f"  第 {round_no} 轮  {case.get('nodeid', case.get('case_name', '?'))}", file=self.stream)
                processing = data.get("extensions", {}).get("dynamic_model", {}).get("processing", {})
                for phase in ("capture", "analysis", "upload"):
                    counts = processing.get(phase, {})
                    if counts.get("failed") or counts.get("partial"):
                        print(f"  {phase} 处理异常: {json.dumps(counts, ensure_ascii=False)}", file=self.stream)
                if data.get("extensions", {}).get("dynamic_model", {}).get("processing_error"):
                    print("  解析或上传收尾异常，请查看运行日志", file=self.stream)
            except (OSError, ValueError, TypeError, AttributeError):
                print(f"设备 {serial}  无法读取 session 结果", file=self.stream)
            if result["exit_code"]:
                label = "pytest 退出状态" if result.get("status") == "failed" and self.states[serial].failed else "pytest 任务退出状态"
                print(f"  {label}: {result['exit_code']}；详情: {task_dir / 'pytest-output.log'}", file=self.stream)
        self.stream.flush()
