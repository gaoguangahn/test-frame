"""项目 YAML 的加载与路径处理，不依赖 pytest 或具体模型。"""
from pathlib import Path
from typing import Any
import yaml


def find_project_config(start: Path) -> Path:
    start = Path(start).resolve()
    for directory in (start, *start.parents):
        candidate = directory / "project.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"未找到 project.yaml（从 {start} 向上查找）；请使用 --project-config 指定。")


def resolve_project_path(project_root: Path, raw_path: str) -> Path:
    value = raw_path.strip()
    if not value:
        raise ValueError("路径不能为空。")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def load_project_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"配置文件不存在：{path}")
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise TypeError("YAML 根节点必须是映射对象。")
    if data.get("testbeds") is not None and not isinstance(data["testbeds"], dict):
        raise TypeError("配置中的 testbeds 必须是映射对象。")
    return data
