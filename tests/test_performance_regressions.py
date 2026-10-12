"""Regression coverage for retention/watch-time measurement and learning."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.core.channel_learning import build_channel_learning
from shared.core.experiment_manager import evaluate_experiment
from shared.core.performance_analyzer import (
    aggregate_performance,
    find_snapshot_anomalies,
    normalize_performance_record,
)
from shared.core.performance_dashboard import build_performance_dashboard
from shared.services.performance_store import PerformanceStore


def _metric_row(
    video_id: str = "video-1",
    *,
    variant: str = "control",
    measured_at: str = "2026-08-02T00:00:00+00:00",
    retention_2s: float = 0.80,
    retention_6s: float = 0.60,
) -> dict:
    return {
        "video_id": video_id,
        "channel_id": "channel-1",
        "source_type": "article",
        "duration": 20,
        "views": 1_000,
        "average_watch_time": 10,
        "watched_full_rate": 0.35,
        "retention_2s": retention_2s,
        "retention_6s": retention_6s,
        "likes": 20,
        "comments": 3,
        "shares": 5,
        "saves": 4,
        "follows": 2,
        "story_type": "explainer",
        "hook_type": "result",
        "music_mood": "neutral_news",
        "experiment_id": "retention-test",
        "experiment_variant": variant,
        "published_at": "2026-08-01T00:00:00+00:00",
        "measured_at": measured_at,
        "measurement_window": "24h",
    }


class PerformanceRegressionTests(unittest.TestCase):
    def test_tiktok_count_headers_are_converted_to_retention_rates(self) -> None:
        normalized = normalize_performance_record({
            "video_id": "video-counts",
            "channel_id": "channel-1",
            "views": "10K",
            "duration": "20",
            "average watch duration": "12",
            "watched full video rate": "40%",
            "2-second video views": "7,000",
            "6-second video views": "5,000",
            "published_at": "2026-08-01",
            "measured_at": "2026-08-02",
        })
        self.assertAlmostEqual(normalized["average_watch_time"], 12)
        self.assertAlmostEqual(normalized["retention_2s"], 0.70)
        self.assertAlmostEqual(normalized["retention_6s"], 0.50)
        self.assertAlmostEqual(normalized["watched_full_rate"], 0.40)

    def test_aggregate_reports_weighted_watch_and_retention_drop(self) -> None:
        first = _metric_row("video-1", retention_2s=0.8, retention_6s=0.6)
        second = _metric_row("video-2", retention_2s=0.7, retention_6s=0.5)
        second["views"] = 9_000
        summary = aggregate_performance([first, second])
        self.assertEqual(summary["median_retention_drop_2s_to_6s"], 20.0)
        self.assertEqual(summary["weighted_watch_percentage"], 50.0)
        self.assertEqual(summary["data_quality"]["watch_time_view_coverage"], 100.0)

    def test_retention_anomaly_is_reported(self) -> None:
        valid = _metric_row("video-1", retention_2s=0.6, retention_6s=0.5)
        invalid = _metric_row(
            "video-1",
            measured_at="2026-08-03T00:00:00+00:00",
            retention_2s=0.4,
            retention_6s=0.5,
        )
        anomalies = find_snapshot_anomalies([valid, invalid])
        self.assertTrue(any(item["error_code"] == "RETENTION_6S_GT_2S" for item in anomalies))

    def test_learning_excludes_missing_and_invalid_retention_rows(self) -> None:
        rows = [_metric_row(f"video-{index}") for index in range(30)]
        rows[0]["average_watch_time"] = 0
        rows[1]["retention_6s"] = 0.9
        rows[1]["retention_2s"] = 0.4
        learning = build_channel_learning(
            rows,
            "channel-1",
            minimum_sample_size=28,
            minimum_group_size=5,
        )
        self.assertEqual(learning["status"], "ready")
        self.assertEqual(learning["usable_sample_size"], 28)
        self.assertEqual(learning["excluded_sample_size"], 2)
        self.assertEqual(
            learning["retention_diagnostics"]["median_retention_drop_2s_to_6s"],
            20.0,
        )
        self.assertTrue(any("Watch-time" in item for item in learning["prompt_lessons"]))

    def test_experiment_treats_retention_drop_as_lower_is_better(self) -> None:
        rows = []
        for index in range(30):
            rows.append(_metric_row(
                f"control-{index}",
                variant="control",
                retention_2s=0.8,
                retention_6s=0.4,
            ))
            rows.append(_metric_row(
                f"variant-{index}",
                variant="variant",
                retention_2s=0.8,
                retention_6s=0.7,
            ))
        experiment = {
            "experiment_id": "retention-test",
            "name": "Retention drop",
            "channel_id": "channel-1",
            "status": "running",
            "source_types": ["article"],
            "primary_metric": "median_retention_drop_2s_to_6s",
            "minimum_sample_size": 30,
            "variants": [
                {"name": "control", "weight": 50, "changes": {"hook_type": "result"}},
                {"name": "variant", "weight": 50, "changes": {"hook_type": "conflict"}},
            ],
        }
        report = evaluate_experiment(experiment, rows, minimum_group_size=5)
        self.assertTrue(report["eligible"])
        self.assertEqual(report["leader"], "variant")
        self.assertEqual(report["absolute_difference"], 30.0)

    def test_performance_store_upsert_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "performance.sqlite3"
            with PerformanceStore(path) as store:
                record = store.upsert(_metric_row())
                store.upsert({**_metric_row(), "views": 2_000})
                rows = store.list_measurements()
                self.assertEqual(record["snapshot_key"], rows[0]["snapshot_key"])
                self.assertEqual(store.count(), 1)
                self.assertEqual(rows[0]["views"], 2_000)

    def test_dashboard_exposes_retention_coverage_and_derived_metrics(self) -> None:
        dashboard = build_performance_dashboard(
            [_metric_row("video-1")],
            min_samples=1,
            timezone_name="UTC",
        )
        self.assertEqual(dashboard["status"], "ready")
        self.assertEqual(dashboard["overview"]["median_retention_drop_2s_to_6s"], 20.0)
        self.assertEqual(
            dashboard["data_quality"]["metric_coverage"]["with_retention_6s"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
