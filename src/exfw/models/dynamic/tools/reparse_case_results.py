from __future__ import annotations

import argparse
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from exfw.models.dynamic.analyse.log_parser_dispatcher import LogParserDispatcher
from exfw.models.dynamic.analyse.trace_parser_dispatcher import TraceParserDispatcher
from exfw.models.dynamic.report.data.data_loader import (
    discover_runner_report_tasks,
    load_runner_result,
    normalize_serial_filter,
)
from exfw.models.dynamic.server_config import CASE_RESULT_SERVER

LOGGER = logging.getLogger("exfw.dynamic.reparse_case_results")


@dataclass(frozen=True)
class ReparseCaseItem:
    task_id: str
    serial: str | None
    round: int | None
    case_name: str
    task_dir: Path
    artifact_dir: Path
    logs_dir: Path
    traces_dir: Path


class CaseResultReparseClient:
    def __init__(self, case_results_url: str, timeout: float = 30.0) -> None:
        self.case_results_url = case_results_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def close(self) -> None:
        self.session.close()

    def list_case_results(
        self,
        *,
        task_id: str,
        serial: str | None,
        round_value: int | None,
        case_name: str,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "task_id": task_id,
            "case": case_name,
            "limit": limit,
        }
        if serial:
            params["serial"] = serial
        if round_value is not None:
            params["round"] = round_value

        response = self.session.get(
            self.case_results_url,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return _extract_response_list(payload)

    def get_case_result(self, result_id: int) -> dict[str, Any]:
        response = self.session.get(
            f"{self.case_results_url}/{result_id}",
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return _extract_response_object(payload)

    def update_case_result(
        self,
        result_id: int,
        update_payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.session.put(
            f"{self.case_results_url}/{result_id}",
            json=update_payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return _extract_response_object(payload)


class HistoricalCaseReparser:
    def __init__(
        self,
        *,
        mode: str,
        brand: str,
        parse_workers: int,
        client: CaseResultReparseClient | None,
        upload: bool,
        check_server: bool,
        backup_dir: Path | None,
    ) -> None:
        self.mode = mode
        self.brand = brand
        self.client = client
        self.upload = upload
        self.check_server = check_server or upload
        self.backup_dir = backup_dir

        self.parse_executor = ThreadPoolExecutor(
            max_workers=max(1, parse_workers),
            thread_name_prefix="historical-reparse",
        )
        self.log_parser = LogParserDispatcher(executor=self.parse_executor)
        self.trace_parser = TraceParserDispatcher(executor=self.parse_executor)

    def close(self) -> None:
        self.parse_executor.shutdown(wait=True)

    def reparse_case(self, item: ReparseCaseItem) -> dict[str, Any]:
        item_summary: dict[str, Any] = {
            "task_id": item.task_id,
            "serial": item.serial,
            "round": item.round,
            "case": item.case_name,
            "artifact_dir": str(item.artifact_dir),
            "logs_dir": str(item.logs_dir),
            "traces_dir": str(item.traces_dir),
            "updated": False,
            "server_status": "not_checked",
            "errors": [],
        }

        update_payload: dict[str, Any] = {}

        if self.mode in {"all", "log"}:
            if item.logs_dir.is_dir():
                log_result = self.log_parser.parse(item.logs_dir, brand=self.brand)
                update_payload["log_result"] = log_result
                item_summary["log_result_count"] = len(log_result)
            else:
                item_summary["log_result_count"] = None
                item_summary["errors"].append(f"logs dir not found: {item.logs_dir}")

        if self.mode in {"all", "trace"}:
            if item.traces_dir.is_dir():
                trace_result = self.trace_parser.parse(
                    item.traces_dir, brand=self.brand
                )
                update_payload["trace_result"] = trace_result
                item_summary["trace_result_count"] = len(trace_result)
            else:
                item_summary["trace_result_count"] = None
                item_summary["errors"].append(
                    f"traces dir not found: {item.traces_dir}"
                )

        if not update_payload:
            item_summary["status"] = "skipped_no_update_payload"
            self._write_case_backup(item, "after_payload", update_payload)
            return item_summary

        self._write_case_backup(item, "after_payload", update_payload)

        if not self.check_server:
            item_summary["status"] = "parsed_only"
            return item_summary

        if self.client is None:
            item_summary["status"] = "failed_no_client"
            item_summary["errors"].append("server check/upload requires client")
            return item_summary

        try:
            records = self.client.list_case_results(
                task_id=item.task_id,
                serial=item.serial,
                round_value=item.round,
                case_name=item.case_name,
            )
        except Exception as error:
            item_summary["status"] = "failed_server_query"
            item_summary["server_status"] = "query_failed"
            item_summary["errors"].append(str(error))
            return item_summary

        item_summary["server_match_count"] = len(records)

        if len(records) != 1:
            item_summary["status"] = "skipped_server_match_not_unique"
            item_summary["server_status"] = (
                "not_found" if not records else "multiple_found"
            )
            return item_summary

        result_id = records[0].get("id")
        if not isinstance(result_id, int):
            item_summary["status"] = "skipped_invalid_result_id"
            item_summary["server_status"] = "invalid_result_id"
            return item_summary

        item_summary["result_id"] = result_id
        item_summary["server_status"] = "matched"

        if not self.upload:
            item_summary["status"] = "dry_run_matched"
            return item_summary

        try:
            before = self.client.get_case_result(result_id)
            self._write_case_backup(item, f"before_{result_id}", before)
            updated = self.client.update_case_result(result_id, update_payload)
            self._write_case_backup(item, f"updated_{result_id}", updated)
        except Exception as error:
            item_summary["status"] = "failed_update"
            item_summary["errors"].append(str(error))
            return item_summary

        item_summary["status"] = "updated"
        item_summary["updated"] = True
        return item_summary

    def _write_case_backup(
        self,
        item: ReparseCaseItem,
        name: str,
        data: Any,
    ) -> None:
        if self.backup_dir is None:
            return

        case_dir = self.backup_dir / _safe_filename(
            f"{item.serial or 'unknown'}_round_{item.round}_{item.case_name}"
        )
        case_dir.mkdir(parents=True, exist_ok=True)
        _write_json(case_dir / f"{name}.json", data)


def iter_reparse_cases(
    *,
    runner_output_dir: str | Path,
    serial_filter: set[str] | None,
    round_filter: int | None,
    case_filter: set[str] | None,
) -> list[ReparseCaseItem]:
    runner_result = load_runner_result(runner_output_dir)
    tasks = discover_runner_report_tasks(
        runner_output_dir=runner_output_dir,
        runner_result=runner_result,
        serial_filter=serial_filter,
    )

    items: list[ReparseCaseItem] = []

    for task in tasks:
        cases = task.session_data.get("cases") or []
        if not isinstance(cases, list):
            continue

        for case in cases:
            if not isinstance(case, dict):
                continue

            case_name = (
                case.get("case_name") or case.get("case_id") or case.get("nodeid")
            )
            if not isinstance(case_name, str) or not case_name:
                continue

            case_round = case.get("round")
            if round_filter is not None and case_round != round_filter:
                continue

            if case_filter is not None and case_name not in case_filter:
                continue

            artifact_dir_value = case.get("artifact_dir")
            if not isinstance(artifact_dir_value, str) or not artifact_dir_value:
                continue

            artifact_dir = task.task_dir / Path(artifact_dir_value.replace("\\", "/"))

            items.append(
                ReparseCaseItem(
                    task_id=task.task_id,
                    serial=task.main_serial,
                    round=case_round if isinstance(case_round, int) else None,
                    case_name=case_name,
                    task_dir=task.task_dir,
                    artifact_dir=artifact_dir,
                    logs_dir=artifact_dir / "logs",
                    traces_dir=artifact_dir / "traces",
                )
            )

    return items


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Re-parse historical dynamic test artifacts with current parsers and "
            "optionally update case_result records on the server."
        )
    )
    parser.add_argument("--runner-output-dir", required=True)
    parser.add_argument("--mode", choices=("all", "trace", "log"), default="all")
    parser.add_argument("--serial", action="append", default=None)
    parser.add_argument("--round", type=int, default=None, dest="round_filter")
    parser.add_argument("--case", action="append", default=None, dest="case_filter")
    parser.add_argument("--brand", default="Honor")
    parser.add_argument("--parse-workers", type=int, default=8)
    parser.add_argument("--case-results-url", default=CASE_RESULT_SERVER.upload_url)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument(
        "--check-server",
        action="store_true",
        help="Query server to check whether each local case maps to one remote record.",
    )
    parser.add_argument("--backup-dir", default=None)
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--summary-file", default=None)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    runner_output_dir = Path(args.runner_output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.no_backup:
        backup_dir = None
    elif args.backup_dir:
        backup_dir = Path(args.backup_dir)
    else:
        backup_dir = runner_output_dir / "reparse_outputs" / timestamp

    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)

    serial_filter = normalize_serial_filter(args.serial)
    case_filter = set(args.case_filter) if args.case_filter else None

    items = iter_reparse_cases(
        runner_output_dir=runner_output_dir,
        serial_filter=serial_filter,
        round_filter=args.round_filter,
        case_filter=case_filter,
    )

    client: CaseResultReparseClient | None = None
    if args.upload or args.check_server:
        client = CaseResultReparseClient(
            case_results_url=args.case_results_url,
            timeout=args.timeout,
        )

    reparser = HistoricalCaseReparser(
        mode=args.mode,
        brand=args.brand,
        parse_workers=args.parse_workers,
        client=client,
        upload=args.upload,
        check_server=args.check_server,
        backup_dir=backup_dir,
    )

    summary: dict[str, Any] = {
        "runner_output_dir": str(runner_output_dir),
        "mode": args.mode,
        "upload": args.upload,
        "check_server": args.check_server or args.upload,
        "case_results_url": args.case_results_url,
        "backup_dir": str(backup_dir) if backup_dir else None,
        "total": len(items),
        "items": [],
    }

    try:
        for index, item in enumerate(items, start=1):
            LOGGER.info(
                "Reparsing [%s/%s] serial=%s round=%s case=%s",
                index,
                len(items),
                item.serial,
                item.round,
                item.case_name,
            )
            item_summary = reparser.reparse_case(item)
            summary["items"].append(item_summary)
            LOGGER.info(
                "Done case=%s status=%s updated=%s",
                item.case_name,
                item_summary.get("status"),
                item_summary.get("updated"),
            )
    finally:
        reparser.close()
        if client is not None:
            client.close()

    _fill_summary_counts(summary)

    summary_file = Path(args.summary_file) if args.summary_file else None
    if summary_file is None and backup_dir is not None:
        summary_file = backup_dir / "summary.json"

    if summary_file is not None:
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        _write_json(summary_file, summary)
        LOGGER.info("Summary written to %s", summary_file)
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if summary.get("failed", 0) == 0 else 1


def _fill_summary_counts(summary: dict[str, Any]) -> None:
    items = summary.get("items") or []
    summary["updated"] = sum(1 for item in items if item.get("updated") is True)
    summary["failed"] = sum(
        1 for item in items if str(item.get("status", "")).startswith("failed")
    )
    summary["skipped"] = sum(
        1 for item in items if str(item.get("status", "")).startswith("skipped")
    )
    summary["dry_run_matched"] = sum(
        1 for item in items if item.get("status") == "dry_run_matched"
    )
    summary["parsed_only"] = sum(
        1 for item in items if item.get("status") == "parsed_only"
    )


def _extract_response_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    raise TypeError(f"Unexpected list response payload: {type(payload).__name__}")


def _extract_response_object(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    raise TypeError(f"Unexpected object response payload: {type(payload).__name__}")


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", value)
    return safe[:180] or "case"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(_json_safe(data), file, ensure_ascii=False, indent=2)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
