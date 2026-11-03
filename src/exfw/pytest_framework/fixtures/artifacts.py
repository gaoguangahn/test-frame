from __future__ import annotations

import pytest

from exfw.pytest_framework.core.artifacts import CaseArtifacts, build_case_artifacts
from exfw.pytest_framework.core.runtime import RunConfig


@pytest.fixture(scope="function")
def case_artifacts(
    request: pytest.FixtureRequest,
    run_config: RunConfig,
    output_dir,
    current_round: int,
) -> CaseArtifacts:
    """返回当前用例的通用产物路径。"""
    return build_case_artifacts(
        output_dir=output_dir,
        round_no=current_round,
        nodeid=request.node.nodeid,
        use_round_dir=run_config.artifact_layout == "round",
    )
