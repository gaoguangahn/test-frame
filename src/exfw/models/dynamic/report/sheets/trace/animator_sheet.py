class TraceAnimatorSheet:
    """专门处理报表生成的类"""

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, sheets_data):
        self.create_launcher_detail_sheet(sheets_data.get("launcher_detail", []))
        self.create_launcher_summary_sheet(sheets_data.get("launcher_summary", []))
        self.create_engine_detail_sheet(sheets_data.get("engine_detail", []))
        self.create_engine_summary_sheet(sheets_data.get("engine_summary", []))

    def create_launcher_detail_sheet(self, input_data):
        titles = {
            "5.trace启退launcher动效详情页": [
                "SN",
                "Loop",
                "Case",
                "Trace",
                "Package",
                "Animation",
                "Scene",
                "Number(34~50ms)",
                "Number(50~84ms)",
                "Number(84~134ms)",
                "Number(>134ms)",
                "Numbers",
                "Frames",
            ]
        }
        self.excel.add_sheet(titles, input_data)
        print("5.trace启退launcher动效详情页 已生成")

    def create_launcher_summary_sheet(self, input_data):
        titles = {
            "6.trace启退launcher动效汇总页": [
                "Package",
                "Animation",
                "Scene",
                "Number(34~50ms)",
                "Number(50~84ms)",
                "Number(84~134ms)",
                "Number(>134ms)",
                "Numbers",
            ]
        }
        self.excel.add_sheet(titles, input_data)
        print("6.trace启退launcher动效汇总页 已生成")

    def create_engine_detail_sheet(self, input_data):
        titles = {
            "7.trace启退动效引擎详情页": [
                "SN",
                "Loop",
                "Case",
                "Trace",
                "Package",
                "Animation",
                "Scene",
                "Number(34~50ms)",
                "Number(50~84ms)",
                "Number(84~134ms)",
                "Number(>134ms)",
                "Numbers",
                "Frames",
            ]
        }
        self.excel.add_sheet(titles, input_data)
        print("7.trace启退动效引擎详情页 已生成")

    def create_engine_summary_sheet(self, input_data):
        titles = {
            "8.trace启退动效引擎汇总页": [
                "Package",
                "Animation",
                "Scene",
                "Number(34~50ms)",
                "Number(50~84ms)",
                "Number(84~134ms)",
                "Number(>134ms)",
                "Numbers",
            ]
        }
        self.excel.add_sheet(titles, input_data)
        print("8.trace启退动效引擎汇总页 已生成")
