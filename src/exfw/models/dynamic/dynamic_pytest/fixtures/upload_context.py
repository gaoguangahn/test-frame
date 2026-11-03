from __future__ import annotations

from typing import Any

import pytest

from exfw.models.dynamic.dynamic_pytest.runtime import get_dynamic_model_runtime


@pytest.fixture(scope="function")
def dynamic_upload_context(
    request: pytest.FixtureRequest,
    pytestconfig: pytest.Config,
    current_round: int,
) -> dict[str, Any]:
    """构造当前动态模型用例的结果上传上下文。"""

    runtime = get_dynamic_model_runtime(pytestconfig)

    return {
        "task_id": runtime.task_id,
        "round": current_round,
        "case": request.node.name,
        "step": "__case__",
    }
