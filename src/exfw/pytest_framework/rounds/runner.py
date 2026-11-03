from __future__ import annotations

import logging
from collections.abc import Sequence

import pytest

from exfw.pytest_framework.core.runtime import ROUND_TASK_RUNNER_KEY

from .tasks import RoundContext, RoundTask


class RoundTaskRunner:
    """负责按顺序执行 round 生命周期任务。"""

    def __init__(self, tasks: Sequence[RoundTask]) -> None:
        self._tasks = list(tasks)
        self._logger = logging.getLogger("exfw.round_task_runner")

    def add_task(self, task: RoundTask) -> bool:
        """追加一个 round 生命周期任务；同名任务已存在时跳过。"""
        if any(registered_task.name == task.name for registered_task in self._tasks):
            self._logger.debug("round 生命周期任务已注册，跳过：%s", task.name)
            return False

        self._tasks.append(task)
        return True

    def before_round(self, context: RoundContext) -> list[RoundTask]:
        """
        按顺序执行 round 前置任务。

        返回已进入启动流程的任务列表，供 round 结束或启动失败时反向清理。
        某个任务即使在 before_round 中途失败，也会被纳入清理范围。
        """
        started_tasks: list[RoundTask] = []

        for task in self._tasks:
            self._logger.info(
                "执行 round 前置任务：round=%03d, task=%s",
                context.round_no,
                task.name,
            )

            started_tasks.append(task)
            task.before_round(context)

        return started_tasks

    def after_round(
        self,
        *,
        context: RoundContext,
        started_tasks: Sequence[RoundTask],
    ) -> None:
        """
        反向执行 round 后置任务。

        反向清理可保证资源依赖关系正确，例如：
        环境准备 -> 开始采集 -> 执行测试
        停止采集 -> 环境清理
        """
        for task in reversed(started_tasks):
            try:
                self._logger.info(
                    "执行 round 后置任务：round=%03d, task=%s",
                    context.round_no,
                    task.name,
                )

                task.after_round(context)
            except Exception:
                # 清理任务失败不能覆盖测试本身的错误。
                self._logger.exception(
                    "Round 后置任务执行失败：round=%03d, task=%s",
                    context.round_no,
                    task.name,
                )


def get_or_create_round_task_runner(config: pytest.Config) -> RoundTaskRunner:
    """获取 pytest 会话共享的 RoundTaskRunner；不存在时创建。"""
    runner = config.stash.get(ROUND_TASK_RUNNER_KEY, None)

    if runner is None:
        runner = RoundTaskRunner(tasks=())
        config.stash[ROUND_TASK_RUNNER_KEY] = runner

    return runner
