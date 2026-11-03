from __future__ import annotations

import argparse
from pathlib import Path

from .report_generate import ReportGenerator


def main() -> int:
    parser = argparse.ArgumentParser(description="生成动态模型 Excel 报告")
    parser.add_argument(
        "--task-dir",
        required=True,
        help="dynamic runner 输出目录，目录下必须包含 runner_result.json。",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Excel 报告输出路径。",
    )
    parser.add_argument(
        "--serial",
        action="append",
        default=None,
        help="按 main 设备序列号筛选，可重复传入。默认包含 runner 下全部设备。",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=None,
        help="按轮次筛选。默认包含全部轮次。",
    )

    args = parser.parse_args()

    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    reporter = ReportGenerator()
    reporter.load_report_data(
        task_dir=args.task_dir,
        serial=args.serial,
        round=args.round,
    )
    reporter.generate_report(output_file=output_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
