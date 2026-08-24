import os
import tempfile
import unittest

from scripts.import_tiktok_metrics import import_metric_rows, load_metric_rows
from shared.services.performance_store import PerformanceStore


class MetricsImporterTests(unittest.TestCase):
    def test_jsonl_reads_each_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "metrics.jsonl")
            with open(path, "w", encoding="utf-8") as file:
                file.write('{"video_id":"v1","channel_id":"a"}\n')
                file.write('{"video_id":"v2","channel_id":"a"}\n')
            rows, _ = load_metric_rows(input_path=path)
        self.assertEqual(["v1", "v2"], [row["video_id"] for row in rows])

    def test_csv_import_keeps_valid_rows_and_reports_invalid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = os.path.join(temp_dir, "metrics.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as file:
                file.write(
                    "video_id,views,watched_full_rate\n"
                    "v1,100,30%\n"
                    ",200,40%\n"
                    "v2,300,50%\n"
                )
            rows, source_name = load_metric_rows(input_path=csv_path)
            db_path = os.path.join(temp_dir, "performance.sqlite3")
            with PerformanceStore(db_path) as store:
                summary, canonical = import_metric_rows(
                    rows,
                    store=store,
                    defaults={
                        "channel_id": "channel-a",
                        "measurement_window": "24h",
                        "import_source": source_name,
                    },
                )
                self.assertEqual(3, summary.input_rows)
                self.assertEqual(2, summary.valid_rows)
                self.assertEqual(1, summary.rejected_rows)
                self.assertEqual(2, store.count())
                self.assertEqual({"v1", "v2"}, {row["video_id"] for row in canonical})

    def test_strict_mode_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "performance.sqlite3")
            with PerformanceStore(db_path) as store:
                with self.assertRaises(ValueError):
                    import_metric_rows(
                        [{"video_id": "v1"}, {"views": 20}],
                        store=store,
                        defaults={"channel_id": "channel-a"},
                        strict=True,
                    )
                self.assertEqual(0, store.count())


if __name__ == "__main__":
    unittest.main()
