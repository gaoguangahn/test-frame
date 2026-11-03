from __future__ import annotations

import logging
from pathlib import Path

import pytest

from exfw.aw.trace import TraceCollector

from .capture.manager import LogcatManager
from .core.artifacts import CaseArtifacts
from .core.runtime import RunConfig


class BaseTestCase:
    """EXFW 通用测试基类，不主动连接设备。"""

    # 配置上下文
    run_config: RunConfig
    testbed_name: str | None
    output_dir: Path

    # 当前用例上下文
    current_round: int
    case_artifacts: CaseArtifacts
    test_logger: logging.Logger

    # 会话级采集能力
    logcat_manager: LogcatManager
    trace_collector: TraceCollector

    @pytest.fixture(autouse=True)
    def _inject_common_context(
        self,
        run_config: RunConfig,
        testbed_name: str | None,
        output_dir: Path,
        current_round: int,
        case_artifacts: CaseArtifacts,
        test_logger: logging.Logger,
        logcat_manager: LogcatManager,
        trace_collector: TraceCollector,
    ) -> None:
        """注入不涉及设备连接的通用测试上下文。"""

        self.run_config = run_config
        self.testbed_name = testbed_name
        self.output_dir = output_dir

        self.current_round = current_round
        self.case_artifacts = case_artifacts
        self.test_logger = test_logger

        self.logcat_manager = logcat_manager
        self.trace_collector = trace_collector
