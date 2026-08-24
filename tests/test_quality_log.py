import json
import os
import tempfile
import unittest

from shared.core.quality_log import append_quality_event


class QualityLogTests(unittest.TestCase):
    def test_structured_failure_keeps_legacy_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "quality.jsonl")
            entry = append_quality_event(
                "article",
                "channel-a",
                8,
                "failed",
                stage="qa_passed",
                item_id="https://example.com/a",
                error_code="SAFE_ZONE_FAILED",
                retryable=False,
                message="subtitle outside safe zone",
                qa={"passed": False},
                log_path=path,
            )
            with open(path, "r", encoding="utf-8") as file:
                stored = json.loads(file.readline())

        self.assertEqual("failed", entry["st"])
        self.assertEqual("qa_passed", stored["stage"])
        self.assertEqual("SAFE_ZONE_FAILED", stored["error_code"])
        self.assertFalse(stored["retryable"])
        self.assertEqual({"passed": False}, stored["qa"])


if __name__ == "__main__":
    unittest.main()
