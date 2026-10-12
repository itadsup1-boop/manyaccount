"""Thread-safe JSONL events shared by all video creation pipelines."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Mapping


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_QUALITY_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "quality_log.jsonl")
DEFAULT_PIPELINE_EVENT_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "pipeline_events.jsonl")
_QUALITY_LOG_LOCK = threading.Lock()


def append_pipeline_event(
    pipeline: str,
    item_id: str,
    stage: str,
    event: str,
    *,
    channel_id: str = "",
    message: str = "",
    error_code: str = "",
    retryable: bool | None = None,
    metadata: Mapping[str, Any] | None = None,
    log_path: str = DEFAULT_PIPELINE_EVENT_LOG_PATH,
) -> dict[str, Any]:
    """Write a step-level trace without changing the quality score contract."""
    entry: dict[str, Any] = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pipeline": str(pipeline or "unknown"),
        "item_id": str(item_id or ""),
        "stage": str(stage or "unknown"),
        "event": str(event or "step"),
    }
    if channel_id:
        entry["channel_id"] = str(channel_id)
    if message:
        entry["message"] = str(message)
    if error_code:
        entry["error_code"] = str(error_code)
    if retryable is not None:
        entry["retryable"] = bool(retryable)
    if metadata:
        entry["metadata"] = dict(metadata)

    log_dir = os.path.dirname(os.path.abspath(log_path))
    os.makedirs(log_dir, exist_ok=True)
    with _QUALITY_LOG_LOCK:
        with open(log_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def append_quality_event(
    pipeline: str,
    source_name: str,
    quality_score: int,
    status: str,
    reason: str = "",
    *,
    stage: str = "",
    item_id: str = "",
    error_code: str = "",
    retryable: bool | None = None,
    message: str = "",
    qa: Mapping[str, Any] | None = None,
    source_url: str = "",
    content_hash: str = "",
    editorial_score: int | None = None,
    ai_quality_score: int | None = None,
    quality_breakdown: Mapping[str, Any] | None = None,
    log_path: str = DEFAULT_QUALITY_LOG_PATH,
) -> dict[str, Any]:
    """Append one backward-compatible, structured pipeline event.

    ``quality_score`` remains the legacy 0-10 field consumed by existing
    reports. New deterministic article-gate telemetry is stored separately in
    ``editorial_score`` and ``quality_breakdown``; ``ai_quality_score`` is
    retained for comparison only.
    """
    normalized_status = str(status or stage or "unknown")
    entry: dict[str, Any] = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pl": str(pipeline or "unknown"),
        "src": str(source_name or ""),
        "score": int(quality_score or 0),
        "st": normalized_status,
        "reason": str(reason or message or ""),
        "status": normalized_status,
        "stage": str(stage or normalized_status),
    }
    if item_id:
        entry["item_id"] = str(item_id)
    if error_code:
        entry["error_code"] = str(error_code)
    if retryable is not None:
        entry["retryable"] = bool(retryable)
    if message:
        entry["message"] = str(message)
    if qa is not None:
        entry["qa"] = dict(qa)
    if source_url:
        entry["source_url"] = str(source_url)
    if content_hash:
        entry["content_hash"] = str(content_hash)
    if editorial_score is not None:
        entry["editorial_score"] = int(editorial_score)
    if ai_quality_score is not None:
        entry["ai_quality_score"] = int(ai_quality_score)
    if quality_breakdown is not None:
        entry["quality_breakdown"] = dict(quality_breakdown)

    log_dir = os.path.dirname(os.path.abspath(log_path))
    os.makedirs(log_dir, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _QUALITY_LOG_LOCK:
        with open(log_path, "a", encoding="utf-8") as file:
            file.write(line)
    return entry
