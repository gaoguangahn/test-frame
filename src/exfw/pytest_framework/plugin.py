from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from .core.config_loader import (
    load_project_config,
    load_testbed_devices,
    resolve_project_path,
)
from exfw.project_config import find_project_config
from .core.logging_setup import configure_logging
from .core.runtime import EXFW_RUN_CONFIG_KEY, DeviceSpec, RunConfig
from .rounds.runner import get_or_create_round_task_runner
from .rounds.scheduler import RoundSchedulerPlugin

pytest_plugins = [
    "exfw.pytest_framework.fixtures.run_config",
    "exfw.pytest_framework.fixtures.devices",
    "exfw.pytest_framework.fixtures.rounds",
    "exfw.pytest_framework.fixtures.logging",
    "exfw.pytest_framework.fixtures.artifacts",
    "exfw.pytest_framework.fixtures.steps",
    "exfw.pytest_framework.hooks.session_results",
    "exfw.pytest_framework.hooks.case_results",
    "exfw.pytest_framework.hooks.log_context",
    "exfw.pytest_framework.hooks.terminal_output",
]


def pytest_addoption(parser: pytest.Parser) -> None:
    """
    注册框架运行所需的命令行参数。

    此 Hook 在 pytest 参数解析阶段调用。
    """
    group = parser.getgroup("exfw", "EXFW 测试框架选项")

    group.addoption("--exfw-console-log", action="store_true", default=False,
                    help="在终端显示框架运行日志。")

    group.addoption(
        "--project-config",
        action="store",
        default=None,
        metavar="PATH",
        help="项目 YAML 路径；默认从 pytest 项目根目录向上查找 project.yaml。",
    )

    group.addoption(
        "--testbed",
        action="store",
        default=None,
        metavar="NAME",
        help="测试床名称，例如：lab_a",
    )

    group.addoption(
        "--device",
        action="append",
        default=[],
        metavar="NAME",
        help=("选择设备名称。可重复传入，例如：--device main --device assistant"),
    )

    group.addoption(
        "--output-dir",
        action="store",
        default=None,
        metavar="PATH",
        help=(
            "调试输出父目录，默认为 outputs；实际写入其 debug 子目录。"
            "相对路径以项目配置文件所在目录为基准。"
        ),
    )

    group.addoption(
        "--rounds",
        action="store",
        type=int,
        default=None,
        metavar="COUNT",
        help="按测试套执行的轮数；未指定时不启用 round 调度。",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """解析 EXFW 配置并构造本次运行的 RunConfig。"""
    try:
        config_value = config.getoption("--project-config")
        testbed_value = config.getoption("--testbed")
        device_values = config.getoption("--device")
        output_value = config.getoption("--output-dir")
        rounds_value = config.getoption("--rounds")

        if config_value is not None and (not isinstance(config_value, str) or not config_value.strip()):
            raise ValueError("--project-config 必须是非空路径。")

        if testbed_value is not None and not isinstance(testbed_value, str):
            raise ValueError("--testbed 必须是有效的测试床名称。")

        if not isinstance(device_values, list):
            raise TypeError("--device 参数格式错误。")

        if output_value is not None and (not isinstance(output_value, str) or not output_value.strip()):
            raise ValueError("--output-dir 必须是非空路径。")

        if rounds_value is not None and rounds_value < 1:
            raise ValueError("--rounds 必须是大于等于 1 的整数。")

        # 配置文件本身可使用当前工作目录下的相对路径；
        # 一旦解析完成，项目根目录固定为其父目录。
        config_path = (Path(config_value).expanduser().resolve() if config_value
                       else find_project_config(config.rootpath))

        project_config = load_project_config(config_path)
        project_root = config_path.parent

        # runner 为每个子进程提供私有的实际 session 目录，不改变公开选项的父目录语义。
        session_output = os.environ.get("EXFW_SESSION_OUTPUT") if os.environ.get("EXFW_RUNNER_MODE") else None
        output_dir = (Path(session_output).resolve() if session_output else
                      resolve_project_path(project_root, output_value or "outputs") / "debug")
        output_dir.mkdir(parents=True, exist_ok=True)

        runtime_config = project_config.get("runtime")
        if not isinstance(runtime_config, dict):
            raise TypeError("配置文件中必须包含 runtime 映射对象。")

        configured_resources_dir = runtime_config.get("resources_dir")
        if (
            not isinstance(configured_resources_dir, str)
            or not configured_resources_dir.strip()
        ):
            raise ValueError("配置文件中的 runtime.resources_dir 必须是非空字符串。")

        resources_dir = resolve_project_path(
            project_root=project_root, raw_path=configured_resources_dir
        )

        if not resources_dir.is_dir():
            raise ValueError(f"资源目录不存在或不是目录：{resources_dir}")

        testbed_name = testbed_value
        if testbed_name is None and config.pluginmanager.hasplugin("exfw.models.dynamic.dynamic_pytest.plugin"):
            testbeds = project_config.get("testbeds") or {}
            if len(testbeds) == 1:
                testbed_name = next(iter(testbeds))
            elif len(testbeds) > 1:
                raise ValueError("配置包含多个 testbed，请通过 --testbed NAME 选择调试设备。")
        requested_device_names = device_values

        if testbed_name is None:
            if requested_device_names:
                raise ValueError(
                    "使用 --device 前必须先通过 --testbed NAME 选择测试床。"
                )
            device_specs = ()
        else:
            all_device_specs = load_testbed_devices(
                project_config=project_config, testbed_name=testbed_name
            )

            device_specs = _select_devices(
                all_devices=all_device_specs,
                requested_device_names=requested_device_names,
            )

        runtime_config = project_config.get("runtime")

        run_config = RunConfig(
            config_path=config_path,
            testbed_name=testbed_name,
            device_specs=device_specs,
            output_dir=output_dir,
            resources_dir=resources_dir,
            artifact_layout="round" if rounds_value is not None else "plain",
            project_config=project_config,
        )

        config.stash[EXFW_RUN_CONFIG_KEY] = run_config

        # 再初始化日志：此后 exfw.* 的日志都会写入同一文件。
        log_file = configure_logging(run_config.output_dir, console=config.getoption("--exfw-console-log"))

        logger = logging.getLogger("exfw.plugin")

        get_or_create_round_task_runner(config)

        config.pluginmanager.register(
            RoundSchedulerPlugin(),
            name="exfw-round-scheduler",
        )

        logger.info(
            "框架初始化完成，testbed=%s，devices=%s，log_file=%s",
            run_config.testbed_name,
            [device.name for device in run_config.device_specs],
            log_file,
        )

    except (FileNotFoundError, TypeError, ValueError) as error:
        raise pytest.UsageError(str(error)) from error


def _select_devices(
    all_devices: tuple[DeviceSpec, ...], requested_device_names: list[str]
) -> tuple[DeviceSpec, ...]:
    """按命令行设备名称筛选设备；未指定时使用全部设备。"""
    if not requested_device_names:
        return all_devices

    device_map = {device.name: device for device in all_devices}

    missing_names = [name for name in requested_device_names if name not in device_map]

    if missing_names:
        available_names = ", ".join(device_map) or "无"
        raise ValueError(
            f"测试床中未找到设备：{', '.join(missing_names)}; "
            f"可用设备：{available_names}"
        )

    return tuple(device_map[name] for name in requested_device_names)
