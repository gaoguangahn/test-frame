"""解析字段顺序变化时，启动和点击的线程状态表头仍须一致。"""
import openpyxl
import pytest

from exfw.models.dynamic.report.sheets.trace.app_click_sheet import TraceAppClickSheet
from exfw.models.dynamic.report.sheets.trace.data_analyse.click_processor import process_all_click_data
from exfw.models.dynamic.report.sheets.trace.data_analyse.startup_processor import process_all_startup_data
from exfw.models.dynamic.report.sheets.trace.startup_sheet import TraceStartupSheet
from exfw.models.dynamic.report.utils.excel_generator import ExcelGenerator


EXPECTED_COLUMNS = [
    "running_dur_ns",
    "runnable_dur_ns",
    "interruptible_sleep_dur_ns",
    "uninterruptible_sleep_dur_ns",
    "uninterruptible_io_sleep_dur_ns",
    "uninterruptible_non_io_sleep_dur_ns",
]


@pytest.mark.parametrize("model,state_field", [
    ("startup", "thread_states"),
    ("click", "thread_state"),
    ("click", "thread_states"),
])
@pytest.mark.parametrize("sparse", [False, True])
def test_detail_and_summary_headers_match_and_values_stay_aligned(tmp_path, model, state_field, sparse):
    values = {name: index * 1_000_000 for index, name in enumerate(EXPECTED_COLUMNS, 1)}
    if sparse:
        values = {name: values[name] for name in (EXPECTED_COLUMNS[0], EXPECTED_COLUMNS[-1])}
    record = {
        "round": 1,
        "new_package": "com.demo",
        "new_process": "com.demo",
        "new_activity": "Main",
        "case": "test_launch",
        "startup_type": "cold",
        "spend_time": 100,
        "response_time": 50,
        state_field: {"extra_state": 19_000_000, **dict(reversed(list(values.items())))},
    }
    if model == "startup":
        sheets = process_all_startup_data([record], {})["sheets_data"]
        generator = TraceStartupSheet
        detail_name = "1.trace启动响应&耗时详情页"
        summary_names = ["3.trace启动耗时汇总页", "3.1.trace启动耗时(启动类型)汇总页"]
    else:
        sheets = process_all_click_data([record])["sheets_data"]
        generator = TraceAppClickSheet
        detail_name = "5.trace应用内点击响应详情页"
        summary_names = ["6.trace应用内点击汇总页"]

    assert sheets["state_columns"] == EXPECTED_COLUMNS + ["extra_state"]
    path = tmp_path / "thread_states.xlsx"
    excel = ExcelGenerator(path)
    generator(excel).generate_all(sheets)
    excel.save()
    workbook = openpyxl.load_workbook(path, data_only=True)
    try:
        for sheet_name in [detail_name, *summary_names]:
            sheet = workbook[sheet_name]
            headers = [cell.value for cell in sheet[1]]
            start = headers.index("running_dur_ns")
            assert headers[start:start + 6] == EXPECTED_COLUMNS
            value_row = 2 if sheet_name == detail_name else 3  # 汇总第 3 行是 Avg。
            for name, nanoseconds in values.items():
                assert sheet.cell(value_row, headers.index(name) + 1).value == nanoseconds / 1_000_000
        detail = workbook[detail_name]
        assert detail.cell(1, detail.max_column).value == "extra_state"
        assert detail.cell(2, detail.max_column).value == 19
    finally:
        workbook.close()
