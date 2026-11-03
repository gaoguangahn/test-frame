import os
import re
import time


def split_jlog_by_keywords(src_path: str) -> None:
    """
    把指定 src_path（例如 1_jank_raw.log）按照 jlog_map 里的关键词拆分到各自文件
    行为：
    - 新文件保存在原文件所在目录
    - 文件名：{loop_name}_{filename}，例如：1_JLOG396.log、1_JLOG475.log ...
    - 解析结束后删除原始 *_jank_raw.log
    """
    jlog_map = {
        ("JLOG396", "lmk"): "JLOG396.log",
        "JLOG475": "JLOG475.log",
        "JLOG480": "JLOG480.log",
        "JLOG413": "JLOG413.log",
    }

    jlog413_pattern = re.compile(
        r".*?\[JLOG413]: #ARG1:<([^>]*)>#ARG2:<(\d+)>#ARG3:<(\d+)>"
    )
    if not os.path.exists(src_path):
        return

    base_name = os.path.basename(src_path)
    loop_name = base_name.split("_", 1)[0]
    out_dir = os.path.dirname(src_path)

    file_handles = {}
    try:
        # 打开目标文件句柄（每个 tag 一个文件）
        for filename in set(jlog_map.values()):
            dst_path = os.path.join(out_dir, f"{loop_name}_{filename}")
            file_handles[filename] = open(dst_path, "w", encoding="utf-8")

        # 预处理 jlog_map -> [(kws_list, fname), ...]
        rules = []
        for kws, fname in jlog_map.items():
            if kws == "JLOG413":
                continue

            if isinstance(kws, str):
                kws_list = [kws]
            elif isinstance(kws, tuple):
                kws_list = list(kws)
            else:
                try:
                    kws_list = list(kws)
                except TypeError:
                    kws_list = [str(kws)]
            rules.append((kws_list, fname))

        with open(src_path, "r", encoding="utf-8", errors="ignore") as src:
            for line in src:
                line_stripped = line.rstrip("\n")

                if jlog413_pattern.match(line_stripped):
                    f = file_handles.get("JLOG413.log")
                    if f:
                        f.write(line)
                    continue

                for kws_list, fname in rules:
                    if all(kw in line_stripped for kw in kws_list):
                        f = file_handles.get(fname)
                        if f:
                            f.write(line)
                        break

    except Exception as e:
        print(f"{time.strftime('%Y:%m:%d %H:%M:%S')} - jlog 拆分失败: {e}")
    finally:
        for f in file_handles.values():
            try:
                f.close()
            except Exception:
                pass
        # 解析结束后删除原始 *_jank_raw.log
        # try:
        #     if os.path.exists(src_path):
        #         os.remove(src_path)
        # except Exception:
        #     pass


def split_all_jank_raw_in_dir(raw_dir: str) -> None:
    """
    扫描 raw_dir 下所有 *_jank_raw.log，分别拆分。
    """
    if not os.path.isdir(raw_dir):
        return

    for name in os.listdir(raw_dir):
        if not name.endswith("_jank_raw.log"):
            continue

        src_path = os.path.join(raw_dir, name)
        split_jlog_by_keywords(src_path)


if __name__ == "__main__":
    split_all_jank_raw_in_dir(
        r"D:\ptrace_analysis\exfw\output\test_02\ASPS015928000498\perf_logs\Jlogs"
    )
