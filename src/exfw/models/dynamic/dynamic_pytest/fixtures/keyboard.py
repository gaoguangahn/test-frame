from pathlib import Path

import pytest

from exfw.aw.device.adb.driver import AdbDriver
from exfw.aw.keyboard import Keyboard


@pytest.fixture(scope="session")
def keyboard_factory(resources_dir: Path):
    """
    键盘助手工厂，支持多设备
    resources_dir 由 EXFW 通用 pytest 插件提供，
    并已完成配置读取、相对路径解析和目录校验。
    """  # 用于存储已经初始化过的助手，避免同一个测试 Session 内重复初始化
    instances: dict[str, Keyboard] = {}

    def get_agent(driver: AdbDriver) -> Keyboard:
        serial = driver.serial

        if serial not in instances:
            agent = Keyboard(
                driver=driver,
                resources_dir=resources_dir,
            )

            model_name = getattr(driver, "model", "Unknown_Model")
            agent.init_by_model(model_name)

            instances[serial] = agent

        return instances[serial]

    return get_agent
