import time
from pathlib import Path

import adbutils

BASE_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = BASE_DIR / "resources"


def adb_install_apks_and_push_agent(serial: str):
    """ADB设备资源预置"""
    adb_dev = adbutils.adb.device(serial)

    def is_package_installed(package_name):
        return adb_dev.app_info(package_name) is not None

    apk_infos = [
        ("app-uiautomator.apk", "com.github.uiautomator", False),
        ("app-uiautomator-test.apk", "com.github.uiautomator.test", False),
    ]

    for apk_name, pkg_name, need_g in apk_infos:
        if not is_package_installed(pkg_name):
            apk_path = RESOURCE_DIR / apk_name
            if need_g:
                # 如果需要 -g 参数 (授予所有运行时权限)
                remote_tmp_path = f"/data/local/tmp/{apk_name}"
                adb_dev.sync.push(apk_path, remote_tmp_path)
                adb_dev.shell(f"pm install -r -g {remote_tmp_path}")
            else:
                adb_dev.install(apk_path)

            time.sleep(0.1)

    # 推送 atx-agent
    local_agent_path = RESOURCE_DIR / "atx-agent"
    remote_agent_path = "/data/local/tmp/atx-agent"

    adb_dev.sync.push(local_agent_path, remote_agent_path)
    time.sleep(0.2)

    # 赋予可执行权限
    adb_dev.shell(f"chmod 755 {remote_agent_path}")
    time.sleep(0.2)


if __name__ == "__main__":
    adb_install_apks_and_push_agent("ASPS015928000498")
