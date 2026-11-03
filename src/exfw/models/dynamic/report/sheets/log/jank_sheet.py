class LogTypeJankSheet:
    """专门处理报表生成的类"""

    def __init__(self, excel_handler):
        self.excel = excel_handler
        self.summary_data = {}  # 存放跨报表的汇总数据

    def generate_all(self, jank_data):
        self.create_type_jank_sheet(jank_data)
        return self.summary_data

    def create_type_jank_sheet(self, jank_data):
        """按键卡顿类型数据表格"""

        titles = {"30.按键卡顿": ["sn", "loop", "Numbers", "Records"]}
        self.excel.add_sheet(titles, jank_data)
        print("30.按键卡顿页 已生成")
        return
