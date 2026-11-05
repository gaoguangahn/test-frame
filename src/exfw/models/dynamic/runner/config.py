from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from exfw.project_config import load_project_config, resolve_project_path


@dataclass(frozen=True)
class DynamicRunnerConfig:
    """动态模型 runner 配置。"""

    config_path: Path
    project_root: Path
    test_path: Path
    output_dir: Path
    rounds: int | None = None


@dataclass(frozen=True)
class DynamicRunnerTask:
    """一个 testbed 对应一个 pytest 子任务。"""

    testbed_name: str
    main_serial: str
    output_dir: Path


def load_dynamic_runner_plan(
    config_path: str | Path,
) -> tuple[DynamicRunnerConfig, list[DynamicRunnerTask]]:
    """读取 project.yaml，生成动态模型 runner 执行计划。"""

    resolved_config_path = Path(config_path).expanduser().resolve()
    project_config = load_project_config(resolved_config_path)
    project_root = resolved_config_path.parent

    runner_config = _load_runner_config(
        project_config=project_config,
        project_root=project_root,
        config_path=resolved_config_path,
    )

    tasks = _load_runner_tasks(
        project_config=project_config,
        runner_output_dir=runner_config.output_dir,
    )

    return runner_config, tasks


def _load_runner_config(
    *,
    project_config: dict[str, Any],
    project_root: Path,
    config_path: Path,
) -> DynamicRunnerConfig:
    test_models = project_config.get("test_models") or {}

    if not isinstance(test_models, dict):
        raise TypeError("配置中的 test_models 必须是映射对象。")

    dynamic_model_config = test_models.get("dynamic_model") or {}

    if not isinstance(dynamic_model_config, dict):
        raise TypeError("配置中的 test_models.dynamic_model 必须是映射对象。")

    runner_config = dynamic_model_config.get("runner") or {}

    if not isinstance(runner_config, dict):
        raise TypeError("配置中的 test_models.dynamic_model.runner 必须是映射对象。")

    raw_test_path = runner_config.get("test_path", "tests/dynamic")
    if not isinstance(raw_test_path, str) or not raw_test_path.strip():
        raise ValueError("test_models.dynamic_model.runner.test_path 必须是非空字符串。")

    raw_output_dir = runner_config.get("output_dir")
    if not isinstance(raw_output_dir, str) or not raw_output_dir.strip():
        raise ValueError("必须配置 test_models.dynamic_model.runner.output_dir。")

    test_name = runner_config.get("test_name")
    if (not isinstance(test_name, str) or not test_name.strip()
            or test_name != test_name.strip() or re.search(r'[<>:"/\\|?*\x00-\x1f]', test_name)
            or test_name in (".", "..") or test_name.endswith(".")):
        raise ValueError("test_models.dynamic_model.runner.test_name 必须是有效的目录名称。")

    rounds = runner_config.get("rounds")
    if rounds is not None:
        if not isinstance(rounds, int) or rounds < 1:
            raise ValueError("test_models.dynamic_model.runner.rounds 必须为空或大于等于 1 的整数。")

    return DynamicRunnerConfig(
        config_path=config_path,
        project_root=project_root,
        test_path=resolve_project_path(project_root, raw_test_path),
        output_dir=resolve_project_path(project_root, raw_output_dir) / f"{test_name}_{datetime.now():%Y%m%d_%H%M%S}",
        rounds=rounds,
    )


def _load_runner_tasks(
    *,
    project_config: dict[str, Any],
    runner_output_dir: Path,
) -> list[DynamicRunnerTask]:
    testbeds = project_config.get("testbeds")

    if not isinstance(testbeds, dict) or not testbeds:
        raise ValueError("配置中必须包含非空 testbeds 映射。")

    tasks: list[DynamicRunnerTask] = []
    seen_output_names: set[str] = set()

    for testbed_name, testbed_config in testbeds.items():
        if not isinstance(testbed_name, str) or not testbed_name:
            raise ValueError("testbeds 的 key 必须是非空字符串。")

        main_serial = _get_main_serial(testbed_name, testbed_config)

        if main_serial in seen_output_names:
            raise ValueError(
                f"多个 testbed 使用相同 main serial，输出目录会冲突：serial={main_serial}"
            )

        seen_output_names.add(main_serial)
        tasks.append(
            DynamicRunnerTask(
                testbed_name=testbed_name,
                main_serial=main_serial,
                output_dir=runner_output_dir / main_serial,
            )
        )

    return tasks


def _get_main_serial(testbed_name: str, testbed_config: Any) -> str:
    if not isinstance(testbed_config, dict):
        raise TypeError(f"测试床 {testbed_name} 必须是映射对象。")

    devices = testbed_config.get("devices")

    if not isinstance(devices, list) or not devices:
        raise ValueError(f"测试床 {testbed_name} 必须包含非空 devices 列表。")

    for index, device in enumerate(devices, start=1):
        if not isinstance(device, dict):
            raise TypeError(f"测试床 {testbed_name} 的第 {index} 个设备必须是映射对象。")

        if device.get("name") != "main":
            continue

        serial = device.get("serial")
        if not isinstance(serial, str) or not serial.strip():
            raise ValueError(f"测试床 {testbed_name} 的 main 设备 serial 必须是非空字符串。")

        return serial.strip()

    raise ValueError(f"动态模型 runner 要求测试床 {testbed_name} 必须包含 name=main 的设备。")
