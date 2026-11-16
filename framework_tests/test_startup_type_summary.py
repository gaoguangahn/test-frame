"""验证启动类型细分与原 Activity 汇总保持相同统计口径。"""
import openpyxl
import pytest

from exfw.models.dynamic.report.sheets.trace.data_analyse.startup_processor import (
    process_all_startup_data,
)
from exfw.models.dynamic.report.sheets.trace.startup_sheet import TraceStartupSheet
from exfw.models.dynamic.report.utils.excel_generator import ExcelGenerator


def startup_record(start_type, spend_time, *, package="com.demo", activity="Main"):
    return {
        "serial": "SN",
        "round": 1,
        "case": "test_launch",
        "new_package": package,
        "new_activity": activity,
        "startup_type": start_type,
        "spend_time": spend_time,
        "response_time": 100,
        "thread_states": {"running_dur_ns": spend_time * 10_000},
    }


def test_type_statistics_match_activity_summary_and_keep_unknown_in_all():
    records = [startup_record(kind, value) for kind, value in [
        ("cold", 100), ("warm", 300), ("hot", 500), ("UNKNOWN", 700),
    ]]
    records[1].update(serial="OTHER_SN", round=2, case="test_other")
    result = process_all_startup_data(records, {"com.demo": "演示应用"})
    sheets = result["sheets_data"]
    typed = sheets["spend_type_summary"]
    all_rows = [{key: value for key, value in row.items() if key != "StartType"}
                for row in typed if row["StartType"] == "all"]
    assert all_rows == sheets["spend_summary"]
    assert len(typed) == 32
    rows = {(row["StartType"], row["statistics"]): row for row in typed}
    assert rows["all", "Count"]["SpendTime"] == 4
    assert rows["all", "Avg"]["SpendTime"] == 400
    assert rows["all", "Std"]["SpendTime"] == pytest.approx(258.20)
    assert rows["all", "25%"]["SpendTime"] == 250
    assert rows["all", "50%"]["SpendTime"] == 400
    assert rows["all", "75%"]["SpendTime"] == 550
    for kind, value in [("cold", 100), ("warm", 300), ("hot", 500)]:
        assert rows[kind, "Count"]["SpendTime"] == 1
        assert rows[kind, "Avg"]["SpendTime"] == value
        assert rows[kind, "Std"]["SpendTime"] == 0
    assert rows["all", "Avg"]["running_dur_ns"] == 4
    assert result["summary_data"]["start_spend_values"] == {
        "cold": [100], "warm": [300], "hot": [500], "unknown": [700],
    }


def test_excel_sheet_order_and_hierarchical_groups(tmp_path):
    records = [
        startup_record("cold", 100),
        startup_record("hot", 200, activity="Other"),
        startup_record("cold", 900, package="com.another"),
    ]
    sheets = process_all_startup_data(records, {})["sheets_data"]
    path = tmp_path / "startup.xlsx"
    excel = ExcelGenerator(path)
    TraceStartupSheet(excel).generate_all(sheets)
    excel.save()
    workbook = openpyxl.load_workbook(path, data_only=True)
    try:
        names = workbook.sheetnames
        new_name = "3.1.trace启动耗时(启动类型)汇总页"
        assert names.index("3.trace启动耗时汇总页") + 1 == names.index(new_name)
        assert names.index(new_name) + 1 == names.index("4.trace启动耗时(package)汇总页")
        sheet = workbook[new_name]
        assert sheet.cell(1, 4).value == "StartType"
        assert sheet.max_row == 49
        assert [sheet.cell(row, 4).value for row in (2, 10, 18, 26)] == [
            "all", "cold", "all", "hot",
        ]
        assert sheet.cell(18, 3).value == "Other"
        assert sheet.cell(34, 2).value == "com.another"
        assert sheet.cell(34, 6).value == 1
        assert sheet.cell(35, 6).value == 900
        merged = {str(region) for region in sheet.merged_cells.ranges}
        assert "C2:C17" in merged
        assert "C18:C33" in merged
        assert "D2:D9" in merged
        assert "D10:D17" in merged
    finally:
        workbook.close()


def test_absent_or_invalid_start_types_are_omitted():
    invalid_warm = startup_record("warm", 300)
    invalid_warm.update(spend_time=None, thread_states={})
    records = [startup_record("cold", 100), startup_record("hot", 500), invalid_warm]
    sheets = process_all_startup_data(records, {})["sheets_data"]
    types = list(dict.fromkeys(row["StartType"] for row in sheets["spend_type_summary"]))
    assert types == ["all", "cold", "hot"]
    assert len(sheets["spend_type_summary"]) == 24

    unknown = process_all_startup_data([startup_record("UNKNOWN", 700)], {})
    assert {row["StartType"] for row in unknown["sheets_data"]["spend_type_summary"]} == {"all"}


def test_empty_startup_data_does_not_create_type_groups():
    result = process_all_startup_data([], {})
    assert result["sheets_data"]["spend_type_summary"] == []
