from openpyxl.styles import Alignment


class LogAutoStartCleanSheet:
    """专门处理报表生成的类"""

    def __init__(self, excel_handler):
        self.excel = excel_handler
        self.summary_data = {}  # 存放跨报表的汇总数据

    def generate_all(self, sheets_data):
        """生成全部自启清理相关报表。"""

        self.create_start_cleanup_sheet(sheets_data.get("start_cleanup", {}))

    def create_start_cleanup_sheet(self, data):
        """自启动清理汇总数据表格"""

        # 辅助函数：添加一行数据并居中对齐
        def _append_and_align_row(ws_obj, row_data, align_center=False):
            ws_obj.append(row_data)
            if align_center:
                for cell in ws_obj[ws_obj.max_row]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")

        # 辅助函数：将列表转换为逗号分隔的字符串，如果为空则返回空字符串
        def _join_list_or_empty(data_list):
            return ", ".join(data_list) if data_list else ""

        def custom_layout(ws, data):
            # ================= 1. 自启基础统计 =================
            total_start_num = data.get("total_start_num", 0)
            single_start_num = data.get("single_start_num", 0)
            single_percent = data.get("single_percent", "0%")
            multi_start_num = data.get("multi_start_num", 0)
            multi_percent = data.get("multi_percent", "0%")

            _append_and_align_row(
                ws,
                [
                    "自启总次数",
                    "单次启动次数",
                    "单次启动占比",
                    "多次启动次数",
                    "多次启动占比",
                ],
            )
            _append_and_align_row(
                ws,
                [
                    total_start_num,
                    single_start_num,
                    single_percent,
                    multi_start_num,
                    multi_percent,
                ],
                align_center=True,
            )
            ws.append([])  # 添加空行分隔

            # ================= 2. 冷热启统计 =================
            total_iAware_num = data.get("total_iAware_num", 0)
            cold_start_num = data.get("cold_start_num", 0)
            warm_start_num = data.get("warm_start_num", 0)
            _append_and_align_row(ws, ["iAware拦截总次数", "冷启次数", "热启次数"])
            _append_and_align_row(
                ws,
                [total_iAware_num, cold_start_num, warm_start_num],
                align_center=True,
            )
            ws.append([])

            # ================= 3. 自启原因详情 =================
            start_reasons = data.get("start_reasons", [])
            _append_and_align_row(
                ws, ["被拉起进程名", "自启次数", "自启原因", "拉起方式", "拉起方"]
            )
            for start_item in start_reasons:
                process_name = start_item.get("process_name", "")
                start_times = start_item.get("start_times", 0)
                reason = _join_list_or_empty(start_item.get("reason", []))
                req = _join_list_or_empty(start_item.get("req", []))
                caller = _join_list_or_empty(start_item.get("caller", []))
                _append_and_align_row(
                    ws, [process_name, start_times, reason, req, caller]
                )
            ws.append([])

            # ================= 4. 高频自启片段 (替代原先的全部启动时间) =================
            start_hf_segments = data.get("start_high_freq_segments", [])
            if start_hf_segments:
                _append_and_align_row(ws, ["进程名", "高频自启时间段"])
                for hf_segment in start_hf_segments:
                    process_name = hf_segment.get("process_name", "")
                    records = hf_segment.get("segments", [])
                    merged_records = [ts for record in records for ts in record]
                    for record in merged_records:
                        _append_and_align_row(ws, [process_name, record])
                ws.append([])

            # ================= 5. 清理基础统计 =================
            total_kill_num = data.get("total_kill_num", 0)
            total_kill_num_repeat = data.get("total_kill_num_repeat", 0)
            repeat_kill_percent = data.get("repeat_kill_percent", "0%")
            _append_and_align_row(ws, ["清理总次数", "多次被杀", "多次被杀占比"])
            _append_and_align_row(
                ws,
                [total_kill_num, total_kill_num_repeat, repeat_kill_percent],
                align_center=True,
            )
            ws.append([])

            # ================= 6. 清理原因分布 =================
            kill_reason_stats = data.get("kill_reason_stats", {})
            _append_and_align_row(ws, ["清理原因", "清理次数", "比例"])
            for reason, reason_item in kill_reason_stats.items():
                _append_and_align_row(
                    ws,
                    [
                        reason,
                        reason_item.get("count", 0),
                        reason_item.get("percent", "0%"),
                    ],
                    align_center=True,
                )
            ws.append([])

            # ================= 7. 进程清理详情 =================
            kill_process_reasons = data.get("kill_process_reasons", [])
            _append_and_align_row(ws, ["进程名", "清理次数", "清理原因"])
            for kill_process_item in kill_process_reasons:
                process_name = kill_process_item.get("process_name", "")
                kill_times = kill_process_item.get("kill_times", 0)
                # 注意：新字典里键名是 "reasons"
                reason = _join_list_or_empty(kill_process_item.get("reasons", []))
                _append_and_align_row(ws, [process_name, kill_times, reason])
            ws.append([])

            # ================= 8. 高频被杀片段 =================
            kill_hf_segments = data.get("high_freq_kill_segments", [])
            if kill_hf_segments:
                _append_and_align_row(ws, ["进程名", "高频被清理时间段"])
                for hf_segment in kill_hf_segments:
                    process_name = hf_segment.get("process_name", "")
                    records = hf_segment.get("segments", [])
                    merged_records = [ts for record in records for ts in record]
                    for record in merged_records:
                        _append_and_align_row(ws, [process_name, record])

        # 生成表格
        self.excel.custom_add_sheet("15.自启清理汇总", custom_layout, data)
        print("15.自启清理汇总页 已生成")
