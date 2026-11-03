from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


# trace ts 通常对应 BOOTTIME。
# REALTIME 对应 Unix epoch 纳秒时间戳。
#
# realtime_ns = boottime_ts + (REALTIME.clock_value - BOOTTIME.clock_value)
#
# 注意：使用 IS 而不是 =，避免 machine_id / snapshot_id 为 NULL 时无法 join。
TRACE_BOUNDS_SQL = """
WITH
bounds AS (
  SELECT
    start_ts,
    end_ts
  FROM trace_bounds
),

clock_offset AS (
  SELECT
    rt.clock_value - bt.clock_value AS offset_ns
  FROM clock_snapshot bt
  JOIN clock_snapshot rt
    ON bt.snapshot_id IS rt.snapshot_id
   AND bt.machine_id IS rt.machine_id
  CROSS JOIN bounds b
  WHERE bt.clock_name = 'BOOTTIME'
    AND rt.clock_name IN ('REALTIME', 'REALTIME_COARSE')
  ORDER BY
    CASE rt.clock_name
      WHEN 'REALTIME' THEN 0
      ELSE 1
    END,
    ABS(bt.ts - b.start_ts)
  LIMIT 1
)

SELECT
  b.start_ts AS start_boottime_ns,
  b.end_ts AS end_boottime_ns,
  b.start_ts + co.offset_ns AS start_realtime_ns,
  b.end_ts + co.offset_ns AS end_realtime_ns,
  b.end_ts - b.start_ts AS duration_ns
FROM bounds b
CROSS JOIN clock_offset co;
""".strip()


# 供 trace_processor_shell -Q 使用。
# 将五个值拼为单列，以便稳定从 CSV / 文本输出中提取。
TRACE_BOUNDS_QUERY_SQL = """
WITH
bounds AS (
  SELECT
    start_ts,
    end_ts
  FROM trace_bounds
),

clock_offset AS (
  SELECT
    rt.clock_value - bt.clock_value AS offset_ns
  FROM clock_snapshot bt
  JOIN clock_snapshot rt
    ON bt.snapshot_id IS rt.snapshot_id
   AND bt.machine_id IS rt.machine_id
  CROSS JOIN bounds b
  WHERE bt.clock_name = 'BOOTTIME'
    AND rt.clock_name IN ('REALTIME', 'REALTIME_COARSE')
  ORDER BY
    CASE rt.clock_name
      WHEN 'REALTIME' THEN 0
      ELSE 1
    END,
    ABS(bt.ts - b.start_ts)
  LIMIT 1
),

result AS (
  SELECT
    b.start_ts AS start_boottime_ns,
    b.end_ts AS end_boottime_ns,
    b.start_ts + co.offset_ns AS start_realtime_ns,
    b.end_ts + co.offset_ns AS end_realtime_ns,
    b.end_ts - b.start_ts AS duration_ns
  FROM bounds b
  CROSS JOIN clock_offset co
)

SELECT
  CAST(start_boottime_ns AS TEXT) || '|' ||
  CAST(end_boottime_ns AS TEXT) || '|' ||
  CAST(start_realtime_ns AS TEXT) || '|' ||
  CAST(end_realtime_ns AS TEXT) || '|' ||
  CAST(duration_ns AS TEXT) AS bounds_result
FROM result;
""".strip()


# 失败时输出 trace 内时钟摘要，方便诊断。
CLOCK_DIAGNOSTIC_SQL = """
SELECT
  clock_name,
  COUNT(*) AS count,
  MIN(ts) AS min_ts,
  MAX(ts) AS max_ts
FROM clock_snapshot
GROUP BY clock_name
ORDER BY clock_name;
""".strip()


@dataclass(frozen=True)
class TraceBounds:
    start_boottime_ns: int
    end_boottime_ns: int
    start_realtime_ns: int
    end_realtime_ns: int
    duration_ns: int

    @property
    def start_time(self) -> float:
        """Unix epoch 秒级时间戳。"""
        return self.start_realtime_ns / 1_000_000_000

    @property
    def end_time(self) -> float:
        """Unix epoch 秒级时间戳。"""
        return self.end_realtime_ns / 1_000_000_000

    @property
    def duration_seconds(self) -> float:
        return self.duration_ns / 1_000_000_000


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="用 pftrace 内真实设备时间修正 dynamic 结果中的 trace_records.json。"
    )

    parser.add_argument(
        "--task-dir",
        required=True,
        help="dynamic runner 输出目录、traces 目录或 trace_records.json 文件。",
    )

    parser.add_argument(
        "--trace-processor",
        default="trace_processor_shell",
        help="trace_processor_shell 可执行文件路径，默认从 PATH 查找。",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=min(4, max(1, os.cpu_count() or 1)),
        help=(
            "并发解析 trace 的最大线程数。"
            "每个 worker 会启动一个 trace_processor_shell 进程；"
            "建议先使用 2，默认最大为 4。"
        ),
    )

    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="不生成 trace_records.json.bak 备份。",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅查询和打印修正结果，不写回文件。",
    )

    args = parser.parse_args(argv)

    if args.workers < 1:
        print(f"--workers 必须大于等于 1，当前值：{args.workers}")
        return 2

    task_dir = Path(args.task_dir)

    if not task_dir.exists():
        print(f"目录或文件不存在：{task_dir}")
        return 2

    records_files = discover_trace_record_files(task_dir)

    if not records_files:
        print(f"未找到 trace_records.json：{task_dir}")
        return 1

    total_files = 0
    total_traces = 0
    patched_traces = 0
    missing_traces = 0
    failed_traces = 0

    for records_file in records_files:
        total_files += 1

        result = patch_trace_records_file(
            records_file=records_file,
            trace_processor=args.trace_processor,
            backup=not args.no_backup,
            dry_run=args.dry_run,
            workers=args.workers,
        )

        total_traces += result["total"]
        patched_traces += result["patched"]
        missing_traces += result["missing"]
        failed_traces += result["failed"]

    print(
        "修正完成："
        f"files={total_files}, "
        f"total={total_traces}, "
        f"patched={patched_traces}, "
        f"missing={missing_traces}, "
        f"failed={failed_traces}, "
        f"workers={args.workers}, "
        f"dry_run={args.dry_run}"
    )

    return 0 if failed_traces == 0 else 1


def discover_trace_record_files(task_dir: Path) -> list[Path]:
    """发现 traces/trace_records.json。"""

    if task_dir.is_file() and task_dir.name == "trace_records.json":
        return [task_dir]

    if task_dir.is_dir() and task_dir.name == "traces":
        records_file = task_dir / "trace_records.json"
        if records_file.is_file():
            return [records_file]

    if task_dir.is_dir():
        return sorted(task_dir.rglob("traces/trace_records.json"))

    return []


def patch_trace_records_file(
    *,
    records_file: Path,
    trace_processor: str,
    backup: bool,
    dry_run: bool,
    workers: int,
) -> dict[str, int]:
    """并发查询 traces，随后按原始 JSON 顺序写回结果。"""

    print(f"处理 Trace 记录：{records_file}")

    try:
        data = json.loads(records_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"  读取失败：{error}")
        return {"total": 0, "patched": 0, "missing": 0, "failed": 1}

    traces = data.get("traces")
    if not isinstance(traces, list):
        print("  格式异常：traces 不是列表")
        return {"total": 0, "patched": 0, "missing": 0, "failed": 1}

    total = 0
    patched = 0
    missing = 0
    failed = 0

    traces_dir = records_file.parent

    # (trace 在 JSON 中的位置, trace 字典, 文件名, 完整文件路径)
    jobs: list[tuple[int, dict, str, Path]] = []

    for index, trace in enumerate(traces):
        if not isinstance(trace, dict):
            continue

        total += 1

        trace_name = Path(str(trace.get("trace_path") or "")).name
        if not trace_name:
            failed += 1
            print("  跳过：trace_path 为空")
            continue

        trace_file = traces_dir / trace_name
        if not trace_file.is_file():
            missing += 1
            print(f"  缺少 trace 文件：{trace_file}")
            continue

        jobs.append((index, trace, trace_name, trace_file))

    if not jobs:
        print("  没有可查询的 trace 文件。")
        return {
            "total": total,
            "patched": patched,
            "missing": missing,
            "failed": failed,
        }

    actual_workers = min(workers, len(jobs))

    print(f"  开始并发查询：trace_count={len(jobs)}, workers={actual_workers}")

    # worker 中只查询，不修改 JSON 数据。
    # 防止多线程同时写 trace 字典。
    query_results: dict[int, TraceBounds | Exception] = {}

    with ThreadPoolExecutor(
        max_workers=actual_workers,
        thread_name_prefix="trace-bounds",
    ) as executor:
        future_to_job = {
            executor.submit(
                query_trace_bounds,
                trace_file=trace_file,
                trace_processor=trace_processor,
            ): (index, trace, trace_name, trace_file)
            for index, trace, trace_name, trace_file in jobs
        }

        for future in as_completed(future_to_job):
            index, _trace, _trace_name, _trace_file = future_to_job[future]

            try:
                query_results[index] = future.result()
            except Exception as error:
                query_results[index] = error

    # 保持按 trace_records.json 中原本的顺序输出和更新。
    for index, trace, trace_name, _trace_file in jobs:
        result = query_results[index]

        if isinstance(result, Exception):
            failed += 1
            print(f"  查询失败：{trace_name}, error={result}")
            continue

        bounds = result

        old_start_time = trace.get("start_time")
        old_end_time = trace.get("end_time")
        old_duration = trace.get("duration_seconds")

        trace["start_time"] = bounds.start_time
        trace["end_time"] = bounds.end_time
        trace["duration_seconds"] = round(bounds.duration_seconds, 3)

        if "trace_name" not in trace:
            trace["trace_name"] = trace_name

        patched += 1

        print(
            "  修正："
            f"{trace_name}, "
            f"start {old_start_time} -> {trace['start_time']}, "
            f"end {old_end_time} -> {trace['end_time']}, "
            f"duration {old_duration} -> {trace['duration_seconds']}"
        )

    data["schema_version"] = data.get("schema_version") or 1
    data["time_source"] = "device_realtime"
    data["trace_count"] = len([item for item in traces if isinstance(item, dict)])

    # dry-run 只修改内存中的 data，不写文件。
    if not dry_run and patched:
        if backup:
            backup_file = records_file.with_suffix(records_file.suffix + ".bak")

            if not backup_file.exists():
                shutil.copy2(records_file, backup_file)
                print(f"  已备份：{backup_file}")

        temp_file = records_file.with_suffix(records_file.suffix + ".tmp")

        temp_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        temp_file.replace(records_file)
        print(f"  已写回：{records_file}")

    return {
        "total": total,
        "patched": patched,
        "missing": missing,
        "failed": failed,
    }


def query_trace_bounds(*, trace_file: Path, trace_processor: str) -> TraceBounds:
    """查询 trace 的 wall-clock 起止时间。

    优先走 trace_processor_shell -Q。
    shell 查询失败时，尝试 perfetto Python API。
    """

    try:
        return _query_trace_bounds_with_shell(
            trace_file=trace_file,
            trace_processor=trace_processor,
        )
    except Exception as shell_error:
        try:
            return _query_trace_bounds_with_perfetto_api(
                trace_file=trace_file,
                trace_processor=trace_processor,
            )
        except Exception as api_error:
            diagnostic = _query_clock_diagnostic_safely(
                trace_file=trace_file,
                trace_processor=trace_processor,
            )

            raise RuntimeError(
                "trace_processor_shell 和 Perfetto Python API 均查询失败；"
                f"shell_error={shell_error}; "
                f"api_error={api_error}; "
                f"clock_snapshot={diagnostic}"
            ) from api_error


def _query_trace_bounds_with_shell(
    *,
    trace_file: Path,
    trace_processor: str,
) -> TraceBounds:
    """通过 trace_processor_shell -Q 直接运行 Perfetto SQL。"""

    completed = _run_trace_processor_query(
        trace_file=trace_file,
        trace_processor=trace_processor,
        sql=TRACE_BOUNDS_QUERY_SQL,
    )

    return _parse_bounds_from_query_output(completed.stdout)


def _query_trace_bounds_with_perfetto_api(
    *,
    trace_file: Path,
    trace_processor: str,
) -> TraceBounds:
    """通过 perfetto Python API 查询。"""

    try:
        from perfetto.trace_processor import TraceProcessor, TraceProcessorConfig
    except ImportError as error:
        raise RuntimeError(
            "未安装 perfetto Python 包；"
            "如需 Python API 兜底，请执行：pip install perfetto"
        ) from error

    processor_path = _resolve_trace_processor_path(trace_processor)

    config = TraceProcessorConfig(
        bin_path=processor_path,
    )

    # perfetto 不同版本构造参数名可能不同。
    try:
        processor_instance = TraceProcessor(
            file_path=str(trace_file),
            config=config,
        )
    except TypeError:
        processor_instance = TraceProcessor(
            trace=str(trace_file),
            config=config,
        )

    with processor_instance as tp:
        row = next(iter(tp.query(TRACE_BOUNDS_SQL)), None)

    if row is None:
        raise RuntimeError(
            "未查询到 trace_bounds / clock_offset；"
            "trace 可能缺少 BOOTTIME + REALTIME 时钟映射。"
        )

    return TraceBounds(
        start_boottime_ns=int(row.start_boottime_ns),
        end_boottime_ns=int(row.end_boottime_ns),
        start_realtime_ns=int(row.start_realtime_ns),
        end_realtime_ns=int(row.end_realtime_ns),
        duration_ns=int(row.duration_ns),
    )


def _resolve_trace_processor_path(trace_processor: str) -> str:
    """解析 trace_processor_shell 路径。"""

    explicit_path = Path(trace_processor)

    if explicit_path.is_file():
        return str(explicit_path.resolve())

    found = shutil.which(trace_processor)
    if found:
        return found

    raise RuntimeError(
        "找不到 trace_processor_shell："
        f"{trace_processor}。请检查 --trace-processor 参数或 PATH。"
    )


def _run_trace_processor_query(
    *,
    trace_file: Path,
    trace_processor: str,
    sql: str,
) -> subprocess.CompletedProcess[str]:
    """运行 trace_processor_shell -Q <sql> <trace_file>。"""

    executable = _resolve_trace_processor_path(trace_processor)

    command = [
        executable,
        "-Q",
        sql,
        str(trace_file),
    ]

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"trace_processor_shell 查询超时：timeout=120s, trace={trace_file}"
        ) from error
    except OSError as error:
        raise RuntimeError(
            f"无法启动 trace_processor_shell：{executable}, error={error}"
        ) from error

    if completed.returncode != 0:
        raise RuntimeError(
            "trace_processor_shell 直接查询失败："
            f"returncode={completed.returncode}, "
            f"stderr={completed.stderr.strip()}, "
            f"stdout={completed.stdout.strip()}"
        )

    return completed


def _parse_bounds_from_query_output(output: str) -> TraceBounds:
    """解析 shell 查询输出中的 5 段纳秒值。"""

    for line in output.splitlines():
        match = re.search(
            r"(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)",
            line,
        )

        if not match:
            continue

        return TraceBounds(
            start_boottime_ns=int(match.group(1)),
            end_boottime_ns=int(match.group(2)),
            start_realtime_ns=int(match.group(3)),
            end_realtime_ns=int(match.group(4)),
            duration_ns=int(match.group(5)),
        )

    raise RuntimeError(
        f"无法从 trace_processor_shell 输出解析 bounds_result：{output!r}"
    )


def _query_clock_diagnostic_safely(
    *,
    trace_file: Path,
    trace_processor: str,
) -> str:
    """查询失败时输出时钟摘要，仅用于诊断。"""

    try:
        completed = _run_trace_processor_query(
            trace_file=trace_file,
            trace_processor=trace_processor,
            sql=CLOCK_DIAGNOSTIC_SQL,
        )

        output = completed.stdout.strip()

        if not output:
            return "<empty>"

        return output.replace("\r", "").replace("\n", " | ")

    except Exception as error:
        return f"<diagnostic failed: {error}>"


if __name__ == "__main__":
    raise SystemExit(main())
