from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from pathlib import Path

log_context = ContextVar("exfw_log_context", default={})


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = log_context.get()
        record.exfw_case = context.get("case", "-")
        record.exfw_round = context.get("round", "-")
        return True


def configure_logging(log_dir: Path) -> Path:
    """
    初始化框架日志。

    所有名称以 ``exfw`` 开头的 Logger，
    都会输出到控制台和当前运行目录的日志文件。

    Args:
        log_dir: 框架日志保存目录。

    Returns:
        日志文件路径。
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "exfw.log"

    formatter = logging.Formatter(
        fmt=("%(asctime)s.%(msecs)03d | %(levelname)-8s | round=%(exfw_round)s | case=%(exfw_case)s | %(name)s | %(message)s"),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台只显示 INFO 及以上，避免输出过多 DEBUG 信息。
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.addFilter(ContextFilter())
    console_handler.setFormatter(formatter)

    # 文件记录 DEBUG 及以上，便于问题排查。
    file_handler = logging.FileHandler(
        filename=log_file,
        mode="w",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.addFilter(ContextFilter())
    file_handler.setFormatter(formatter)

    # exfw 是整个框架的日志根节点。
    framework_logger = logging.getLogger("exfw")
    framework_logger.setLevel(logging.DEBUG)

    # 防止日志继续向 root logger 传播而重复打印。
    framework_logger.propagate = False

    # 避免重复初始化导致一条日志打印多次。
    for handler in framework_logger.handlers[:]:
        framework_logger.removeHandler(handler)
        handler.close()

    if not os.environ.get("EXFW_RUNNER_MODE"):
        framework_logger.addHandler(console_handler)
    else:
        console_handler.close()
    framework_logger.addHandler(file_handler)

    return log_file
