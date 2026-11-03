import time

import uiautomator2 as u2

from .base.mixin_base import AdbMixinBase
from .constants import DESKTOP_PACKAGE
from .exception import InvalidArgumentError, OperationError
from .model.direction import Direction


class AdbActionMixin(AdbMixinBase):
    def screen_state(self) -> str | None:
        output = self.shell_cmd("dumpsys power | grep mWakefulness=")

        if "Awake" in output:
            return "AWAKE"
        elif "Asleep" in output or "Dozing" in output:
            return "SLEEP"

        return None

    def top_activity(self) -> tuple[str | None, str | None]:
        """获取当前前台包名和 Activity 名称。

        返回:
            (package_name, activity_name)
            解析失败时返回 (None, None)
            特殊系统窗口时返回 (None, window_name)
        """
        output = self.shell_cmd(
            "dumpsys window displays | grep mCurrentFocus", timeout=3
        )
        if not output or not output.strip():
            return None, None

        try:
            focus_line = None
            for line in output.splitlines():
                line = line.strip()
                if "mCurrentFocus" in line and "Window{" in line and "null" not in line:
                    focus_line = line
                    break

            if not focus_line:
                return None, None

            clean_line = " ".join(focus_line.split())
            focus_part = (
                clean_line.split("mCurrentFocus=", 1)[-1].strip().rstrip("}").strip()
            )
            focus_info = focus_part.split()[-1]

            if "/" in focus_info:
                package_name, activity_name = focus_info.split("/", 1)

                if activity_name.startswith("."):
                    activity_name = package_name + activity_name

                return package_name, activity_name

            # 特殊情况：没有斜杠，属于特殊系统窗口（如 HeadsupCardListWindow）
            return None, focus_info
        except Exception as e:
            self.logger.warning(f"解析前台包名失败: {e}")
            return None, None

    def lock(self):
        """锁屏"""
        screen_state = self.screen_state()
        if screen_state is None:
            raise OperationError("cannot get screen_state")
        if screen_state != "AWAKE":
            self.logger.warning("当前不是已解锁亮屏状态, 锁屏未生效")
            return

        self.device.screen_off()

    def unlock(self):
        """解锁, 只能亮屏，需要滑动解锁"""
        screen_state = self.screen_state()
        if screen_state is None:
            raise OperationError("cannot get screen_state")
        if screen_state == "AWAKE":
            self.logger.warning("当前已解锁亮屏状态, 解锁未生效")
            return

        self.shell_cmd("input keyevent 224")
        self.shell_cmd("wm dismiss-keyguard")

    def start_pkg(self, package_name: str):
        """通过包名启动应用"""
        if not package_name:
            err_msg = "package_name is empty"
            self.logger.error(err_msg)
            raise InvalidArgumentError(err_msg)

        self.device.app_start(package_name)

    def start_app(self, app_name: str, max_pages: int = 6):
        """通过APP名称启动应用"""

        # 连续点击两次 home 键，确保进入桌面第一页
        self.device.press("home")
        time.sleep(0.5)
        self.device.press("home")
        time.sleep(0.5)

        selectors = [
            {"text": app_name},
            {"description": app_name},
        ]

        for _ in range(max_pages):
            for kwargs in selectors:
                obj = self.device(**kwargs)
                if obj.exists(timeout=1):
                    obj.click()
                    return

            start_x = int(self.width * 0.85)
            end_x = int(self.width * 0.15)
            y = int(self.height * 0.5)

            self.device.swipe(start_x, y, end_x, y, steps=8)
            time.sleep(0.5)

        err_msg = f"{app_name} not found"
        self.logger.error(err_msg)
        raise OperationError(err_msg)

    def stop_app(self, package_name: str | None = None, desktop: str | None = None):
        """停止APP, 未指明包名则停止当前应用"""
        if package_name is not None and not isinstance(package_name, str):
            err_msg = "package_name must be string"
            self.logger.error(err_msg)
            raise InvalidArgumentError(err_msg)

        if package_name:
            self.device.app_stop(package_name)
            return

        pkg, _ = self.top_activity()
        if not pkg:
            err_msg = "cannot get current package"
            self.logger.error(err_msg)
            raise OperationError(err_msg)

        desktop_pkg = [desktop] if desktop else DESKTOP_PACKAGE

        if pkg in desktop_pkg:
            err_msg = "current app is desktop"
            self.logger.error(err_msg)
            raise OperationError(err_msg)

        self.device.app_stop(pkg)

    def _build_selector(
        self,
        *,
        text=None,
        textMatches=None,
        resourceId=None,
        description=None,
        descriptionMatches=None,
        className=None,
    ):
        selector = {}
        if text is not None:
            selector["text"] = text
        if textMatches is not None:
            selector["textMatches"] = textMatches
        if resourceId is not None:
            selector["resourceId"] = resourceId
        if description is not None:
            selector["description"] = description
        if descriptionMatches is not None:
            selector["descriptionMatches"] = descriptionMatches
        if className is not None:
            selector["className"] = className
        return selector

    def find_element(
        self,
        *,
        text=None,
        textMatches=None,
        resourceId=None,
        description=None,
        descriptionMatches=None,
        className=None,
        timeout=1,
    ) -> u2.UiObject | None:
        selector = self._build_selector(
            text=text,
            textMatches=textMatches,
            resourceId=resourceId,
            description=description,
            descriptionMatches=descriptionMatches,
            className=className,
        )

        if selector:
            obj = self.device(**selector)
            if obj.wait(timeout=timeout):
                return obj
            return None

        return None

    def click(
        self,
        *,
        obj: u2.UiObject | None = None,
        point=None,
        text=None,
        textMatches=None,
        resourceId=None,
        description=None,
        descriptionMatches=None,
        className=None,
    ):
        """点击一个元素, 支持已查找到的 UiObject、selector 或坐标。"""

        if obj is not None:
            obj.click()
            return

        obj = self.find_element(
            text=text,
            textMatches=textMatches,
            resourceId=resourceId,
            description=description,
            descriptionMatches=descriptionMatches,
            className=className,
            timeout=1,
        )

        if obj is not None:
            obj.click()
            return

        if point is not None:
            x, y = point
            self.device.click(x, y)
            return

        err_msg = "click failed"
        self.logger.error(err_msg)
        raise OperationError(err_msg)

    def double_click(
        self,
        *,
        obj: u2.UiObject | None = None,
        point=None,
        text=None,
        textMatches=None,
        resourceId=None,
        description=None,
        descriptionMatches=None,
        className=None,
        duration=0.1,
    ):
        """双击某个元素, 支持已查找到的 UiObject、selector 或坐标。"""

        if obj is not None:
            x, y = obj.center()
            self.device.double_click(x, y, duration=duration)
            return

        obj = self.find_element(
            text=text,
            textMatches=textMatches,
            resourceId=resourceId,
            description=description,
            descriptionMatches=descriptionMatches,
            className=className,
            timeout=1,
        )
        if obj is not None:
            x, y = obj.center()
            self.device.double_click(x, y, duration=duration)
            return

        if point is not None:
            x, y = point
            self.device.double_click(x, y, duration=duration)
            return

        err_msg = "double click failed"
        self.logger.error(err_msg)
        raise OperationError(err_msg)

    def long_click(
        self,
        *,
        obj: u2.UiObject | None = None,
        point=None,
        text=None,
        textMatches=None,
        resourceId=None,
        description=None,
        descriptionMatches=None,
        className=None,
        duration=1.0,
    ):
        """长按某个元素, 支持已查找到的 UiObject、selector 或坐标。"""

        if obj is not None:
            x, y = obj.center()
            self.device.long_click(x, y, duration=duration)
            return

        obj = self.find_element(
            text=text,
            textMatches=textMatches,
            resourceId=resourceId,
            description=description,
            descriptionMatches=descriptionMatches,
            className=className,
            timeout=1,
        )
        if obj is not None:
            x, y = obj.center()
            self.device.long_click(x, y, duration=duration)
            return

        if point is not None:
            x, y = point
            self.device.long_click(x, y, duration=duration)
            return

        err_msg = "long click failed"
        self.logger.error(err_msg)
        raise OperationError(err_msg)

    def swipe(
        self,
        *,
        start=None,
        end=None,
        direction=None,
        steps: int = 10,
        times: int = 1,
        interval: float = 1.0,
    ):
        """滑动, 支持 start/end 或 direction"""

        if times <= 0:
            err_msg = "swipe times must be greater than 0"
            self.logger.error(err_msg)
            raise InvalidArgumentError(err_msg)

        if direction is not None:
            x_mid = int(self.width / 2)
            y_mid = int(self.height / 2)

            if direction == Direction.LEFT:
                start = (int(self.width * 0.85), y_mid)
                end = (int(self.width * 0.15), y_mid)
            elif direction == Direction.RIGHT:
                start = (int(self.width * 0.15), y_mid)
                end = (int(self.width * 0.85), y_mid)
            elif direction == Direction.UP:
                start = (x_mid, int(self.height * 0.65))
                end = (x_mid, int(self.height * 0.3))
            elif direction == Direction.DOWN:
                start = (x_mid, int(self.height * 0.4))
                end = (x_mid, int(self.height * 0.8))
            elif direction == Direction.DOWN_SLIGHT:
                start = (x_mid, int(self.height * 0.4))
                end = (x_mid, int(self.height * 0.5))
            else:
                err_msg = f"invalid swipe direction: {direction}"
                self.logger.error(err_msg)
                raise InvalidArgumentError(err_msg)

        if not (
            isinstance(start, (list, tuple))
            and isinstance(end, (list, tuple))
            and len(start) == 2
            and len(end) == 2
        ):
            err_msg = f"invalid swipe coordinates: {start} -> {end}"
            self.logger.error(err_msg)
            raise InvalidArgumentError(err_msg)

        if not all(isinstance(v, (int, float)) for v in (*start, *end)):
            err_msg = f"invalid swipe coordinates: {start} -> {end}"
            self.logger.error(err_msg)
            raise InvalidArgumentError(err_msg)

        for i in range(times):
            self.device.swipe(start[0], start[1], end[0], end[1], steps=steps)
            if i < times - 1:
                time.sleep(interval)

    def back(self, method: str = "key"):
        """返回，支持 "key" 和 "swipe" 两种方式"""
        if method == "key":
            self.device.press("back")
        elif method == "swipe":
            mid_y = int(self.height * 0.5)
            mid_x = int(self.width * 0.5)
            self.device.swipe(0, mid_y, mid_x, mid_y, steps=8)
        else:
            err_msg = f"invalid back method: {method}"
            raise InvalidArgumentError(err_msg)

    def open_multitask(self, method: str = "key"):
        """打开多任务

        Args:
            method (str): 打开多任务的方式, 支持 "key" 和 "swipe"
        """
        if method == "key":
            self.device.press("recent")
        elif method == "swipe":
            mid_x = int(self.width * 0.5)
            start_y = int(self.height - 1)
            end_y = int(self.height * 0.5)

            self.device.touch.down(mid_x, start_y)
            self.device.touch.move(mid_x, end_y)
            time.sleep(0.3)
            self.device.touch.up(mid_x, end_y)
        else:
            err_msg = f"invalid open_multitask method: {method}"
            raise InvalidArgumentError(err_msg)

    def home(self, method: str = "key"):
        """返回桌面, 支持 "key" 和 "swipe" 两种方式"""
        if method == "key":
            self.device.press("home")

        elif method == "swipe":
            mid_x = int(self.width * 0.5)
            self.device.swipe(
                mid_x, self.height - 1, mid_x, int(self.height * 0.6), steps=15
            )

        else:
            err_msg = f"invalid home method: {method}"
            raise InvalidArgumentError(err_msg)

    def open_control(self):
        """下拉打开右上控制中心"""
        try:
            x = int(self.width * 0.8)
            end_y = int(self.height * 0.15)
            self.device.swipe(x, 0, x, end_y, steps=10)
        except Exception as e:
            self.logger.error(f"open control center failed: {e}")
            raise

    def open_notification(self, method: str = "key"):
        """打开通知栏, 支持 "key" 和 "swipe" 两种方式"""
        if method == "key":
            self.device.open_notification()
        elif method == "swipe":
            x = int(self.width * 0.2)
            end_y = int(self.height * 0.15)
            self.device.swipe(x, 0, x, end_y, steps=10)
        else:
            err_msg = f"invalid open_notification method: {method}"
            self.logger.error(err_msg)
            raise InvalidArgumentError(err_msg)

    def drag(self, start, end, duration: float):
        """拖动"""
        if not (
            isinstance(start, (list, tuple))
            and isinstance(end, (list, tuple))
            and len(start) == 2
            and len(end) == 2
        ):
            err_msg = f"invalid drag coordinates: {start}->{end}"
            self.logger.error(err_msg)
            raise InvalidArgumentError(err_msg)

        self.device.drag(start[0], start[1], end[0], end[1], duration)

    def set_text(self, text: str, obj: u2.UiObject | None = None):
        """输入文本, obj 为 None 时, 在聚焦控件输入或者adb输入"""
        if not isinstance(text, str):
            err_msg = f"invalid text: {text}"
            self.logger.error(err_msg)
            raise InvalidArgumentError(err_msg)

        if obj is not None:
            obj.set_text(text, timeout=3)
            return

        if any("\u4e00" <= ch <= "\u9fff" for ch in text):
            self.device(focused=True).set_text(text, timeout=3)
        else:
            safe = text.replace(" ", "%s")
            self.device.shell(f"input text {safe}", timeout=3)
