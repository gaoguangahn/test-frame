# time: 2022-09-24 15:50
# author: Fucker (Refactored to class)
# description: 弹窗检测器, selector 聚合正则 + AI视觉叉号检测
import json
import logging
import os
from logging import Logger
from pathlib import Path
from typing import Any

import uiautomator2 as u2

from .rules import WatcherRule


class WatcherDetector:
    """Watcher 弹窗检测器"""

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or logging.getLogger("exfw.WatcherDetector")
        self.common_watchers: list[dict] = []
        self.load_common_watcher()

    def load_common_watcher(self):
        """加载通用规则"""

        file_path = str(Path(__file__).resolve().parent / "common_watcher.json")
        if not os.path.exists(file_path):
            self.logger.warning(f"未在指定路径找到通用watcher规则: {file_path}")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.common_watchers = data.get("rules") or []

    def _get_node_info(self, node) -> dict:
        """一次性获取 node.info"""
        try:
            return node.info or {}
        except Exception:
            return {}

    def _get_node_center(self, info: dict) -> tuple[int, int]:
        """获取中心点"""
        bounds = info.get("bounds") or {}
        if not isinstance(bounds, dict):
            return -1, -1

        left = bounds.get("left")
        top = bounds.get("top")
        right = bounds.get("right")
        bottom = bounds.get("bottom")

        if not all(isinstance(v, int) for v in (left, top, right, bottom)):
            return -1, -1

        return ((left + right) // 2, (top + bottom) // 2)

    def _find_action_node(
        self, device: u2.Device, action: dict[str, Any]
    ) -> Any | None:
        """在指定设备上找到 watcher 对应的处理控件。"""
        target = action.get("target")

        if not isinstance(target, dict):
            return None

        target_resource_id = target.get("resourceId")
        if isinstance(target_resource_id, str):
            node = device(resourceId=target_resource_id)
            if node.exists(timeout=0):
                return node

        target_text = target.get("text")
        if isinstance(target_text, str):
            node = device(text=target_text)
            if node.exists(timeout=0):
                return node

        target_description = target.get("description")
        if isinstance(target_description, str):
            node = device(description=target_description)
            if node.exists(timeout=0):
                return node

        return None

    def detect(
        self, device: u2.Device, watcher: list[dict[str, Any]] | None = None
    ) -> tuple[str, tuple[int, int]]:
        """检测弹窗并返回动作

        Args:
            device: 当前需要检测的 uiautomator2 设备对象。
            watcher (list[dict], optional): 要匹配的弹窗规则. Defaults to None.
            例:[{"text":"升级", "action":{"type": "click", "target": "确定"}}, {"description": "登录", "action": {"type": "back"}}]

        Returns:
            tuple[str, tuple[int, int]]: 返回动作类型和坐标, 类型 back/click/unknown, 坐标 (-1, -1)
        """

        # 1. 加载watcher匹配的规则
        if watcher:
            rule = WatcherRule(watcher)
        # elif self.common_watchers:
        #     rule = WatcherRule(self.common_watchers)
        else:
            self.logger.warning("未找到要匹配的watcher")
            return "unknown", (-1, -1)

        # 2. 生成watcher匹配的正则字符串
        text_pattern = rule.build_text_pattern()
        desc_pattern = rule.build_description_pattern()

        # 3. 找到匹配的节点
        text_node = None
        desc_node = None

        if text_pattern:
            text_node = device(textMatches=text_pattern)
            if not text_node.exists(timeout=0):
                text_node = None

        if desc_pattern:
            desc_node = device(descriptionMatches=desc_pattern)
            if not desc_node.exists(timeout=0):
                desc_node = None

        if text_node is None and desc_node is None:
            self.logger.debug("未找到匹配的弹窗节点")
            return "unknown", (-1, -1)

        # 4. 获取匹配到的节点信息和对应 watcher
        node = text_node or desc_node
        info = self._get_node_info(node)
        if not info:
            self.logger.warning("匹配到的弹窗元素获取信息失败")
            return "unknown", (-1, -1)

        matched_item = rule.match_item(info)
        if matched_item is None:
            self.logger.warning("弹窗元素信息未能匹配到对应的watcher规则")
            return "unknown", (-1, -1)

        # 5. 获取去弹窗要执行的操作
        action_type = matched_item.get_action_type()

        if action_type == "back":
            return "back", (-1, -1)

        if action_type == "click":
            target = matched_item.get_action_target()

            if not target:
                coords = self._get_node_center(info)
                if coords != (-1, -1):
                    return "click", coords
                return "unknown", (-1, -1)

            action_node = self._find_action_node(
                device=device, action=matched_item.action
            )
            if action_node is None:
                self.logger.warning(
                    f"找到弹窗-{matched_item.name}, 但无法找到对应的处理控件"
                )
                return "unknown", (-1, -1)

            action_info = self._get_node_info(action_node)
            coords = self._get_node_center(action_info)
            if coords != (-1, -1):
                return "click", coords

        return "unknown", (-1, -1)


if __name__ == "__main__":
    d = u2.connect_usb()
    w = WatcherDetector()
    watcher = [
        {"text_regex": "跳过.*", "action": {"type": "click"}},
        {"description": "关闭弹窗", "action": {"type": "click"}},
    ]
    print(w.detect(d, watcher))
