"""回放引擎。

职责：

1. 维护计划链表和 ``current_node`` 指针；
2. 同步执行新提交的节点；
3. 检查点失败时，探测历史检查点并回放后续操作；
4. 操作异常时直接终止，不进入恢复；
5. 保持普通操作方法的原始返回值。

核心语义：

- OperationNode：
  正常返回任意值都表示操作执行完成，返回值属于业务语义；
  只有抛异常才表示操作失败。

- CheckpointNode：
  必须严格返回 bool；
  True 表示通过；
  False 表示未通过，触发恢复。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from .nodes import CheckpointNode, CheckpointReturnTypeError, Node
from .plan import Plan


class ReplayAbortError(RuntimeError):
    """回放彻底失败（恢复超限或无锚点），用例无法继续。"""


class CheckpointError(AssertionError):
    """非回放模式下检查点未通过。"""


class OperationError(RuntimeError):
    """操作执行失败（界面已验证正确，但动作本身失败）。

    最近检查点已验证页面状态正确，但操作自身仍抛异常。
    此类失败通常不能通过回放修正，因此直接终止。
    """


RecoveryStep = Callable[[int], None]


class ReplayEngine:
    def __init__(
        self,
        *,
        recovery_step: RecoveryStep | None = None,
        max_recover: int = 4,
        max_probe_per_recover: int = 4,
        fatal_exceptions: tuple[type[BaseException], ...] = (),
        logger: Any = None,
    ):
        self.plan = Plan()
        self.current_node: Node | None = None
        self.replay_enabled: bool = True

        self._recover_count = 0
        # 恢复周期次数上限：限制最多进入多少次 _recover
        self.max_recover = max_recover
        # 单次恢复内的找锚次数上限：每次找锚前先做一次清理/策略动作
        self.max_probe_per_recover = max_probe_per_recover

        # 每次恢复探测前执行一次；参数为当前恢复周期内的 attempt。
        self.recovery_step = recovery_step

        # 这些异常视为设备致命故障，不拦入恢复，直接上抛
        self.fatal_exceptions = fatal_exceptions
        self.logger = logger or logging.getLogger("exfw.replay")

        # 可选钩子：供步骤记录/结果上报
        self.on_step: Callable[[Node, bool, float], None] | None = None

    # ---- 对外：提交并执行一个节点 ----
    def submit(self, node: Node) -> bool:
        """提交节点并同步执行。

        返回值规则：

        - 操作节点：返回原业务方法的原始结果；
        - 检查点节点：返回原检查点方法的 bool 结果；
        - 操作异常：抛 ``OperationError``；
        - 非回放模式下检查点返回 False：抛 ``CheckpointError``；
        - 回放模式下检查点无法恢复：抛 ``ReplayAbortError``。
        """
        if not self.replay_enabled:
            return self._submit_without_replay(node)

        self.plan.append(node)

        if self.current_node is None:
            self.current_node = node

        self._drive()

        # _drive 返回时，当前提交节点已经被前向执行完成，
        # 或已在恢复探测中确认通过。
        return node.result

    def _submit_without_replay(self, node: Node) -> Any:
        """无回放模式：仅执行一次，不入链表、不恢复。"""
        try:
            result = self._run_node(node)
        except CheckpointReturnTypeError:
            raise
        except Exception as error:
            if node.is_checkpoint:
                # 检查点查询本身异常，在非回放模式下按检查点不通过处理。
                raise CheckpointError(f"检查点执行异常: {node}") from error

            raise OperationError(f"操作异常（不回放）: {node}") from error

        if node.is_checkpoint and result is False:
            raise CheckpointError(f"检查点未通过: {node}")

        return result

    # ---- 主循环 ----
    def _drive(self):
        """从 current_node 驱动到尾巴。

        分流：检查点失败→恢复；操作失败→直接抛 OperationError (不回放)。
        恢复仅在检查点上触发——操作失败回放纠正不了（界面已验证正确，
        控件/动作本身有问题）。业务通过检查点密度自定回放频率。
        """
        while self.current_node is not None:
            node = self.current_node

            if node.is_checkpoint:
                ok = self._run_node(node)

                if ok:
                    self.current_node = node.next
                    continue

                # 检查点未通过 → 恢复
                anchor = self._recover()
                if anchor is None:
                    raise ReplayAbortError(f"恢复失败：检查点 {node} 重试耗尽")
                # anchor 是找到的检查点锚；从其后继重放。锚若是链表尾节点，
                # anchor.next=None，主循环自然结束（本次提交恰好完成）
                self.current_node = anchor.next
                continue

            # 普通操作：
            # 不解释其返回值，正常返回任意值都视为执行成功。
            try:
                self._run_node(node)
            except Exception as error:
                raise OperationError(
                    f"操作异常（界面已验证正确，不回放）: {node}"
                ) from error

            self.current_node = node.next

        # 追上尾巴 = 本次提交完成推进，清零失败计数
        self._recover_count = 0

    def _run_node(self, node: Node) -> bool:
        """执行单个节点并触发 ``on_step`` 钩子。

        处理规则：

        - 普通操作：
          原样返回业务结果；异常直接上抛。

        - 检查点：
          返回严格 bool；
          普通查询异常按 False 处理；
          返回类型错误直接上抛。
        """

        t0 = time.perf_counter()
        result: Any = False

        try:
            result = node.execute()
        except (SystemExit, KeyboardInterrupt):
            raise
        except self.fatal_exceptions:
            raise
        except Exception as e:
            if node.is_checkpoint:
                self.logger.warning(f"检查点异常 {node}: {e}")
                result = False
                node.result = False
            else:
                raise  # 操作异常向上抛，由 _drive 转 OperationError

        duration = time.perf_counter() - t0

        # 操作只要没有抛异常，步骤即成功；
        # 检查点的成功状态由其严格 bool 返回值决定。
        ok = result if node.is_checkpoint else True

        if self.on_step is not None:
            try:
                self.on_step(node, ok, duration)
            except Exception as e:
                self.logger.warning(f"on_step 钩子异常: {e}")

        if node.is_checkpoint and result is False:
            self.logger.warning(f"检查点未通过 {node}")

        return result

    # ---- 恢复 ----
    def _recover(self) -> CheckpointNode | None:
        """统一恢复循环：执行“策略动作 -> 锚点探测”，返回最近可用锚点。

        两个次数限制分开：

        - ``max_recover``：最多进入多少次恢复周期，跨检查点失败累计。
        - ``max_probe_per_recover``：单个恢复周期内最多执行多少个策略步骤。

        策略通过 ``step(attempt)`` 接收本周期的步骤号。引擎只控制次数、探测与
        回放，不了解任何设备和业务细节。
        """

        self._recover_count += 1
        if self._recover_count > self.max_recover:
            self.logger.error(f"恢复次数超限 ({self.max_recover})")
            return None

        for attempt in range(self.max_probe_per_recover):
            if self.recovery_step is not None:
                try:
                    self.recovery_step(attempt)
                except Exception as error:
                    self.logger.warning(
                        f"恢复策略 step 异常(recover={self._recover_count}, attempt={attempt}): {error}"
                    )

            anchor = self._probe_anchor()
            if anchor is not None:
                self.logger.info(
                    f"恢复成功(recover={self._recover_count}, attempt={attempt})，锚点为 {anchor}，从 {anchor.next} 重放"
                )
                return anchor

        self.logger.error(
            f"无可用恢复锚点（第 {self._recover_count} 个恢复周期，已探测 {self.max_probe_per_recover} 次）"
        )
        return None

    def _probe_anchor(self) -> CheckpointNode | None:
        """倒序探测失败节点及之前的检查点，第一个 verify 为真者即锚。

        含失败节点本身：恢复 step 策略后，失败的检查点可能
        重新满足，从它续跑比重放更早的锚更短。倒序取最近匹配点 → 重放段最短。
        """
        failed = self.current_node
        if failed is None:
            return None

        candidates = [
            n for n in self.plan.nodes_upto(failed) if isinstance(n, CheckpointNode)
        ]
        for checkpoint in reversed(candidates):
            if checkpoint.probe():
                return checkpoint

        return None

    # ---- 生命周期辅助 ----
    def reset(self):
        """新用例前重置（若复用引擎实例）。"""
        self.plan = Plan()
        self.current_node = None
        self._recover_count = 0
