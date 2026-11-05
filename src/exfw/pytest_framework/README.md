# exfw.pytest_framework 通用 pytest 扩展

`exfw.pytest_framework` 是 EXFW 的通用 pytest 能力层，只放和具体测试模型无关的能力。

它负责：

- 读取项目配置，构造本次运行的 `RunConfig`；
- 提供设备配置、设备连接、产物目录和日志等通用 fixtures；
- 在 `session_result.json` 中输出统一的用例结果；
- 提供通用步骤标记 `Step()`；
- 支持按测试套多轮执行；
- 为业务测试模型提供 round 生命周期扩展点。

它不应该直接包含动态模型、回放模型等业务专属逻辑。业务模型如果需要额外配置或能力，应在自己的插件中从 `RunConfig.project_config` 读取自己的 namespace。

---

## 目录结构

```text
exfw.pytest_framework/
  __init__.py
  plugin.py
  base_case.py
  step.py

  core/
    runtime.py
    config_loader.py
    artifacts.py
    logging_setup.py
    path.py

  fixtures/
    run_config.py
    devices.py
    rounds.py
    logging.py
    artifacts.py
    steps.py

  hooks/
    case_results.py

  rounds/
    tasks.py
    runner.py
    scheduler.py

```

### 顶层文件

| 文件 | 职责 |
|---|---|
| `plugin.py` | pytest 插件入口：注册命令行参数、读取配置、初始化运行时、加载 fixtures/hooks、注册 round scheduler。 |
| `base_case.py` | 通用测试基类，只注入不主动连接设备的通用上下文。 |
| `step.py` | 通用 `Step()` 步骤记录能力。 |
| `__init__.py` | 对外导出常用对象。 |

### `core/`

| 文件 | 职责 |
|---|---|
| `runtime.py` | 定义 `RunConfig`、`DeviceSpec` 和 pytest stash key。 |
| `config_loader.py` | 读取 YAML 项目配置，解析 testbed 设备列表。 |
| `artifacts.py` | 构造 run/case 级产物目录和用例结果路径。 |
| `logging_setup.py` | 初始化 `exfw` logger 的控制台和文件输出。 |
| `path.py` | 路径、文件名安全化工具。 |

### `fixtures/`

| 文件 | 提供能力 |
|---|---|
| `run_config.py` | `run_config`、`testbed_name`、`output_dir`。 |
| `devices.py` | `device_specs`、`device_manager`、`devices`。 |
| `rounds.py` | `current_round`。 |
| `logging.py` | `test_logger`。 |
| `artifacts.py` | `case_artifacts`。 |
| `steps.py` | 当前用例的通用 Step 记录器，将步骤写入 session 中的用例结果。 |

### `hooks/`

| 文件 | 职责 |
|---|---|
| `case_results.py` | 监听 pytest 用例报告，更新 session 中的用例结果。 |

### `rounds/`

| 文件 | 职责 |
|---|---|
| `tasks.py` | 定义 `RoundContext` 和 `RoundTask` 协议。 |
| `runner.py` | 管理 round 生命周期任务，执行 `before_round()` / `after_round()`。 |
| `scheduler.py` | 在传入 `--rounds` 时接管 pytest 执行循环，实现多轮执行和 round fixture 生命周期控制。 |

## 如何启用

项目根目录或测试目录的 `conftest.py` 加载：

```python
pytest_plugins = [
    "exfw.pytest_framework.plugin",
]
```

动态模型、回放模型等业务插件应在此基础上再加载自己的 pytest 插件。

---

## 命令行参数

`exfw.pytest_framework.plugin` 注册以下参数：

| 参数 | 说明 |
|---|---|
| `--project-config PATH` | 项目 YAML 路径；默认从 pytest 根目录向上查找 `project.yaml`。 |
| `--testbed NAME` | 选择配置文件中的测试床。 |
| `--device NAME` | 从测试床中选择指定设备；可重复传入。未指定时使用测试床全部设备。 |
| `--output-dir PATH` | 直接运行时的输出父目录，默认为 `outputs`，实际写入其 `debug` 子目录。 |
| `--rounds COUNT` | 按测试套执行的轮数；未指定时不启用 round 调度。 |

示例：

```bash
pytest test_models/dynamic_model/tests \
  --project-config project.yaml \
  --testbed lab_a \
  --rounds 3 \
  --output-dir artifacts
```

---

## 项目配置

默认从 pytest 根目录向上查找 `project.yaml`，也可通过 `--project-config` 指定；`runtime.resources_dir` 必须指向已存在的目录。相对路径以配置文件所在目录为基准。

示例：

```yaml
runtime:
  resources_dir: tests/dynamic/resources

testbeds:
  lab_a:
    devices:
      - name: main
        serial: ASPS015928000498
        model: BVL
        driver: adb
```

### 通用字段

| 字段 | 说明 |
|---|---|
| `runtime.resources_dir` | 已存在的资源目录。 |
| `testbeds.<name>.devices` | 测试床设备列表。 |
| `devices[].name` | 设备逻辑名称，例如 `main`。 |
| `devices[].serial` | 设备序列号。 |
| `devices[].model` | 设备型号。 |
| `devices[].driver` | 设备驱动类型，例如 `adb`。 |

### 业务模型扩展配置

`exfw.pytest_framework` 会完整保留原始项目配置到：

```python
run_config.project_config
```

业务插件可以读取自己的 namespace，例如：

```yaml
test_models:
  dynamic_model:
    steps:
      screenshot: true
      picture_dir: pictures
      filename_max_length: 80
```

注意：`exfw.pytest_framework` 不解析业务模型配置，只负责统一读取和传递。

---

## 通用 fixtures

### `run_config`

类型：

```python
RunConfig
```

包含本次运行配置：

```python
run_config.config_path
run_config.testbed_name
run_config.device_specs
run_config.output_dir
run_config.artifact_layout
run_config.project_config
```

用法：

```python
def test_config(run_config):
    assert run_config.output_dir is not None
```

---

### `testbed_name`

当前选择的测试床名称，未选择时为 `None`。

```python
def test_env(testbed_name):
    print(testbed_name)
```

---

### `output_dir`

本次执行产物输出根目录。

```python
def test_output(output_dir):
    print(output_dir)
```

---

### `device_specs`

只返回设备静态配置，不连接设备。

```python
def test_specs(device_specs):
    for spec in device_specs:
        print(spec.name, spec.serial, spec.driver)
```

适合只需要读取设备配置、不需要实际操作设备的用例或插件。

---

### `device_manager`

session 级设备管理器。

```python
def test_manager(device_manager):
    ...
```

一般业务用例不需要直接使用它，优先使用 `devices`。

---

### `devices`

连接当前 testbed 中选中的全部设备，返回：

```python
dict[str, Any]
```

示例：

```python
def test_device(devices):
    main = devices["main"]
    main.home()
```

注意：`devices` 是 session scope。只要用例请求该 fixture，就会连接设备。

---

### `current_round`

当前轮次编号。

未启用 `--rounds` 时默认为 `1`。

```python
def test_round(current_round):
    print(current_round)
```

---

### `case_artifacts`

当前用例产物路径。

类型：

```python
CaseArtifacts
```

字段：

```python
case_artifacts.root_dir
case_artifacts.run_dir
case_artifacts.case_dir
case_artifacts.round_no
case_artifacts.case_id
```

示例：

```python
def test_artifacts(case_artifacts):
    path = case_artifacts.case_dir / "custom.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("hello", encoding="utf-8")
```

---

### `test_logger`

当前用例专属 logger。

```python
def test_log(test_logger):
    test_logger.info("开始执行用例")
```

日志会继承 `exfw` logger 的 handler，写入框架日志文件。

---

日志与 Trace 的具体采集由各测试模型负责。动态模型通过自己的采集服务提供 `self.tracer`；通用 pytest 层不创建或管理采集器。

---

## 通用 Step 能力

### 用法

```python
from exfw.pytest_framework import Step


def test_demo():
    Step("启动应用")
    Step("点击登录", op_type="click", target="登录按钮")
```

`Step()` 支持任意额外字段：

```python
Step("滑动列表", op_type="swipe", direction="up")
```

这些字段会原样写入 step 记录。

### 记录内容

当前通用 Step 默认记录：

```json
{
  "index": 1,
  "description": "启动应用",
  "timestamp": 1780000000.123
}
```

加了 extra 后：

```json
{
  "index": 2,
  "description": "点击登录",
  "timestamp": 1780000001.456,
  "op_type": "click",
  "target": "登录按钮"
}
```

### 输出位置

`session_result.json` 中相应用例会包含：

```json
{
  "steps": [
    {
      "index": 1,
      "description": "启动应用",
      "timestamp": 1780000000.123
    }
  ]
}
```

此外也会写入 `user_properties.exfw_steps`，方便 pytest 报告或其他插件读取。

### 设计边界

通用 `Step()` 只记录通用信息，不做设备截图、不做业务上传、不做动态模型解析。

如果业务模型需要增强，可以在自己的基类中封装：

```python
from exfw.pytest_framework import Step

class DynamicCase(BaseTestCase):
    def step(self, description: str, **extra):
        # 业务增强，例如截图
        return Step(description, **extra)
```

---

## 通用 BaseTestCase

`BaseTestCase` 是可选基类，不会主动连接设备。

它注入以下通用上下文：

```python
self.run_config
self.testbed_name
self.output_dir
self.current_round
self.case_artifacts
self.test_logger
```

示例：

```python
from exfw.pytest_framework import BaseTestCase, Step


class TestDemo(BaseTestCase):
    def test_demo(self):
        self.test_logger.info("开始")
        Step("执行步骤")
        assert self.current_round >= 1
```

注意：`BaseTestCase` 不注入 `devices`，因为连接设备是有副作用的。需要设备的用例应显式声明 fixture：

```python
class TestDevice(BaseTestCase):
    def test_device(self, devices):
        main = devices["main"]
        main.home()
```

业务模型可以继承 `BaseTestCase` 并封装自己的能力，例如动态模型的截图 step、弹窗处理、键盘能力等。

---

## Session 和用例结果

每次 pytest session 在输出根目录写入 `session_result.json`。通用数据类位于 `result/models.py`，包括 session、轮次和用例结果；`result/store.py` 负责线程安全的合并与原子写入。业务模型通过各层的 `extensions` 命名空间补充数据，无设备测试同样可以使用。

```json
{
  "schema_version": 2,
  "summary": {"total": 1, "passed": 1},
  "rounds": [{
    "round": 1,
    "cases": [{
      "case_id": "TestDemo_test_demo",
      "nodeid": "tests/test_demo.py::TestDemo::test_demo",
      "case_name": "test_demo",
      "outcome": "passed",
      "steps": [],
      "artifacts": {"case_dir": "round_001/TestDemo_test_demo"},
      "extensions": {}
    }],
    "extensions": {}
  }],
  "extensions": {}
}
```

用例 teardown 后写入最终执行结果，setup 失败或跳过时也会记录。模型在结果产生前或之后写入扩展时，store 按轮次和 case id 合并，不会覆盖用例执行信息。

---

## 多轮执行能力

传入 `--rounds` 后，`RoundSchedulerPlugin` 会接管 pytest 默认执行循环。

示例：

```bash
pytest tests --rounds 3
```

执行顺序：

```text
Round 1:
  RoundTask.before_round()
  执行全部测试用例
  非 session fixture teardown
  RoundTask.after_round()

Round 2:
  RoundTask.before_round()
  执行全部测试用例
  非 session fixture teardown
  RoundTask.after_round()

所有 round 结束：
  session fixture teardown
```

### fixture 生命周期目标

普通用例结束：

```text
用例 call 结束
-> function fixture teardown
-> 必要时 class/module fixture teardown
-> 继续下一个用例
```

每轮结束：

```text
最后一个用例结束
-> function fixture teardown
-> 必要时 class/module fixture teardown
-> RoundTask.after_round()
```

全部轮次结束：

```text
最后一轮最后一个用例结束
-> function fixture teardown
-> 必要时 class/module fixture teardown
-> RoundTask.after_round()
-> session fixture teardown
-> device_manager.close()
```

### 技术说明

`scheduler.py` 使用 pytest 的内部 setup state：

```python
session._setupstate.teardown_exact(session)
session._setupstate.teardown_exact(None)
```

这是为了在自定义 `pytest_runtestloop` 中精确控制 fixture teardown 顺序：

- round 结束前清理非 session fixture；
- `RoundTask.after_round()` 执行时保留 session fixture；
- 所有 round 完成后再清理 session fixture。

修改这里时需要特别谨慎。

---

## RoundTask 扩展点

业务插件可以注册 round 生命周期任务。

实现协议：

```python
from exfw.pytest_framework.rounds.tasks import RoundContext


class MyRoundTask:
    @property
    def name(self) -> str:
        return "my_round_task"

    def before_round(self, context: RoundContext) -> None:
        ...

    def after_round(self, context: RoundContext) -> None:
        ...
```

注册：

```python
from exfw.pytest_framework.rounds.runner import get_or_create_round_task_runner


def pytest_configure(config):
    runner = get_or_create_round_task_runner(config)
    runner.add_task(MyRoundTask())
```

`RoundContext` 当前包含：

```python
context.run_config
context.round_no
context.rounds
```

不要让业务 task 直接依赖 pytest stash key；优先通过 `RoundContext` 获取需要的通用信息。

---

## 产物目录规则

```text
artifacts/
  session_result.json
  round_001/                     # 使用 --rounds 时
    TestClass_test_method/       # 截图、日志等原始产物
```

未启用 `--rounds` 时，用例目录直接位于 `artifacts/` 下。

### case id 规则

如果 pytest nodeid 中包含测试类：

```text
TestClass::test_method -> TestClass_test_method
```

如果没有测试类：

```text
test_method -> test_method
```

文件名会经过安全化处理，避免非法路径字符。

---

## 边界约定

### exfw.pytest_framework 应该包含

- pytest 插件入口；
- 通用命令行参数；
- 通用配置读取；
- 通用运行上下文；
- 通用 fixtures；
- 通用 result 输出；
- 通用 Step 记录；
- 通用多轮执行调度；
- 业务插件可复用的 round task 扩展点；
- 通用设备连接 fixture。

### exfw.pytest_framework 不应该包含

- 动态模型专属解析逻辑；
- 动态模型上传协议；
- 动态模型服务器接口；
- 动态模型截图策略；
- 回放模型专属恢复策略；
- 具体业务 case 的判断逻辑。

业务模型需要扩展时，推荐模式是：

```text
exfw.pytest_framework 负责通用上下文和机制
业务模型插件读取 run_config.project_config 中自己的 namespace
业务模型基类封装自己的用例写法
业务模型 reporter/parser/uploader 处理自己的结果协议
```

---

## AI 修改注意事项

后续使用 AI 修改本目录时，请遵循以下规则：

1. **不要把业务模型逻辑写进 `exfw.pytest_framework`**  
   动态模型、回放模型等业务逻辑应放在各自目录中。

2. **不要让通用 fixture 默认连接设备**  
   `devices` 是显式使用才连接设备。`BaseTestCase` 不应自动注入设备对象。

3. **不要随意改 `scheduler.py` 的 fixture teardown 逻辑**  
   多轮执行依赖 `nextitem=session` 和 `session._setupstate.teardown_exact(...)` 控制生命周期。

4. **RoundTask 使用 `RoundContext` 作为边界**  
   业务 task 不应直接读取 pytest stash key。

5. **业务配置放在自己的 namespace**  
   例如 `test_models.dynamic_model`。`exfw.pytest_framework` 只读取和保留完整配置，不解析业务字段。

6. **通用 Step 保持轻量**  
   通用 `Step()` 只记录描述、时间和 extra 字段。截图、上传、业务统计应由业务模型封装。

7. **产物路径统一通过 `case_artifacts` 构造**  
   不要在业务代码中手写和 pytest nodeid 强绑定的目录规则。

8. **修改 result 结构时同步更新本文档**  
   `session_result.json` 是业务模型和报告工具的重要接口。

9. **新增 fixture 时放到 `fixtures/` 并在 `plugin.py` 的 `pytest_plugins` 中注册**。

10. **新增通用能力前先确认是否真的通用**  
    如果只服务某个测试模型，应放到该模型自己的 pytest 插件中。

## 日志输出

`execution.log` 记录框架与用例日志，包含可用的用例 nodeid 和轮次。普通 pytest 运行还会将 pytest 终端报告写入输出目录的 `pytest-output.log`；该文件不保证包含 `-s` 时直接写到 stdout/stderr 的内容。直接执行 pytest 时默认保留 pytest 原生输出；需要在终端显示框架日志可添加 `--exfw-console-log`。通过 dynamic runner 运行时，子进程的完整 stdout/stderr 会保存到同名文件，交互式终端显示设备进度，结束后按设备汇总失败用例；非交互终端逐行显示。每次运行会覆盖这些日志，需保留历史时请使用独立输出目录。
