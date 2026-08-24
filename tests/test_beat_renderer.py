import unittest

from shared.core.beat_timeline import compact_overlay_text, plan_beat_timeline


class BeatTimelineTests(unittest.TestCase):
    def test_timeline_uses_real_hook_and_total_audio_duration(self):
        beats = [
            {"role": "hook", "duration_hint": 2, "on_screen_text": "Giá vàng tăng 12 phần trăm", "motion": "slow_push_in"},
            {"role": "context", "duration_hint": 3},
            {"role": "evidence", "duration_hint": 5, "on_screen_text": "Tăng 12%"},
            {"role": "payoff", "duration_hint": 2},
        ]
        timeline = plan_beat_timeline(
            beats,
            total_duration=28.0,
            hook_duration=3.2,
            media_count=3,
            hook_text="Giá vàng tăng mạnh và điều cần lưu ý",
        )

        self.assertAlmostEqual(timeline.segments[0].duration, 3.2, places=2)
        self.assertAlmostEqual(timeline.segments[-1].end, 28.0, places=2)
        self.assertAlmostEqual(sum(item.duration for item in timeline.segments), 28.0, places=2)
        self.assertEqual([item.media_index for item in timeline.segments], [0, 1, 1, 2])
        self.assertLessEqual(len(timeline.first_frame_text.split()), 7)

    def test_legacy_fallback_is_deterministic(self):
        first = plan_beat_timeline(None, total_duration=12, media_count=3, hook_text="Một hook đủ rõ cho video")
        second = plan_beat_timeline([], total_duration=12, media_count=3, hook_text="Một hook đủ rõ cho video")
        self.assertTrue(first.used_fallback)
        self.assertEqual(first, second)
        self.assertEqual(first.segments[0].role, "hook")
        self.assertEqual(first.segments[-1].role, "payoff")

    def test_first_frame_text_is_capped_at_seven_words(self):
        text = compact_overlay_text("Một dòng hook rất dài cần được rút gọn ngay lập tức")
        self.assertEqual(len(text.split()), 7)

    def test_very_short_audio_never_creates_negative_beats(self):
        timeline = plan_beat_timeline(
            [
                {"role": "hook"},
                {"role": "evidence"},
                {"role": "payoff"},
            ],
            total_duration=0.3,
            hook_duration=0.2,
        )
        self.assertAlmostEqual(timeline.segments[-1].end, 0.3, places=3)
        self.assertTrue(all(segment.duration > 0 for segment in timeline.segments))

if __name__ == "__main__":
    unittest.main()
