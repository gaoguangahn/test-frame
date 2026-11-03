from __future__ import annotations

import hashlib
import re


def safe_path_name(value: str, *, max_length: int = 120) -> str:
    """将文本转换为跨平台安全的目录名或文件名前缀。"""
    normalized = re.sub(r'[\\/:*?"<>|\[\]]+', "_", value)
    normalized = re.sub(r"_+", "_", normalized).strip("._ ")

    if not normalized:
        normalized = "unnamed"

    if len(normalized) <= max_length:
        return normalized

    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{normalized[: max_length - 11]}_{digest}"
