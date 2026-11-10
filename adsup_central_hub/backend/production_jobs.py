"""Kho lưu job dựng video từ JSON kịch bản khoá.

Mỗi job là một thư mục ``data/production_jobs/prod_<hash12>/`` chứa bản gốc
JSON, report validate và storyboard preview. ``job_id`` sinh từ hash của nội
dung JSON + kênh nên import lặp lại là idempotent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_JOBS_DIR = os.path.join(PROJECT_ROOT, "data", "production_jobs")

# Ghi đè trong test/smoke để không đụng dữ liệu thật.
JOBS_DIR = os.environ.get("PRODUCTION_JOBS_DIR") or DEFAULT_JOBS_DIR

JOB_ID_RE = re.compile(r"^prod_[0-9a-f]{12}$")

ARTIFACTS = ("source", "validation", "storyboard", "media_plan", "assets_manifest")


def compute_job_id(document: Any, channel_id: str = "") -> str:
    canonical = json.dumps(
        {"channel_id": channel_id, "document": document},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return "prod_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _jobs_dir(override: str | None = None) -> str:
    directory = override or JOBS_DIR
    os.makedirs(directory, exist_ok=True)
    return directory


def _safe_job_dir(job_id: str, override: str | None = None) -> str | None:
    if not JOB_ID_RE.match(str(job_id or "")):
        return None
    return os.path.join(_jobs_dir(override), job_id)


def _atomic_write_json(path: str, payload: Any) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, delete=False, suffix=".tmp"
    )
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def job_exists(job_id: str, *, jobs_dir: str | None = None) -> bool:
    directory = _safe_job_dir(job_id, jobs_dir)
    return bool(directory) and os.path.isfile(os.path.join(directory, "job.json"))


def save_job(
    document: Any,
    *,
    channel_id: str = "",
    validation: dict[str, Any] | None = None,
    storyboard: dict[str, Any] | None = None,
    status: str = "imported",
    source_url: str = "",
    jobs_dir: str | None = None,
) -> tuple[str, bool]:
    """Lưu job mới; nếu job_id đã tồn tại thì trả về bản cũ, không ghi đè.

    Trạng thái render nằm trong job.json của lần tạo đầu; import lại cùng
    JSON không được phép xoá trạng thái đó.
    """

    clean_channel = str(channel_id or "").replace("@", "").strip()
    job_id = compute_job_id(document, clean_channel)
    directory = _safe_job_dir(job_id, jobs_dir)
    if directory is None:
        raise ValueError("job_id không hợp lệ")

    existing = load_job(job_id, jobs_dir=jobs_dir)
    if existing is not None:
        return job_id, False

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    job_meta = {
        "job_id": job_id,
        "schema": "locked_script_v1",
        "status": status,
        "channel_id": clean_channel,
        "source_url": str(source_url or (document or {}).get("source_url") or "")
        if isinstance(document, dict)
        else str(source_url or ""),
        "beat_count": (validation or {}).get("beat_count", 0),
        "passed": bool((validation or {}).get("passed", False)),
        "created_at": now,
        "updated_at": now,
    }

    _atomic_write_json(os.path.join(directory, "source.json"), document)
    _atomic_write_json(os.path.join(directory, "validation.json"), validation or {})
    _atomic_write_json(os.path.join(directory, "storyboard.json"), storyboard or {})
    _atomic_write_json(os.path.join(directory, "job.json"), job_meta)
    return job_id, True


def load_job(job_id: str, *, jobs_dir: str | None = None) -> dict[str, Any] | None:
    directory = _safe_job_dir(job_id, jobs_dir)
    if not directory:
        return None
    path = os.path.join(directory, "job.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def load_job_artifact(
    job_id: str, artifact: str, *, jobs_dir: str | None = None
) -> dict[str, Any] | None:
    if artifact not in ARTIFACTS:
        return None
    directory = _safe_job_dir(job_id, jobs_dir)
    if not directory:
        return None
    path = os.path.join(directory, f"{artifact}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def job_file_path(job_id: str, filename: str, *, jobs_dir: str | None = None) -> str | None:
    """Đường dẫn file trong job dir (đã chặn path traversal qua basename)."""

    directory = _safe_job_dir(job_id, jobs_dir)
    if directory is None:
        return None
    path = os.path.join(directory, os.path.basename(str(filename)))
    return path if os.path.isfile(path) else None


def set_job_status(job_id: str, status: str, *, jobs_dir: str | None = None) -> dict[str, Any] | None:
    meta = load_job(job_id, jobs_dir=jobs_dir)
    if meta is None:
        return None
    from datetime import datetime, timezone

    meta["status"] = str(status or "").strip() or meta.get("status") or "imported"
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    directory = _safe_job_dir(job_id, jobs_dir)
    if directory is None:
        return None
    _atomic_write_json(os.path.join(directory, "job.json"), meta)
    return meta


def list_jobs(limit: int = 50, *, jobs_dir: str | None = None) -> list[dict[str, Any]]:
    directory = _jobs_dir(jobs_dir)
    items: list[dict[str, Any]] = []
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return []
    for name in entries:
        meta = load_job(name, jobs_dir=jobs_dir)
        if meta is None:
            continue
        items.append(meta)
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[: max(1, int(limit))]
