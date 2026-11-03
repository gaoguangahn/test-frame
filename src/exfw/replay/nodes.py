"""回放引擎节点。

两类同构节点，都进链表，引擎按 ``is_checkpoint`` 分流：

- :class:`OperationNode` —— 一个原子设备动作，可被重放。``execute`` 调用
  封装的可执行闭包，返回 ``None/True`` 视为成功。
- :class:`CheckpointNode` —— 一个 ``verify`` 断言闭包（纯查询、无副作用），
  既是正常流程的前向闸，也是恢复时的探测锚。

两者结构对齐，遍历逻辑统一；区别仅在 ``execute`` 语义与恢复时是否参与探测。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class CheckpointReturnTypeError(TypeError):
    """检查点方法没有严格返回 bool。"""


def require_checkpoint_bool(result: Any, desc: str) -> bool:
    """校验检查点返回值必须是严格的 bool。

    使用 ``type(result) is bool`` 而不是 ``isinstance(result, bool)``，
    防止 Python 中 ``bool`` 是 ``int`` 子类导致 0 / 1 被误接收。
    """
    if type(result) is not bool:
        raise CheckpointReturnTypeError(
            f"检查点必须返回 bool，实际返回 {type(result).__name__}: {desc}"
        )
    return result


class Node:
    """链表节点基类：链表指针、索引、执行计数。不带业务语义。"""

    def __init__(self, desc: str = ""):
        self.idx: int = -1
        self.desc: str = desc
        self.next: Node | None = None
        self.prev: Node | None = None
        self.exec_count: int = 0

        # 最近一次 execute / probe 的结果。
        # 对 OperationNode：原始业务返回值。
        # 对 CheckpointNode：严格的 True / False。
        self.result: Any = None

    @property
    def is_checkpoint(self) -> bool:
        return False

    def execute(self) -> bool:
        raise NotImplementedError

    def __repr__(self) -> str:
        kind = "CP" if self.is_checkpoint else "OP"
        return f"{kind}[{self.idx}]{self.desc!r}"


class OperationNode(Node):
    """操作节点。

    ``func`` 是由装饰器创建的零参闭包，闭包中已经捕获原始 ``self``、
    位置参数与关键字参数。

    业务方法返回值完全原样保留，不作任何真假判断：

    - ``None`` 是合法结果；
    - ``False`` 是合法结果；
    - ``0``、空字符串、空列表等都是合法结果；
    - 只有方法抛异常时，操作才视为失败。
    """

    def __init__(
        self,
        func: Callable[[], object],
        desc: str,
        method_name: str | None = None,
        op_type: list | None = None,
    ):
        super().__init__(desc=desc)
        self.func = func
        self.method_name = method_name or getattr(func, "__name__", "unknown")
        self.op_type = op_type

    def execute(self) -> Any:
        """执行原始业务方法，并原样返回其结果。"""
        self.exec_count += 1
        self.result = self.func()
        return self.result


class CheckpointNode(Node):
    """检查点节点。

    ``verify`` 必须满足以下约束：

    1. 是纯查询，无副作用；
    2. 必须严格返回 ``bool``；
    3. ``True`` 表示当前状态符合预期；
    4. ``False`` 表示当前状态不符合预期。

    恢复时会反复调用 ``probe()``，因此检查点方法不能执行点击、输入、
    删除、提交等状态修改动作。
    """

    def __init__(self, verify: Callable[[], bool], desc: str):
        super().__init__(desc=desc)
        self.verify = verify
        self.cp_id: str | None = None

    @property
    def is_checkpoint(self) -> bool:
        return True

    def _verify(self) -> bool:
        """执行检查点方法并严格校验其返回值类型。"""
        result = self.verify()
        result = require_checkpoint_bool(result, self.desc)
        self.result = result
        return result

    def execute(self) -> bool:
        """正常前向执行检查点。"""
        self.exec_count += 1
        return self._verify()

    def probe(self) -> bool:
        """恢复过程中探测当前状态是否符合该检查点。

        - 不增加 ``exec_count``；
        - 普通查询异常视为当前状态不匹配，返回 ``False``；
        - 返回值类型不合法属于开发错误，直接抛出。
        """
        try:
            return self._verify()
        except CheckpointReturnTypeError:
            raise
        except Exception:
            return False
