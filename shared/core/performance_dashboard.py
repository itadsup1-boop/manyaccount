"""Build dashboard-ready performance and pipeline quality summaries."""

from __future__ import annotations

import json
from collections import Counter, deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from shared.core.performance_analyzer import (
    aggregate_performance,
    analyze_performance,
    latest_snapshots,
)
from shared.core.quality_log import DEFAULT_QUALITY_LOG_PATH
from shared.services.performance_store import DEFAULT_PERFORMANCE_DB, PerformanceStore


DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
MAX_DASHBOARD_RECORDS = 100_000
SUCCESS_STATUSES = {"uploaded", "published", "measured"}


def _parse_date(value: str, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"INVALID_{field.upper()}") from exc


def _local_date(value: Any, timezone_name: str) -> date | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo(timezone_name)).date()


def _matches_date_range(
    value: Any,
    start_date: date | None,
    end_date: date | None,
    timezone_name: str,
) -> bool:
    if start_date is None and end_date is None:
        return True
    local_day = _local_date(value, timezone_name)
    if local_day is None:
        return False
    if start_date is not None and local_day < start_date:
        return False
    return end_date is None or local_day <= end_date


def _value_counts(values: Iterable[Any]) -> list[dict[str, Any]]:
    counts = Counter(str(value or "unknown") for value in values)
    return [
        {"value": value, "count": count}
        for value, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0].casefold())
        )
    ]


def _available_values(records: Sequence[Mapping[str, Any]], field: str) -> list[str]:
    return sorted(
        {
            str(record.get(field, "")).strip()
            for record in records
            if str(record.get(field, "")).strip()
        },
        key=str.casefold,
    )


def read_quality_events(
    path: str | Path = DEFAULT_QUALITY_LOG_PATH,
    limit: int = MAX_DASHBOARD_RECORDS,
) -> tuple[list[dict[str, Any]], int]:
    """Read JSONL quality events without creating or mutating the runtime file."""

    quality_path = Path(path)
    if not quality_path.exists():
        return [], 0

    events: deque[dict[str, Any]] = deque(maxlen=max(1, limit))
    malformed = 0
    with quality_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                malformed += 1
                continue
            if isinstance(event, dict):
                events.append(event)
            else:
                malformed += 1
    return list(events), malformed


def _filter_records(
    records: Sequence[Mapping[str, Any]],
    *,
    start_date: date | None,
    end_date: date | None,
    channel_id: str,
    measurement_window: str,
    timezone_name: str,
) -> list[dict[str, Any]]:
    requested_channel = channel_id.strip().casefold()
    requested_window = measurement_window.strip().casefold()
    ignore_window = requested_window in {"", "all", "latest"}
    filtered: list[dict[str, Any]] = []
    for source in records:
        record = dict(source)
        current_channel = str(record.get("channel_id", "")).strip().casefold()
        current_window = str(record.get("measurement_window", "")).strip().casefold()
        if requested_channel and current_channel != requested_channel:
            continue
        if not ignore_window and current_window != requested_window:
            continue
        if not _matches_date_range(
            record.get("measured_at"), start_date, end_date, timezone_name
        ):
            continue
        filtered.append(record)
    return filtered


def _filter_quality_events(
    events: Sequence[Mapping[str, Any]],
    *,
    start_date: date | None,
    end_date: date | None,
    channel_id: str,
    timezone_name: str,
) -> list[dict[str, Any]]:
    requested_channel = channel_id.strip().casefold()
    filtered: list[dict[str, Any]] = []
    for source in events:
        event = dict(source)
        current_channel = str(
            event.get("channel_id") or event.get("src") or ""
        ).strip().casefold()
        if requested_channel and current_channel != requested_channel:
            continue
        if not _matches_date_range(
            event.get("ts") or event.get("timestamp"),
            start_date,
            end_date,
            timezone_name,
        ):
            continue
        filtered.append(event)
    return filtered


def _build_trends(
    records: Sequence[Mapping[str, Any]], timezone_name: str
) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        local_day = _local_date(record.get("measured_at"), timezone_name)
        if local_day is not None:
            groups.setdefault(local_day.isoformat(), []).append(record)
    return [
        {"date": day, **aggregate_performance(groups[day])}
        for day in sorted(groups)
    ]


def _top_videos(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        records,
        key=lambda row: (
            -(int(row.get("views") or 0)),
            str(row.get("video_id", "")),
        ),
    )[:10]
    result: list[dict[str, Any]] = []
    for record in ranked:
        summary = aggregate_performance([record])
        duration = float(record.get("duration") or 0)
        duration_bucket = (
            "unknown"
            if duration <= 0
            else "<20s"
            if duration < 20
            else "20-24s"
            if duration < 25
            else "25-29s"
            if duration < 30
            else "30-39s"
            if duration < 40
            else "40s+"
        )
        result.append(
            {
                "video_id": str(record.get("video_id", "")),
                "channel_id": str(record.get("channel_id", "")),
                "title": str(record.get("title", "")),
                "story_type": str(record.get("story_type", "unknown")),
                "hook_type": str(record.get("hook_type", "unknown")),
                "duration_bucket": duration_bucket,
                "music_mood": str(record.get("music_mood", "unknown")),
                "views": int(record.get("views") or 0),
                "source_url": str(record.get("source_url", "")),
                **summary,
            }
        )
    return result


def _build_pipeline_summary(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failures = [
        event
        for event in events
        if str(event.get("status") or event.get("st") or "").casefold()
        == "failed"
        or bool(event.get("error_code"))
    ]
    successful_items: dict[str, set[str]] = {}
    for event in events:
        status = str(event.get("status") or event.get("st") or "").casefold()
        if status not in SUCCESS_STATUSES:
            continue
        pipeline = str(event.get("pipeline") or event.get("pl") or "unknown")
        item_key = str(
            event.get("item_id")
            or event.get("video_id")
            or event.get("source_url")
            or event.get("ts")
            or id(event)
        )
        successful_items.setdefault(pipeline, set()).add(item_key)

    recent = sorted(
        failures,
        key=lambda event: str(event.get("ts") or event.get("timestamp") or ""),
        reverse=True,
    )[:20]
    return {
        "total_events": len(events),
        "status_counts": _value_counts(
            event.get("status") or event.get("st") for event in events
        ),
        "stage_counts": _value_counts(event.get("stage") for event in events),
        "successful_items_by_pipeline": [
            {"value": pipeline, "count": len(items)}
            for pipeline, items in sorted(
                successful_items.items(), key=lambda item: item[0].casefold()
            )
        ],
        "failures": {
            "total": len(failures),
            "by_stage": _value_counts(event.get("stage") for event in failures),
            "by_error_code": _value_counts(
                event.get("error_code") for event in failures
            ),
            "recent": [
                {
                    "ts": str(event.get("ts") or event.get("timestamp") or ""),
                    "pipeline": str(
                        event.get("pipeline") or event.get("pl") or "unknown"
                    ),
                    "channel_id": str(
                        event.get("channel_id") or event.get("src") or ""
                    ),
                    "stage": str(event.get("stage") or "unknown"),
                    "error_code": str(event.get("error_code") or "unknown"),
                    "retryable": bool(event.get("retryable", False)),
                    "message": str(
                        event.get("message") or event.get("reason") or ""
                    ),
                    "item_id": str(event.get("item_id") or ""),
                }
                for event in recent
            ],
        },
    }


def build_performance_dashboard(
    records: Sequence[Mapping[str, Any]],
    quality_events: Sequence[Mapping[str, Any]] = (),
    *,
    start_date: str = "",
    end_date: str = "",
    channel_id: str = "",
    measurement_window: str = "",
    min_samples: int = 30,
    timezone_name: str = DEFAULT_TIMEZONE,
    malformed_quality_lines: int = 0,
) -> dict[str, Any]:
    """Return one serializable payload for the Central Hub dashboard."""

    if not 1 <= min_samples <= 1000:
        raise ValueError("INVALID_MIN_SAMPLES")
    try:
        ZoneInfo(timezone_name)
    except Exception as exc:
        raise ValueError("INVALID_TIMEZONE") from exc

    parsed_start = _parse_date(start_date, "start_date")
    parsed_end = _parse_date(end_date, "end_date")
    if parsed_start and parsed_end and parsed_end < parsed_start:
        raise ValueError("INVALID_DATE_RANGE")

    filtered_records = _filter_records(
        records,
        start_date=parsed_start,
        end_date=parsed_end,
        channel_id=channel_id,
        measurement_window=measurement_window,
        timezone_name=timezone_name,
    )
    current_records = latest_snapshots(filtered_records)
    analysis = analyze_performance(
        filtered_records, min_samples=min_samples, latest_only=True
    )
    filtered_events = _filter_quality_events(
        quality_events,
        start_date=parsed_start,
        end_date=parsed_end,
        channel_id=channel_id,
        timezone_name=timezone_name,
    )
    pipeline = _build_pipeline_summary(filtered_events)
    sample_size = int(analysis["overview"].get("sample_size", 0))
    status = (
        "empty"
        if sample_size == 0
        else "ready"
        if sample_size >= min_samples
        else "insufficient_sample"
    )
    has_activity = bool(filtered_events)
    system_health = (
        "attention"
        if pipeline["failures"]["total"]
        else "healthy"
        if has_activity
        else "empty"
    )

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "channel_id": channel_id,
            "measurement_window": measurement_window,
            "min_samples": min_samples,
            "timezone": timezone_name,
        },
        "available_filters": {
            "channels": _available_values(records, "channel_id"),
            "measurement_windows": _available_values(
                records, "measurement_window"
            ),
        },
        "overview": analysis["overview"],
        "breakdowns": analysis["breakdowns"],
        "trends": _build_trends(current_records, timezone_name),
        "top_videos": _top_videos(current_records),
        "data_quality": {
            "snapshot_count": len(filtered_records),
            "latest_video_count": len(current_records),
            "anomaly_count": len(analysis["snapshot_anomalies"]),
            "malformed_quality_lines": malformed_quality_lines,
        },
        "pipeline": pipeline,
        "system_health": system_health,
    }


def load_performance_dashboard(
    *,
    db_path: str | Path = DEFAULT_PERFORMANCE_DB,
    quality_log_path: str | Path = DEFAULT_QUALITY_LOG_PATH,
    **filters: Any,
) -> dict[str, Any]:
    """Load runtime telemetry and build a dashboard without creating missing files."""

    database_path = Path(db_path)
    records: list[dict[str, Any]] = []
    if database_path.exists():
        with PerformanceStore(database_path) as store:
            records = store.list_measurements(limit=MAX_DASHBOARD_RECORDS)
    events, malformed = read_quality_events(quality_log_path)
    return build_performance_dashboard(
        records,
        events,
        malformed_quality_lines=malformed,
        **filters,
    )


def dashboard_compat_stats(
    dashboard: Mapping[str, Any], active_tools: int = 0
) -> dict[str, Any]:
    """Map real telemetry to the legacy dashboard stats response."""

    counts = {
        str(item.get("value", "")).casefold(): int(item.get("count", 0))
        for item in dashboard.get("pipeline", {}).get(
            "successful_items_by_pipeline", []
        )
    }

    def count_matching(*prefixes: str) -> int:
        return sum(
            count
            for pipeline, count in counts.items()
            if any(pipeline == prefix or pipeline.startswith(f"{prefix}_")
                   for prefix in prefixes)
        )

    health_labels = {
        "healthy": "Good",
        "attention": "Needs attention",
        "empty": "No data",
    }
    return {
        "active_tools": active_tools,
        "articles_processed": count_matching("article"),
        "facebook_posts": count_matching("facebook"),
        "tiktok_uploads": count_matching("tiktok"),
        "system_health": health_labels.get(
            str(dashboard.get("system_health", "empty")), "No data"
        ),
    }
