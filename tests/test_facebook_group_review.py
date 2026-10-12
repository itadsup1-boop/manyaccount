from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.creator_facebook.facebook_pipeline.group_review import (
    APPROVED,
    PENDING_REVIEW,
    REJECTED,
    approve_group_review,
    reject_group_review,
    stage_group_review,
)


class _MemoryResponse:
    def __init__(self, data):
        self.data = data


class _MemoryQuery:
    def __init__(self, client, table, operation="select", payload=None):
        self.client = client
        self.table = table
        self.operation = operation
        self.payload = payload
        self.filters = []
        self.in_filter = None

    def insert(self, payload):
        return _MemoryQuery(self.client, self.table, "insert", payload)

    def select(self, *_args):
        return self

    def update(self, payload):
        return _MemoryQuery(self.client, self.table, "update", payload)

    def delete(self):
        return _MemoryQuery(self.client, self.table, "delete")

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def in_(self, key, values):
        self.in_filter = (key, set(values))
        return self

    def limit(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def _matches(self, row):
        if any(row.get(key) != value for key, value in self.filters):
            return False
        if self.in_filter:
            key, values = self.in_filter
            return row.get(key) in values
        return True

    def execute(self):
        rows = self.client.rows.setdefault(self.table, [])
        if self.operation == "insert":
            row = dict(self.payload)
            rows.append(row)
            return _MemoryResponse([dict(row)])
        if self.operation == "update":
            changed = []
            for row in rows:
                if self._matches(row):
                    row.update(self.payload)
                    changed.append(dict(row))
            return _MemoryResponse(changed)
        if self.operation == "delete":
            deleted = [dict(row) for row in rows if self._matches(row)]
            self.client.rows[self.table] = [
                row for row in rows if not self._matches(row)
            ]
            return _MemoryResponse(deleted)
        return _MemoryResponse([dict(row) for row in rows if self._matches(row)])


class _MemoryClient:
    def __init__(self):
        self.rows = {}

    def table(self, name):
        return _MemoryQuery(self, name)


class FacebookGroupReviewTests(unittest.TestCase):
    def _stage(self, client, root):
        rendered = root / "rendered.mp4"
        rendered.write_bytes(b"fake mp4 data")
        review_id = stage_group_review(
            client,
            {"id": 7, "source_name": "Nhóm xe", "id_tiktok": "gbn.car.24h"},
            {
                "video_id": "12345",
                "url": "https://facebook.com/groups/1/posts/12345",
                "caption": "Video thử nghiệm",
            },
            {"hash": "abc", "size": 13},
            {"title_tiktok": "Tiêu đề", "hook": "Hook thử nghiệm"},
            str(rendered),
            review_root=root / "queue",
        )
        return review_id, root / "queue" / review_id / "video.mp4"

    def test_stage_keeps_one_video_and_does_not_upload(self):
        client = _MemoryClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_id, queued_video = self._stage(client, root)
            self.assertTrue(queued_video.is_file())
            row = client.rows["facebook_group_videos"][0]
            self.assertEqual(row["id"], review_id)
            self.assertEqual(row["status"], PENDING_REVIEW)
            self.assertEqual(row["review_payload"]["source_name"], "Nhóm xe")

    def test_approve_uploads_then_removes_local_video(self):
        client = _MemoryClient()
        updates = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_id, queued_video = self._stage(client, root)
            result = approve_group_review(
                client,
                review_id,
                "drive-folder",
                upload_fn=lambda path, folder: (
                    "https://drive.test/video" if Path(path).is_file() and folder else ""
                ),
                save_sheet_fn=lambda **_kwargs: {"status": "success", "row": 12},
                update_status_fn=lambda row, value: updates.append(("status", row, value)) or True,
                update_drive_fn=lambda row, value: updates.append(("drive", row, value)) or True,
                update_finished_fn=lambda row, value: updates.append(("time", row, value)) or True,
                review_root=root / "queue",
            )
            self.assertEqual(result["status"], APPROVED)
            self.assertFalse(queued_video.exists())
            self.assertEqual(client.rows["facebook_group_videos"][0]["status"], APPROVED)
            self.assertEqual(updates[0], ("status", 12, "uploaded"))

    def test_reject_deletes_video_and_database_record(self):
        client = _MemoryClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_id, queued_video = self._stage(client, root)
            result = reject_group_review(
                client, review_id, review_root=root / "queue"
            )
            self.assertEqual(result, {"status": REJECTED, "file_removed": True})
            self.assertFalse(queued_video.exists())
            self.assertEqual(client.rows["facebook_group_videos"], [])

    def test_retry_reuses_drive_link_and_sheet_row(self):
        client = _MemoryClient()
        calls = {"drive": 0, "sheet": 0}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_id, _queued_video = self._stage(client, root)

            def upload(_path, _folder):
                calls["drive"] += 1
                return "https://drive.test/video"

            def save_sheet(**_kwargs):
                calls["sheet"] += 1
                return {"status": "success", "row": 21}

            with self.assertRaisesRegex(
                RuntimeError, "Không cập nhật được trạng thái"
            ):
                approve_group_review(
                    client,
                    review_id,
                    "drive-folder",
                    upload_fn=upload,
                    save_sheet_fn=save_sheet,
                    update_status_fn=lambda _row, _value: False,
                    update_drive_fn=lambda _row, _value: True,
                    update_finished_fn=lambda _row, _value: True,
                    review_root=root / "queue",
                )

            result = approve_group_review(
                client,
                review_id,
                "drive-folder",
                upload_fn=upload,
                save_sheet_fn=save_sheet,
                update_status_fn=lambda _row, _value: True,
                update_drive_fn=lambda _row, _value: True,
                update_finished_fn=lambda _row, _value: True,
                review_root=root / "queue",
            )
            self.assertEqual(result["status"], APPROVED)
            self.assertEqual(calls, {"drive": 1, "sheet": 1})


if __name__ == "__main__":
    unittest.main()
