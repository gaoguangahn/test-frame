class TraceKeyboardSheet:
    """专门处理报表生成的类（纯渲染）"""

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, sheets_data):
        """生成全部输入法相关报表"""

        self.create_response_sheet(sheets_data.get("response", []))
        self.create_animation_sheet(sheets_data.get("animation", []))

    def create_response_sheet(self, input_data):
        """输入法弹出响应页"""
        titles = {
            "13.trace输入法弹出响应页": [
                "SN",
                "Loop",
                "Case",
                "Trace",
                "Scene",
                "Package",
                "AnimatorType",
                "ResponseTime",
            ]
        }
        self.excel.add_sheet(titles, input_data)
        print("13.trace输入法弹出响应页 已生成")

    def create_animation_sheet(self, input_data):
        """输入法弹窗动效页"""
        titles = {
            "14.trace输入法弹窗动效页": [
                "SN",
                "Loop",
                "Case",
                "Trace",
                "Scene",
                "Package",
                "AnimatorType",
                "Number(34~50ms)",
                "Number(50~84ms)",
                "Number(84~134ms)",
                "Number(>134ms)",
                "Numbers",
                "Frames",
            ]
        }
        self.excel.add_sheet(titles, input_data)
        print("14.trace输入法弹窗动效页 已生成")
