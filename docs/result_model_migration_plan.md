# 测试结果聚合迁移计划

目标：通用 pytest 输出包含模型扩展的 `session_result.json`；动态模型输出设备级 `parsed_results.json`；runner 输出 `task_result.json`，保留 `main_device_info.json`。原始日志、Trace、截图留在用例/轮次目录。结果代码不再写用例级 result、processing_status、trace_records 或 analysis_result 文件。

- [x] 通用结果数据类与线程安全结果 store；case/round/session 扩展、原子写入、失败和多轮。
- [x] 动态结果数据类、共享解析结果 store；采集/解析/上传以 `round + case_id` 更新模型扩展，整轮日志单独记录。
- [x] AW Trace 记录按用例快照和确认清理；动态层持久化后再确认，保留本地相对路径与时间来源。
- [x] 迁移 runner、报告本地/服务端数据、BD 归档、重解析和 Trace 时间修正工具；不添加旧文件转发代码。
- [x] 更新文档；自动化测试覆盖无设备、多轮、并发、先扩展后 pytest 结果、失败写入、离线结果、报告和 Trace 归档。
- [ ] 在真实设备和部署内网验证采集、报告和上传；对 Trace 时间修正及重解析工具补充端到端验证。

约束：一次 pytest session 对应一个 testbed，不以设备作为通用层强制概念；直接 pytest 只生成 session 文件。服务端 case/task 旧协议保持不变，安全补传仍需确认服务端幂等协议。真实设备和内网验证需在对应环境进行。保留已有未提交的架构与用例 profile 改动。
