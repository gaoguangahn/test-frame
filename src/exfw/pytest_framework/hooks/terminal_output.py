"""直接运行时复制 pytest 的终端报告，不改变 pytest 的展示。"""
import os
import pytest
from exfw.pytest_framework.core.runtime import EXFW_RUN_CONFIG_KEY


class _Tee:
    def __init__(self, original, output):
        self.original, self.output = original, output

    def write(self, text):
        self.original.write(text)
        self.output.write(text)
        self.output.flush()

    def flush(self):
        self.original.flush()
        self.output.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session):
    if os.environ.get("EXFW_RUNNER_MODE"):
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    run_config = session.config.stash.get(EXFW_RUN_CONFIG_KEY, None)
    if reporter is not None and run_config is not None:
        output = (run_config.output_dir / "pytest-output.log").open("w", encoding="utf-8")
        original = reporter._tw._file
        reporter._tw._file = _Tee(original, output)
        session.config._exfw_terminal_tee = (reporter, original, output)
        reporter.write_line(f"调试输出目录: {run_config.output_dir}")


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    tee = getattr(config, "_exfw_terminal_tee", None)
    if tee:
        reporter, original, output = tee
        reporter._tw._file = original
        output.close()
