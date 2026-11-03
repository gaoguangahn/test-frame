class TraceAppClickSheet:
    """专门处理报表生成的类"""

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, sheets_data):
        """生成全部应用内点击相关报表。"""

        self.create_detail_sheet(
            sheets_data.get("detail", []), sheets_data.get("state_columns", [])
        )
        self.create_summary_sheet(sheets_data.get("summary", []))

    def create_detail_sheet(self, input_data, state_columns):
        """trace应用内响应详情页"""
        titles = {
            "5.trace应用内点击响应详情页": [
                "SN",
                "Loop",
                "Case",
                "Trace",
                "Scene",
                "Package",
                "Activity",
                "Type",
                "dur",
            ]
            + state_columns
        }
        self.excel.add_sheet(titles, input_data)
        print("5.trace应用内点击响应详情页 已生成")

    def create_summary_sheet(self, input_data):
        """trace应用内响应数据汇总页"""
        titles = {
            "6.trace应用内点击汇总页": [
                "Case",
                "Package",
                "Activity",
                "statistics",
                "dur",
                "running_dur_ns",
                "runnable_dur_ns",
                "uninterruptible_sleep_dur_ns",
                "interruptible_sleep_dur_ns",
                "uninterruptible_io_sleep_dur_ns",
                "uninterruptible_non_io_sleep_dur_ns",
            ]
        }
        self.excel.add_sheet(titles, input_data, merge_cols=[1, 2, 3, 4])
        print("6.trace应用内点击汇总页 已生成")
