import json
import traceback
from pathlib import Path
from typing import Any

from .data.data_fetcher import ReportDataFetcher
from .data.report_dataset import build_report_dataset
from .bd_jank.archive import archive_jank_traces
from .bd_jank.selection import select_jank_cases
from .sheets import (
    LogAutoStartCleanSheet,
    LogIoStatSheet,
    LogMemoryIoSheet,
    LogRadarSheet,
    SummarySheet,
    TraceAppClickSheet,
    TraceStartupSheet,
)
from .sheets.log.data_analyse.adb_log import process_all_adb_log_data
from .sheets.log.data_analyse.io_stat import process_all_io_stat_data
from .sheets.log.data_analyse.memory_io import process_all_memory_io_data
from .sheets.log.data_analyse.radar import process_all_radar_data
from .sheets.trace.data_analyse.click_processor import process_all_click_data
from .sheets.trace.data_analyse.startup_processor import process_all_startup_data
from .utils.excel_generator import ExcelGenerator


class ReportGenerator:
    """测试报告生成器"""

    def __init__(self):
        self.current_file = Path(__file__).resolve()
        self.trace_data = {}
        self.test_info = {}

        self.log_data = {}
        self.summary_data = {}
        self.steps = {}
        self.app_map = {}

        self.session_data = {}
        self.report_tasks = []
        self.dataset = None
        self.data_fetcher = ReportDataFetcher()

    def get_task_id_from_session(self, session_data: dict[str, Any]) -> str | None:
        """从 session_result.json 中提取动态任务 ID。"""

        return (
            session_data.get("extensions", {}).get("dynamic_model", {}).get("task_id")
        )

    def load_report_data(self, task_dir: str, serial=None, round=None):
        """从 dynamic runner 输出目录和结果服务读取并整理报表数据。"""

        self._load_app_map()
        self.dataset = build_report_dataset(
            runner_output_dir=task_dir,
            serial=serial,
            round=round,
            fetcher=self.data_fetcher,
        )
        self._apply_dataset()

    def _apply_dataset(self) -> None:
        """将 ReportDataset 应用到现有 sheet 生成流程使用的字段。"""

        if self.dataset is None:
            raise RuntimeError("ReportDataset 尚未构造，请先调用 load_report_data()。")

        self.case_results = self.dataset.case_results
        self.test_info = self.dataset.test_info
        self.trace_data = self.dataset.trace_data
        self.log_data = self.dataset.log_data

        self.summary_data = {}

    def _load_app_map(self) -> None:
        """加载应用包名映射配置。"""

        report_dir = Path(__file__).resolve().parent
        app_map_path = report_dir / "configs" / "app_map.json"

        with app_map_path.open("r", encoding="utf-8") as file:
            self.app_map = json.load(file)

    def generate_report(self, output_file):
        """生成测试报告"""

        self.excel = ExcelGenerator(output_file)

        # 1. trace启动指标。
        try:
            trace_startup_data = process_all_startup_data(
                self.trace_data.get("startup_transition", []),
                self.app_map,
                self.test_info,
            )
            TraceStartupSheet(self.excel).generate_all(
                trace_startup_data["sheets_data"]
            )
            self.summary_data.update(trace_startup_data.get("summary_data", {}))
        except Exception as error:
            print(f"❌ [Trace启动指标] 报表生成失败: {error}")
            traceback.print_exc()

        # 2. trace应用内点击响应指标。
        try:
            trace_click_data = process_all_click_data(
                self.trace_data.get("click_transition", []),
                self.test_info,
            )
            TraceAppClickSheet(self.excel).generate_all(trace_click_data["sheets_data"])
            self.summary_data.update(trace_click_data.get("summary_data", {}))
        except Exception as error:
            print(f"❌ [Trace应用内点击] 报表生成失败: {error}")
            traceback.print_exc()

        # 3. log性能雷达指标。
        try:
            log_radar_data = process_all_radar_data(
                self.log_data.get("parse_radar_log", [])
            )
            LogRadarSheet(self.excel).generate_all(log_radar_data["sheets_data"])
            self.summary_data.update(log_radar_data.get("summary_data", {}))
        except Exception as error:
            print(f"❌ [Log性能雷达] 报表生成失败: {error}")
            traceback.print_exc()

        # 4. log Memory 和 IO 指标。
        try:
            log_memory_io_data = process_all_memory_io_data(
                self.log_data.get("parse_io_measure"),
                self.log_data.get("parse_proc_memory"),
                self.log_data.get("parse_dumpsys_meminfo"),
                self.log_data.get("parse_jank_log"),
            )
            LogMemoryIoSheet(self.excel).generate_all(log_memory_io_data["sheets_data"])
            self.summary_data.update(log_memory_io_data.get("summary_data", {}))
        except Exception as error:
            print(f"❌ [Log Memory和IO] 报表生成失败: {error}")
            traceback.print_exc()

        # 5. IOStat 指标。
        try:
            log_io_stat_data = process_all_io_stat_data(
                self.log_data.get("parse_io_stat", [])
            )
            LogIoStatSheet(self.excel).generate_all(log_io_stat_data["sheets_data"])
            self.summary_data.update(log_io_stat_data.get("summary_data", {}))
        except Exception as error:
            print(f"❌ [Log IOStat] 报表生成失败: {error}")
            traceback.print_exc()

        # 6. 自启指标。
        try:
            log_auto_start_data = process_all_adb_log_data(
                self.log_data.get("parse_adb_log", [])
            )
            LogAutoStartCleanSheet(self.excel).generate_all(
                log_auto_start_data["sheets_data"]
            )
            self.summary_data.update(log_auto_start_data.get("summary_data", {}))
        except Exception as error:
            print(f"❌ [Log自启指标] 报表生成失败: {error}")
            traceback.print_exc()

        # 7. 结果汇总
        try:
            SummarySheet(self.excel).generate_all(self.summary_data, self.test_info)
        except Exception as error:
            print(f"❌ [结果汇总页] 报表生成失败: {error}")
            traceback.print_exc()

        # 14. 保存表格
        try:
            self.excel.move_sheet_to_front("0.结果汇总")
            self.excel.save()
            print(f"✅ 报告已成功保存至: {output_file}")
        except Exception as e:
            print(f"❌ 报告保存失败: {e}")
            traceback.print_exc()
            return

        if self.dataset is None:
            raise RuntimeError("报告数据尚未加载，无法归档 BD 卡顿 Trace。")
        selected = select_jank_cases(
            self.log_data.get("parse_radar_log", []), self.dataset.selected_round
        )
        archive_jank_traces(self.dataset.report_tasks, selected)


if __name__ == "__main__":
    reporter = ReportGenerator()
    task_dir = r"D:\ptrace_analysis\execute_framework\execute_framework\bvl"
    reporter.load_report_data(task_dir=task_dir)
    print(reporter.trace_data.keys())
    reporter.generate_report(output_file="test.xlsx")
