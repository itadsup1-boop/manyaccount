import unittest
from datetime import datetime, timezone

from shared.core.performance_analyzer import (
    analyze_performance,
    find_snapshot_anomalies,
    normalize_performance_record,
    parse_number,
)


class PerformanceAnalyzerTests(unittest.TestCase):
    def test_normalizes_vietnamese_csv_and_percentages(self):
        record = normalize_performance_record(
            {
                "ID video": "731234",
                "Kênh": "@Adsupnews",
                "Link": "https://www.tiktok.com/@adsup/video/731234",
                "Lượt xem": "1.2K",
                "Tỷ lệ xem hết": "35,5%",
                "Thời lượng": "25",
                "Thời gian xem trung bình": "12.5",
                "Ngày đăng": "2026-08-20 00:00:00",
                "Ngày đo": "2026-08-21 00:00:00",
                "test_id": "hook-test",
                "variant": "control",
            },
            now=datetime(2026, 8, 21, tzinfo=timezone.utc),
        )
        self.assertEqual("731234", record["video_id"])
        self.assertEqual("Adsupnews", record["channel_id"])
        self.assertEqual(1200, record["views"])
        self.assertAlmostEqual(0.355, record["watched_full_rate"])
        self.assertEqual("24h", record["measurement_window"])
        self.assertEqual("tiktok.com", record["source_domain"])
        self.assertEqual("hook-test", record["experiment_id"])
        self.assertEqual("control", record["experiment_variant"])

    def test_number_parser_supports_exports(self):
        self.assertEqual(1234, parse_number("1,234"))
        self.assertEqual(12500, parse_number("12.5K"))
        self.assertEqual(1_200_000, parse_number("1,2 triệu"))
        self.assertAlmostEqual(0.35, parse_number("35", rate=True))

    def test_latest_snapshot_and_median_resist_viral_outlier(self):
        rows = []
        for video_id, views, measured_at in (
            ("a", 100, "2026-08-20T02:00:00+00:00"),
            ("a", 120, "2026-08-21T00:00:00+00:00"),
            ("b", 130, "2026-08-21T00:00:00+00:00"),
            ("c", 100_000, "2026-08-21T00:00:00+00:00"),
        ):
            rows.append(normalize_performance_record({
                "video_id": video_id,
                "channel_id": "channel-a",
                "views": views,
                "duration": 25,
                "average_watch_time": 12.5,
                "watched_full_rate": "40%",
                "measured_at": measured_at,
                "measurement_window": "24h" if views != 100 else "2h",
            }))
        result = analyze_performance(rows, min_samples=3)
        self.assertEqual(3, result["overview"]["sample_size"])
        self.assertEqual(130, result["overview"]["median_views"])
        channel = result["breakdowns"]["channel_id"][0]
        self.assertTrue(channel["eligible"])
        self.assertEqual(50.0, result["overview"]["median_watch_percentage"])
        self.assertEqual("ready", result["status"])

    def test_missing_required_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "MISSING_VIDEO_ID"):
            normalize_performance_record({"channel_id": "channel-a", "views": 10})

    def test_invalid_explicit_measured_at_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_MEASURED_AT"):
            normalize_performance_record({
                "video_id": "v1",
                "channel_id": "channel-a",
                "measured_at": "not-a-date",
            })

    def test_warns_when_cumulative_metrics_go_backwards(self):
        rows = [
            normalize_performance_record({
                "video_id": "v1", "channel_id": "a", "views": 100,
                "measured_at": "2026-08-20T02:00:00+00:00", "window": "2h",
            }),
            normalize_performance_record({
                "video_id": "v1", "channel_id": "a", "views": 90,
                "measured_at": "2026-08-21T00:00:00+00:00", "window": "24h",
            }),
        ]
        warnings = find_snapshot_anomalies(rows)
        self.assertEqual("NON_MONOTONIC_VIEWS", warnings[0]["error_code"])


if __name__ == "__main__":
    unittest.main()
