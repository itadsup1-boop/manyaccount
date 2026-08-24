"""Thread-safe JSONL events shared by all video creation pipelines."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Mapping


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_QUALITY_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "quality_log.jsonl")
_QUALITY_LOG_LOCK = threading.Lock()


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
    log_path: str = DEFAULT_QUALITY_LOG_PATH,
) -> dict[str, Any]:
    """Append one backward-compatible, structured pipeline event."""
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

    log_dir = os.path.dirname(os.path.abspath(log_path))
    os.makedirs(log_dir, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _QUALITY_LOG_LOCK:
        with open(log_path, "a", encoding="utf-8") as file:
            file.write(line)
    return entry
