"""Kho dữ liệu tách biệt cho nguồn Page và nguồn Group Facebook."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .source_config import (
    canonicalize_source_url,
    SOURCE_TYPE_GROUP,
    SOURCE_TYPE_PAGE,
    normalize_group_source_record,
    normalize_page_source_record,
)


PAGE_SOURCES_TABLE = "facebook_sources"
PAGE_VIDEOS_TABLE = "facebook_videos"
GROUP_SOURCES_TABLE = "facebook_group_sources"
GROUP_VIDEOS_TABLE = "facebook_group_videos"
SOURCE_SCOPES = {SOURCE_TYPE_PAGE, SOURCE_TYPE_GROUP, "all"}


def normalize_source_scope(value: Any, *, default: str = SOURCE_TYPE_PAGE) -> str:
    scope = str(value or default).strip().lower()
    if scope not in SOURCE_SCOPES:
        raise ValueError("Phạm vi nguồn chỉ nhận 'page', 'group' hoặc 'all'.")
    return scope


def _attach_storage_metadata(
    source: dict[str, Any], *, source_table: str, video_table: str
) -> dict[str, Any]:
    result = dict(source)
    result["_source_table"] = source_table
    result["_video_table"] = video_table
    return result


def _load_table(client: Any, *, source_type: str) -> list[dict[str, Any]]:
    is_group = source_type == SOURCE_TYPE_GROUP
    source_table = GROUP_SOURCES_TABLE if is_group else PAGE_SOURCES_TABLE
    video_table = GROUP_VIDEOS_TABLE if is_group else PAGE_VIDEOS_TABLE
    normalizer = normalize_group_source_record if is_group else normalize_page_source_record
    result = (
        client.table(source_table)
        .select("*")
        .eq("is_active", True)
        .order("created_at")
        .execute()
    )
    normalized: list[dict[str, Any]] = []
    for source in result.data or []:
        try:
            normalized.append(
                _attach_storage_metadata(
                    normalizer(source),
                    source_table=source_table,
                    video_table=video_table,
                )
            )
        except ValueError as error:
            print(
                f"⚠️ Bỏ nguồn {source_type} cấu hình sai "
                f"[{source.get('source_name', '')}]: {error}"
            )
    return normalized


def load_active_sources(client: Any, source_scope: str) -> list[dict[str, Any]]:
    """Load độc lập; bảng Group lỗi/thiếu không làm hỏng luồng Page cũ."""
    scope = normalize_source_scope(source_scope)
    source_types = (
        (SOURCE_TYPE_PAGE, SOURCE_TYPE_GROUP)
        if scope == "all"
        else (scope,)
    )
    sources: list[dict[str, Any]] = []
    for source_type in source_types:
        try:
            sources.extend(_load_table(client, source_type=source_type))
        except Exception as error:
            table = (
                GROUP_SOURCES_TABLE
                if source_type == SOURCE_TYPE_GROUP
                else PAGE_SOURCES_TABLE
            )
            print(f"❌ Lỗi load bảng {table}: {error}")
    # Một Page có thể đã tồn tại nhiều lần trong bảng cũ trước khi API có
    # kiểm tra URL. Chỉ chạy bản ghi đầu tiên để các source_id khác nhau không
    # xử lý cùng một feed và tạo duplicate.
    unique_sources: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for source in sources:
        try:
            canonical_url = canonicalize_source_url(
                source.get("source_url", ""), source.get("source_type")
            )
        except ValueError:
            canonical_url = str(source.get("source_url", "")).strip().rstrip("/")
        key = (str(source.get("source_type") or SOURCE_TYPE_PAGE), canonical_url)
        if key in seen_keys:
            print(f"⚠️ Bỏ qua nguồn Facebook trùng URL: {canonical_url}")
            continue
        seen_keys.add(key)
        unique_sources.append(source)
    return unique_sources


def source_table_for(source: dict[str, Any]) -> str:
    return str(source.get("_source_table") or PAGE_SOURCES_TABLE)


def video_table_for(source: dict[str, Any]) -> str:
    return str(source.get("_video_table") or PAGE_VIDEOS_TABLE)


def update_scan_checkpoint(
    client: Any,
    source: dict[str, Any],
    last_video_id: str | None = None,
) -> None:
    update = {"last_scan_at": datetime.now(timezone.utc).isoformat()}
    if last_video_id:
        update["last_video_id"] = last_video_id
    client.table(source_table_for(source)).update(update).eq(
        "id", source["id"]
    ).execute()


def insert_video_record(
    client: Any,
    source: dict[str, Any],
    video: dict[str, Any],
    download: dict[str, Any],
    ai_result: dict[str, Any],
    final_path: str,
) -> str | None:
    result = client.table(video_table_for(source)).insert(
        {
            "source_id": source.get("id"),
            "facebook_video_id": video.get("video_id"),
            "original_url": video["url"],
            "caption": video.get("caption", "")[:500],
            "status": "uploaded",
            "file_hash": download.get("hash"),
            "file_size_bytes": download.get("size"),
            "downloaded_path": download.get("path"),
            "ai_title": ai_result.get("title_tiktok", ""),
            "ai_script": ai_result.get("script_voice", ""),
            "processed_path": final_path,
        }
    ).execute()
    return str(result.data[0]["id"]) if result.data else None


def claim_video_record(
    client: Any,
    source: dict[str, Any],
    video: dict[str, Any],
) -> str | None:
    """Đặt chỗ cho video trước khi chạy các bước tốn thời gian."""
    source_id = source.get("id")
    video_id = video.get("video_id")
    if not source_id or not video_id:
        raise ValueError("Thiếu source_id hoặc facebook_video_id khi claim video.")
    existing = (
        client.table(video_table_for(source))
        .select("id")
        .eq("source_id", source_id)
        .eq("facebook_video_id", video_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return None
    try:
        result = client.table(video_table_for(source)).insert(
            {
                "source_id": source_id,
                "facebook_video_id": video_id,
                "original_url": video.get("url", ""),
                "caption": video.get("caption", "")[:500],
                "status": "processing",
            }
        ).execute()
    except Exception as error:
        error_text = str(error).lower()
        if (
            "23505" in error_text
            or "duplicate key" in error_text
            or "unique constraint" in error_text
        ):
            return None
        raise
    return str(result.data[0]["id"]) if result.data else None


def finalize_video_record(
    client: Any,
    source: dict[str, Any],
    record_id: str,
    download: dict[str, Any],
    ai_result: dict[str, Any],
    final_path: str,
) -> None:
    """Cập nhật claim đã đặt chỗ thành record hoàn tất."""
    result = (
        client.table(video_table_for(source))
        .update(
            {
                "status": "uploaded",
                "file_hash": download.get("hash"),
                "file_size_bytes": download.get("size"),
                "downloaded_path": download.get("path"),
                "ai_title": ai_result.get("title_tiktok", ""),
                "ai_script": ai_result.get("script_voice", ""),
                "processed_path": final_path,
            }
        )
        .eq("id", record_id)
        .execute()
    )
    # Một số cấu hình PostgREST trả về data rỗng cho UPDATE dù lệnh đã thành
    # công (return=minimal). Chỉ coi exception từ execute() là lỗi thật.


def video_id_exists(
    client: Any,
    source: dict[str, Any],
    video_id: str,
) -> bool:
    if not source.get("id") or not video_id:
        return False
    result = (
        client.table(video_table_for(source))
        .select("id")
        .eq("source_id", source["id"])
        .eq("facebook_video_id", video_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def file_hash_exists(client: Any, source: dict[str, Any], file_hash: str) -> bool:
    if not file_hash:
        return False
    result = (
        client.table(video_table_for(source))
        .select("id")
        .eq("file_hash", file_hash)
        .limit(1)
        .execute()
    )
    return bool(result.data)
