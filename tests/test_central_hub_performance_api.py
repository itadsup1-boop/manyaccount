import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from adsup_central_hub.backend import main
from shared.services.performance_store import PerformanceStore


class CentralHubPerformanceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "performance.sqlite3")
        self.log_path = os.path.join(self.temp_dir.name, "quality.jsonl")
        with PerformanceStore(self.db_path) as store:
            store.upsert({
                "video_id": "v1",
                "channel_id": "channel-a",
                "measured_at": "2026-08-21T01:00:00+00:00",
                "measurement_window": "24h",
                "views": 500,
                "duration": 20,
                "average_watch_time": 12,
                "watched_full_rate": "45%",
                "retention_6s": "60%",
                "shares": 10,
                "saves": 5,
                "follows": 2,
            })
        events = [
            {
                "ts": "2026-08-21T01:00:00+00:00",
                "pl": "article",
                "src": "channel-a",
                "status": "uploaded",
                "stage": "uploaded",
                "item_id": "article-1",
            },
            {
                "ts": "2026-08-21T02:00:00+00:00",
                "pl": "tiktok_matrix",
                "src": "channel-a",
                "status": "failed",
                "stage": "rendered",
                "error_code": "RENDER_FAILED",
                "item_id": "video-2",
            },
        ]
        with open(self.log_path, "w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")
        self.db_patch = patch.object(main, "PERFORMANCE_DB_PATH", self.db_path)
        self.log_patch = patch.object(main, "QUALITY_LOG_PATH", self.log_path)
        self.db_patch.start()
        self.log_patch.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.log_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_performance_stats_and_pipeline_routes_use_runtime_data(self):
        performance = self.client.get(
            "/api/dashboard/performance",
            params={"channel_id": "channel-a", "min_samples": 1},
        )
        self.assertEqual(200, performance.status_code)
        payload = performance.json()
        self.assertEqual("ready", payload["status"])
        self.assertEqual(1, payload["overview"]["sample_size"])
        self.assertEqual(500, payload["overview"]["total_views"])
        self.assertEqual(1, payload["pipeline"]["failures"]["total"])

        pipeline = self.client.get("/api/dashboard/pipeline-errors")
        self.assertEqual(200, pipeline.status_code)
        self.assertEqual(1, pipeline.json()["pipeline"]["failures"]["total"])

        stats = self.client.get("/api/dashboard/stats")
        self.assertEqual(200, stats.status_code)
        self.assertEqual(1, stats.json()["articles_processed"])
        self.assertEqual(0, stats.json()["tiktok_uploads"])
        self.assertEqual("Needs attention", stats.json()["system_health"])

    def test_invalid_date_and_sample_filters_return_422(self):
        invalid_date = self.client.get(
            "/api/dashboard/performance",
            params={"start_date": "21/08/2026"},
        )
        invalid_sample = self.client.get(
            "/api/dashboard/performance",
            params={"min_samples": 0},
        )
        self.assertEqual(422, invalid_date.status_code)
        self.assertEqual("INVALID_START_DATE", invalid_date.json()["detail"])
        self.assertEqual(422, invalid_sample.status_code)


if __name__ == "__main__":
    unittest.main()
