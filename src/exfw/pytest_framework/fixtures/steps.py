from __future__ import annotations

from collections.abc import Generator

import pytest

from exfw.pytest_framework.step import (
    StepRecorder,
    reset_current_step_recorder,
    set_current_step_recorder,
)


@pytest.fixture(scope="function", autouse=True)
def step_recorder(
    request: pytest.FixtureRequest,
    test_logger,
) -> Generator[StepRecorder, None, None]:
    """记录当前用例通过 Step() 输出的步骤信息。"""

    recorder = StepRecorder(logger=test_logger)
    token = set_current_step_recorder(recorder)

    try:
        yield recorder
    finally:
        reset_current_step_recorder(token)

        steps = recorder.records
        setattr(request.node, "_exfw_steps", steps)

        request.node.user_properties = [
            item for item in request.node.user_properties if item[0] != "exfw_steps"
        ]
        request.node.user_properties.append(("exfw_steps", steps))
