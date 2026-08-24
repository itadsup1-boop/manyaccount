import tempfile
import unittest
from pathlib import Path

from shared.core.beat_timeline import plan_beat_timeline
from shared.services.audio_director import plan_audio_cues


class AudioDirectorTests(unittest.TestCase):
    def test_cues_are_intentional_limited_and_sensitive_safe(self):
        timeline = plan_beat_timeline(
            [
                {"role": "hook", "duration_hint": 3},
                {
                    "role": "evidence",
                    "duration_hint": 4,
                    "on_screen_text": "Tăng 20%",
                },
                {"role": "turn", "duration_hint": 4},
                {"role": "payoff", "duration_hint": 3},
            ],
            total_duration=20,
            hook_duration=3,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            sfx_dir = Path(temp_dir)
            (sfx_dir / "number_pop.wav").write_bytes(b"test")
            (sfx_dir / "turn_whoosh.wav").write_bytes(b"test")
            cues = plan_audio_cues(timeline, sfx_dir=sfx_dir)
            sensitive = plan_audio_cues(
                timeline,
                sfx_dir=sfx_dir,
                is_sensitive=True,
            )

        self.assertGreaterEqual(len(cues), 1)
        self.assertLessEqual(len(cues), 2)
        self.assertEqual(sensitive, [])
        self.assertTrue(all(cue.timestamp >= 0 for cue in cues))

    def test_vietnamese_warning_selects_warning_asset(self):
        timeline = plan_beat_timeline(
            [{"role": "hook", "on_screen_text": "Cảnh báo giá tăng"}],
            total_duration=4,
            hook_duration=4,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            warning = Path(temp_dir) / "warning_alert.wav"
            warning.write_bytes(b"test")
            cues = plan_audio_cues(timeline, sfx_dir=temp_dir)

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].cue_type, "warning")


if __name__ == "__main__":
    unittest.main()
