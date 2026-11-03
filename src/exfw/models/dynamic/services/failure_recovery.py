from __future__ import annotations

import logging
import time
from logging import Logger
from typing import Any

DESKTOP_ACTIVITY = "com.hihonor.android.launcher.unihome.UniHomeLauncher"

HOME_ONLY_ACTIVITIES = {
    "NotificationShade",
    "com.hihonor.hiboard.Workspace",
    DESKTOP_ACTIVITY,
}


def should_stop_app(package: str | None, activity: str | None) -> bool:
    """判断当前前台应用是否需要先停止，再执行 Home 恢复。"""

    return bool(package) and activity not in HOME_ONLY_ACTIVITIES


def is_desktop_activity(activity: str | None) -> bool:
    """判断当前前台 Activity 是否为动态模型期望的桌面 Activity。"""

    return activity == DESKTOP_ACTIVITY


def recover_to_desktop(
    *,
    device: Any,
    serial: str | None = None,
    logger: Logger | None = None,
) -> bool:
    """
    将动态模型设备恢复到桌面。

    只要进入恢复流程，就至少执行一次 Home；区别仅在于执行 Home 前是否需要先
    stop_app 当前前台应用。恢复异常只记录日志并返回 False，不向外抛出，避免阻塞
    后续用例执行。
    """

    logger = logger or logging.getLogger("exfw.dynamic_model.failure_recovery")

    try:
        package, activity = device.top_activity()
        logger.info(
            "动态模型失败恢复开始：serial=%s, package=%s, activity=%s",
            serial,
            package,
            activity,
        )

        if should_stop_app(package, activity):
            try:
                device.stop_app(package)
            except Exception:
                logger.exception(
                    "动态模型失败恢复停止当前应用失败，继续执行 Home：serial=%s, package=%s",
                    serial,
                    package,
                )

        device.home()

        time.sleep(0.5)
        package, activity = device.top_activity()

        if is_desktop_activity(activity):
            logger.info("动态模型失败恢复成功：serial=%s", serial)
            return True

        logger.warning(
            "动态模型失败恢复一次 Home 后仍未在桌面，补充执行一次 Home：serial=%s, package=%s, activity=%s",
            serial,
            package,
            activity,
        )
        device.home()

        time.sleep(0.5)
        package, activity = device.top_activity()
        recovered = is_desktop_activity(activity)

        if recovered:
            logger.info("动态模型失败恢复成功：serial=%s", serial)
        else:
            logger.warning(
                "动态模型失败恢复后仍未在桌面：serial=%s, package=%s, activity=%s",
                serial,
                package,
                activity,
            )

        return recovered

    except Exception:
        logger.exception("动态模型失败恢复异常：serial=%s", serial)
        return False
