import os
import tempfile
import unittest
from unittest.mock import patch

from shared.core.channel_learning import (
    ChannelLearningStore,
    build_channel_learning,
    load_prompt_learning,
)


def _records(per_group=3):
    rows = []
    index = 0
    for story_type in ("explainer", "warning"):
        for hook_type, watch_time, duration in (
            ("result", 15, 22),
            ("conflict", 8, 27),
        ):
            for _ in range(per_group):
                index += 1
                rows.append({
                    "video_id": f"video-{index}",
                    "channel_id": "Adsupnews",
                    "story_type": story_type,
                    "hook_type": hook_type,
                    "duration": duration,
                    "average_watch_time": watch_time,
                    "watched_full_rate": 0.65 if hook_type == "result" else 0.3,
                    "retention_6s": 0.8 if hook_type == "result" else 0.45,
                    "music_mood": "neutral_news",
                    "views": 1000,
                    "shares": 20 if hook_type == "result" else 2,
                    "saves": 10 if hook_type == "result" else 1,
                    "follows": 5 if hook_type == "result" else 0,
                    "measured_at": f"2026-08-{index + 1:02d}T00:00:00+00:00",
                })
    return rows


class ChannelLearningTests(unittest.TestCase):
    def test_refuses_to_conclude_with_small_sample(self):
        learning = build_channel_learning(
            _records()[:3],
            "Adsupnews",
            minimum_sample_size=6,
            minimum_group_size=2,
        )

        self.assertEqual("insufficient_sample", learning["status"])
        self.assertEqual([], learning["winning_hook_types"])
        self.assertEqual([], learning["prompt_lessons"])
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ChannelLearningStore(os.path.join(
                temp_dir,
                "channel_learning.json",
            ))
            with self.assertRaisesRegex(
                ValueError,
                "CHANNEL_LEARNING_REQUIRES_30_VIDEOS",
            ):
                store.upsert(learning, enabled=True)

    def test_uses_medians_and_compares_hooks_inside_story_type(self):
        rows = _records()
        rows.append({
            **rows[-1],
            "video_id": "viral-outlier",
            "views": 10_000_000,
            "average_watch_time": 1,
            "measured_at": "2026-08-23T00:00:00+00:00",
        })
        learning = build_channel_learning(
            rows,
            "Adsupnews",
            minimum_sample_size=6,
            minimum_group_size=2,
        )

        self.assertEqual("ready", learning["status"])
        self.assertEqual("result", learning["winning_hook_types"][0])
        self.assertEqual([20, 24], learning["best_duration_range"])
        self.assertTrue(learning["prompt_lessons"])
        hook_analysis = learning["analysis"]["hook_type"]
        self.assertGreater(
            hook_analysis[0]["median_relative_to_story_type"],
            hook_analysis[-1]["median_relative_to_story_type"],
        )

    def test_operator_must_enable_and_can_disable_or_delete(self):
        learning = build_channel_learning(
            _records(per_group=8),
            "Adsupnews",
            minimum_sample_size=30,
            minimum_group_size=5,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "channel_learning.json")
            store = ChannelLearningStore(path)
            stored = store.upsert(learning)
            self.assertFalse(stored["enabled"])
            self.assertEqual([], load_prompt_learning(
                "Adsupnews", path=path, enabled=True,
            ))

            store.set_enabled("Adsupnews", True)
            with patch.dict(
                os.environ,
                {"PERFORMANCE_LEARNING_ENABLED": "1"},
            ):
                lessons = load_prompt_learning("Adsupnews", path=path)
            self.assertTrue(lessons)
            store.set_enabled("Adsupnews", False)
            self.assertEqual([], load_prompt_learning(
                "Adsupnews", path=path, enabled=True,
            ))
            self.assertTrue(store.delete("Adsupnews"))
            self.assertIsNone(store.get("Adsupnews"))


if __name__ == "__main__":
    unittest.main()
