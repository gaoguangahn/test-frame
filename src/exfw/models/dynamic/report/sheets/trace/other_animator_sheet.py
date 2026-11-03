class TraceOtherAnimatorSheet:
    """专门处理报表生成的类（纯渲染）"""

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, sheets_data):
        """生成全部其他动效相关报表"""

        self.create_other_detail_sheet(sheets_data.get("detail", []))

    def create_other_detail_sheet(self, input_data):
        """控制中心/多任务动效详情页"""

        titles = {
            "15.trace其他动效详情页": [
                "SN",
                "Loop",
                "Case",
                "Scene",
                "Trace",
                "StartTime",
                "Operation",
                "VsyncFps",
                "JankTime",
                "FrameCounts",
                "Frames",
            ]
        }
        self.excel.add_sheet(titles, input_data)
        print("15.trace其他动效详情页 已生成")
