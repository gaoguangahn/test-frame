"""回放相关装饰器。

- ``@replayable``：
  操作方法进入回放计划。
  原方法返回什么，包装后仍返回什么。

- ``@checkpoint``：
  检查点方法进入回放计划。
  方法必须严格返回 bool：
  True 表示通过，False 表示不通过。

- ``@noreplay``：
  不进入回放计划，始终直接执行原方法。
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from .context import get_current_replay_engine
from .engine import CheckpointError
from .nodes import CheckpointNode, OperationNode, require_checkpoint_bool

_MARK = "_replay_mark"

M_OP = "op"
M_CP = "cp"
M_NO = "no"


def _engine_of(instance: Any):
    """从当前用例上下文取回放引擎；未绑定时降级为直接执行。"""
    return get_current_replay_engine()


def _wrap_op(
    func: Callable,
    desc: str | None = None,
    op_type: Any = None,
) -> Callable:
    """将普通业务方法包装成可回放操作。

    重要语义：

    - 无引擎：直接调用原方法，原样返回；
    - 有引擎：创建 ``OperationNode`` 并同步提交；
    - 操作方法的返回值不做任何真假转换；
    - 原方法返回什么，最终调用者就收到什么；
    - 操作失败由异常表达，而不是由返回 ``False`` 表达。
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kw):
        engine = _engine_of(self)

        # 未启用引擎：保持原始 Python 调用语义。
        if engine is None:
            return func(self, *args, **kw)

        node = OperationNode(
            func=lambda: func(self, *args, **kw),
            desc=desc or func.__name__,
            method_name=func.__name__,
            op_type=_normalize_type(op_type),
        )

        return engine.submit(node)

    setattr(wrapper, _MARK, M_OP)
    return wrapper


def _wrap_checkpoint(func: Callable, desc: str | None = None) -> Callable:
    """将验证方法包装成检查点。

    检查点方法必须严格返回 ``bool``：

    - ``True``：检查点通过；
    - ``False``：检查点不通过；
    - ``None``、``0``、``1``、字符串、对象等：抛出类型异常。

    无引擎模式下，检查点失败抛 ``CheckpointError``；
    有引擎模式下，检查点失败由引擎执行恢复逻辑。
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kw):
        label = desc or func.__name__
        engine = _engine_of(self)

        if engine is None:
            # 未启用引擎：保持原始 Python 调用语义。
            return func(self, *args, **kw)

        node = CheckpointNode(
            verify=lambda: func(self, *args, **kw),
            desc=label,
        )
        return engine.submit(node)

    setattr(wrapper, _MARK, M_CP)
    return wrapper


def replayable(arg: Any = None, *, desc: str | None = None, op_type: Any = None):
    """声明方法或类可回放。

    支持以下用法：

    ```python
    @replayable
    def click_login(self):
        ...
    ```

    ```python
    @replayable(desc="点击登录", op_type="click")
    def click_login(self):
        ...
    ```

    ```python
    @replayable
    class LoginPage:
        def input_account(self, account: str):
            ...

        @checkpoint("已进入首页")
        def is_on_home(self) -> bool:
            ...

        @noreplay
        def current_title(self) -> str:
            ...
    ```

    类级装饰时：

    - 所有 public 方法默认包为操作节点；
    - 已标记为 ``@checkpoint`` 的方法保持检查点语义；
    - 已标记为 ``@noreplay`` 的方法不参与回放；
    - 下划线开头的方法不处理。
    """

    if isinstance(arg, type):
        return _replayable_class(arg)

    if callable(arg):
        return _wrap_op(arg, desc=desc, op_type=op_type)

    if arg is not None:
        desc = str(arg)

    def deco(func: Callable):
        return _wrap_op(func, desc=desc, op_type=op_type)

    return deco


def _replayable_class(cls: type) -> type:
    """为类中未特殊标记的 public 方法自动添加 ``@replayable``。"""

    for name, val in list(vars(cls).items()):
        if name.startswith("_"):
            continue

        if not callable(val):
            continue

        # 已被 @checkpoint 或 @noreplay（或显式 @replayable）处理过，
        # 不重复包装。
        if getattr(val, _MARK, None) is not None:
            continue  # 已被 @checkpoint / @noreplay 标记，跳过

        setattr(cls, name, _wrap_op(val))

    cls._replayable_class = True
    return cls


def noreplay(func: Callable) -> Callable:
    """标记方法不参与回放。

    适用场景：

    - 获取当前页面文本；
    - 获取动态 ID；
    - 读取设备状态；
    - 获取网络响应；
    - 不应在恢复期间重放的副作用操作。

    此装饰器只打标，不包装。因此该方法始终是普通 Python 方法调用，
    返回值也完全由原方法决定。
    """
    setattr(func, _MARK, M_NO)
    return func


def checkpoint(arg: Any = None, *, desc: str | None = None):
    """声明方法为检查点。

    支持以下用法：

    ```python
    @checkpoint
    def is_on_home(self) -> bool:
        return self.device(resourceId="home_root").exists
    ```

    ```python
    @checkpoint("确认已进入首页")
    def is_on_home(self) -> bool:
        return self.device(resourceId="home_root").exists
    ```

    检查点方法必须是纯查询，不可修改页面或设备状态。
    """

    if callable(arg):
        return _wrap_checkpoint(arg, desc=desc)

    if arg is not None:
        desc = str(arg)

    def deco(func: Callable):
        return _wrap_checkpoint(func, desc=desc)

    return deco


def _to_str(v) -> str:
    """枚举取 .value，其余取 str()。"""
    return getattr(v, "value", None) or str(v)


def _normalize_type(value) -> list | None:
    """标准化操作类型参数。

    ```python
    _normalize_type(None)
    # None

    _normalize_type("click")
    # ["click"]

    _normalize_type(["click", "ui"])
    # ["click", "ui"]
    ```
    """

    if value is None:
        return None

    if not isinstance(value, (list, tuple)):
        value = [value]

    return [_to_str(v) for v in value]
