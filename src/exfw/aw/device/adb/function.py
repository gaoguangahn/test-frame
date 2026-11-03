import re
import shlex

import lxml.etree as etree

from .base.mixin_base import AdbMixinBase
from .utils import get_center


class AdbFunctionMixin(AdbMixinBase):
    """安卓设备功能性操作"""

    def monotonic_time(self) -> float:
        """获取手机当前的单调时间戳 (秒), 可以和trace对齐."""
        result = self.shell_cmd("cat /proc/uptime")
        if not result:  # 拦截空字符串，避免触发异常处理的开销
            return 0.0
        try:
            return float(result.split()[0])
        except Exception as e:
            self.logger.warning(f"获取单调时间戳失败: {e}")
            return 0.0

    def absolute_time(self) -> float:
        """获取手机当前的绝对时间戳 (秒), 用于和 Logcat 日期对齐"""
        result = self.shell_cmd("date +%s.%N")
        if not result:
            return 0.0
        try:
            return float(result.strip())
        except Exception as e:
            self.logger.warning(f"获取绝对时间戳失败: {e}")
            return 0.0

    def get_page_elements(self, light: bool = False):
        """获取页面所有元素"""
        current_page = self.device.dump_hierarchy(compressed=True)
        if not current_page:
            return []

        root = etree.fromstring(current_page.encode("utf-8"))

        if light:
            xpath_expr = "//*[@text!='' or @content-desc!='']"
            return [
                {
                    "text": el.get("text", ""),
                    "desc": el.get("content-desc", ""),
                    "bounds": el.get("bounds", ""),
                }
                for el in root.xpath(xpath_expr)
            ]

        xpath_expr = "//*[@text!='' or @content-desc!='' or @resource-id!='']"
        return [
            {
                "text": el.get("text", ""),
                "desc": el.get("content-desc", ""),
                "resourceId": el.get("resource-id", ""),
                "bounds": el.get("bounds", ""),
            }
            for el in root.xpath(xpath_expr)
        ]

    def check_page_elements(
        self,
        text=None,
        textContains=None,
        description=None,
        descriptionContains=None,
        resourceId=None,
        resourceIdMatches=None,
    ):
        """检查页面元素是否存在, 可以传入列表，检查多个元素全部满足"""

        def _normalize_to_list(value):
            if value is None:
                return []
            if isinstance(value, list):
                return value
            return [value]

        checks = [
            ("text", text, lambda v: self.device(text=v).exists(timeout=0)),
            (
                "textContains",
                textContains,
                lambda v: self.device(textContains=v).exists(timeout=0),
            ),
            (
                "description",
                description,
                lambda v: self.device(description=v).exists(timeout=0),
            ),
            (
                "descriptionContains",
                descriptionContains,
                lambda v: self.device(descriptionContains=v).exists(timeout=0),
            ),
            (
                "resourceId",
                resourceId,
                lambda v: self.device(resourceId=v).exists(timeout=0),
            ),
            (
                "resourceIdMatches",
                resourceIdMatches,
                lambda v: self.device(resourceIdMatches=v).exists(timeout=0),
            ),
        ]

        for _, value, checker in checks:
            for item in _normalize_to_list(value):
                if not checker(item):
                    return False

        return True

    def find_page_icons(self, desktop_package: str) -> dict:
        """获取桌面所有应用图标信息, 请保证在桌面"""

        page_apps = {}
        ui_info_str = self.device.dump_hierarchy(compressed=True)
        if not ui_info_str:
            return page_apps

        root = etree.fromstring(ui_info_str.encode("utf-8"))

        nodes = root.xpath(
            f"//*[@package='{desktop_package}' and @long-clickable='true' and ((string-length("
            "@content-desc)>=0 and string-length(@content-desc)<10) or (string-length(@text)>=0 and string-length("
            "@text)<10))]"
        )

        for node in nodes:
            text = node.attrib.get("text", "")
            desc = node.attrib.get("content-desc", "")
            if "条通知" in desc:
                desc = desc.split(" ")[0].strip()
            bounds = node.attrib.get("bounds", "")
            center = get_center(bounds) if bounds else None

            # first: text, else: desc
            if text:
                if center:
                    page_apps[text] = center
            elif desc:
                page_apps[desc] = center
        return page_apps

    def pull_file(self, phone_path: str, local_path: str):
        try:
            self.adb_dev.sync.pull(phone_path, local_path, exist_ok=True)
        except Exception as e:
            self.logger.error(
                f"ADB pull failed: {phone_path} -> {local_path}, error: {e}"
            )
            raise

    def push_file(self, local_path: str, phone_path: str):
        try:
            self.adb_dev.sync.push(local_path, phone_path)
        except Exception as e:
            self.logger.error(
                f"ADB push failed: {local_path} -> {phone_path}, error: {e}"
            )
            raise

    def delete_files(self, file_paths: list[str]):
        """删除手机内文件, 只允许传入文件列表, 不支持目录"""
        if not file_paths:
            return

        try:
            quoted_paths = " ".join(shlex.quote(p) for p in file_paths)
            self.shell_cmd(f"rm -f {quoted_paths}")
        except Exception as e:
            self.logger.error(f"ADB delete files failed: {file_paths}, error: {e}")
            raise

    def get_detail_info(self) -> dict:
        """获取当前设备详细信息"""
        width = 0
        height = 0

        wm_size = self.shell_cmd("wm size")
        match = re.search(r"(\d+)x(\d+)", wm_size)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))

        model = self.shell_cmd("getprop ro.product.model")
        brand = self.shell_cmd("getprop ro.product.brand")
        system_version = self.shell_cmd("getprop ro.build.display.id")
        os_version = self.shell_cmd("getprop ro.build.version.release")
        sdk = self.shell_cmd("getprop ro.build.version.sdk")
        ro_build = self.shell_cmd("getprop ro.build")

        ddr = self.shell_cmd("cat /proc/ddr_info")
        if not ddr:
            ddr = self.shell_cmd("getprop ro.product.ddr_info")

        flash_size = self.shell_cmd("cat /proc/bootdevice/size")
        flash_vid = self.shell_cmd("cat /proc/bootdevice/vid")

        match_size = re.search(r"(?:^|,|\s)(\d+[GT])(?:$|,|\s)", flash_vid)
        storage_size = match_size.group(1) if match_size else ""

        def kb_to_storage(kb: int) -> str:
            gb = kb / 1024 / 1024
            if gb < 8:
                return "8G"
            elif gb < 12:
                return "12G"
            elif gb < 16:
                return "16G"
            elif gb < 24:
                return "24G"
            else:
                return "24G+"

        mem_total = ""
        mem_total_str = self.shell_cmd("cat /proc/meminfo | grep MemTotal")
        match = re.search(r"\d+", mem_total_str)
        if match:
            mem_total = kb_to_storage(int(match.group()))

        return {
            "model": model,
            "brand": brand,
            "system_version": system_version,
            "os_version": os_version,
            "sdk": sdk,
            "resolution": [width, height],
            "ddr": ddr,
            "flash_size": flash_size,
            "flash_vid": flash_vid,
            "ro_build": ro_build,
            "mem_total": mem_total,
            "storage_size": storage_size,
        }
