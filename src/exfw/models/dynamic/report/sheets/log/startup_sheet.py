class LogStartSheet:
    """专门处理报表生成的类"""

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, sheets_data):
        """生成全部启动相关报表"""
        self.create_detail_sheet(sheets_data.get("all_data", []))
        self.create_organized_sheet(sheets_data.get("organized_data", []))
        self.create_startup_sheet(sheets_data.get("startup_data", []))
        self.create_window_response_sheet(sheets_data.get("click_data", []))

    def create_detail_sheet(self, raw_data):
        """输出log冷启动源数据的表格"""
        if not raw_data:
            print("警告: 16.源-log冷启动 数据为空")
            return

        titles = {
            "16.源-log冷启动": [
                "SN",
                "Loop",
                "Case",
                "Package",
                "Activity",
                "Scene",
                "Type",
                "Trace",
                "Value",
            ]
        }
        self.excel.add_sheet(titles, raw_data)
        print("16.源-log冷启动页 已生成")

    def create_organized_sheet(self, organized_data):
        """输出整理后的log冷启动数据表格"""
        if not organized_data:
            print("警告: 17.log冷启动数据整理 数据为空")
            return

        titles = {
            "17.log冷启动数据整理": [
                "Package",
                "Activity",
                "Scene",
                "Type",
                "Average",
                "Standard",
                "Number",
                "Values",
            ]
        }
        self.excel.add_sheet(titles, organized_data)
        print("17.log冷启动数据整理页 已生成")

    def create_startup_sheet(self, startup_data):
        """log中启动耗时数据生成表格"""
        if not startup_data:
            print("警告: 18.log启动耗时 数据为空")
            return

        titles = {
            "18.log启动耗时": [
                "Activity",
                "Application",
                "启动时长均值ms",
                "标准差",
                "最大值",
                "最小值",
                "轻微启动慢次数（1~2s）",
                "明显启动慢次数（2~3s）",
                "严重启动慢次数（>=3s）",
                "冷启动总次数",
                "Top Values",
            ]
        }
        self.excel.add_sheet(titles, startup_data)
        print("18.log启动耗时页 已生成")

    def create_window_response_sheet(self, click_data):
        """log数据中的窗口响应数据表格"""
        if not click_data:
            print("警告: 19.log窗口响应 数据为空")
            return

        titles = {
            "19.log窗口响应": [
                "Activity",
                "应用内转场",
                "响应时延均值ms",
                "标准差",
                "最大值",
                "最小值",
                "轻微延迟次数（155~245ms）",
                "明显延迟次数（245~390ms）",
                "严重延迟次数（>=390ms）",
                "转场总次数",
                "Top Values",
            ]
        }
        self.excel.add_sheet(titles, click_data)
        print("19.log窗口响应页 已生成")
