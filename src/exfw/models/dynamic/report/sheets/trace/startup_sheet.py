class TraceStartupSheet:
    """专门处理报表生成的类"""

    def __init__(self, excel_handler):
        self.excel = excel_handler
        self.summary_data = {}  # 存放跨报表的汇总数据

    def generate_all(self, sheets_data):
        """生成全部启动相关报表"""
        if not sheets_data.get("detail"):
            print("没有启动数据，跳过报表生成")
            return

        self.create_detail_sheet(
            sheets_data.get("detail", []), sheets_data.get("state_columns", [])
        )
        self.create_response_summary(sheets_data.get("response_summary", []))
        self.create_spend_summary(sheets_data.get("spend_summary", []))
        self.create_spend_package_summary(sheets_data.get("spend_package_summary", []))

    def create_detail_sheet(self, data_input, state_columns):
        titles = {
            "1.trace启动响应&耗时详情页": [
                "SN",
                "Loop",
                "Case",
                "Trace",
                "Scene",
                "Package",
                "Activity",
                "StartType",
                "ResponseTime",
                "SpendTime",
            ]
            + state_columns
        }
        self.excel.add_sheet(titles, data_input)
        print("1.trace启动响应耗时详情页 已生成")

    def create_response_summary(self, data_input):
        titles = {
            "2.trace启动响应汇总页": [
                "Package",
                "Application",
                "Average",
                "Standard",
                "Max",
                "Min",
                "Number(155~245ms)",
                "Number(245~390ms)",
                "Number(>=390ms)",
                "Numbers",
                "Top Values",
            ]
        }
        self.excel.add_sheet(titles, data_input)
        print("2.trace启动响应汇总页 已生成")

    def create_spend_summary(self, data_input):
        titles = {
            "3.trace启动耗时汇总页": [
                "Application",
                "Package",
                "Activity",
                "statistics",
                "SpendTime",
                "running_dur_ns",
                "runnable_dur_ns",
                "uninterruptible_sleep_dur_ns",
                "interruptible_sleep_dur_ns",
                "uninterruptible_io_sleep_dur_ns",
                "uninterruptible_non_io_sleep_dur_ns",
            ]
        }
        self.excel.add_sheet(titles, data_input, merge_cols=[1, 2, 3])
        print("3.trace启动耗时汇总页 已生成")

    def create_spend_package_summary(self, data_input):
        titles = {
            "4.trace启动耗时(package)汇总页": [
                "Package",
                "Application",
                "Average",
                "Standard",
                "Max",
                "Min",
                "Numbers",
                "Top Values",
            ]
        }
        self.excel.add_sheet(titles, data_input)
        print("4.trace启动耗时(package)汇总页 已生成")
