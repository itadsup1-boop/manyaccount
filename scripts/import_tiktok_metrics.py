#!/usr/bin/env python3
"""Import TikTok performance snapshots from CSV, JSON, JSONL or Sheet CSV."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.core.performance_analyzer import (  # noqa: E402
    analyze_performance,
    normalize_performance_record,
)
from shared.services.performance_store import (  # noqa: E402
    DEFAULT_PERFORMANCE_DB,
    PerformanceStore,
)


@dataclass(frozen=True)
class ImportSummary:
    input_rows: int
    valid_rows: int
    rejected_rows: int
    unique_snapshots: int
    stored_rows: int
    dry_run: bool
    errors: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rows_from_text(text: str, source_name: str = "") -> list[dict[str, Any]]:
    suffix = os.path.splitext(source_name.lower())[1]
    stripped = text.lstrip("\ufeff\n\r\t ")
    if suffix in {".jsonl", ".ndjson"}:
        rows = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, Mapping):
                raise ValueError(f"JSONL line {line_number} is not an object")
            rows.append(dict(item))
        return rows
    if suffix == ".json" or stripped.startswith(("[", "{")):
        payload = json.loads(stripped or "[]")
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, Mapping)]
        if isinstance(payload, Mapping):
            for key in ("data", "rows", "items", "videos"):
                items = payload.get(key)
                if isinstance(items, list):
                    return [dict(item) for item in items if isinstance(item, Mapping)]
            return [dict(payload)]
        raise ValueError("JSON metrics must contain an object or array")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [dict(row) for row in csv.DictReader(io.StringIO(text), dialect=dialect)]


def load_metric_rows(
    *,
    input_path: str = "",
    sheet_csv_url: str = "",
) -> tuple[list[dict[str, Any]], str]:
    if bool(input_path) == bool(sheet_csv_url):
        raise ValueError("Provide exactly one of input_path or sheet_csv_url")
    if sheet_csv_url:
        if not str(sheet_csv_url).startswith("https://"):
            raise ValueError("Sheet CSV URL must use HTTPS")
        request = Request(sheet_csv_url, headers={"User-Agent": "MannyMetricsImporter/1.0"})
        with urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8-sig")
        return _rows_from_text(text, "sheet.csv"), sheet_csv_url
    path = os.path.abspath(input_path)
    if not os.path.isfile(path):
        raise ValueError(f"Input file does not exist: {path}")
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        return _rows_from_text(file.read(), path), path


def import_metric_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    store: PerformanceStore | None,
    defaults: Mapping[str, Any] | None = None,
    strict: bool = False,
    dry_run: bool = False,
) -> tuple[ImportSummary, list[dict[str, Any]]]:
    raw_rows = list(rows)
    canonical: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row_number, row in enumerate(raw_rows, 2):
        try:
            canonical.append(normalize_performance_record(row, defaults=defaults))
        except (TypeError, ValueError) as error:
            errors.append({"row": row_number, "error": str(error)})
    if strict and errors:
        raise ValueError(json.dumps(errors, ensure_ascii=False))
    if not dry_run:
        if store is None:
            raise ValueError("PerformanceStore is required unless dry_run=True")
        store.upsert_many(canonical)
    summary = ImportSummary(
        input_rows=len(raw_rows),
        valid_rows=len(canonical),
        rejected_rows=len(errors),
        unique_snapshots=len({item["snapshot_key"] for item in canonical}),
        stored_rows=0 if dry_run or store is None else store.count(),
        dry_run=bool(dry_run),
        errors=tuple(errors[:100]),
    )
    return summary, canonical


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Local .csv, .json or .jsonl file")
    source.add_argument("--sheet-csv-url", help="HTTPS Google Sheet export CSV URL")
    parser.add_argument("--db", default=DEFAULT_PERFORMANCE_DB)
    parser.add_argument("--channel-id", default="")
    parser.add_argument("--source-type", default="tiktok")
    parser.add_argument("--measured-at", default="")
    parser.add_argument("--measurement-window", default="")
    parser.add_argument("--strict", action="store_true", help="Reject the whole import if one row is invalid")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing SQLite")
    parser.add_argument("--report-json", default="", help="Optional path for the import/analysis report")
    parser.add_argument("--min-samples", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    rows, source_name = load_metric_rows(
        input_path=args.input or "",
        sheet_csv_url=args.sheet_csv_url or "",
    )
    defaults = {
        "channel_id": args.channel_id,
        "source_type": args.source_type,
        "measured_at": args.measured_at,
        "measurement_window": args.measurement_window,
        "import_source": source_name,
    }
    store = None if args.dry_run else PerformanceStore(args.db)
    try:
        summary, canonical = import_metric_rows(
            rows,
            store=store,
            defaults=defaults,
            strict=args.strict,
            dry_run=args.dry_run,
        )
        analysis_rows = (
            canonical if store is None else store.list_measurements(limit=100_000)
        )
    finally:
        if store is not None:
            store.close()
    report = {
        "import": summary.to_dict(),
        "performance": analyze_performance(
            analysis_rows,
            min_samples=max(1, args.min_samples),
        ),
    }
    if args.report_json:
        report_path = os.path.abspath(args.report_json)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
    console_report = {
        "import": report["import"],
        "status": report["performance"]["status"],
        "overview": report["performance"]["overview"],
        "snapshot_anomaly_count": len(
            report["performance"]["snapshot_anomalies"]
        ),
        "full_report": os.path.abspath(args.report_json) if args.report_json else "",
    }
    print(json.dumps(console_report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
