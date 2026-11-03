from enum import Enum


class DeviceType(Enum):
    """设备操作实现类型。"""

    ADB = "adb"
    ROBOT = "robot"
