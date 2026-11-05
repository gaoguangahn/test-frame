from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .path import safe_path_name


@dataclass(frozen=True)
class CaseArtifacts:
    """当前用例的通用产物路径。"""

    root_dir: Path
    run_dir: Path
    case_dir: Path
    round_no: int
    case_id: str


def build_run_artifact_dir(
    *,
    output_dir: Path,
    round_no: int,
    use_round_dir: bool,
) -> Path:
    """按当前执行模式返回本次执行产物目录。"""
    if use_round_dir:
        return output_dir / f"round_{round_no:03d}"

    return output_dir


def build_case_artifacts(
    *,
    output_dir: Path,
    round_no: int,
    nodeid: str,
    use_round_dir: bool,
) -> CaseArtifacts:
    """返回统一用例产物路径；不提前创建目录。"""
    run_dir = build_run_artifact_dir(
        output_dir=output_dir,
        round_no=round_no,
        use_round_dir=use_round_dir,
    )
    case_id = build_case_id(nodeid)
    case_dir = run_dir / case_id

    return CaseArtifacts(
        root_dir=output_dir,
        run_dir=run_dir,
        case_dir=case_dir,
        round_no=round_no,
        case_id=case_id,
    )


def build_case_id(nodeid: str) -> str:
    """根据 pytest nodeid 生成简洁且稳定的用例产物标识。

    目录名优先使用 pytest 方法名，方便和报告中的 case 名称对应；同时追加
    nodeid 的短哈希，避免不同类/文件中同名方法或参数化用例发生目录冲突。
    """
    parts = nodeid.split("::")
    method_name = parts[-1]
    digest = hashlib.sha1(nodeid.encode("utf-8")).hexdigest()[:8]
    case_name = f"{method_name}__{digest}"

    return safe_path_name(case_name, max_length=80)
