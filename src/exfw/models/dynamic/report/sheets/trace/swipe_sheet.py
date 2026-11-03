class TraceSwipeSheet:
    """专门处理报表生成的类（纯渲染）"""

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, sheets_data):
        """生成全部滑动相关报表"""

        detail_for_excel = [
            {k: v for k, v in row.items() if not k.startswith("_")}
            for row in sheets_data.get("detail", [])
        ]

        self.create_swipe_detail_sheet(detail_for_excel)
        self.create_swipe_summary_sheet(sheets_data.get("summary", []))

    def create_swipe_detail_sheet(self, input_data):
        """trace滑动掉帧详情页"""
        titles = {
            "11.trace滑动详情页": [
                "SN",
                "Loop",
                "Case",
                "Trace",
                "Package",
                "Activity",
                "SwipeStart",
                "Off_avg_fps",
                "Off_Count",
                "Off_Jank",
            ]
        }
        self.excel.add_sheet(titles, input_data)
        print("11.trace滑动详情页 已生成")

    def create_swipe_summary_sheet(self, input_data):
        """滑动数据汇总页"""
        titles = {
            "12.trace滑动汇总页": [
                "Case",
                "Package",
                "Activity",
                "SlideNumbers",
                "Number(25~58ms)",
                "Number(58~84ms)",
                "Number(84~133ms)",
                "Number(>133ms)",
                "Top Values",
            ]
        }
        self.excel.add_sheet(titles, input_data)
        print("12.trace滑动汇总页 已生成")
