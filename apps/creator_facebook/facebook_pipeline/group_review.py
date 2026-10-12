"""Vòng đời duyệt thủ công cho video được tạo từ Facebook Group."""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REVIEW_ROOT = PACKAGE_ROOT / "data" / "group_review"
GROUP_VIDEOS_TABLE = "facebook_group_videos"
PENDING_REVIEW = "pending_review"
APPROVING = "approving"
APPROVED = "approved"
REJECTED = "rejected"
UPLOAD_FAILED = "upload_failed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _review_path(review_id: str, review_root: Path = REVIEW_ROOT) -> Path:
    return review_root / review_id / "video.mp4"


def safe_review_path(raw_path: Any, review_root: Path = REVIEW_ROOT) -> Path:
    """Chỉ chấp nhận file nằm bên trong kho review do ứng dụng quản lý."""
    path = Path(str(raw_path or "")).expanduser().resolve()
    root = review_root.expanduser().resolve()
    if path == root or root not in path.parents:
        raise ValueError("Đường dẫn video review không hợp lệ.")
    return path


def remove_review_artifact(
    raw_path: Any, review_root: Path = REVIEW_ROOT
) -> bool:
    try:
        path = safe_review_path(raw_path, review_root)
    except ValueError:
        return False
    removed = False
    if path.is_file():
        path.unlink()
        removed = True
    try:
        path.parent.rmdir()
    except OSError:
        pass
    return removed


def stage_group_review(
    client: Any,
    source: dict[str, Any],
    video: dict[str, Any],
    download: dict[str, Any],
    ai_result: dict[str, Any],
    final_path: str,
    *,
    review_root: Path = REVIEW_ROOT,
) -> str:
    """Di chuyển MP4 hoàn chỉnh vào kho bền vững rồi tạo hàng chờ duyệt."""
    source_path = Path(final_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy video render: {source_path}")

    review_id = str(uuid.uuid4())
    destination = _review_path(review_id, review_root)
    destination.parent.mkdir(parents=True, exist_ok=False)
    shutil.move(str(source_path), str(destination))
    payload = {
        "ai_result": ai_result,
        "video_url": video.get("url", ""),
        "video_id": video.get("video_id", ""),
        "source_name": source.get("source_name", ""),
        "id_tiktok": source.get("id_tiktok") or "Adsupnews",
    }
    try:
        client.table(GROUP_VIDEOS_TABLE).insert(
            {
                "id": review_id,
                "source_id": source.get("id"),
                "facebook_video_id": video.get("video_id"),
                "original_url": video.get("url", ""),
                "caption": video.get("caption", "")[:500],
                "status": PENDING_REVIEW,
                "file_hash": download.get("hash"),
                "file_size_bytes": destination.stat().st_size,
                "downloaded_path": "",
                "ai_title": ai_result.get("title_tiktok", ""),
                "ai_script": ai_result.get("script_voice", ""),
                "processed_path": str(destination),
                "review_video_path": str(destination),
                "review_payload": payload,
                "review_error": "",
            }
        ).execute()
    except Exception:
        remove_review_artifact(destination, review_root)
        raise
    return review_id


def list_group_reviews(client: Any) -> list[dict[str, Any]]:
    result = (
        client.table(GROUP_VIDEOS_TABLE)
        .select("*")
        .in_("status", [PENDING_REVIEW, UPLOAD_FAILED])
        .order("created_at", desc=True)
        .execute()
    )
    reviews = []
    for record in result.data or []:
        item = dict(record)
        item.pop("review_video_path", None)
        item.pop("processed_path", None)
        item.pop("downloaded_path", None)
        item["preview_url"] = f"/api/facebook/group-review/{item['id']}/video"
        reviews.append(item)
    return reviews


def get_group_review(client: Any, review_id: str) -> dict[str, Any] | None:
    result = (
        client.table(GROUP_VIDEOS_TABLE)
        .select("*")
        .eq("id", review_id)
        .limit(1)
        .execute()
    )
    return dict(result.data[0]) if result.data else None


def get_group_review_video_path(
    client: Any,
    review_id: str,
    review_root: Path = REVIEW_ROOT,
) -> Path:
    record = get_group_review(client, review_id)
    if not record:
        raise FileNotFoundError("Không tìm thấy video chờ duyệt.")
    path = safe_review_path(record.get("review_video_path"), review_root)
    if not path.is_file():
        raise FileNotFoundError("File video chờ duyệt không còn tồn tại.")
    return path


def _claim_review(client: Any, record: dict[str, Any]) -> None:
    result = (
        client.table(GROUP_VIDEOS_TABLE)
        .update({"status": APPROVING, "review_error": ""})
        .eq("id", record["id"])
        .eq("status", record["status"])
        .execute()
    )
    if not result.data:
        raise RuntimeError("Video đã được tiến trình khác xử lý.")


def approve_group_review(
    client: Any,
    review_id: str,
    drive_folder_id: str,
    *,
    upload_fn: Callable[[str, str], str] | None = None,
    save_sheet_fn: Callable[..., dict[str, Any] | None] | None = None,
    update_status_fn: Callable[[int, str], bool] | None = None,
    update_drive_fn: Callable[[int, str], bool] | None = None,
    update_finished_fn: Callable[[int, str], bool] | None = None,
    review_root: Path = REVIEW_ROOT,
) -> dict[str, Any]:
    record = get_group_review(client, review_id)
    if not record:
        raise ValueError("Không tìm thấy video chờ duyệt.")
    if record.get("status") not in {PENDING_REVIEW, UPLOAD_FAILED}:
        raise ValueError("Video không còn ở trạng thái có thể duyệt.")
    video_path = get_group_review_video_path(client, review_id, review_root)
    _claim_review(client, record)

    if upload_fn is None:
        from shared.modules.upload_drive import upload_video_to_drive

        upload_fn = upload_video_to_drive
    if any(
        function is None
        for function in (
            save_sheet_fn,
            update_status_fn,
            update_drive_fn,
            update_finished_fn,
        )
    ):
        from apps.creator_facebook.fb_sheet_api import (
            save_fb_to_sheet,
            update_fb_drive_link,
            update_fb_finished_time,
            update_fb_status,
        )

        save_sheet_fn = save_sheet_fn or save_fb_to_sheet
        update_status_fn = update_status_fn or update_fb_status
        update_drive_fn = update_drive_fn or update_fb_drive_link
        update_finished_fn = update_finished_fn or update_fb_finished_time

    payload = record.get("review_payload") or {}
    ai_result = payload.get("ai_result") or {}
    try:
        drive_link = str(record.get("drive_link") or "").strip()
        if not drive_link:
            drive_link = upload_fn(str(video_path), drive_folder_id)
            if not drive_link:
                raise RuntimeError("Upload Google Drive không trả về link.")
            client.table(GROUP_VIDEOS_TABLE).update(
                {"drive_link": drive_link}
            ).eq("id", review_id).execute()

        sheet_row = record.get("sheet_row")
        if not sheet_row:
            sheet_result = save_sheet_fn(
                ai_result=ai_result,
                video_url=payload.get("video_url") or record.get("original_url", ""),
                source_name=payload.get("source_name", ""),
                id_tiktok=payload.get("id_tiktok") or "Adsupnews",
            )
            sheet_row = sheet_result.get("row") if sheet_result else None
        if not sheet_row:
            raise RuntimeError("Google Sheet không trả về số dòng đã ghi.")
        client.table(GROUP_VIDEOS_TABLE).update(
            {"sheet_row": int(sheet_row)}
        ).eq("id", review_id).execute()
        if not update_status_fn(sheet_row, "uploaded"):
            raise RuntimeError("Không cập nhật được trạng thái Google Sheet.")
        if not update_drive_fn(sheet_row, drive_link):
            raise RuntimeError("Không cập nhật được link Drive trên Google Sheet.")
        if not update_finished_fn(
            sheet_row, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ):
            raise RuntimeError("Không cập nhật được thời gian hoàn tất trên Google Sheet.")
        client.table(GROUP_VIDEOS_TABLE).update(
            {
                "status": APPROVED,
                "drive_link": drive_link,
                "sheet_row": int(sheet_row),
                "reviewed_at": _utc_now(),
                "review_error": "",
                "processed_path": "",
                "review_video_path": "",
            }
        ).eq("id", review_id).execute()
        remove_review_artifact(video_path, review_root)
        return {
            "status": APPROVED,
            "drive_link": drive_link,
            "sheet_row": int(sheet_row),
        }
    except Exception as error:
        client.table(GROUP_VIDEOS_TABLE).update(
            {"status": UPLOAD_FAILED, "review_error": str(error)[:1000]}
        ).eq("id", review_id).execute()
        raise


def reject_group_review(
    client: Any,
    review_id: str,
    *,
    review_root: Path = REVIEW_ROOT,
) -> dict[str, Any]:
    record = get_group_review(client, review_id)
    if not record:
        raise ValueError("Không tìm thấy video chờ duyệt.")
    if record.get("status") not in {PENDING_REVIEW, UPLOAD_FAILED}:
        raise ValueError("Video không còn ở trạng thái có thể từ chối.")
    removed = remove_review_artifact(
        record.get("review_video_path"), review_root
    )
    client.table(GROUP_VIDEOS_TABLE).delete().eq("id", review_id).execute()
    return {"status": REJECTED, "file_removed": removed}
