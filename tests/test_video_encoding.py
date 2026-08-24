import json
import unittest
from pathlib import Path

from shared.core.video_encoding import (
    FINAL_AUDIO_ARGS,
    FINAL_VIDEO_ARGS,
    build_color_filter,
    final_output_args,
    intermediate_output_args,
    resolve_color_grade,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class VideoEncodingTests(unittest.TestCase):
    def test_final_preset_matches_vertical_delivery_contract(self):
        args = final_output_args()
        expected_pairs = {
            "-c:v": "libx264",
            "-crf": "19",
            "-pix_fmt": "yuv420p",
            "-profile:v": "high",
            "-level:v": "4.1",
            "-r": "30",
            "-fps_mode": "cfr",
            "-g": "60",
            "-c:a": "aac",
            "-ar": "48000",
            "-ac": "2",
        }
        for option, value in expected_pairs.items():
            self.assertEqual(args[args.index(option) + 1], value)
        self.assertIn("+faststart", FINAL_VIDEO_ARGS)
        self.assertIn("192k", FINAL_AUDIO_ARGS)

    def test_color_grade_is_deterministic_and_bounded(self):
        style = {
            "grading_preset": "sports_energy",
            "contrast": 9,
            "saturation": -3,
            "brightness": 2,
            "sharpen": 5,
        }
        first = resolve_color_grade(video_style=style)
        second = resolve_color_grade(video_style=style)
        self.assertEqual(first, second)
        self.assertEqual(first.contrast, 1.08)
        self.assertEqual(first.saturation, 0.90)
        self.assertEqual(first.brightness, 0.04)
        self.assertEqual(first.sharpen, 0.35)
        self.assertNotIn("random", build_color_filter(first))

    def test_sensitive_context_overrides_channel_grade(self):
        grade = resolve_color_grade(
            is_sensitive=True,
            video_style={"grading_preset": "entertainment_pop"},
        )
        self.assertEqual(grade.name, "sensitive_neutral")

    def test_intermediate_is_lossless_video_and_audio(self):
        args = intermediate_output_args()
        self.assertEqual(args[args.index("-crf") + 1], "0")
        self.assertEqual(args[args.index("-c:a") + 1], "flac")
        self.assertEqual(args[args.index("-ar") + 1], "48000")

    def test_all_channel_profiles_have_valid_fixed_grade(self):
        config_path = PROJECT_ROOT / "config" / "channel_editorial_profiles.json"
        profiles = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(len(profiles), 8)
        for channel_id, channel in profiles.items():
            style = channel["content_profile"]["video_style"]
            grade = resolve_color_grade(video_style=style)
            self.assertEqual(grade.name, style["grading_preset"], channel_id)

    def test_renderers_do_not_contain_fingerprint_randomization(self):
        paths = [
            PROJECT_ROOT / "apps" / "creator_article" / "article_ffmpeg.py",
            PROJECT_ROOT / "apps" / "creator_facebook" / "fb_pipeline.py",
            PROJECT_ROOT / "shared" / "modules" / "video_remix.py",
        ]
        forbidden = (
            "random.uniform",
            "lenscorrection",
            "noise=alls",
            "os.urandom",
            "preset='ultrafast'",
        )
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, source, f"{token} remains in {path.name}")


if __name__ == "__main__":
    unittest.main()
