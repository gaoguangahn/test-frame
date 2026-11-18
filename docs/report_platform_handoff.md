# 动态模型报告平台交接

更新日期：2026-11-16。供独立网站工程的新聊天接续需求使用。

## 1. 项目与状态

现有框架仓库位于 `D:\dev\projects\test_framework-agent`，基于 pytest，对 Android 手机执行动态性能测试，采集日志和 Trace，本地解析、可选上传，再生成性能 Excel。

准备创建独立的报告展示网站。建议在一个新仓库内用 `frontend/` 和 `backend/` 分开维护。前后端技术栈、数据库引擎、部署方式尚未确定；本文件没有指定框架选型。

现有服务端源码和数据库 DDL 尚未在本工程中审查。后文的六表设计是已讨论确认的目标，不能当成现有数据库结构。已有服务需要先检查源码、表结构和样例响应，再确定迁移方案。

## 2. 已确认的使用体验

- 网站左侧树为“产品 → 型号 → 系统版本”。例如 `BVL → BVL-AN00 → 某个完整系统版本`。产品和型号的实际含义、命名映射仍需用户确认。
- 选中版本后，右侧显示该版本下的多次测试批次，进入批次后查看其设备和指标。
- 可选择应用包名，再按 Activity、启动类型、轮次、设备等条件筛选，集中查看明细及统计值。
- 希望支持少量选定任务或不同版本之间的对比、Excel 导出。
- 希望以后能排除错误数据、修正解析字段，再生成和归档报告。人工修正及归档流程尚未实现。
- 每次测试规模相对固定，通常为几台手机和固定轮数。优先优化目录查询及单次任务加载，不需要一开始为全历史指标检索设计数据仓库。

## 3. 批次与设备任务

```text
一次 runner 测试
run_id：整批测试 ID（待实现）
name：用户确认的任务名称（待实现）
├── 手机 A：task_id_A（当前服务端已有此级别 ID）
│   └── 各轮用例与解析结果
└── 手机 B：task_id_B
    └── 各轮用例与解析结果
```

任务名称属于批次。允许同名，唯一性由 ID 保证。系统版本应单独保存，用户在名称中加“重测”“小包验证”等标识不会改变版本归属。

期望 runner 先连接设备读取型号和版本，给出建议名称，用户回车接受或修改。现有 runner 还没有实现这一确认过程，也没有向服务端登记批次和设备版本关系。

设备中的准确版本字段、产品映射、小包标识需要在真实设备上确认。每台设备保存自己的环境快照，混合型号或版本的任务应按实际设备归属筛选。

## 4. 数据库目标：六张核心表

| 表 | 主要职责与建议字段 |
|---|---|
| `products` | `id`、稳定产品标识、展示名称 |
| `device_models` | `id`、`product_id`、型号编码、展示名称 |
| `software_versions` | `id`、`model_id`、系统版本编码、展示名称 |
| `test_runs` | `run_id`、任务名称、备注、批次状态、开始结束时间、扩展元数据 |
| `device_tasks` | `task_id`、`run_id`、`version_id`、设备 SN、设备任务状态、开始结束时间、环境 JSON |
| `case_results` | 记录主键、`task_id`、轮次、用例身份、记录范围、`log_result` JSON、`trace_result` JSON、可选操作统计及数据版本 |

各表需要服务端创建和更新时间。执行时间与入库时间分别保存。

六表是目标核心结构，不是已完成的 DDL。字段长度、外键、唯一约束和索引需按实际数据库及旧数据明确。产品下型号、型号下版本应有合理的去重约束。

`log_result`、`trace_result` 分别存 JSON。新增性能指标扩展 JSON，避免每个指标新增数据库列。实际服务端是否已经采用两个 JSON 列仍需查表确认。

暂不增加 `metric_samples`。从选定任务读取 JSON 后再展开明细。以后确有大范围历史查询需求并测出瓶颈，再评估指标明细表。

索引优先覆盖目录父子关系、设备任务的 `version_id` 和 `run_id`、结果的 `task_id` 及 `task_id + 轮次 + id` 查询路径。任务列表分页，结果沿用游标分页，目录接口不读取性能 JSON。

需补稳定的结果上传标识及数据库唯一约束。同一条结果上传重试不能新增重复样本。当前客户端会重试，服务端现有去重能力未知。

## 5. 网站数据处理与缓存

```text
目录导航 → 分页加载批次基本信息 → 选择某次测试
    → 获取选定设备任务的结果 → 展开成适合展示的明细集合
    → 在浏览器内筛选应用、Activity、启动类型、轮次和设备
```

服务端可以复用现有 Python 数据转换与统计逻辑，向网页返回整理后的数据。页面内存用于当前查询，IndexedDB 可缓存已查看任务。具体哪些统计在前端执行，需结合复用现有 Python 逻辑和实际数据量确定。

缓存需要 `run_id/task_id`、服务端 `data_revision` 和展示数据结构版本。重新解析、补传、人工修正后需递增数据版本并刷新缓存。浏览器缓存失效时可从服务端重建。

不要把所有版本的全部结果一次下载。版本对比先限定任务集合，对齐应用版本、Activity、启动类型、指标单位及筛选范围。统计应基于有效样本，不能直接平均各组均值或各组分位数。

## 6. 人工修正和归档的后续约束

- 支持排除记录和修正字段，保存原因及操作人，保留原始解析结果以便追溯或撤销。
- 保存人工修改后更新数据修订版本，后续旧的上传重试不应覆盖已审核数据。
- 归档报告固定筛选条件、采用的数据修订和报告文件，重建时使用相同数据。
- 六张表之外的修订审计和报告归档表，等实现这部分功能时再设计。
- 数据库中的本地 Trace、截图路径不能直接变成网站下载地址。若要网页查看产物，需要另行设计产物上传与访问。

## 7. 现有服务接口与客户端行为

以下为框架源码可确认的契约。基础 URL 见 `src/exfw/models/dynamic/server_config.py`，不要直接假设新服务地址或认证方式。

| 接口 | 当前客户端约定 |
|---|---|
| `POST /api/v1/case-results/task-id` | 返回 `{"code":200,"data":{"task_id":"..."}}`，代表单设备 pytest 子任务 |
| `POST /api/v1/case-results` | 上传一条用例或整轮日志解析结果，超时 10 秒，失败最多重试 2 次 |
| `GET /api/v1/case-results` | 支持 `task_id`、`serial`、`round`、`case`、`limit`、`last_id`，报告客户端预期直接返回对象数组 |
| `GET /api/v1/case-results/{id}` | 查询单条结果 |
| `PUT /api/v1/case-results/{id}` | 重解析工具更新结果，可只提交 `log_result` 或 `trace_result` |

列表分页依赖整数 `id`，每页取最后一条的 ID 继续查询。空页或数量少于 limit 时停止，客户端将 limit 限制在 1～1000。服务端应保证确定的排序和游标语义。

当前 POST payload 的顶层形状如下，列表内具体结构需结合解析器和真实响应确认。

```json
{
  "task_id": "设备子任务 ID",
  "serial": "设备 SN",
  "round": 1,
  "case": "test_leftmost",
  "step": "__case__",
  "action_stats": {},
  "log_result": [],
  "trace_result": []
}
```

`action_stats` 是可选字段。整轮日志使用 `case="__round_logs__"`、`step="__round__"`。

本地已有 `case_id`、`nodeid`，当前上传明确排除了它们。未来接入时应增加稳定用例身份，不能仅依靠方法名。当前上传也没有 `run_id`、产品型号版本、完整用例执行状态及错误堆栈。

当前上传成功默认按 HTTP 状态判断，没有专用业务响应校验；服务端落库确认和重试幂等需统一设计。报告当前按设备 `task_id` 查询，源码注明绕过了旧服务的 serial 过滤问题，接入真实服务时需要核对。

## 8. 框架现有本地产物和运行约定

- `task_result.json`：runner 增量任务清单，现阶段没有批次 `run_id`。
- 每设备 `session_result.json`：轮次、用例、步骤、执行结果和 `extensions.dynamic_model` 中的采集／解析／上传状态及产物信息。
- 每设备 `parsed_results.json`：本地解析明细，字段使用 `log_results`、`trace_results`；服务端 payload 则使用单数 `log_result`、`trace_result`。
- `execution_report.html`：动态模型本地执行情况快照，与性能 Excel 分开。
- JSON 采用原子写入，异常中断后允许仅有部分结果。
- 独立 pytest 调试默认普通执行流程，只有传 `--rounds` 才启用轮次级采集；默认不上传。
- runner 按 `project.yaml` 的上传配置执行。仅正式测试上传的原则已确认，不应默认把个人调试数据纳入平台。
- CLI 项目配置参数统一为 `--project-config`。调试 `--output-dir` 表示父目录，实际写入固定的 `debug` 子目录，不自动清理。
- runner 每次创建 `测试名_年月日_时分秒` 目录。现有配置名称 `test_name` 与未来服务端任务展示名的衔接仍待实现。
- `local_run_id` 当前由每个设备的结果处理器生成，不能直接当成未来整次 runner 的批次 ID。

## 9. 可复用的框架源码

路径均相对框架仓库根目录。新工作区需要访问这些代码时，可添加框架目录作为只读参考或复制必要样例。

| 文件或目录 | 参考用途 |
|---|---|
| `src/exfw/models/dynamic/upload/service.py` | task_id 申请和上传协议 |
| `src/exfw/models/dynamic/result/processor.py` | 上传 payload、本地解析与处理状态 |
| `src/exfw/models/dynamic/report/data/data_fetcher.py` | 服务端查询和分页 |
| `src/exfw/models/dynamic/report/data/data_transformer.py` | 展开结果、按 metric 分发和上下文关联 |
| `src/exfw/models/dynamic/report/data/report_dataset.py` | 组装性能报告数据 |
| `src/exfw/models/dynamic/report/sheets/trace/data_analyse/` | 启动、点击等指标统计 |
| `src/exfw/models/dynamic/report/sheets/log/data_analyse/` | Log、雷达卡顿等数据处理 |
| `src/exfw/models/dynamic/report/utils/excel_generator.py` | Excel 导出 |
| `src/exfw/models/dynamic/tools/reparse_case_results.py` | 历史解析结果更新接口 |
| `src/exfw/models/dynamic/result/execution_html/` | 本地执行结果 HTML，可作为数据展示参考 |

启动指标已有两个 Activity 汇总。第 3 页按 Package + Activity，3.1 页进一步分 all/cold/warm/hot，只展示有有效数据的类型；all 包含未知启动类型。每组统计 Count、Avg、样本标准差、Min、Max、25%、50%、75%。目前所选设备和轮次会合并统计。

启动和点击的线程状态详情、汇总共用固定列序。注意旧字段名带 `_ns`，现有报告处理中已经将线程状态值从纳秒转换为毫秒。网页实现必须确认输入单位，避免重复换算。统计单样本标准差为 0，缺失值不能按 0 参与计算。

## 10. 新工程建议执行顺序

1. 取得现有服务端源码、数据库类型、DDL 和脱敏样例，先验证本文件第 7 节的契约。
2. 确认六表的实际字段、旧数据迁移方式，以及型号和系统版本的采集字段。
3. 实现目录、批次列表、单任务查询接口，用样例完成“启动指标”的整条展示链路。
4. 增加浏览器缓存版本校验、筛选统计与导出，再扩展点击及其他指标。
5. 接入框架批次登记和设备元数据上传，然后实现版本对比、人工修正与归档。

首版优先打通可验证的数据链路，技术栈、数据库引擎和具体接口变更应以现有服务及用户部署要求为准。

## 11. 新聊天开场提示

将本文件复制到新网站工程的 `docs/report_platform_handoff.md`，新聊天可以使用以下提示：

> 请先阅读 docs/report_platform_handoff.md。这是一个 Android 性能测试结果展示平台，框架仓库位于 D:\dev\projects\test_framework-agent。已确认采用六张核心表，Log 和 Trace 结果分别存 JSON，按选定测试任务加载并缓存整理后的数据。请区分文档中的现有接口与未来方案，先检查当前工作区和已有后端资料，列出首版启动指标展示需要的最小实现及待确认项。技术栈和数据库引擎尚未确定。
