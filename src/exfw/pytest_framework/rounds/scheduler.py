from __future__ import annotations

import logging

import pytest

from ..core.runtime import (
    EXFW_CURRENT_ROUND_KEY,
    EXFW_RUN_CONFIG_KEY,
    ROUND_TASK_RUNNER_KEY,
)
from .runner import RoundTaskRunner
from .tasks import RoundContext, RoundTask


class RoundSchedulerPlugin:
    """负责多轮执行以及 round 级采集生命周期管理。"""

    def __init__(self) -> None:
        self._logger = logging.getLogger("exfw.round_scheduler")

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtestloop(self, session: pytest.Session) -> bool | None:
        """
        仅当用户传入 --rounds 时，接管 pytest 的默认执行循环。

        未传 --rounds 时返回 None，让 pytest 按默认逻辑执行测试。
        """
        config = session.config
        rounds = config.getoption("--rounds")

        # 未显式指定 --rounds：
        # 不启用 round 采集，也绝不能接管 pytest 默认执行流程。
        if rounds is None:
            return None

        run_config = config.stash[EXFW_RUN_CONFIG_KEY]
        task_runner: RoundTaskRunner = config.stash[ROUND_TASK_RUNNER_KEY]

        try:
            for round_no in range(1, rounds + 1):
                if session.shouldstop:
                    break

                config.stash[EXFW_CURRENT_ROUND_KEY] = round_no

                context = RoundContext(
                    run_config=run_config,
                    round_no=round_no,
                    rounds=rounds,
                )

                self._logger.info(
                    "========== Round %03d/%03d 开始 ==========", round_no, rounds
                )

                started_tasks: list[RoundTask] = []

                try:
                    # 1. 执行所有 round 前置任务。
                    started_tasks = task_runner.before_round(context)

                    # 2. 执行本轮完整测试套。
                    for index, item in enumerate(session.items):
                        if session.shouldstop:
                            break

                        self._logger.info(
                            "执行测试：round=%03d, case=%s", round_no, item.nodeid
                        )

                        # 让报告、Junit XML 等产物能区分当前轮次。
                        item.user_properties = [
                            property_
                            for property_ in item.user_properties
                            if property_[0] != "exfw_round"
                        ]
                        item.user_properties.append(("exfw_round", round_no))

                        if index + 1 < len(session.items):
                            next_item = session.items[index + 1]
                        else:
                            # 每轮最后一个 case 后只保留 session fixture，
                            # 先让 function/class/module fixture 完成 teardown，
                            # 再进入 RoundTask.after_round()。
                            next_item = session

                        config.hook.pytest_runtest_protocol(
                            item=item, nextitem=next_item
                        )

                        if session.shouldfail:
                            raise session.Failed(session.shouldfail)

                        if session.shouldstop:
                            raise session.Interrupted(session.shouldstop)

                except Exception:
                    self._logger.exception("Round 执行异常：round=%03d", round_no)
                    raise

                finally:
                    try:
                        # 正常完成本轮时，最后一个 case 的 next_item=session
                        # 已完成这一步；这里基本为空操作。
                        #
                        # 若本轮提前结束，则兜底清理仍活跃的非 session fixture。
                        session._setupstate.teardown_exact(session)
                    finally:
                        task_runner.after_round(
                            context=context, started_tasks=started_tasks
                        )

                    self._logger.info(
                        "========== Round %03d/%03d 结束 ==========", round_no, rounds
                    )

        finally:
            # 所有 round 的 after_round 都完成后，最后再 teardown session fixture。
            session._setupstate.teardown_exact(None)

        return True
