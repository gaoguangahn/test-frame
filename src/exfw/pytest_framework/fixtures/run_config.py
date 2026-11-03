from __future__ import annotations

from pathlib import Path

import pytest

from exfw.pytest_framework.core.runtime import EXFW_RUN_CONFIG_KEY, RunConfig


@pytest.fixture(scope="session")
def run_config(pytestconfig: pytest.Config) -> RunConfig:
    """获取本次 EXFW 执行的全局运行配置。"""
    config = pytestconfig.stash.get(EXFW_RUN_CONFIG_KEY, None)

    if config is None:
        raise RuntimeError(
            "未找到 EXFW 运行配置。"
            "请确认 pytest_ext.plugin 已加载，且 pytest_configure 已正常执行。"
        )

    return config


@pytest.fixture(scope="session")
def testbed_name(run_config: RunConfig) -> str | None:
    """获取本次执行选择的测试床名称。"""
    return run_config.testbed_name


@pytest.fixture(scope="session")
def output_dir(run_config: RunConfig) -> Path:
    """获取本次执行产物的输出根目录。"""
    return run_config.output_dir


@pytest.fixture(scope="session")
def resources_dir(run_config: RunConfig) -> Path:
    """获取项目资源目录。该目录由配置文件 runtime.resources_dir 指定。"""
    return run_config.resources_dir
