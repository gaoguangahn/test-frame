# execute-framework

基于 pytest 的 Android 自动化测试框架，提供设备操作、多轮执行、动态模型采集与结果上报，以及 Excel 报告。

## 环境与配置

需要 Python 3.12 或更高版本、uv、ADB 和可连接的 Android 设备。安装依赖：

```bash
uv sync
adb devices
```

业务用例由使用者维护；仓库主要提供 `src/` 下的能力。在用例目录的 `conftest.py` 中加载插件：

```python
pytest_plugins = [
    "exfw.pytest_framework.plugin",
    "exfw.models.dynamic.dynamic_pytest.plugin",
]
```

参考根目录 `project.yaml` 配置 `runtime.resources_dir`、`testbeds` 和 `test_models.dynamic_model`。资源目录必须存在，设备序列号须与 ADB 一致；动态模型要求测试床包含名为 `main` 的设备。相对路径以配置文件所在目录为基准。动态插件初始化时向结果服务申请任务 ID，运行或收集用例前需确保服务可连接；服务地址见 `src/exfw/models/dynamic/server_config.py`。

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
uv run python -m pytest tests/dynamic --exfw-config project.yaml --testbed lab_a --device main --exfw-output outputs/debug --rounds 3 -s
```

`--device` 可重复指定，省略时使用测试床全部设备；不指定 `--rounds` 时使用普通 pytest 执行。`--exfw-config` 和 `--exfw-output` 必填。用 `--collect-only -q` 可检查用例收集。

## 批量运行和报告

在 `test_models.dynamic_model.runner` 配置 `test_path`、`output_dir` 和可选的 `rounds`，然后运行：

```bash
uv run python -m exfw.models.dynamic.runner --config project.yaml
uv run python -m exfw.models.dynamic.report --task-dir outputs/dynamic2 --output outputs/dynamic2/report.xlsx
```

runner 为每个 testbed 启动 pytest 子进程，要求各主设备序列号不同。输出包括 `runner_result.json`、每台设备的 `session_result.json` 和 `main_device_info.json`，以及各用例的截图、日志和 Trace 记录。报告命令可重复传入 `--serial` 筛选设备，或通过 `--round` 筛选轮次。

动态模型默认解析 Trace 和日志并上报用例结果。无法连接结果服务时，可在 `project.yaml` 中设置：

```yaml
test_models:
  dynamic_model:
    upload:
      enabled: false
```

关闭后不会请求服务端 task ID，也不会执行结果后台解析和上传；日志、Trace 等本地采集产物仍保留。`session_result.json` 中会记录 `upload_enabled: false` 和空的 task ID，此次运行不能通过服务端结果生成完整报告。部署网络可用时设为 `true`；不配置该字段时默认启用上报，连接失败仍会报错。

报告结合 runner 本地产物和服务端按 task ID 查询的结果生成；无数据时请检查 runner 输出、session 中的 task ID 和服务端连接。

报告生成成功后，会在每个参与报告的设备目录下重新生成 `bd_jank/fluency` 和 `bd_jank/animator`。前者收集发生滑动卡顿用例的 `AppSwipe` Trace，后者收集发生启退动效卡顿用例的 `AppLaunch`、`AppExit` Trace。文件名包含轮次、用例名及原 Trace 名称；这些是候选 Trace，不代表每个文件都包含卡顿。未找到对应 Trace 时会在终端提示。

归档范围与报告的设备、轮次筛选一致：选中设备的 `bd_jank` 会整体替换，未选中的设备不受影响。复制前先在设备目录中暂存，复制失败会保留旧归档；原始 Trace 不受影响。卡顿判定沿用汇总页的 Counts 分段下标，依赖 BD 数据分段口径一致。

## 代码结构

- `src/exfw/pytest_framework`：通用 pytest 插件、fixture、步骤记录、结果及轮次调度，详见该目录 README。
- `src/exfw/models/dynamic`：动态模型插件、用例基类、采集、解析、上报、runner 和报告。
- `src/exfw/aw`：ADB 设备、日志、Trace、图像识别及键盘等基础能力。
- `src/exfw/replay`：操作、检查点和回放恢复引擎。
- `src/exfw/common`：HTTP 和模型客户端等公共能力。

键盘识别资源位于 `<resources_dir>/keyboard/<device.model>/`，包括字母和数字页的整屏截图 `letter.png`、`digit.png`；识别后的坐标缓存为 `layout.json`，可人工修正。设备型号优先使用配置值，否则通过 ADB 查询，失败时使用序列号。
## 运行日志

批量 runner 在输出根目录写入 `runner.log`；每个以主设备 SN 命名的子任务目录包含 `exfw.log` 和 `pytest-output.log`。终端只显示带 SN、轮次和用例的进度及任务结果，失败时显示 pytest 输出路径。`exfw.log` 包含框架和用例的详细日志；`pytest-output.log` 保存子进程合并后的 stdout/stderr 和 pytest 终端报告。最终测试结果保存在 `session_result.json`。

直接执行 pytest 时，`exfw.log` 同时写文件和终端；`pytest-output.log` 保存 pytest 终端报告。直接运行时，`-s` 下用例或第三方库直接写入 stdout/stderr 的内容不保证进入该文件；默认捕获下失败报告中展示的捕获内容会随报告保存。日志文件每次运行覆盖，请为需要保留的运行指定不同输出目录。

一个 testbed 对应一个子任务目录；如果其中有多台设备，它们共享该目录。用例上下文中的日志包含轮次和完整 nodeid，后台解析与上传任务会延续提交时的上下文。
