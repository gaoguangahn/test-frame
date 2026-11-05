# 动态模型采集模块

本模块负责动态模型运行中的日志和 Trace 采集：定义采集项、决定采集时机、调用 AW、记录采集状态。解析和上传由 `dynamic.analyse`、`dynamic.upload` 及结果编排模块负责。通用 pytest 层只提供生命周期、设备配置和产物路径，不管理动态模型采集器。

## 模块组成

| 文件 | 职责 |
|---|---|
| `profile.yaml` / `profile.py` | 模块内部采集项及执行顺序；加载时校验阶段、名称、重复项与依赖。 |
| `registry.py` | 注册动态模型具体采集器；每次创建服务时构造一组独立实例。 |
| `collectors/continuous_collector.py` | `jank_log`、`events_log`、`adb_log`、`dmesg_log` 等持续采集。 |
| `collectors/instant_collector.py` | `radar`、`io_stat`、`proc_memory` 等快照或设备文件采集。 |
| `service.py` | 按轮次和用例编排采集，管理共享 TraceCollector，记录采集状态。 |
| `trace.py` | 动态模型操作级 `tracer`，为 Trace 名附加用例名和轮次。 |
| `time_sync.py` | 采样设备与 PC 时间偏移，转换 Trace 记录中的时间。 |

AW 的 `exfw.aw.logcat` 提供 `ContinuousCollector`、`InstantCollector`、`CmdRunner` 等基础能力；`exfw.aw.trace.TraceCollector` 提供设备上的 Trace 启动、停止、拉取和清理。具体日志的命令和采集策略属于本模块。

## 执行时机

动态 pytest 插件创建本次运行的 `DynamicModelCaptureService`；轮次通过 `dynamic_pytest/round/round_capture.py` 接入，用例通过 `dynamic_pytest/fixtures/capture.py` 接入。

```text
round_start     按配置顺序启动持续采集
  case_start    清理设备端旧 Trace；采集前置快照、重置 radar
    用例操作    需要时通过 self.tracer 包围操作采集 Trace
  case_end      采集后置快照；拉取 Trace 并将元数据写入 session 结果
round_end       采集轮次结束快照；按启动的逆序停止持续采集
                后台解析本地结果，并按配置决定是否上传
```

**当前只有显式传入 `--rounds` 才执行轮次级任务。** 不传时用例级采集仍会执行，但不会自动采集整轮持续日志。动态模型用例使用 testbed 中名为 `main` 的设备。

## 采集配置

默认配置见同目录 `profile.yaml`：

| 阶段 | 默认采集项 |
|---|---|
| `round_start` | `jank_log`、`events_log`、`adb_log`、`dmesg_log` |
| `round_end` | `dumpsys_meminfo` |
| `case_start` | `io_stat`、`proc_memory`、`radar`（reset） |
| `case_end` | `io_measure`、`io_stat`、`radar`、`proc_memory` |

四个字段均须存在，允许将某个列表设为空。可配置项受 `profile.py` 的 `_ALLOWED` 限制，不能重复；`jank_log` 会清空 logcat，启用时必须放在 `round_start` 首位；`radar` 必须同时出现在 `case_start` 和 `case_end`。Trace 采集由用例中的 `self.tracer` 显式包围操作，不由这四个列表启停。

注册表还包含 `broadcasts_history`、`soft_resource` 等采集器，但目前未在 `_ALLOWED` 的阶段列表中开放，仅修改 YAML 不会启用它们。配置变更应考虑报告和解析对产物的依赖。

## Trace 用法与产物

动态模型用例使用 `self.tracer`：

```python
from exfw.aw.device import Direction

self.step("向上滑动")
with self.tracer.collect(self.device.serial, name="AppSwipe1", description="向上滑动"):
    self.device.swipe(direction=Direction.UP, times=1)
```

命名采用 `AppLaunch1`、`AppExit1`、`AppSwipe1`、`AppClick1` 等，同类操作递增；`tracer` 自动加上 `<用例名>_loop<轮次>_` 前缀。当前约定只对启动/退出应用、滑动及明确导致 Activity 切换的点击采集 Trace，普通点击和输入等操作不需要采集。

每个动态模型采集服务持有一个 AW `TraceCollector`，操作级 tracer、用例结束时的拉取和记录使用同一实例。AW TraceCollector 不再是全局单例；如果多个实例同时操作同一设备，调用方需避免并发采集。

典型产物：

```text
<设备子任务>/
├── session_result.json          # 用例、采集产物及处理状态
├── parsed_results.json          # 各轮和用例的本地解析结果
└── round_001/
    ├── logs/                    # 整轮日志
    └── <用例目录>/
        ├── logs/                # 用例快照日志
        └── traces/
            └── <用例>_loop1_AppSwipe1.pftrace
```

未启用多轮时没有 `round_001` 层。Trace 元数据和用例日志清单位于 session 对应用例的 `extensions.dynamic_model`；关闭上传仍会进行本地解析。部分采集器只返回 `None` 并写日志，详细错误可查看 `execution.log`。

## 扩展采集项

1. 在 `collectors/` 实现采集器：持续采集继承 AW `ContinuousCollector`，单次采集继承 `InstantCollector`，并设置唯一的 `name`。保持设备命令、产物命名和错误记录在动态模型内。
2. 在 `registry.py` 的 `_COLLECTOR_TYPES` 注册类；在 `profile.py` 的对应 `_ALLOWED` 阶段添加名称，并在 `profile.yaml` 选择是否默认启用。
3. 确认 `service.py` 的阶段调用与采集器接口匹配。特殊生命周期需要显式编排：例如 `radar` 的用例开始是 `reset()`、结束才是 `collect()`，不能只加配置名称。
4. 检查启动顺序、资源冲突、失败清理和产物命名；如需解析，在 `dynamic/analyse/profile.yaml` 配置对应映射，并核对报告是否依赖该结果。
5. 添加不依赖设备的测试，覆盖阶段顺序、失败和清理；再在目标设备上验证真实命令、权限及产物。

现有状态记录和失败恢复仍有待完善，具体进度见项目 `docs/dynamic_pipeline_refactor_plan.md`。
