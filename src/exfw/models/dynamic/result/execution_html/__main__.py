"""从已有运行目录生成执行结果 HTML，不执行性能解析。"""
import argparse
from .render import generate_execution_html


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成动态模型执行结果 HTML")
    parser.add_argument("--task-dir", required=True, help="包含 task_result.json 的本次 runner 结果目录")
    args = parser.parse_args(argv)
    try:
        output = generate_execution_html(args.task_dir)
    except (OSError, ValueError) as error:
        parser.exit(1, f"生成执行结果失败：{error}\n")
    print(f"执行结果：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
