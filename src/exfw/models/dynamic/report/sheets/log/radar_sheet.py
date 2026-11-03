class LogRadarSheet:
    """专门处理报表生成的类"""

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, sheets_data):
        """生成全部性能雷达相关报表。"""

        self.create_radar_sheets(sheets_data)

    def create_radar_sheets(self, sheets_data):
        """性能雷达数据整理输出"""

        all_records = sheets_data.get("all_records", [])
        max_counts = sheets_data.get("max_counts", 0)
        fluency_result = sheets_data.get("fluency_result", [])
        fluency_marks = sheets_data.get("fluency_marks", [])
        animation_result = sheets_data.get("animation_result", [])
        animation_marks = sheets_data.get("animation_marks", [])

        raw_titles = {
            "7.源-BD数据": ["sn", "loop", "case", "Comment", "Name", "Type"]
            + [f"Count {i}" for i in range(max_counts)]
        }
        self.excel.add_sheet(raw_titles, all_records)
        print("7.源-BD数据页 已生成")

        fluency_titles = {
            "8.FLUENCY整理": ["Activity", "Numbers"] + fluency_marks
        }
        self.excel.add_sheet(fluency_titles, fluency_result)
        print("8.FLUENCY整理页 已生成")

        animation_titles = {
            "9.ANIMATOR整理": ["Activity", "Type", "Numbers"] + animation_marks
        }
        self.excel.add_sheet(animation_titles, animation_result)
        print("9.ANIMATOR整理页 已生成")
