"""回放引擎 —— 可标记、可开关、以检查点为锚的步骤回放。

对外入口：
- :class:`ReplayCase` pytest 用例回放基类，每个测试方法一个引擎；
- :class:`ReplayEngine` 回放引擎（计划链表 + 前向闸 + 检查点恢复）；
- :func:`replayable` / :func:`noreplay` / :func:`checkpoint` 标记装饰器；
- :class:`RecoveryStrategy` 恢复策略协议；
- :class:`ReplayAbortError` / :class:`CheckpointError` / :class:`OperationError` 异常。

典型用法::

    class UiActions:
        def __init__(self, device):
            self.device = device

        @replayable("点击登录")
        def click_login(self):
            self.device.click(text="登录")

        @checkpoint("确认首页")
        def check_home(self):
            return self.device.exists(text="首页")

    class TestLogin(ReplayCase):
        def test_login(self, primary_device):
            actions = UiActions(primary_device)
            actions.click_login()
            actions.check_home()
"""

from .case import ReplayCase
from .decorators import checkpoint, noreplay, replayable
from .engine import (
    CheckpointError,
    OperationError,
    ReplayAbortError,
    ReplayEngine,
)
from .nodes import CheckpointNode, Node, OperationNode
from .plan import Plan
from .strategy import RecoveryStrategy

__all__ = [  # noqa: RUF022
    # 用例基类
    "ReplayCase",
    # 引擎
    "ReplayEngine",
    "ReplayAbortError",
    "CheckpointError",
    "OperationError",
    # 数据
    "Plan",
    "Node",
    "OperationNode",
    "CheckpointNode",
    # 标记
    "replayable",
    "noreplay",
    "checkpoint",
    # 恢复策略
    "RecoveryStrategy",
]
