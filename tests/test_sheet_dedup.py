import json
import unittest
from unittest.mock import patch

from shared.services import sheet_api


class _Response:
    def __init__(self, status_code=200, body=None, text=None):
        self.status_code = status_code
        self.text = json.dumps(body) if text is None and body is not None else (text or "")

    def json(self):
        return json.loads(self.text)


class SheetDedupTests(unittest.TestCase):
    def test_existing_row_is_reused_without_save(self):
        payload = {"action": "save_facebook", "link": "https://example.com/v1", "id_tiktok": "channel-a"}

        def post(_url, json, timeout):
            self.assertEqual(json["action"], "read_bulk_optimized")
            return _Response(body={"status": "success", "data": [{"row": 42, "link": payload["link"], "tiktok_id": "channel-a"}]})

        with patch.object(sheet_api.requests, "post", side_effect=post) as mocked:
            result = sheet_api.save_idempotent_to_sheet(
                "https://sheet.test/exec",
                payload,
                source_url=payload["link"],
                channel_id=payload["id_tiktok"],
                sheet_name="facebook",
            )

        self.assertEqual(result["row"], 42)
        self.assertTrue(result["deduplicated"])
        self.assertEqual(mocked.call_count, 1)

    def test_ambiguous_save_recovers_row_without_retrying_append(self):
        payload = {"action": "save", "link": "https://example.com/article", "tiktok_id": "channel-a"}
        reads = 0

        def post(_url, json, timeout):
            nonlocal reads
            if json["action"] == "read_bulk_optimized":
                reads += 1
                rows = [] if reads == 1 else [{"row": 123, "url": payload["link"], "tiktok_id": "channel-a"}]
                return _Response(body={"status": "success", "data": rows})
            self.assertEqual(json["action"], "save")
            return _Response(text="")

        with patch.object(sheet_api.requests, "post", side_effect=post) as mocked:
            result = sheet_api.save_idempotent_to_sheet(
                "https://sheet.test/exec",
                payload,
                source_url=payload["link"],
                channel_id=payload["tiktok_id"],
                sheet_name="tổng",
            )

        self.assertEqual(result["row"], 123)
        self.assertTrue(result["recovered"])
        self.assertEqual(sum(call.kwargs["json"].get("action") == "save" for call in mocked.call_args_list), 1)

    def test_legacy_safe_post_json_save_is_also_guarded(self):
        payload = {"action": "save", "link": "https://example.com/legacy", "tiktok_id": "channel-b"}

        def post(_url, json, timeout):
            if json["action"] == "read_bulk_optimized":
                return _Response(body={"status": "success", "data": []})
            return _Response(body={"status": "success", "row": 88})

        with patch.object(sheet_api.requests, "post", side_effect=post) as mocked:
            result = sheet_api.safe_post_json("https://sheet.test/exec", payload)

        self.assertEqual(result["row"], 88)
        self.assertEqual(sum(call.kwargs["json"].get("action") == "save" for call in mocked.call_args_list), 1)


if __name__ == "__main__":
    unittest.main()
