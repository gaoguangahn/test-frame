"""计划：回放引擎持有的 操作/检查点 链表。

边跑边填：用户调用被标记的方法时，节点追加到链表尾；``current_node``
指针之前的节点已执行，之后（含当前）待执行。恢复时回拨指针即可重放，
重放完指针自然走到原失败点，再往后就是还没执行过的代码——"回放的 vs
没执行的"靠指针一气贯通，无需特殊处理。
"""
from __future__ import annotations

from collections.abc import Iterator

from .nodes import CheckpointNode, Node


class Plan:
    def __init__(self):
        self.head: Node | None = None
        self.tail: Node | None = None
        self._length: int = 0

    @property
    def length(self) -> int:
        return self._length

    def append(self, node: Node) -> Node:
        """追加节点到链表尾，分配索引。"""
        node.idx = self._length
        if isinstance(node, CheckpointNode):
            node.cp_id = f"cp-{node.idx}"
        self._length += 1
        node.next = None
        node.prev = self.tail
        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node
        self.tail = node
        return node

    def nodes_before(self, node: Node | None) -> Iterator[Node]:
        """从 head 迭代到 node（不含 node）；node 为 None 时遍历到尾。"""
        cur = self.head
        while cur is not None and cur is not node:
            yield cur
            cur = cur.next

    def nodes_upto(self, node: Node | None) -> Iterator[Node]:
        """从 head 迭代到 node（含 node）；node 为 None 时遍历到尾。

        恢复探测用：失败的检查点本身也纳入候选——清理后它可能重新满足，
        从它续跑比重放更早的锚更短。
        """
        cur = self.head
        while cur is not None:
            yield cur
            if cur is node:
                break
            cur = cur.next

    def all_nodes(self) -> list:
        return list(self.nodes_upto(None))
