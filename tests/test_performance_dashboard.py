import json
import os
import tempfile
import unittest

from shared.core.performance_analyzer import normalize_performance_record
from shared.core.performance_dashboard import (
    build_performance_dashboard,
    dashboard_compat_stats,
    load_performance_dashboard,
    read_quality_events,
)
from shared.services.performance_store import PerformanceStore


def make_record(
    video_id,
    channel_id,
    measured_at,
    views,
    *,
    window="24h",
    story_type="news",
    hook_type="question",
    music_mood="neutral",
    duration=20,
    watch_time=10,
    completion="40%",
    retention_6s="55%",
    shares=4,
    saves=2,
    follows=1,
):
    return normalize_performance_record({
        "video_id": video_id,
        "channel_id": channel_id,
        "measured_at": measured_at,
        "measurement_window": window,
        "views": views,
        "story_type": story_type,
        "hook_type": hook_type,
        "music_mood": music_mood,
        "duration": duration,
        "average_watch_time": watch_time,
        "watched_full_rate": completion,
        "retention_6s": retention_6s,
        "shares": shares,
        "saves": saves,
        "follows": follows,
        "title": f"Video {video_id}",
    })


class PerformanceDashboardTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            make_record(
                "v1", "channel-a", "2026-08-20T02:00:00+00:00", 100,
                window="2h", story_type="serious", music_mood="tense",
            ),
            make_record(
                "v1", "channel-a", "2026-08-21T00:00:00+00:00", 300,
                story_type="serious", music_mood="tense", shares=12,
            ),
            make_record(
                "v2", "channel-a", "2026-08-21T01:00:00+00:00", 200,
                story_type="fun", hook_type="surprise", music_mood="upbeat",
                duration=28, watch_time=14,
            ),
            make_record(
                "v3", "channel-b", "2026-08-22T01:00:00+00:00", 1000,
                story_type="normal", hook_type="fact", duration=35,
            ),
        ]
        self.events = [
            {
                "ts": "2026-08-20T17:30:00+00:00",
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
                "retryable": True,
                "message": "FFmpeg failed",
                "item_id": "video-1",
            },
            {
                "ts": "2026-08-22T02:00:00+00:00",
                "pl": "facebook",
                "src": "channel-b",
                "status": "uploaded",
                "stage": "uploaded",
                "item_id": "facebook-1",
            },
        ]

    def test_uses_latest_snapshot_and_builds_real_kpis(self):
        result = build_performance_dashboard(
            self.records,
            self.events,
            min_samples=3,
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual(3, result["overview"]["sample_size"])
        self.assertEqual(300, result["overview"]["median_views"])
        self.assertEqual(3, len(result["top_videos"]))
        self.assertEqual("v3", result["top_videos"][0]["video_id"])
        self.assertEqual(2, len(result["trends"]))
        self.assertEqual("attention", result["system_health"])
        self.assertEqual(1, result["pipeline"]["failures"]["total"])
        self.assertEqual(
            "rendered",
            result["pipeline"]["failures"]["by_stage"][0]["value"],
        )

    def test_filters_dates_in_vietnam_timezone_and_channel(self):
        result = build_performance_dashboard(
            self.records,
            self.events,
            start_date="2026-08-21",
            end_date="2026-08-21",
            channel_id="CHANNEL-A",
            min_samples=2,
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual(2, result["overview"]["sample_size"])
        self.assertEqual({"v1", "v2"}, {
            item["video_id"] for item in result["top_videos"]
        })
        self.assertEqual(2, result["pipeline"]["total_events"])
        self.assertEqual("2026-08-21", result["trends"][0]["date"])

    def test_filters_exact_measurement_window(self):
        result = build_performance_dashboard(
            self.records,
            measurement_window="2h",
            min_samples=1,
        )
        self.assertEqual(1, result["overview"]["sample_size"])
        self.assertEqual(100, result["overview"]["total_views"])

    def test_rejects_invalid_filters(self):
        with self.assertRaisesRegex(ValueError, "INVALID_START_DATE"):
            build_performance_dashboard(self.records, start_date="21/08/2026")
        with self.assertRaisesRegex(ValueError, "INVALID_DATE_RANGE"):
            build_performance_dashboard(
                self.records,
                start_date="2026-08-22",
                end_date="2026-08-21",
            )
        with self.assertRaisesRegex(ValueError, "INVALID_MIN_SAMPLES"):
            build_performance_dashboard(self.records, min_samples=0)

    def test_reads_jsonl_and_reports_malformed_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "quality.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(self.events[0]) + "\n")
                handle.write("not-json\n")
                handle.write("[]\n")
            events, malformed = read_quality_events(path)
        self.assertEqual(1, len(events))
        self.assertEqual(2, malformed)

    def test_loads_store_and_does_not_create_missing_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "performance.sqlite3")
            log_path = os.path.join(temp_dir, "quality.jsonl")
            missing_path = os.path.join(temp_dir, "missing.sqlite3")
            with PerformanceStore(db_path) as store:
                store.upsert_many(self.records)
            loaded = load_performance_dashboard(
                db_path=db_path,
                quality_log_path=log_path,
                min_samples=3,
            )
            empty = load_performance_dashboard(
                db_path=missing_path,
                quality_log_path=log_path,
            )
            self.assertEqual(3, loaded["overview"]["sample_size"])
            self.assertEqual("empty", loaded["system_health"])
            self.assertEqual("empty", empty["status"])
            self.assertFalse(os.path.exists(missing_path))

    def test_legacy_stats_use_real_pipeline_counts_and_aliases(self):
        dashboard = build_performance_dashboard(
            [],
            [
                *self.events,
                {
                    "ts": "2026-08-22T03:00:00+00:00",
                    "pl": "tiktok_auto_clone",
                    "status": "uploaded",
                    "stage": "uploaded",
                    "item_id": "video-2",
                },
            ],
        )
        stats = dashboard_compat_stats(dashboard, active_tools=2)
        self.assertEqual(2, stats["active_tools"])
        self.assertEqual(1, stats["articles_processed"])
        self.assertEqual(1, stats["facebook_posts"])
        self.assertEqual(1, stats["tiktok_uploads"])
        self.assertEqual("Needs attention", stats["system_health"])


if __name__ == "__main__":
    unittest.main()
