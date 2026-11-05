from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import pytest

if TYPE_CHECKING:
    from exfw.pytest_framework.rounds.runner import RoundTaskRunner


@dataclass(frozen=True)
class DeviceSpec:
    """单台设备的静态配置。"""

    name: str
    serial: str
    model: str | None
    driver: str


@dataclass(frozen=True)
class RunConfig:
    """一次 Pytest 执行对应的 EXFW 运行上下文。"""

    config_path: Path
    testbed_name: str | None
    device_specs: tuple[DeviceSpec, ...]
    output_dir: Path
    resources_dir: Path
    artifact_layout: Literal["plain", "round"] = "plain"
    project_config: dict[str, Any] = field(default_factory=dict)

    @property
    def project_root(self) -> Path:
        """项目根目录：EXFW 配置文件所在目录。"""
        return self.config_path.parent


EXFW_RUN_CONFIG_KEY: pytest.StashKey[RunConfig] = pytest.StashKey()

# round task 调度器。
ROUND_TASK_RUNNER_KEY: pytest.StashKey[RoundTaskRunner] = pytest.StashKey()

# 当前 round 编号。
EXFW_CURRENT_ROUND_KEY: pytest.StashKey[int] = pytest.StashKey()
