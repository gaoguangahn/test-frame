# execute-framework

基于 pytest 的 Android 自动化测试框架，提供设备操作、多轮执行、动态模型采集与结果上报，以及 Excel 报告。

## 环境与配置

需要 Python 3.12 或更高版本、uv、ADB 和可连接的 Android 设备。安装依赖：

```bash
uv sync
adb devices
```

如果尚未安装 uv，或同步依赖时遇到网络问题，见文末的“uv 安装与环境排查”。

业务用例由使用者维护；仓库主要提供 `src/` 下的能力。在用例目录的 `conftest.py` 中加载插件：

```python
pytest_plugins = [
    "exfw.pytest_framework.plugin",
    "exfw.models.dynamic.dynamic_pytest.plugin",
]
```

参考根目录 `project.yaml` 配置 `runtime.resources_dir`、`testbeds` 和 `test_models.dynamic_model`。资源目录必须存在，设备序列号须与 ADB 一致；动态模型要求测试床包含名为 `main` 的设备。相对路径以配置文件所在目录为基准。runner 启用结果上传时，动态插件初始化会向结果服务申请任务 ID，需确保服务可连接；直接 pytest 调试默认不上报。服务地址见 `src/exfw/models/dynamic/server_config.py`。

## 编写和运行用例

```python
from exfw.models.dynamic import DynamicCase

class TestDemo(DynamicCase):
    def test_demo(self):
        self.step("点击搜索框")
        self.device.click(500, 1000)
```

`self.step()` 记录步骤并按配置截图，返回记录字典；失败时也会截图。`self.device` 是主设备；基类还提供键盘工厂、弹窗处理和 Trace 采集能力。

```bash
uv run python -m pytest tests/debug/test_demo.py
```

默认读取项目根目录的 `project.yaml`，输出到 `outputs/debug`。单个 testbed 自动选择；多个 testbed 时通过 `--testbed` 选择，`--device` 可重复指定以筛选设备。不指定 `--rounds` 时走普通 pytest 流程，只进行用例级采集和本地解析；使用 `--rounds 1` 可启用轮次级采集。直接调试默认不上传。

可用 `--project-config other.yaml` 指定项目配置；`--output-dir results` 指定输出父目录，实际调试目录为 `results/debug`。该目录重复使用且不自动清理，旧原始产物可能影响解析，需要时请手动清理。用 `--collect-only -q` 可检查用例收集。

## 批量运行和报告

在 `test_models.dynamic_model.runner` 配置 `test_path`、输出父目录 `output_dir`、测试名 `test_name` 和可选的 `rounds`，然后运行：

```bash
uv run python -m exfw.models.dynamic.runner
uv run python -m exfw.models.dynamic.report --task-dir outputs/debug_20261104_143025 --output outputs/debug_20261104_143025/report.xlsx --source local
```

runner 每次在输出父目录下创建 `测试名_年月日_时分秒` 目录，并在终端打印路径；同名目录已存在时直接报错，避免覆盖。runner 为每个 testbed 启动 pytest 子进程，要求各主设备序列号不同。输出包括 `task_result.json`、每台设备的 `session_result.json`、`parsed_results.json` 和 `main_device_info.json`，以及各用例的截图、日志和 Trace 记录。报告命令可重复传入 `--serial` 筛选设备，或通过 `--round` 筛选轮次。

runner 结束时会在本次测试目录生成 `execution_report.html`，可离线查看设备、用例、失败详情及采集、解析、上传状态。需要在运行中或异常中断后更新页面时，可基于已落盘的数据重新生成：

```bash
uv run python -m exfw.models.dynamic.result.execution_html --task-dir outputs/debug_20261104_143025
```

HTML 是生成时的快照；整个结果目录一起移动时可保留页面内的相对文件链接。

动态模型默认解析 Trace 和日志；runner 按配置决定是否上报用例结果。无法连接结果服务时，可在 `project.yaml` 中设置：

```yaml
test_models:
  dynamic_model:
    upload:
      enabled: false
```

关闭后不会请求服务端 task ID，也不会上传；日志、Trace 等原始产物仍会在本地解析。每台设备的 `parsed_results.json` 保存各轮和用例的解析结果；`session_result.json` 保存用例执行结果、采集产物及解析、上传状态，并记录本地运行 ID。部署网络可用时设为 `true`；不配置该字段时默认启用上报，服务端 task ID 创建失败仍会报错。

离线运行完成后可指定本地结果生成报告：

```bash
uv run python -m exfw.models.dynamic.report --task-dir outputs/debug_20261104_143025 --output outputs/debug_20261104_143025/report.xlsx --source local
```

本地报告只包含已配置解析器产生的指标；缺少用例解析结果时会报错。当前未实现安全补传，服务端去重规则需要先确认。

报告结合 runner 本地产物和服务端按 task ID 查询的结果生成；无数据时请检查 runner 输出、session 中的 task ID 和服务端连接。

动态模型采集项由 `src/exfw/models/dynamic/capture/profile.yaml` 配置，解析映射由 `src/exfw/models/dynamic/analyse/profile.yaml` 配置；两者都属于模型内部配置。采集 profile 中 `jank_log` 必须先于其他持续日志启动，radar 重置与采集必须成对配置。

具体日志采集器由动态模型维护；AW 的 `exfw.aw.logcat` 提供采集基类和 `CmdRunner`。动态模型用例使用 `self.tracer` 采集 Trace，通用 pytest 层不再提供 `trace_collector`、`logcat_manager` fixture 或对应基类属性。AW `TraceCollector` 不再是全局单例，同一设备的多个采集器实例需由调用方避免并发采集。

报告生成成功后，会在每个参与报告的设备目录下重新生成 `bd_jank/fluency` 和 `bd_jank/animator`。前者收集发生滑动卡顿用例的 `AppSwipe` Trace，后者收集发生启退动效卡顿用例的 `AppLaunch`、`AppExit` Trace。归档时保留原文件名；遇到重名时追加区分标识。这些是候选 Trace，不代表每个文件都包含卡顿。未找到对应 Trace 时会在终端提示。

归档范围与报告的设备、轮次筛选一致：选中设备的 `bd_jank` 会整体替换，未选中的设备不受影响。复制前先在设备目录中暂存，复制失败会保留旧归档；原始 Trace 不受影响。卡顿判定沿用汇总页的 Counts 分段下标，依赖 BD 数据分段口径一致。

## 代码结构

- `src/exfw/pytest_framework`：通用 pytest 插件、fixture、步骤记录、结果及轮次调度，详见该目录 README。
- `src/exfw/models/dynamic`：动态模型插件、用例基类、采集、解析、上报、runner 和报告。
- `src/exfw/aw`：ADB 设备、日志、Trace、图像识别及键盘等基础能力。
- `src/exfw/replay`：操作、检查点和回放恢复引擎。
- `src/exfw/common`：HTTP 和模型客户端等公共能力。

键盘识别资源位于 `<resources_dir>/keyboard/<device.model>/`，包括字母和数字页的整屏截图 `letter.png`、`digit.png`；识别后的坐标缓存为 `layout.json`，可人工修正。设备型号优先使用配置值，否则通过 ADB 查询，失败时使用序列号。
## 运行日志

批量 runner 在输出根目录写入 `runner.log`；每个以主设备 SN 命名的子任务目录包含 `execution.log` 和 `pytest-output.log`。交互式终端按设备刷新用例进度、当前用例和失败数；不支持刷新时逐行输出。全部设备结束后按设备汇总用例结果及失败清单，任务异常时显示 pytest 输出路径。`execution.log` 包含框架和用例的详细日志；`pytest-output.log` 保存子进程合并后的 stdout/stderr 和 pytest 终端报告。最终测试结果保存在 `session_result.json`。

直接执行 pytest 时，终端默认保留 pytest 原生输出，`execution.log` 保存框架运行日志；需要在终端实时查看框架日志时可加 `--exfw-console-log`。`pytest-output.log` 保存 pytest 终端报告。直接运行时，`-s` 下用例或第三方库直接写入 stdout/stderr 的内容不保证进入该文件；默认捕获下失败报告中展示的捕获内容会随报告保存。日志文件每次运行覆盖，请为需要保留的运行指定不同输出目录。

一个 testbed 对应一个子任务目录；如果其中有多台设备，它们共享该目录。用例上下文中的日志包含轮次和完整 nodeid，后台解析与上传任务会延续提交时的上下文。

## uv 安装与环境排查

首次拿到工程后，在工程根目录执行 `uv sync`。uv 会根据项目配置创建 `.venv` 并安装依赖；项目默认使用 Python 3.12，若本机没有合适的 Python，uv 可能需要联网下载。运行手机用例前，还需安装 ADB、连接设备，并确认 `adb devices` 能看到设备。

如果没有安装 uv，可参考 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)。Windows PowerShell 的安装命令为：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装后重新打开终端，执行 `uv --version` 确认，再进入工程根目录运行 `uv sync`。安装命令本身需要访问 uv 的下载地址；无法访问时可按官方说明选择其他安装方式。

当前项目默认使用清华 PyPI 镜像。若 `uv sync` 因镜像连接、超时或包下载失败，可以临时指定其他可访问的源重试，例如官方 PyPI：

```powershell
uv sync --default-index https://pypi.org/simple
```

该选项只用于本次命令，不会修改 `pyproject.toml`；切换源可能重新解析本地 `uv.lock`。如果仍然失败，请根据报错检查网络、代理、包源权限或 Python 下载地址；依赖构建失败和版本冲突不一定能通过更换镜像解决。项目的 `metric-parser` 使用仓库内 `vendor/metric_parser-2.0.8-py3-none-any.whl`，请确认该文件已完整下载。

当前默认开发依赖中的 `weditor` 依赖 Windows 专用的 `pywin32`。Linux 环境可以尝试 `uv sync --no-dev` 不安装开发依赖；Linux 实际运行仍需在目标环境验证。
