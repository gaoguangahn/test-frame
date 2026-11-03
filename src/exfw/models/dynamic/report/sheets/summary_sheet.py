from openpyxl.styles import Alignment, Font
from exfw.models.dynamic.report.bd_jank.selection import jank_count

from ..utils.report_util import (
    _avg_and_std,
    _counts_in_range,
    _gen_count_and_label2,
    _get_range_percent,
    format_duration,
)


class SummarySheet:
    """专门处理报表生成的类"""

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, summary_data, test_info=None):
        """结果汇总页，汇总各类性能测试结果。"""

        test_info = test_info if isinstance(test_info, dict) else {}
        total_test_time = self._get_total_test_time(test_info)
        total_swipes = self._get_total_swipes(test_info)
        total_start_exit = self._get_total_start_exit(test_info)
        header_info = self._build_header_info(test_info)

        report_rows = []

        # 1.应用启动响应-Trace
        report_rows.extend(self.startup_response_trace(summary_data))

        # 2.应用启动耗时-Trace
        report_rows.extend(self.startup_spend_trace(summary_data))

        # 3.应用内点击响应-Trace
        report_rows.extend(self.click_transition_trace(summary_data))

        # 4.应用启动退出动效（性能雷达）
        report_rows.extend(self.app_animator_log(summary_data, total_start_exit))

        # 5.应用内滑动（性能雷达）
        report_rows.extend(self.app_swipe_log(summary_data, total_swipes))

        # 6.应用启动微观指标-Trace
        report_rows.extend(self.startup_misc_trace(summary_data))

        # 7.应用内点击微观指标-Trace
        report_rows.extend(self.click_misc_trace(summary_data))

        # 8.IO微观指标
        report_rows.extend(self.io_misc_log(summary_data))

        # 9.Memory微观指标
        report_rows.extend(self.memory_misc_log(summary_data))
        titles = {
            "0.结果汇总": ["测试场景", "测试指标", "标准(S/A/B)", "指标值", "指标数值"]
        }
        self.excel.add_sheet(titles, report_rows, merge_cols=[1], header_offset=1)

        self.insert_summary_line("0.结果汇总", header_info)
        print("0.结果汇总页 已生成")

    def _get_total_test_time(self, test_info):
        """获取整次 runner 任务耗时，单位秒。"""

        runner = test_info.get("runner") or {}
        duration_seconds = runner.get("duration_seconds", 0)
        return duration_seconds if isinstance(duration_seconds, (int, float)) else 0

    def _get_total_swipes(self, test_info):
        """获取整次测试总滑动次数。"""

        action_stats = test_info.get("action_stats") or {}
        total_swipes = action_stats.get("total_swipes", 0)
        return total_swipes if isinstance(total_swipes, (int, float)) else 0


    def _get_total_start_exit(self, test_info):
        """获取整次测试启动退出总次数，start_app 与 home 都计入启退动效。"""

        action_stats = test_info.get("action_stats") or {}
        total_start_exit = action_stats.get("total_start_exit")

        if isinstance(total_start_exit, (int, float)) and not isinstance(
            total_start_exit, bool
        ):
            return total_start_exit

        total_start_app = action_stats.get("total_start_app", 0)
        total_home = action_stats.get("total_home", 0)
        total = 0

        if isinstance(total_start_app, (int, float)) and not isinstance(
            total_start_app, bool
        ):
            total += total_start_app
        if isinstance(total_home, (int, float)) and not isinstance(total_home, bool):
            total += total_home

        return total

    def _build_header_info(self, test_info):
        """从 test_info 构造 summary 顶部展示信息。"""

        devices = test_info.get("devices") or {}
        case_summary = test_info.get("case_summary") or {}
        duration_seconds = self._get_total_test_time(test_info)

        return {
            "设备数": len(devices),
            "总测试时间": format_duration(duration_seconds),
            "用例总数": case_summary.get("total", 0),
            "通过率": self._format_pass_rate(case_summary.get("pass_rate", 0)),
            "devices": devices,
        }

    @staticmethod
    def _format_pass_rate(pass_rate):
        if isinstance(pass_rate, bool):
            return "0%"

        if not isinstance(pass_rate, (int, float)):
            return "0%"

        return f"{round(pass_rate * 100, 2)}%"

    def startup_response_trace(self, summary_data):
        """应用启动响应-Trace"""

        startup_response_values = summary_data.get("start_response_values") or {}

        cold_vals = startup_response_values.get("cold") or []
        warm_vals = startup_response_values.get("warm") or []
        hot_vals = startup_response_values.get("hot") or []
        values = cold_vals + warm_vals + hot_vals

        total_cnt = all_avg = all_std = "-"
        c_avg = w_avg = h_avg = "-"
        c1 = l1 = c2 = l2 = c3 = l3 = "-"

        if values:
            total_cnt = len(values)
            all_avg, all_std = _avg_and_std(values)  # 整体平均值、标准差
            c_avg, _ = _avg_and_std(cold_vals)  # 冷启动平均值
            w_avg, _ = _avg_and_std(warm_vals)  # 温启动平均值
            h_avg, _ = _avg_and_std(hot_vals)  # 热启动平均值

            # 轻微响应延迟次数（155~245ms）/百次启动
            c1, l1 = _get_range_percent(values, 155, 245, 100, total_cnt)
            # 明显响应延迟次数（245~390ms）/百次启动
            c2, l2 = _get_range_percent(values, 245, 390, 100, total_cnt)
            # 严重响应延迟次数（>=390ms）/百次启动)
            c3, l3 = _get_range_percent(values, 390, None, 100, total_cnt)

        return [
            {
                "测试场景": "应用启动响应-Trace",
                "测试指标": "启动响应总次数",
                "标准(S/A/B)": "-",
                "指标值": total_cnt,
                "指标数值": total_cnt,
            },
            {
                "测试场景": "应用启动响应-Trace",
                "测试指标": "启动响应平均值(ms)",
                "标准(S/A/B)": "85/120",
                "指标值": all_avg,
                "指标数值": all_avg,
            },
            {
                "测试场景": "应用启动响应-Trace",
                "测试指标": "启动响应标准差(ms)",
                "标准(S/A/B)": "-",
                "指标值": all_std,
                "指标数值": all_std,
            },
            {
                "测试场景": "应用启动响应-Trace",
                "测试指标": "冷/温/热启动响应平均值(ms)",
                "标准(S/A/B)": "-",
                "指标值": f"{c_avg}/{w_avg}/{h_avg}",
                "指标数值": f"{c_avg}/{w_avg}/{h_avg}",
            },
            {
                "测试场景": "应用启动响应-Trace",
                "测试指标": "轻微响应延迟次数（155~245ms）/百次启动",
                "标准(S/A/B)": "-",
                "指标值": c1,
                "指标数值": l1,
            },
            {
                "测试场景": "应用启动响应-Trace",
                "测试指标": "明显响应延迟次数（245~390ms）/百次启动",
                "标准(S/A/B)": "0/0",
                "指标值": c2,
                "指标数值": l2,
            },
            {
                "测试场景": "应用启动响应-Trace",
                "测试指标": "严重响应延迟次数（>=390ms）/百次启动",
                "标准(S/A/B)": "0/0",
                "指标值": c3,
                "指标数值": l3,
            },
        ]

    def startup_spend_trace(self, summary_data):
        """应用启动耗时-Trace"""

        startup_spend_values = summary_data.get("start_spend_values") or {}

        cold_vals = startup_spend_values.get("cold") or []
        warm_vals = startup_spend_values.get("warm") or []
        hot_vals = startup_spend_values.get("hot") or []
        values = cold_vals + warm_vals + hot_vals

        total_cnt = all_avg = rate_str = rate_val = "-"
        c_avg = w_avg = h_avg = c_std = w_std = h_std = "-"
        c1 = l1 = c2 = l2 = c3 = l3 = "-"

        if values:
            total_cnt = len(values)

            # 计算冷/温/热比例
            rate_str = f"{round(len(cold_vals) / total_cnt, 2)}/{round(len(warm_vals) / total_cnt, 2)}/{round(len(hot_vals) / total_cnt, 2)}"
            rate_val = f"{len(cold_vals)}/{len(warm_vals)}/{len(hot_vals)}"

            # 计算均值和标准差
            all_avg, all_std = _avg_and_std(values)
            c_avg, c_std = _avg_and_std(cold_vals)
            w_avg, w_std = _avg_and_std(warm_vals)
            h_avg, h_std = _avg_and_std(hot_vals)

            # 轻微启动慢次数（1~2s）/百次启动
            c1, l1 = _get_range_percent(values, 1000, 2000, 100, total_cnt)
            # 明显启动慢次数（2~3s）/百次启动
            c2, l2 = _get_range_percent(values, 2000, 3000, 100, total_cnt)
            # 严重启动慢次数（>=3s）/百次启动
            c3, l3 = _get_range_percent(values, 3000, None, 100, total_cnt)

        return [
            {
                "测试场景": "应用启动耗时-Trace",
                "测试指标": "应用启动次数",
                "标准(S/A/B)": "-",
                "指标值": total_cnt,
                "指标数值": total_cnt,
            },
            {
                "测试场景": "应用启动耗时-Trace",
                "测试指标": "应用启动耗时平均值(ms)",
                "标准(S/A/B)": "540/800",
                "指标值": all_avg,
                "指标数值": all_avg,
            },
            {
                "测试场景": "应用启动耗时-Trace",
                "测试指标": "应用冷/温/热启动比例",
                "标准(S/A/B)": "-",
                "指标值": rate_str,
                "指标数值": rate_val,
            },
            {
                "测试场景": "应用启动耗时-Trace",
                "测试指标": "冷/温/热启动耗时平均值(ms)",
                "标准(S/A/B)": "-",
                "指标值": f"{c_avg}/{w_avg}/{h_avg}",
                "指标数值": f"{c_avg}/{w_avg}/{h_avg}",
            },
            {
                "测试场景": "应用启动耗时-Trace",
                "测试指标": "应用冷/温/热启动耗时标准差(ms)",
                "标准(S/A/B)": "-",
                "指标值": f"{c_std}/{w_std}/{h_std}",
                "指标数值": f"{c_std}/{w_std}/{h_std}",
            },
            {
                "测试场景": "应用启动耗时-Trace",
                "测试指标": "轻微启动慢次数（1~2s）/百次启动",
                "标准(S/A/B)": "-",
                "指标值": c1,
                "指标数值": l1,
            },
            {
                "测试场景": "应用启动耗时-Trace",
                "测试指标": "明显启动慢次数（2~3s）/百次启动",
                "标准(S/A/B)": "0/0.3",
                "指标值": c2,
                "指标数值": l2,
            },
            {
                "测试场景": "应用启动耗时-Trace",
                "测试指标": "严重启动慢次数（>=3s）/百次启动",
                "标准(S/A/B)": "0/0",
                "指标值": c3,
                "指标数值": l3,
            },
        ]

    def startup_misc_trace(self, summary_data):
        """应用启动微观指标"""

        start_micro_data = summary_data.get("start_states_values")

        # 1. 统一初始化为 "-"，彻底防止脏数据残留
        mt_running_avg = mt_runnable_avg = mt_uninterruptible_avg = (
            mt_interruptible_avg
        ) = mt_io_avg = mt_non_io_avg = "-"

        mt_running_std = mt_runnable_std = mt_uninterruptible_std = (
            mt_interruptible_std
        ) = mt_io_std = mt_non_io_std = "-"

        if start_micro_data:
            # mt.running_dur 均值/标准差
            running_vals = start_micro_data.get("running_dur_ns") or []
            if running_vals:
                mt_running_avg, mt_running_std = _avg_and_std(running_vals)
            # mt.running_dur 均值/标准差
            runnable_vals = start_micro_data.get("runnable_dur_ns") or []
            if runnable_vals:
                mt_runnable_avg, mt_runnable_std = _avg_and_std(runnable_vals)
            # mt.running_dur 均值/标准差
            uninterruptible_vals = (
                start_micro_data.get("uninterruptible_sleep_dur_ns") or []
            )
            if uninterruptible_vals:
                mt_uninterruptible_avg, mt_uninterruptible_std = _avg_and_std(
                    uninterruptible_vals
                )
            # mt.running_dur 均值/标准差
            interruptible_vals = (
                start_micro_data.get("interruptible_sleep_dur_ns") or []
            )
            if interruptible_vals:
                mt_interruptible_avg, mt_interruptible_std = _avg_and_std(
                    interruptible_vals
                )
            # mt.running_dur 均值/标准差
            io_vals = start_micro_data.get("uninterruptible_io_sleep_dur_ns") or []
            if io_vals:
                mt_io_avg, mt_io_std = _avg_and_std(io_vals)
            # mt.running_dur 均值/标准差
            non_io_vals = (
                start_micro_data.get("uninterruptible_non_io_sleep_dur_ns") or []
            )
            if non_io_vals:
                mt_non_io_avg, mt_non_io_std = _avg_and_std(non_io_vals)

        return [
            {
                "测试场景": "应用启动微观指标",
                "测试指标": "mt.running_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_running_avg}/{mt_running_std}",
                "指标数值": f"{mt_running_avg}/{mt_running_std}",
            },
            {
                "测试场景": "应用启动微观指标",
                "测试指标": "mt.runnable_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_runnable_avg}/{mt_runnable_std}",
                "指标数值": f"{mt_runnable_avg}/{mt_runnable_std}",
            },
            {
                "测试场景": "应用启动微观指标",
                "测试指标": "mt.uninterruptible_sleep_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_uninterruptible_avg}/{mt_uninterruptible_std}",
                "指标数值": f"{mt_uninterruptible_avg}/{mt_uninterruptible_std}",
            },
            {
                "测试场景": "应用启动微观指标",
                "测试指标": "mt.interruptible_sleep_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_interruptible_avg}/{mt_interruptible_std}",
                "指标数值": f"{mt_interruptible_avg}/{mt_interruptible_std}",
            },
            {
                "测试场景": "应用启动微观指标",
                "测试指标": "mt.io_sleep_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_io_avg}/{mt_io_std}",
                "指标数值": f"{mt_io_avg}/{mt_io_std}",
            },
            {
                "测试场景": "应用启动微观指标",
                "测试指标": "mt.non_io_sleep_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_non_io_avg}/{mt_non_io_std}",
                "指标数值": f"{mt_non_io_avg}/{mt_non_io_std}",
            },
        ]

    def click_transition_trace(self, summary_data):
        """应用内点击转场-Trace"""

        click_spend_values = summary_data.get("click_spend_values") or {}

        # 1. 安全获取列表
        cold_vals = click_spend_values.get("cold") or []
        warm_vals = click_spend_values.get("warm") or []
        hot_vals = click_spend_values.get("hot") or []
        values = cold_vals + warm_vals + hot_vals

        # 2. 统一初始化为 "-"，彻底防止脏数据残留和未定义报错
        total_cnt = all_avg = all_std = "-"
        rate_str = rate_val = "-"
        cold_avg = warm_avg = hot_avg = cold_std = warm_std = hot_std = "-"
        count1 = label1 = count2 = label2 = count3 = label3 = "-"

        if values:
            total_cnt = len(values)

            # 计算冷/温/热比例
            rate_str = f"{round(len(cold_vals) / total_cnt, 2)}/{round(len(warm_vals) / total_cnt, 2)}/{round(len(hot_vals) / total_cnt, 2)}"
            rate_val = f"{len(cold_vals)}/{len(warm_vals)}/{len(hot_vals)}"

            # 计算均值和标准差
            all_avg, all_std = _avg_and_std(values)
            cold_avg, cold_std = _avg_and_std(cold_vals)
            warm_avg, warm_std = _avg_and_std(warm_vals)
            hot_avg, hot_std = _avg_and_std(hot_vals)

            # 轻微响应延迟次数（155~245ms）/百次点击
            count1, label1 = _get_range_percent(values, 155, 245, 100, total_cnt)
            # 明显响应延迟次数（245~390ms）/百次点击
            count2, label2 = _get_range_percent(values, 245, 390, 100, total_cnt)

            # 严重响应延迟次数（>=390ms）/百次点击
            count3, label3 = _get_range_percent(values, 390, None, 100, total_cnt)

        return [
            {
                "测试场景": "应用内点击响应-Trace",
                "测试指标": "新窗口响应总次数",
                "标准(S/A/B)": "-",
                "指标值": total_cnt,
                "指标数值": total_cnt,
            },
            {
                "测试场景": "应用内点击响应-Trace",
                "测试指标": "新窗口响应平均值(ms)",
                "标准(S/A/B)": "85/120",
                "指标值": all_avg,
                "指标数值": all_avg,
            },
            {
                "测试场景": "应用内点击响应-Trace",
                "测试指标": "新窗口响应冷/温/热比例",
                "标准(S/A/B)": "-",
                "指标值": rate_str,
                "指标数值": rate_val,
            },
            {
                "测试场景": "应用内点击响应-Trace",
                "测试指标": "新窗口响应冷/温/热平均值(ms)",
                "标准(S/A/B)": "-",
                "指标值": f"{cold_avg}/{warm_avg}/{hot_avg}",
                "指标数值": f"{cold_avg}/{warm_avg}/{hot_avg}",
            },
            {
                "测试场景": "应用内点击响应-Trace",
                "测试指标": "新窗口响应冷/温/热标准差(ms)",
                "标准(S/A/B)": "-",
                "指标值": f"{cold_std}/{warm_std}/{hot_std}",
                "指标数值": f"{cold_std}/{warm_std}/{hot_std}",
            },
            {
                "测试场景": "应用内点击响应-Trace",
                "测试指标": "轻微响应延迟次数（155~245ms）/百次点击",
                "标准(S/A/B)": "-",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": "应用内点击响应-Trace",
                "测试指标": "明显响应延迟次数（245~390ms）/百次点击",
                "标准(S/A/B)": "0/0",
                "指标值": count2,
                "指标数值": label2,
            },
            {
                "测试场景": "应用内点击响应-Trace",
                "测试指标": "严重响应延迟次数（>=390ms）/百次点击",
                "标准(S/A/B)": "0/0",
                "指标值": count3,
                "指标数值": label3,
            },
        ]

    def click_misc_trace(self, summary_data):
        """应用内点击微观指标"""

        click_states_values = summary_data.get("click_states_values") or {}

        # 1. 统一初始化为 "-"，彻底防止脏数据残留
        mt_running_avg = mt_runnable_avg = mt_uninterruptible_avg = (
            mt_interruptible_avg
        ) = mt_io_avg = mt_non_io_avg = "-"
        mt_running_std = mt_runnable_std = mt_uninterruptible_std = (
            mt_interruptible_std
        ) = mt_io_std = mt_non_io_std = "-"

        if click_states_values:
            # mt.running_dur 均值/标准差
            running_vals = click_states_values.get("running_dur_ns") or []
            if running_vals:
                mt_running_avg, mt_running_std = _avg_and_std(running_vals)
            # mt.running_dur 均值/标准差
            runnable_vals = click_states_values.get("runnable_dur_ns") or []
            if runnable_vals:
                mt_runnable_avg, mt_runnable_std = _avg_and_std(runnable_vals)
            # mt.running_dur 均值/标准差
            uninterruptible_vals = (
                click_states_values.get("uninterruptible_sleep_dur_ns") or []
            )
            if uninterruptible_vals:
                mt_uninterruptible_avg, mt_uninterruptible_std = _avg_and_std(
                    uninterruptible_vals
                )
            # mt.running_dur 均值/标准差
            interruptible_vals = (
                click_states_values.get("interruptible_sleep_dur_ns") or []
            )
            if interruptible_vals:
                mt_interruptible_avg, mt_interruptible_std = _avg_and_std(
                    interruptible_vals
                )
            # mt.running_dur 均值/标准差
            io_vals = click_states_values.get("uninterruptible_io_sleep_dur_ns") or []
            if io_vals:
                mt_io_avg, mt_io_std = _avg_and_std(io_vals)
            # mt.running_dur 均值/标准差
            non_io_vals = (
                click_states_values.get("uninterruptible_non_io_sleep_dur_ns") or []
            )
            if non_io_vals:
                mt_non_io_avg, mt_non_io_std = _avg_and_std(non_io_vals)

        return [
            {
                "测试场景": "应用内点击微观指标",
                "测试指标": "mt.running_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_running_avg}/{mt_running_std}",
                "指标数值": f"{mt_running_avg}/{mt_running_std}",
            },
            {
                "测试场景": "应用内点击微观指标",
                "测试指标": "mt.runnable_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_runnable_avg}/{mt_runnable_std}",
                "指标数值": f"{mt_runnable_avg}/{mt_runnable_std}",
            },
            {
                "测试场景": "应用内点击微观指标",
                "测试指标": "mt.uninterruptible_sleep_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_uninterruptible_avg}/{mt_uninterruptible_std}",
                "指标数值": f"{mt_uninterruptible_avg}/{mt_uninterruptible_std}",
            },
            {
                "测试场景": "应用内点击微观指标",
                "测试指标": "mt.interruptible_sleep_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_interruptible_avg}/{mt_interruptible_std}",
                "指标数值": f"{mt_interruptible_avg}/{mt_interruptible_std}",
            },
            {
                "测试场景": "应用内点击微观指标",
                "测试指标": "mt.io_sleep_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_io_avg}/{mt_io_std}",
                "指标数值": f"{mt_io_avg}/{mt_io_std}",
            },
            {
                "测试场景": "应用内点击微观指标",
                "测试指标": "mt.non_io_sleep_dur 均值/标准差",
                "标准(S/A/B)": "-",
                "指标值": f"{mt_non_io_avg}/{mt_non_io_std}",
                "指标数值": f"{mt_non_io_avg}/{mt_non_io_std}",
            },
        ]

    def launch_animator_trace(self, total_time, summary_data):
        """应用启动退出 launcher 动效指标"""

        frame_summary = summary_data.get("startexit_launcher_frame_summary") or {}
        return self._animator_trace_rows(
            scene="应用启动退出动效-Trace（launcher）",
            total_time=total_time,
            frame_summary=frame_summary,
        )

    def motion_animator_trace(self, total_time, summary_data):
        """应用启动退出 motion 动效指标"""

        frame_summary = summary_data.get("startexit_engine_frame_summary") or {}
        return self._animator_trace_rows(
            scene="应用启动退出动效-Trace（motion）",
            total_time=total_time,
            frame_summary=frame_summary,
        )

    def _animator_trace_rows(self, scene, total_time, frame_summary):
        """根据 processor 输出的动效帧区间汇总生成第 0 页指标。"""

        all_counts = "-"
        count1 = label1 = count2 = label2 = count3 = label3 = count4 = label4 = "-"
        count5 = label5 = count6 = label6 = count7 = label7 = count8 = label8 = "-"

        if frame_summary:
            all_counts = frame_summary.get("AnimatorCounts", 0)
            slight_count = frame_summary.get("Number(34~50ms)", 0)
            obvious_count = frame_summary.get("Number(50~84ms)", 0)
            serious_count = frame_summary.get(
                "Number(84~134ms)", 0
            ) + frame_summary.get("Number(>134ms)", 0)
            total_jank_count = slight_count + obvious_count + serious_count

            if total_time:
                time_hours = total_time / 3600
                # 总卡顿次数（>33ms）/千小时
                count1, label1 = _gen_count_and_label2(
                    total_jank_count, time_hours, multiplier=1000
                )
                # 轻微卡顿次数（34~50ms）/千小时
                count2, label2 = _gen_count_and_label2(
                    slight_count, time_hours, multiplier=1000
                )
                # 明显卡顿次数（50~84ms）/千小时
                count3, label3 = _gen_count_and_label2(
                    obvious_count, time_hours, multiplier=1000
                )
                # 严重卡顿次数（>84ms）/千小时
                count4, label4 = _gen_count_and_label2(
                    serious_count, time_hours, multiplier=1000
                )

            if all_counts:
                # 总卡顿次数（>33ms）/百次启退
                count5, label5 = _gen_count_and_label2(
                    total_jank_count, all_counts, multiplier=100
                )
                # 轻微卡顿次数（34~50ms）/百次启退
                count6, label6 = _gen_count_and_label2(
                    slight_count, all_counts, multiplier=100
                )
                # 明显卡顿次数（50~84ms）/百次启退
                count7, label7 = _gen_count_and_label2(
                    obvious_count, all_counts, multiplier=100
                )
                # 严重卡顿次数（>84ms）/百次启退
                count8, label8 = _gen_count_and_label2(
                    serious_count, all_counts, multiplier=100
                )

        return [
            {
                "测试场景": scene,
                "测试指标": "总动效次数",
                "标准(S/A/B)": "-",
                "指标值": all_counts,
                "指标数值": all_counts,
            },
            {
                "测试场景": scene,
                "测试指标": "总卡顿次数（>33ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": scene,
                "测试指标": "轻微卡顿次数（34~50ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count2,
                "指标数值": label2,
            },
            {
                "测试场景": scene,
                "测试指标": "明显卡顿次数（50~84ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count3,
                "指标数值": label3,
            },
            {
                "测试场景": scene,
                "测试指标": "严重卡顿次数（>84ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count4,
                "指标数值": label4,
            },
            {
                "测试场景": scene,
                "测试指标": "总卡顿次数（>33ms）/百次启退",
                "标准(S/A/B)": "-",
                "指标值": count5,
                "指标数值": label5,
            },
            {
                "测试场景": scene,
                "测试指标": "轻微卡顿次数（34~50ms）/百次启退",
                "标准(S/A/B)": "-",
                "指标值": count6,
                "指标数值": label6,
            },
            {
                "测试场景": scene,
                "测试指标": "明显卡顿次数（50~84ms）/百次启退",
                "标准(S/A/B)": "-",
                "指标值": count7,
                "指标数值": label7,
            },
            {
                "测试场景": scene,
                "测试指标": "严重卡顿次数（>84ms）/百次启退",
                "标准(S/A/B)": "-",
                "指标值": count8,
                "指标数值": label8,
            },
        ]

    def keyboard_response_trace(self, summary_data):
        """输入法弹出响应指标"""

        keyboard_popup_count = summary_data.get("keyboard_popup_count")
        keyboard_response_values = summary_data.get("keyboard_response_values") or []

        all_counts = keyboard_popup_count if keyboard_popup_count is not None else 0
        all_avg = all_std = count1 = count2 = count3 = "-"
        label1 = label2 = label3 = "-"

        if keyboard_response_values:
            # 整体平均值，标准差
            all_avg, all_std = _avg_and_std(keyboard_response_values)
            denominator = all_counts or len(keyboard_response_values)
            # 轻微响应延迟次数（155~245ms）/百次唤起
            count1, label1 = _get_range_percent(
                keyboard_response_values, 155, 245, 100, denominator
            )
            # 明显响应延迟次数（245~390ms）/百次唤起
            count2, label2 = _get_range_percent(
                keyboard_response_values, 245, 390, 100, denominator
            )
            # 严重响应延迟次数（>=390ms）/百次唤起
            count3, label3 = _get_range_percent(
                keyboard_response_values, 390, None, 100, denominator
            )

        return [
            {
                "测试场景": "输入法弹出响应-Trace",
                "测试指标": "输入法唤起次数",
                "标准(S/A/B)": "-",
                "指标值": all_counts,
                "指标数值": all_counts,
            },
            {
                "测试场景": "输入法弹出响应-Trace",
                "测试指标": "响应耗时平均值(ms)",
                "标准(S/A/B)": "-",
                "指标值": all_avg,
                "指标数值": all_avg,
            },
            {
                "测试场景": "输入法弹出响应-Trace",
                "测试指标": "响应耗时标准差",
                "标准(S/A/B)": "-",
                "指标值": all_std,
                "指标数值": all_std,
            },
            {
                "测试场景": "输入法弹出响应-Trace",
                "测试指标": "轻微响应延迟次数（155~245ms）/百次唤起",
                "标准(S/A/B)": "-",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": "输入法弹出响应-Trace",
                "测试指标": "明显响应延迟次数（245~390ms）/百次唤起",
                "标准(S/A/B)": "-",
                "指标值": count2,
                "指标数值": label2,
            },
            {
                "测试场景": "输入法弹出响应-Trace",
                "测试指标": "严重响应延迟次数（>=390ms）/百次唤起",
                "标准(S/A/B)": "-",
                "指标值": count3,
                "指标数值": label3,
            },
        ]

    def keyboard_animator_trace(self, total_time, summary_data):
        """输入法弹出动效指标"""

        keyboard_popup_count = summary_data.get("keyboard_popup_count")
        frame_summary = summary_data.get("keyboard_frame_summary") or {}

        all_counts = keyboard_popup_count if keyboard_popup_count is not None else "-"
        count1 = label1 = count2 = label2 = count3 = label3 = count4 = label4 = "-"
        count5 = label5 = count6 = label6 = count7 = label7 = count8 = label8 = "-"

        if frame_summary:
            slight_count = frame_summary.get("Number(34~50ms)", 0)
            obvious_count = frame_summary.get("Number(50~84ms)", 0)
            serious_count = frame_summary.get(
                "Number(84~134ms)", 0
            ) + frame_summary.get("Number(>134ms)", 0)
            total_jank_count = slight_count + obvious_count + serious_count

            if total_time:
                time_hours = total_time / 3600
                # 总卡顿次数（>33ms）/千小时
                count1, label1 = _gen_count_and_label2(
                    total_jank_count, time_hours, multiplier=1000
                )
                # 轻微卡顿次数（34~50ms）/千小时
                count2, label2 = _gen_count_and_label2(
                    slight_count, time_hours, multiplier=1000
                )
                # 明显卡顿次数（50~84ms）/千小时
                count3, label3 = _gen_count_and_label2(
                    obvious_count, time_hours, multiplier=1000
                )
                # 严重卡顿次数（>84ms）/千小时
                count4, label4 = _gen_count_and_label2(
                    serious_count, time_hours, multiplier=1000
                )

            if all_counts and all_counts != "-":
                # 总卡顿次数（>33ms）/百次唤起
                count5, label5 = _gen_count_and_label2(
                    total_jank_count, all_counts, multiplier=100
                )
                # 轻微卡顿次数（34~50ms）/百次唤起
                count6, label6 = _gen_count_and_label2(
                    slight_count, all_counts, multiplier=100
                )
                # 明显卡顿次数（50~84ms）/百次唤起
                count7, label7 = _gen_count_and_label2(
                    obvious_count, all_counts, multiplier=100
                )
                # 严重卡顿次数（>84ms）/百次唤起
                count8, label8 = _gen_count_and_label2(
                    serious_count, all_counts, multiplier=100
                )

        return [
            {
                "测试场景": "输入法弹出动效-Trace",
                "测试指标": "输入法唤起次数",
                "标准(S/A/B)": "-",
                "指标值": all_counts,
                "指标数值": all_counts,
            },
            {
                "测试场景": "输入法弹出动效-Trace",
                "测试指标": "总卡顿次数（>33ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": "输入法弹出动效-Trace",
                "测试指标": "轻微卡顿次数（34~50ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count2,
                "指标数值": label2,
            },
            {
                "测试场景": "输入法弹出动效-Trace",
                "测试指标": "明显卡顿次数（50~84ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count3,
                "指标数值": label3,
            },
            {
                "测试场景": "输入法弹出动效-Trace",
                "测试指标": "严重卡顿次数（>84ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count4,
                "指标数值": label4,
            },
            {
                "测试场景": "输入法弹出动效-Trace",
                "测试指标": "总卡顿次数（>33ms）/百次唤起",
                "标准(S/A/B)": "-",
                "指标值": count5,
                "指标数值": label5,
            },
            {
                "测试场景": "输入法弹出动效-Trace",
                "测试指标": "轻微卡顿次数（34~50ms）/百次唤起",
                "标准(S/A/B)": "-",
                "指标值": count6,
                "指标数值": label6,
            },
            {
                "测试场景": "输入法弹出动效-Trace",
                "测试指标": "明显卡顿次数（50~84ms）/百次唤起",
                "标准(S/A/B)": "-",
                "指标值": count7,
                "指标数值": label7,
            },
            {
                "测试场景": "输入法弹出动效-Trace",
                "测试指标": "严重卡顿次数（>84ms）/百次唤起",
                "标准(S/A/B)": "-",
                "指标值": count8,
                "指标数值": label8,
            },
        ]

    def startup_spend_log(self, summary_data):
        """应用启动耗时-log"""

        startup_data = summary_data.get("startup_data") or []

        values = []
        if startup_data:
            for start_spend_info in startup_data:
                # 安全获取，防止 get 返回 None 导致 split() 报错
                top_values_str = start_spend_info.get("Top Values")
                if top_values_str:
                    value_str_list = top_values_str.split(", ")
                    values.extend([int(float(x)) for x in value_str_list])

        all_counts = "-"
        all_avg = all_std = "-"
        count1 = count2 = count3 = count4 = count5 = "-"
        label1 = label2 = label3 = label4 = label5 = "-"

        if values:
            all_counts = len(values)  # 总次数
            # 整体平均值，标准差
            all_avg, all_std = _avg_and_std(values)
            # 应用启动耗时大于1.5s比例
            count1, label1 = _get_range_percent(values, 1500, None, 1, all_counts)
            # 应用启动耗时大于3.0s比例
            count2, label2 = _get_range_percent(values, 3000, None, 1, all_counts)
            # 轻微启动慢次数百分比
            count3, label3 = _get_range_percent(values, 1000, 2000, 100, all_counts)
            # 明显启动慢次数百分比
            count4, label4 = _get_range_percent(values, 2000, 3000, 100, all_counts)
            # 严重启动慢次数百分比
            count5, label5 = _get_range_percent(values, 3000, None, 100, all_counts)

        return [
            {
                "测试场景": "应用启动耗时-log",
                "测试指标": "应用启动总次数",
                "标准(S/A/B)": "-",
                "指标值": all_counts,
                "指标数值": all_counts,
            },
            {
                "测试场景": "应用启动耗时-log",
                "测试指标": "应用启动耗时平均值(ms)",
                "标准(S/A/B)": "-",
                "指标值": all_avg,
                "指标数值": all_avg,
            },
            {
                "测试场景": "应用启动耗时-log",
                "测试指标": "应用启动耗时标准差",
                "标准(S/A/B)": "-",
                "指标值": all_std,
                "指标数值": all_std,
            },
            {
                "测试场景": "应用启动耗时-log",
                "测试指标": "应用启动耗时大于1.5s比例",
                "标准(S/A/B)": "-",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": "应用启动耗时-log",
                "测试指标": "应用启动耗时大于3.0s比例",
                "标准(S/A/B)": "-",
                "指标值": count2,
                "指标数值": label2,
            },
            {
                "测试场景": "应用启动耗时-log",
                "测试指标": "轻微启动慢次数（1~2s）/百次启动",
                "标准(S/A/B)": "-",
                "指标值": count3,
                "指标数值": label3,
            },
            {
                "测试场景": "应用启动耗时-log",
                "测试指标": "明显启动慢次数（2~3s）/百次启动",
                "标准(S/A/B)": "-",
                "指标值": count4,
                "指标数值": label4,
            },
            {
                "测试场景": "应用启动耗时-log",
                "测试指标": "严重启动慢次数（>=3s）/百次启动",
                "标准(S/A/B)": "-",
                "指标值": count5,
                "指标数值": label5,
            },
        ]

    def click_transition_log(self, summary_data):
        """应用内点击转场-log"""

        click_data = summary_data.get("click_data") or []

        values = []
        if click_data:
            for click_spend_info in click_data:
                # 安全获取，防止 get 返回 None 导致 split() 报错
                top_values_str = click_spend_info.get("Top Values")
                if top_values_str:
                    value_str_list = top_values_str.split(", ")
                    values.extend([int(float(x)) for x in value_str_list])

        all_counts = all_avg = all_std = "-"
        count1 = count2 = count3 = count4 = count5 = "-"
        label1 = label2 = label3 = label4 = label5 = "-"

        if values:
            all_counts = len(values)  # 总次数
            # 整体平均值，标准差
            all_avg, all_std = _avg_and_std(values)
            # 应用启动耗时大于1.5s比例
            count1, label1 = _get_range_percent(values, 300, None, 1, all_counts)
            # 应用启动耗时大于3.0s比例
            count2, label2 = _get_range_percent(values, 600, None, 1, all_counts)
            # 轻微启动慢次数百分比
            count3, label3 = _get_range_percent(values, 155, 245, 100, all_counts)
            # 明显启动慢次数百分比
            count4, label4 = _get_range_percent(values, 245, 390, 100, all_counts)
            # 严重启动慢次数百分比
            count5, label5 = _get_range_percent(values, 390, None, 100, all_counts)

        return [
            {
                "测试场景": "应用内点击响应-log",
                "测试指标": "新窗口响应总次数",
                "标准(S/A/B)": "-",
                "指标值": all_counts,
                "指标数值": all_counts,
            },
            {
                "测试场景": "应用内点击响应-log",
                "测试指标": "新窗口响应平均值(ms)",
                "标准(S/A/B)": "-",
                "指标值": all_avg,
                "指标数值": all_avg,
            },
            {
                "测试场景": "应用内点击响应-log",
                "测试指标": "新窗口响应标准差",
                "标准(S/A/B)": "-",
                "指标值": all_std,
                "指标数值": all_std,
            },
            {
                "测试场景": "应用内点击响应-log",
                "测试指标": "新窗口响应大于0.3s比例",
                "标准(S/A/B)": "-",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": "应用内点击响应-log",
                "测试指标": "新窗口响应大于0.6s比例",
                "标准(S/A/B)": "-",
                "指标值": count2,
                "指标数值": label2,
            },
            {
                "测试场景": "应用内点击响应-log",
                "测试指标": "轻微响应延迟次数（155~245ms）/百次点击",
                "标准(S/A/B)": "-",
                "指标值": count3,
                "指标数值": label3,
            },
            {
                "测试场景": "应用内点击响应-log",
                "测试指标": "明显响应延迟次数（245~390ms）/百次点击",
                "标准(S/A/B)": "-",
                "指标值": count4,
                "指标数值": label4,
            },
            {
                "测试场景": "应用内点击响应-log",
                "测试指标": "严重响应延迟次数（>=390ms）/百次点击",
                "标准(S/A/B)": "-",
                "指标值": count5,
                "指标数值": label5,
            },
        ]

    def app_animator_log(self, summary_data, total_start_exit):
        """应用启动退出动效（性能雷达）"""

        total_bd_time = summary_data.get("total_bd_time") or 0
        bd_animator_counts = summary_data.get("bd_animator_counts") or []

        def _count(index):
            if index < len(bd_animator_counts):
                value = bd_animator_counts[index]
                return value if isinstance(value, (int, float)) else 0
            return 0

        action_total = (
            total_start_exit
            if isinstance(total_start_exit, (int, float))
            and not isinstance(total_start_exit, bool)
            else 0
        )
        all_counts = action_total if action_total > 0 else sum(bd_animator_counts)

        # Counts 为空通常表示没有卡顿。只要有操作次数，就显示 0，而不是横线。
        total_jank_count = jank_count(bd_animator_counts)
        slight_count = _count(1)
        obvious_count = _count(2)
        serious_count = sum(bd_animator_counts[2:]) if len(bd_animator_counts) > 2 else 0

        count1 = label1 = count2 = label2 = count3 = label3 = count4 = label4 = 0
        count5 = label5 = count6 = label6 = count7 = label7 = count8 = label8 = 0

        if all_counts > 0 or bd_animator_counts:
            time_hours = total_bd_time / 3600
            count1, label1 = _gen_count_and_label2(
                total_jank_count, time_hours, multiplier=1000
            )
            count2, label2 = _gen_count_and_label2(
                slight_count, time_hours, multiplier=1000
            )
            count3, label3 = _gen_count_and_label2(
                obvious_count, time_hours, multiplier=1000
            )
            count4, label4 = _gen_count_and_label2(
                serious_count, time_hours, multiplier=1000
            )
            count5, label5 = _gen_count_and_label2(
                total_jank_count, all_counts, multiplier=100
            )
            count6, label6 = _gen_count_and_label2(
                slight_count, all_counts, multiplier=100
            )
            count7, label7 = _gen_count_and_label2(
                obvious_count, all_counts, multiplier=100
            )
            count8, label8 = _gen_count_and_label2(
                serious_count, all_counts, multiplier=100
            )

        return [
            {
                "测试场景": "应用启动退出动效（性能雷达）",
                "测试指标": "总动效次数",
                "标准(S/A/B)": "-",
                "指标值": all_counts,
                "指标数值": all_counts,
            },
            {
                "测试场景": "应用启动退出动效（性能雷达）",
                "测试指标": "总卡顿次数（>50ms）/千小时",
                "标准(S/A/B)": "250/500",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": "应用启动退出动效（性能雷达）",
                "测试指标": "轻微卡顿次数（50~84ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count2,
                "指标数值": label2,
            },
            {
                "测试场景": "应用启动退出动效（性能雷达）",
                "测试指标": "明显卡顿次数（84~134ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count3,
                "指标数值": label3,
            },
            {
                "测试场景": "应用启动退出动效（性能雷达）",
                "测试指标": "严重卡顿次数（>84ms）/千小时",
                "标准(S/A/B)": "0/200",
                "指标值": count4,
                "指标数值": label4,
            },
            {
                "测试场景": "应用启动退出动效（性能雷达）",
                "测试指标": "总卡顿次数（>50ms）/百次启退",
                "标准(S/A/B)": "-",
                "指标值": count5,
                "指标数值": label5,
            },
            {
                "测试场景": "应用启动退出动效（性能雷达）",
                "测试指标": "轻微卡顿次数（50~84ms）/百次启退",
                "标准(S/A/B)": "-",
                "指标值": count6,
                "指标数值": label6,
            },
            {
                "测试场景": "应用启动退出动效（性能雷达）",
                "测试指标": "明显卡顿次数（84~134ms）/百次启退",
                "标准(S/A/B)": "-",
                "指标值": count7,
                "指标数值": label7,
            },
            {
                "测试场景": "应用启动退出动效（性能雷达）",
                "测试指标": "严重卡顿次数（>84ms）/百次启退",
                "标准(S/A/B)": "-",
                "指标值": count8,
                "指标数值": label8,
            },
        ]

    def app_swipe_log(self, summary_data, total_swipes):
        """应用内滑动（性能雷达7.0）"""
        bd_fluency_counts = summary_data.get("bd_fluency_counts") or []
        total_bd_time = summary_data.get("total_bd_time") or 0
        all_counts = total_swipes if isinstance(total_swipes, (int, float)) else 0

        def _count(index):
            if index < len(bd_fluency_counts):
                value = bd_fluency_counts[index]
                return value if isinstance(value, (int, float)) else 0
            return 0

        # Counts 为空通常表示没有卡顿。只要有操作次数，就显示 0，而不是横线。
        num_25_58 = _count(1)
        num_58_133 = _count(2) + _count(3)
        num_133 = sum(bd_fluency_counts[4:]) if len(bd_fluency_counts) > 4 else 0
        num_58 = sum(bd_fluency_counts[2:]) if len(bd_fluency_counts) > 2 else 0

        count1 = label1 = count2 = label2 = count3 = label3 = count4 = label4 = 0
        count5 = label5 = count6 = label6 = count7 = label7 = count8 = label8 = 0

        if all_counts > 0 or bd_fluency_counts:
            time_hours = total_bd_time / 3600
            count1, label1 = _gen_count_and_label2(
                num_25_58, time_hours, multiplier=1000
            )
            count2, label2 = _gen_count_and_label2(
                num_58_133, time_hours, multiplier=1000
            )
            count3, label3 = _gen_count_and_label2(
                num_133, time_hours, multiplier=1000
            )
            count4, label4 = _gen_count_and_label2(
                num_58, time_hours, multiplier=1000
            )
            count5, label5 = _gen_count_and_label2(
                num_25_58, all_counts, multiplier=100
            )
            count6, label6 = _gen_count_and_label2(
                num_58_133, all_counts, multiplier=100
            )
            count7, label7 = _gen_count_and_label2(
                num_133, all_counts, multiplier=100
            )
            count8, label8 = _gen_count_and_label2(
                num_58, all_counts, multiplier=100
            )

        return [
            {
                "测试场景": "应用内滑动（性能雷达7.0）",
                "测试指标": "总次数",
                "标准(S/A/B)": "-",
                "指标值": all_counts,
                "指标数值": all_counts,
            },
            {
                "测试场景": "应用内滑动（性能雷达7.0）",
                "测试指标": "轻微卡顿次数（25~58ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": "应用内滑动（性能雷达7.0）",
                "测试指标": "明显卡顿次数（58~133ms）/千小时",
                "标准(S/A/B)": "-",
                "指标值": count2,
                "指标数值": label2,
            },
            {
                "测试场景": "应用内滑动（性能雷达7.0）",
                "测试指标": "严重卡顿次数（>133ms）/千小时",
                "标准(S/A/B)": "0/200",
                "指标值": count3,
                "指标数值": label3,
            },
            {
                "测试场景": "应用内滑动（性能雷达7.0）",
                "测试指标": "明显+严重卡顿次数（>58ms）/千小时",
                "标准(S/A/B)": "500/2000",
                "指标值": count4,
                "指标数值": label4,
            },
            {
                "测试场景": "应用内滑动（性能雷达7.0）",
                "测试指标": "轻微卡顿次数（25~58ms）/百次滑动",
                "标准(S/A/B)": "-",
                "指标值": count5,
                "指标数值": label5,
            },
            {
                "测试场景": "应用内滑动（性能雷达7.0）",
                "测试指标": "明显卡顿次数（58~133ms）/百次滑动",
                "标准(S/A/B)": "-",
                "指标值": count6,
                "指标数值": label6,
            },
            {
                "测试场景": "应用内滑动（性能雷达7.0）",
                "测试指标": "严重卡顿次数（>133ms）/百次滑动",
                "标准(S/A/B)": "-",
                "指标值": count7,
                "指标数值": label7,
            },
            {
                "测试场景": "应用内滑动（性能雷达7.0）",
                "测试指标": "明显+严重卡顿次数（>58ms）/百次滑动",
                "标准(S/A/B)": "-",
                "指标值": count8,
                "指标数值": label8,
            },
        ]

    def io_misc_log(self, summary_data):
        """IO微观指标"""
        measure_summary = summary_data.get("measure_summary") or {}
        io_stat_summary = summary_data.get("io_stat_summary") or []

        count1 = count2 = count3 = "-"
        label1 = label2 = label3 = "-"

        if measure_summary:
            # FS层Read(>16ms)比例
            count1, label1 = _gen_count_and_label2(
                measure_summary.get("fs-read-16", 0),
                measure_summary.get("fs-read-all", 0),
                1,
                6,
            )
            # Block层Read(>16ms)比例
            count2, label2 = _gen_count_and_label2(
                measure_summary.get("blk-read-16", 0),
                measure_summary.get("blk-read-all", 0),
                1,
                6,
            )
            # Scsi层Read(>16ms)比例
            count3, label3 = _gen_count_and_label2(
                measure_summary.get("scsi-read-16", 0),
                measure_summary.get("scsi-read-all", 0),
                1,
                6,
            )

        r_sum = w_sum = discard_sum = 0
        r_count = w_count = discard_count = 0
        r_str_parts, w_str_parts, discard_str_parts = [], [], []

        if io_stat_summary:
            for item in io_stat_summary:
                if item.get("R-sectors") is not None:
                    r_sum += float(item["R-sectors"])
                    r_count += 1
                    r_str_parts.append(str(item["R-sectors"]))
                else:
                    r_str_parts.append("-")

                if item.get("W-sectors") is not None:
                    w_sum += float(item["W-sectors"])
                    w_count += 1
                    w_str_parts.append(str(item["W-sectors"]))
                else:
                    w_str_parts.append("-")

                if item.get("discard-sectors") is not None:
                    discard_sum += float(item["discard-sectors"])
                    discard_count += 1
                    discard_str_parts.append(str(item["discard-sectors"]))
                else:
                    discard_str_parts.append("-")

        # 4. 计算平均值，如果没有数据则统一返回 "-" 而不是 0.0
        avg_r_sectors = round((r_sum / r_count), 2) if r_count > 0 else "-"
        avg_w_sectors = round((w_sum / w_count), 2) if w_count > 0 else "-"
        avg_discard_sectors = (
            round((discard_sum / discard_count), 2) if discard_count > 0 else "-"
        )

        # 拼接字符串，如果没有数据则返回 "-"
        r_sectors_string = "/".join(r_str_parts) if r_str_parts else "-"
        w_sectors_string = "/".join(w_str_parts) if w_str_parts else "-"
        discard_sectors_string = (
            "/".join(discard_str_parts) if discard_str_parts else "-"
        )

        return [
            {
                "测试场景": "IO微观指标",
                "测试指标": "FS层Read(>16ms)比例",
                "标准(S/A/B)": "-",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": "IO微观指标",
                "测试指标": "Block层Read(>16ms)比例",
                "标准(S/A/B)": "-",
                "指标值": count2,
                "指标数值": label2,
            },
            {
                "测试场景": "IO微观指标",
                "测试指标": "Scsi层Read(>16ms)比例",
                "标准(S/A/B)": "-",
                "指标值": count3,
                "指标数值": label3,
            },
            {
                "测试场景": "IO微观指标",
                "测试指标": "R-sectors",
                "标准(S/A/B)": "-",
                "指标值": avg_r_sectors,
                "指标数值": r_sectors_string,
            },
            {
                "测试场景": "IO微观指标",
                "测试指标": "W-sectors",
                "标准(S/A/B)": "-",
                "指标值": avg_w_sectors,
                "指标数值": w_sectors_string,
            },
            {
                "测试场景": "IO微观指标",
                "测试指标": "discard-sectors",
                "标准(S/A/B)": "-",
                "指标值": avg_discard_sectors,
                "指标数值": discard_sectors_string,
            },
        ]

    def memory_misc_log(self, summary_data):
        """内存微观指标"""

        proc_summary = summary_data.get("proc_summary") or {}

        mem_mean_value = mem_free_mean_value = ac_anon_mean_value = "-"
        inac_anon_mean_value = ac_file_mean_value = inac_file_mean_value = (
            slab_mean_value
        ) = "-"
        mem_mean_string = mem_free_mean_string = ac_anon_mean_string = "-"
        inac_anon_mean_string = ac_file_mean_string = inac_file_mean_string = (
            slab_mean_string
        ) = "-"

        wset_anon_mean = wset_file_mean = khigh_sum = klow_sum = "-"

        if proc_summary:

            def _get_mem_stats(key):
                data = proc_summary.get(key)
                if data:
                    mean_val, _ = _avg_and_std(data)
                    # 确保 mean_val 是数字才能进行数学计算
                    if isinstance(mean_val, (int, float)):
                        return round(mean_val / 1024, 2), f"{mean_val} / 1024"
                return "-", "-"

            mem_mean_value, mem_mean_string = _get_mem_stats("MemAvailable")
            mem_free_mean_value, mem_free_mean_string = _get_mem_stats("MemFree")
            ac_anon_mean_value, ac_anon_mean_string = _get_mem_stats("Active(anon)")
            inac_anon_mean_value, inac_anon_mean_string = _get_mem_stats(
                "Inactive(anon)"
            )
            ac_file_mean_value, ac_file_mean_string = _get_mem_stats("Active(file)")
            inac_file_mean_value, inac_file_mean_string = _get_mem_stats(
                "Inactive(file)"
            )
            slab_mean_value, slab_mean_string = _get_mem_stats("Slab")

            # 安全获取并计算 workingset
            wset_anon_data = proc_summary.get("workingset_refault_anon")
            if wset_anon_data:
                wset_anon_mean, _ = _avg_and_std(wset_anon_data)

            wset_file_data = proc_summary.get("workingset_refault_file")
            if wset_file_data:
                wset_file_mean, _ = _avg_and_std(wset_file_data)

            # 安全获取并累加 kswapd (加入 float 转换防止字符串报错)
            khigh_data = proc_summary.get("kswapd_high_wmark_hit_quickly")
            if khigh_data:
                khigh_sum = sum([float(x) for x in khigh_data])

            klow_data = proc_summary.get("kswapd_low_wmark_hit_quickly")
            if klow_data:
                klow_sum = sum([float(x) for x in klow_data])

        return [
            {
                "测试场景": "Memory微观指标",
                "测试指标": "MemAvailable 均值",
                "标准(S/A/B)": "-",
                "指标值": mem_mean_value,
                "指标数值": mem_mean_string,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "MemFree 均值",
                "标准(S/A/B)": "-",
                "指标值": mem_free_mean_value,
                "指标数值": mem_free_mean_string,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "Active(anon) 均值",
                "标准(S/A/B)": "-",
                "指标值": ac_anon_mean_value,
                "指标数值": ac_anon_mean_string,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "Inactive(anon) 均值",
                "标准(S/A/B)": "-",
                "指标值": inac_anon_mean_value,
                "指标数值": inac_anon_mean_string,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "Active(file) 均值",
                "标准(S/A/B)": "-",
                "指标值": ac_file_mean_value,
                "指标数值": ac_file_mean_string,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "Inactive(file) 均值",
                "标准(S/A/B)": "-",
                "指标值": inac_file_mean_value,
                "指标数值": inac_file_mean_string,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "Slab 均值",
                "标准(S/A/B)": "-",
                "指标值": slab_mean_value,
                "指标数值": slab_mean_string,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "workingset_refault_anon 均值",
                "标准(S/A/B)": "-",
                "指标值": wset_anon_mean,
                "指标数值": wset_anon_mean,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "workingset_refault_file 均值",
                "标准(S/A/B)": "-",
                "指标值": wset_file_mean,
                "指标数值": wset_file_mean,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "kswapd_high_wmark_hit_quickly 累加值",
                "标准(S/A/B)": "-",
                "指标值": khigh_sum,
                "指标数值": khigh_sum,
            },
            {
                "测试场景": "Memory微观指标",
                "测试指标": "kswapd_low_wmark_hit_quickly 累加值",
                "标准(S/A/B)": "-",
                "指标值": klow_sum,
                "指标数值": klow_sum,
            },
        ]

    def keyboard_jank_log(self, total_time, summary_data):
        """输入法按键卡顿"""
        jank_summary = summary_data.get("jank_summary")

        count1 = count2 = "-"
        label1 = label2 = "-"

        if jank_summary:
            total_type_jank_numbers = int(float(jank_summary))

            count1 = label1 = total_type_jank_numbers
            # 总卡顿次数/千小时
            if total_time:
                time_hours = total_time / 3600
                # 总卡顿次数/千小时
                count2, label2 = _gen_count_and_label2(
                    total_type_jank_numbers, time_hours, multiplier=1000
                )

        return [
            {
                "测试场景": "输入法按键卡顿-Jlog",
                "测试指标": "总卡顿次数",
                "标准(S/A/B)": "-",
                "指标值": count1,
                "指标数值": label1,
            },
            {
                "测试场景": "输入法按键卡顿-Jlog",
                "测试指标": "总卡顿次数/千小时",
                "标准(S/A/B)": "-",
                "指标值": count2,
                "指标数值": label2,
            },
        ]

    def insert_summary_line(self, sheet_name, summary_dict, merge_cols=5):
        """
        在sheet最上面插入一行汇总信息
        """
        ws = self.excel.sheet_map[sheet_name]

        if summary_dict is None:
            summary_text = ""
        else:
            # 第一行：原汇总信息（不包含devices）
            summary_items = []
            devices = summary_dict.get("devices", {})
            for k, v in summary_dict.items():
                if k != "devices":
                    summary_items.append(f"{k}: {v}")

            lines = [" | ".join(summary_items)]

            # 后面每个设备一行
            for sn, info in devices.items():
                model = info.get("model", "")
                brand = info.get("brand", "")
                system_version = info.get("system_version", "")
                mem_total = info.get("mem_total", "")
                storage_size = info.get("storage_size", "")
                lines.append(
                    f"{sn} | {brand} {model} | {system_version} | {mem_total} + {storage_size}"
                )

            summary_text = "\n".join(lines)

        cell = ws.cell(row=1, column=1, value=summary_text)
        cell.font = Font(name="等线", size=11, bold=True)
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

        ws.merge_cells(
            start_row=1,
            start_column=1,
            end_row=1,
            end_column=merge_cols,
        )

        # 根据换行数自动调整行高
        line_count = summary_text.count("\n") + 1
        ws.row_dimensions[1].height = line_count * 18
