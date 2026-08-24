import os
import tempfile
import unittest

from shared.services.performance_store import PerformanceStore


class PerformanceStoreTests(unittest.TestCase):
    def test_upsert_is_idempotent_per_video_and_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "performance.sqlite3")
            with PerformanceStore(path) as store:
                base = {
                    "video_id": "v1",
                    "channel_id": "channel-a",
                    "measured_at": "2026-08-20T02:00:00+00:00",
                    "measurement_window": "2h",
                    "views": 100,
                    "experiment_id": "hook-test",
                    "experiment_variant": "control",
                }
                store.upsert(base)
                store.upsert({**base, "views": 150})
                self.assertEqual(1, store.count())
                self.assertEqual(150, store.list_measurements()[0]["views"])
                self.assertEqual(
                    "control",
                    store.list_measurements()[0]["experiment_variant"],
                )
                store.upsert({
                    **base,
                    "views": 300,
                    "measured_at": "2026-08-21T00:00:00+00:00",
                    "measurement_window": "24h",
                })
                self.assertEqual(2, store.count())
                self.assertEqual(1, len(store.list_measurements(measurement_window="24h")))

    def test_batch_validation_is_atomic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "performance.sqlite3")
            with PerformanceStore(path) as store:
                with self.assertRaisesRegex(ValueError, "MISSING_VIDEO_ID"):
                    store.upsert_many([
                        {"video_id": "ok", "channel_id": "channel-a"},
                        {"channel_id": "channel-a"},
                    ])
                self.assertEqual(0, store.count())


if __name__ == "__main__":
    unittest.main()
