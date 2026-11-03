from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import DynamicRunnerConfig, DynamicRunnerTask, load_dynamic_runner_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="动态模型多 testbed runner")
    parser.add_argument(
        "--config",
        required=True,
        help="project.yaml 路径。",
    )

    args = parser.parse_args(argv)

    try:
        runner_config, tasks = load_dynamic_runner_plan(args.config)
    except Exception as error:
        print(f"[dynamic-runner] 配置解析失败：{error}", file=sys.stderr)
        return 2

    if not tasks:
        print("[dynamic-runner] 未发现可执行 testbed。", file=sys.stderr)
        return 2

    runner_config.output_dir.mkdir(parents=True, exist_ok=True)
    runner_logger = logging.getLogger("exfw.runner")
    runner_logger.setLevel(logging.INFO)
    runner_logger.propagate = False
    handler = logging.FileHandler(runner_config.output_dir / "runner.log", mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    runner_logger.addHandler(handler)
    started_at = time.time()

    print(
        "[dynamic-runner] 开始执行："
        f"config={runner_config.config_path}, "
        f"test_path={runner_config.test_path}, "
        f"output_dir={runner_config.output_dir}, "
        f"tasks={len(tasks)}"
    )
    runner_logger.info("开始执行 config=%s tasks=%s", runner_config.config_path, len(tasks))

    results = run_tasks(runner_config=runner_config, tasks=tasks)
    stopped_at = time.time()
    result_file = write_runner_result(
        runner_config=runner_config,
        tasks=tasks,
        results=results,
        started_at=started_at,
        stopped_at=stopped_at,
    )

    failed_count = sum(1 for result in results if result["exit_code"] != 0)
    print(
        "[dynamic-runner] 执行完成："
        f"total={len(results)}, failed={failed_count}, result={result_file}"
    )
    runner_logger.info("执行完成 total=%s failed=%s result=%s", len(results), failed_count, result_file)
    runner_logger.removeHandler(handler)
    handler.close()

    return 1 if failed_count else 0


def run_tasks(
    *,
    runner_config: DynamicRunnerConfig,
    tasks: list[DynamicRunnerTask],
) -> list[dict[str, Any]]:
    """并行启动所有 pytest 子进程并等待完成。"""

    started_processes = []

    for task in tasks:
        task.output_dir.mkdir(parents=True, exist_ok=True)
        command = build_pytest_command(runner_config=runner_config, task=task)

        print(
            "[dynamic-runner] 启动任务："
            f"testbed={task.testbed_name}, serial={task.main_serial}, "
            f"output={task.output_dir}"
        )
        logging.getLogger("exfw.runner").info("启动 testbed=%s serial=%s command=%s", task.testbed_name, task.main_serial, command)
        output = (task.output_dir / "pytest-output.log").open("w", encoding="utf-8")
        progress_handle = tempfile.NamedTemporaryFile(prefix="exfw-progress-", suffix=".jsonl", delete=False)
        progress_path = Path(progress_handle.name)
        progress_handle.close()
        env = os.environ.copy()
        env.update(EXFW_RUNNER_MODE="1", EXFW_PROGRESS_FILE=str(progress_path), PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        try:
            process = subprocess.Popen(command, cwd=str(runner_config.project_root), stdout=output, stderr=subprocess.STDOUT, env=env)
        except Exception:
            output.close()
            progress_path.unlink(missing_ok=True)
            raise
        started_processes.append((task, process, time.time(), command, output, progress_path))

    results: list[dict[str, Any]] = []

    offsets = {task.main_serial: 0 for task, *_ in started_processes}
    pending = list(started_processes)
    while pending:
      for entry in pending[:]:
        task, process, start_time, command, output, progress_path = entry
        exit_code = process.poll()
        with progress_path.open("r", encoding="utf-8") as stream:
            stream.seek(offsets[task.main_serial])
            while True:
                position = stream.tell()
                line = stream.readline()
                if not line or not line.endswith("\n"):
                    stream.seek(position)
                    break
                event = json.loads(line)
                status = "RUNNING" if event["event"] == "start" else event["outcome"]
                print(f"[{task.main_serial}] round {event['round']} | {event['nodeid']} | {status}", flush=True)
            offsets[task.main_serial] = stream.tell()
        if exit_code is None:
            continue
        output.close()
        progress_path.unlink(missing_ok=True)
        duration_seconds = round(time.time() - start_time, 3)

        print(
            "[dynamic-runner] 任务结束："
            f"testbed={task.testbed_name}, serial={task.main_serial}, "
            f"exit_code={exit_code}, duration={duration_seconds}s"
        )
        if exit_code:
            print(f"[{task.main_serial}] pytest 输出：{task.output_dir / 'pytest-output.log'}", flush=True)
        logging.getLogger("exfw.runner").info("任务结束 serial=%s exit_code=%s duration=%s", task.main_serial, exit_code, duration_seconds)

        results.append(
            {
                "testbed": task.testbed_name,
                "main_serial": task.main_serial,
                "output_dir": _to_runner_relative_path(
                    task.output_dir,
                    runner_config.output_dir,
                ),
                "session_result": _to_runner_relative_path(
                    task.output_dir / "session_result.json",
                    runner_config.output_dir,
                ),
                "command": command,
                "exit_code": exit_code,
                "duration_seconds": duration_seconds,
            }
        )
        pending.remove(entry)
      if pending:
        time.sleep(0.1)

    return results


def build_pytest_command(
    *,
    runner_config: DynamicRunnerConfig,
    task: DynamicRunnerTask,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        str(runner_config.test_path),
        "--exfw-config",
        str(runner_config.config_path),
        "--testbed",
        task.testbed_name,
        "--exfw-output",
        str(task.output_dir),
    ]

    if runner_config.rounds is not None:
        command.extend(["--rounds", str(runner_config.rounds)])

    return command


def write_runner_result(
    *,
    runner_config: DynamicRunnerConfig,
    tasks: list[DynamicRunnerTask],
    results: list[dict[str, Any]],
    started_at: float,
    stopped_at: float,
) -> Path:
    result_file = runner_config.output_dir / "runner_result.json"

    failed_count = sum(1 for result in results if result["exit_code"] != 0)
    payload = {
        "config_path": str(runner_config.config_path),
        "test_path": str(runner_config.test_path),
        "output_dir": ".",
        "rounds": runner_config.rounds,
        "started_at": started_at,
        "stopped_at": stopped_at,
        "duration_seconds": round(stopped_at - started_at, 3),
        "summary": {
            "total": len(tasks),
            "passed": len(tasks) - failed_count,
            "failed": failed_count,
        },
        "tasks": results,
    }

    result_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return result_file


def _to_runner_relative_path(path: Path, runner_output_dir: Path) -> str:
    """将 runner 产物路径保存为相对 runner 输出目录的可迁移路径。"""

    try:
        return path.relative_to(runner_output_dir).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
