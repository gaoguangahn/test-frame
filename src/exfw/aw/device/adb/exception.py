class ActionError(Exception):
    """Base class for all action errors."""

    default_code = "ACTION_ERROR"

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.default_code

    def __str__(self):
        return f"[{self.error_code}] {self.message}"


class OperationError(ActionError):
    """Low level device operation failed."""

    default_code = "DEVICE_OPERATION_ERROR"


class InvalidArgumentError(ActionError):
    """Invalid arguments for action."""

    default_code = "INVALID_ARGUMENT"


class DeviceUnavailableError(ActionError):
    """通用设备异常"""

    default_code = "DEVICE_UNAVAILABLE"


class ShellCommandError(ActionError):
    """Shell command execution failed."""

    default_code = "SHELL_COMMAND_ERROR"


class AdbDisconnectedError(DeviceUnavailableError):
    """ADB连接断开（设备掉线、线缆松动、adbd崩溃）"""

    default_code = "ADB_DISCONNECTED"


class U2ServiceError(DeviceUnavailableError):
    """U2/ATX服务异常（RPC报错、空指针、ATX进程被杀）"""

    default_code = "U2_SERVICE_ERROR"


class SystemCrashError(DeviceUnavailableError):
    """Android系统服务崩溃（软重启、System Server挂掉）"""

    default_code = "SYSTEM_CRASH_ERROR"
