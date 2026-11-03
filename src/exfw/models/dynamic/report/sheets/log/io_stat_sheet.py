class LogIoStatSheet:
    """专门处理报表生成的类"""

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, sheets_data):
        """生成全部 IOStat 相关报表。"""

        self.create_io_stat_sheet(sheets_data.get("stat_data", []))
        self.create_io_stat_sn_sheet(sheets_data.get("stat_summary", []))

    def create_io_stat_sheet(self, stat_data):
        """io_stat原始数据表格"""

        titles = {
            "13.IOStat": [
                "sn",
                "loop",
                "case",
                "stage",
                "Read-cnt",
                "Rmerge-cnt",
                "R-sectors",
                "Read-ms",
                "Write-cnt",
                "Wmerge-cnt",
                "W-sectors",
                "Write-ms",
                "inflat-IO",
                "IO-time",
                "IO-weighted-ms",
                "Discard-cnt",
                "discard-merge-cnt",
                "discard-sectors",
                "discard-ms",
                "flush-cnt",
                "flush-ms",
            ]
        }
        self.excel.add_sheet(titles, stat_data)
        print("13.IOStat数据页 已生成")
        return

    def create_io_stat_sn_sheet(self, stat_summary):
        """IOStat-SN统计页"""

        titles = {
            "14.IOStat-SN": [
                "sn",
                "R-sectors",
                "W-sectors",
                "discard-sectors",
                "R-sectors-start",
                "R-sectors-end",
                "W-sectors-start",
                "W-sectors-end",
                "discard-sectors-start",
                "discard-sectors-end",
            ]
        }

        self.excel.add_sheet(titles, stat_summary)
        print("14.IOStat-SN页 已生成")
