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
from .terminal import Terminal
from .result import TaskResultStore
from exfw.models.dynamic.result.execution_html import generate_execution_html
from exfw.project_config import find_project_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="动态模型多 testbed runner")
    parser.add_argument(
        "--project-config",
        default=None,
        help="项目 YAML 路径；默认从当前目录向上查找 project.yaml。",
    )

    args = parser.parse_args(argv)

    try:
        config_path = args.project_config or find_project_config(Path.cwd())
        runner_config, tasks = load_dynamic_runner_plan(config_path)
    except Exception as error:
        print(f"[dynamic-runner] 配置解析失败：{error}", file=sys.stderr)
        return 2

    if not tasks:
        print("[dynamic-runner] 未发现可执行 testbed。", file=sys.stderr)
        return 2

    try:
        # 秒级名称发生冲突时明确失败，绝不覆盖已有测试结果。
        runner_config.output_dir.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(f"[dynamic-runner] 无法创建本次输出目录：{error}", file=sys.stderr)
        return 2
    runner_logger = logging.getLogger("exfw.runner")
    runner_logger.setLevel(logging.INFO)
    runner_logger.propagate = False
    handler = logging.FileHandler(runner_config.output_dir / "runner.log", mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    runner_logger.addHandler(handler)
    started_at = time.time()
    print(f"[dynamic-runner] 开始执行：config={runner_config.config_path}, test_path={runner_config.test_path}, "
          f"output_dir={runner_config.output_dir}, tasks={len(tasks)}", flush=True)
    terminal = Terminal(tasks)
    store = None
    try:
        store = TaskResultStore(runner_config, tasks, started_at)
        runner_logger.info("开始执行 config=%s tasks=%s", runner_config.config_path, len(tasks))
        results = run_tasks(runner_config=runner_config, tasks=tasks, terminal=terminal, store=store)
        results.sort(key=lambda result: next(i for i, task in enumerate(tasks) if task.main_serial == result["main_serial"]))
        terminal.summary(results, runner_config.output_dir)
        failed = any(result["exit_code"] != 0 for result in results)
        store.finish("failed" if failed else "completed")
        _write_execution_report(runner_config.output_dir, runner_logger)
        print(f"[dynamic-runner] 执行完成：结果文件：{store.path}", flush=True)
        runner_logger.info("执行完成 result=%s", store.path)
        return 1 if failed else 0
    except (Exception, KeyboardInterrupt) as error:
        runner_logger.exception("runner 异常中断")
        print(f"\n[dynamic-runner] 异常中断：{error or type(error).__name__}；详情：{runner_config.output_dir / 'runner.log'}", file=sys.stderr, flush=True)
        if store is not None:
            try:
                store.finish("interrupted")
                terminal.summary(store.data["tasks"], runner_config.output_dir)
                _write_execution_report(runner_config.output_dir, runner_logger)
            except Exception:
                runner_logger.exception("异常收尾失败")
        return 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        runner_logger.removeHandler(handler)
        handler.close()


def _write_execution_report(output_dir, logger):
    """报告生成失败只影响展示，不改变已完成的测试结果。"""
    try:
        path = generate_execution_html(output_dir)
        logger.info("执行结果页面：%s", path)
        print(f"[dynamic-runner] 执行结果页面：{path}", flush=True)
    except Exception as error:
        logger.exception("生成执行结果页面失败")
        print(f"[dynamic-runner] 执行结果页面生成失败：{error}；详情：{output_dir / 'runner.log'}", file=sys.stderr, flush=True)


def run_tasks(*, runner_config: DynamicRunnerConfig, tasks: list[DynamicRunnerTask],
              terminal: Terminal | None = None, store: TaskResultStore | None = None) -> list[dict[str, Any]]:
    """并行运行子进程；异常时终止并等待已启动的进程。"""
    terminal = terminal or Terminal(tasks)
    logger = logging.getLogger("exfw.runner")
    started = []
    results = []
    try:
        for task in tasks:
            task.output_dir.mkdir(parents=True, exist_ok=True)
            command = build_pytest_command(runner_config=runner_config, task=task)
            print(f"[dynamic-runner] 启动任务：testbed={task.testbed_name}, serial={task.main_serial}, output={task.output_dir}", flush=True)
            logger.info("启动 testbed=%s serial=%s command=%s", task.testbed_name, task.main_serial, command)
            output = (task.output_dir / "pytest-output.log").open("w", encoding="utf-8")
            progress_handle = tempfile.NamedTemporaryFile(prefix="exfw-progress-", suffix=".jsonl", delete=False)
            progress_path = Path(progress_handle.name)
            progress_handle.close()
            env = os.environ.copy()
            env.update(EXFW_RUNNER_MODE="1", EXFW_SESSION_OUTPUT=str(task.output_dir), EXFW_PROGRESS_FILE=str(progress_path), PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
            started_at = time.time()
            try:
                process = subprocess.Popen(command, cwd=str(runner_config.project_root), stdout=output, stderr=subprocess.STDOUT, env=env)
            except Exception as error:
                output.close()
                progress_path.unlink(missing_ok=True)
                logger.exception("启动设备子进程失败 serial=%s", task.main_serial)
                print(f"[{task.main_serial}] 启动失败：{error}；详情：{runner_config.output_dir / 'runner.log'}", file=sys.stderr, flush=True)
                terminal.finish(task.main_serial, 1)
                result = {"testbed": task.testbed_name, "main_serial": task.main_serial,
                          "output_dir": _to_runner_relative_path(task.output_dir, runner_config.output_dir),
                          "session_result": _to_runner_relative_path(task.output_dir / "session_result.json", runner_config.output_dir),
                          "command": command, "exit_code": 1, "duration_seconds": 0, "processing": None,
                          "status": "failed", "error": str(error)}
                results.append(result)
                if store:
                    store.update(task.main_serial, **{k: v for k, v in result.items() if k != "main_serial"})
                continue
            entry = (task, process, started_at, command, output, progress_path)
            started.append(entry)
            if store:
                store.update(task.main_serial, status="running", command=command)
        pending = list(started)
        offsets = {task.main_serial: 0 for task, *_ in started}
        while pending:
            for entry in pending[:]:
                task, process, started_at, command, output, progress_path = entry
                exit_code = process.poll()
                with progress_path.open("r", encoding="utf-8") as stream:
                    stream.seek(offsets[task.main_serial])
                    while True:
                        position = stream.tell()
                        line = stream.readline()
                        if not line or not line.endswith("\n"):
                            stream.seek(position)
                            break
                        terminal.event(task.main_serial, json.loads(line))
                    offsets[task.main_serial] = stream.tell()
                if exit_code is None:
                    continue
                output.close()
                progress_path.unlink(missing_ok=True)
                duration = round(time.time() - started_at, 3)
                processing = None
                session_data = {}
                session_file = task.output_dir / "session_result.json"
                if session_file.is_file():
                    try:
                        session_data = json.loads(session_file.read_text(encoding="utf-8"))
                        processing = session_data.get("extensions", {}).get("dynamic_model", {}).get("processing")
                    except (OSError, ValueError, AttributeError):
                        logger.exception("读取处理状态失败：%s", session_file)
                result = {"testbed": task.testbed_name, "main_serial": task.main_serial,
                          "output_dir": _to_runner_relative_path(task.output_dir, runner_config.output_dir),
                          "session_result": _to_runner_relative_path(session_file, runner_config.output_dir),
                          "command": command, "exit_code": exit_code, "duration_seconds": duration,
                          "processing": processing, "status": ("passed" if exit_code == 0 else
                              "failed" if exit_code == 1 and session_data.get("exitstatus") is not None else "interrupted")}
                terminal.finish(task.main_serial, exit_code, interrupted=result["status"] == "interrupted")
                results.append(result)
                logger.info("任务结束 serial=%s exit_code=%s duration=%s", task.main_serial, exit_code, duration)
                if store:
                    store.update(task.main_serial, **{k: v for k, v in result.items() if k != "main_serial"})
                pending.remove(entry)
            if pending:
                time.sleep(0.1)
        return results
    finally:
        for task, process, _, _, output, progress_path in started:
            if process.poll() is None:
                logger.warning("终止未完成的子进程 serial=%s", task.main_serial)
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                except OSError:
                    logger.exception("终止子进程失败 serial=%s", task.main_serial)
            if not output.closed:
                output.close()
            progress_path.unlink(missing_ok=True)


def build_pytest_command(
    *,
    runner_config: DynamicRunnerConfig,
    task: DynamicRunnerTask,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "exfw.models.dynamic.dynamic_pytest.progress_events",
        str(runner_config.test_path),
        "--project-config",
        str(runner_config.config_path),
        "--testbed",
        task.testbed_name,
    ]

    if runner_config.rounds is not None:
        command.extend(["--rounds", str(runner_config.rounds)])

    return command


def _to_runner_relative_path(path: Path, runner_output_dir: Path) -> str:
    """将 runner 产物路径保存为相对 runner 输出目录的可迁移路径。"""

    try:
        return path.relative_to(runner_output_dir).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
