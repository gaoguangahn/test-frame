# dynamic tools 使用说明

本目录用于放置 dynamic 模型相关的离线维护工具。目前主要包含：

- `reparse_case_results.py`：历史测试结果重解析工具。

## reparse_case_results.py

### 用途

当已经有一套旧的 dynamic 测试结果目录，但后续更新了解析包、解析策略或 dispatcher 配置时，可以使用该工具对旧的 `logs` / `traces` 重新解析，并可选回写服务端数据库中的 `case_result` 记录。

它不会重新执行测试用例，只会基于历史产物重新生成：

- `log_result`
- `trace_result`

### 数据来源

工具输入的是 dynamic runner 输出目录，例如：

```text
outputs/dynamic2
```

目录中需要存在：

```text
task_result.json
<serial-or-task-dir>/session_result.json
<case artifact_dir>/logs
<case artifact_dir>/traces
```

工具会复用项目已有的数据发现逻辑读取：

- `task_result.json`
- `session_result.json`
- 每个 case 的 `artifact_dir`
- 每个 case 的 `logs` 和 `traces` 目录

### 使用的解析逻辑

工具会复用当前代码中的解析器：

```python
LogParserDispatcher
TraceParserDispatcher
```

因此它使用的是你当前工作区安装/引用的最新解析包和最新 dispatcher 配置。

如果 dispatcher 里已经注释掉某些指标，那么重解析后的结果也不会再包含那些指标。

---

## 常用命令

### 1. 查看帮助

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results --help
```

### 2. 只做本地重解析，不访问服务端

这是默认安全模式，不会更新数据库。

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --mode all
```

默认会在 runner 输出目录下生成备份目录：

```text
outputs/dynamic2/reparse_outputs/<timestamp>/
```

其中包含：

```text
summary.json
<case>/after_payload.json
```

### 3. 只重解析 trace

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --mode trace
```

### 4. 只重解析 log

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --mode log
```

### 5. 只处理某个设备、某轮、某个 case

建议正式上传前先这样小范围验证。

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --serial ASPS015928000498 `
  --round 1 `
  --case test_camera `
  --mode all
```

### 6. 检查服务端是否能唯一匹配记录，但不上传

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --serial ASPS015928000498 `
  --round 1 `
  --case test_camera `
  --mode all `
  --check-server
```

工具会通过以下接口查询服务端：

```http
GET /api/v1/case-results?task_id=xxx&serial=xxx&round=1&case=test_camera
```

只有匹配到唯一一条记录时，后续上传才会允许更新。

### 7. 重解析并回写服务端

确认本地结果和服务端匹配都没问题后，再使用 `--upload`。

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --serial ASPS015928000498 `
  --round 1 `
  --case test_camera `
  --mode all `
  --upload
```

上传流程：

```text
1. 本地重新解析 logs/traces
2. GET /api/v1/case-results 查询服务端记录
3. 如果唯一匹配：
   3.1 GET /api/v1/case-results/{id} 备份旧记录
   3.2 PUT /api/v1/case-results/{id} 更新 log_result / trace_result
4. 如果 0 条或多条匹配：跳过，不更新
```

---

## 参数说明

| 参数 | 说明 |
|---|---|
| `--runner-output-dir` | dynamic runner 输出目录，必填 |
| `--mode` | 重解析范围：`all` / `trace` / `log`，默认 `all` |
| `--serial` | 只处理指定设备，可传多次 |
| `--round` | 只处理指定轮次 |
| `--case` | 只处理指定 case，可传多次 |
| `--brand` | 设备品牌，默认 `Honor` |
| `--parse-workers` | 解析线程数，默认 `8` |
| `--case-results-url` | 服务端 case-results 接口地址，默认使用 `CASE_RESULT_SERVER.upload_url` |
| `--timeout` | HTTP 超时时间，默认 `30` 秒 |
| `--check-server` | 查询服务端匹配情况，但不更新 |
| `--upload` | 回写服务端数据库 |
| `--backup-dir` | 指定备份目录 |
| `--no-backup` | 不保存本地备份，不推荐上传时使用 |
| `--summary-file` | 指定 summary JSON 输出路径 |
| `--log-level` | 日志级别，默认 `INFO` |

---

## 输出文件说明

默认输出目录：

```text
<runner-output-dir>/reparse_outputs/<timestamp>/
```

典型结构：

```text
reparse_outputs/<timestamp>/
  summary.json
  ASPS015928000498_round_1_test_camera/
    after_payload.json
    before_123.json
    updated_123.json
```

文件含义：

| 文件 | 说明 |
|---|---|
| `summary.json` | 本次重解析总览，包含每个 case 的状态、匹配数量、更新结果等 |
| `after_payload.json` | 本次准备写入服务端的新 `log_result` / `trace_result` |
| `before_<id>.json` | 上传前从服务端读取的旧记录备份，仅 `--upload` 时生成 |
| `updated_<id>.json` | 上传后服务端返回的新记录，仅 `--upload` 时生成 |

---

## 安全策略

工具默认尽量保守：

1. 不传 `--upload` 时不会更新服务端。
2. 服务端匹配结果不是唯一一条时不会更新。
3. 上传前会先备份服务端旧记录。
4. 默认只更新 `log_result` 和/或 `trace_result`。
5. 不会重新执行测试用例。

---

## 推荐使用流程

### 第一步：本地小范围重解析

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --round 1 `
  --case test_camera `
  --mode all
```

### 第二步：检查服务端匹配

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --round 1 `
  --case test_camera `
  --mode all `
  --check-server
```

### 第三步：小范围上传验证

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --round 1 `
  --case test_camera `
  --mode all `
  --upload
```

### 第四步：批量上传

```powershell
.\.venv\Scripts\python.exe -m exfw.models.dynamic.tools.reparse_case_results `
  --runner-output-dir outputs\dynamic2 `
  --mode all `
  --upload
```

---

## 注意事项

1. `--upload` 依赖服务端 `PUT /api/v1/case-results/{id}` 支持部分更新。
2. 如果服务端 `CaseResultUpdate` 会把未传字段置空，需要先调整服务端或改工具为“读取旧记录后合并完整对象再 PUT”。
3. 如果旧数据路径移动过，工具会复用现有 runner/report 数据加载逻辑做路径解析。
4. 如果历史数据中的 trace/log 文件缺失，对应 case 会记录错误并跳过缺失部分。
5. CameraPhoto 的特殊归类逻辑在报告数据路由层处理，重解析工具不需要额外处理。
