"""Service Web Hub cho hàng chờ duyệt video Facebook Group."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.creator_facebook.facebook_pipeline.group_review import (
    approve_group_review,
    get_group_review_video_path,
    list_group_reviews,
    reject_group_review,
)


class FacebookGroupReviewService:
    def __init__(self, client: Any, drive_folder_id: str):
        self.client = client
        self.drive_folder_id = drive_folder_id

    def _require_client(self) -> Any:
        if self.client is None:
            raise RuntimeError("Supabase chưa được khởi tạo.")
        return self.client

    def list_pending(self) -> list[dict[str, Any]]:
        return list_group_reviews(self._require_client())

    def video_path(self, review_id: str) -> Path:
        return get_group_review_video_path(self._require_client(), review_id)

    def approve(self, review_id: str) -> dict[str, Any]:
        if not self.drive_folder_id:
            raise RuntimeError("Chưa cấu hình DRIVE_FOLDER_ID/GDRIVE_FOLDER_ID.")
        return approve_group_review(
            self._require_client(), review_id, self.drive_folder_id
        )

    def reject(self, review_id: str) -> dict[str, Any]:
        return reject_group_review(self._require_client(), review_id)
