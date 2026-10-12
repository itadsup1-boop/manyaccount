"""Regression tests for Windows render reliability and diagnostics."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from shared.core.beat_timeline import (
    plan_beat_timeline,
    resolve_intro_overlay_text,
)
from shared.core.safe_zone import plan_text_layout, validate_ass_file
from shared.modules import video_remix
from shared.modules.subtitle_renderer import (
    _apply_long_caption_preset,
    generate_text_ass,
)


class RenderReliabilityRegressionTests(unittest.TestCase):
    def test_intro_overlay_matches_spoken_title_not_compact_beat_label(self):
        spoken_title = (
            "Caption ghi 106 tỷ, nhưng trong video lại tính ra 102 tỷ"
        )
        timeline = plan_beat_timeline(
            [{
                "role": "hook",
                "voice_over": spoken_title,
                "on_screen_text": "106 tỷ hay 102 tỷ?",
            }],
            total_duration=4.0,
            hook_duration=4.0,
            hook_text=spoken_title,
        )

        self.assertEqual(
            resolve_intro_overlay_text(spoken_title, timeline),
            spoken_title,
        )
        self.assertNotEqual(timeline.first_frame_text, spoken_title)

    def test_watermark_removal_is_opt_in(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_config = os.path.join(temp_dir, "missing-render-config.json")
            with patch.object(video_remix, "RENDER_CONFIG_PATH", missing_config):
                config = video_remix.load_render_config()

        self.assertFalse(config["remove_source_watermark"])
        self.assertEqual(
            config["text_overlay_settings"]["position_mode"],
            "manual",
        )
        self.assertEqual(config["subtitle_settings"]["margin_v"], 320)
        self.assertEqual(config["subtitle_settings"]["font_size"], 52)
        self.assertFalse(config["subtitle_settings"]["enabled"])
        self.assertFalse(
            config["subtitle_settings"]["adaptive_long_caption"]
        )
        self.assertEqual(
            config["subtitle_settings"]["position_mode"],
            "manual",
        )

    def test_tiktok_subtitle_boolean_setting_is_parsed_safely(self):
        self.assertTrue(video_remix._as_bool(True))
        self.assertTrue(video_remix._as_bool("on"))
        self.assertFalse(video_remix._as_bool(False))
        self.assertFalse(video_remix._as_bool("off"))
        self.assertFalse(video_remix._as_bool(None, default=False))

    def test_tiktok_karaoke_is_hard_disabled(self):
        self.assertFalse(video_remix.TIKTOK_KARAOKE_SUBTITLES_ENABLED)
        self.assertFalse(
            video_remix._tiktok_karaoke_enabled({"enabled": True})
        )

    def test_manual_subtitle_can_be_placed_below_safe_zone_without_qa_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ass_path = os.path.join(temp_dir, "manual-low.ass")
            generated = generate_text_ass(
                "Phụ đề karaoke đặt thấp theo lựa chọn của người vận hành",
                ass_path,
                duration=3.0,
                font_size=46,
                margin_v=60,
                clamp_to_safe_zone=False,
            )
            result = validate_ass_file(generated)

        self.assertTrue(result.passed)
        self.assertIn(
            "SUBTITLE_MANUAL_OVER_BOTTOM_CAPTION",
            result.warnings,
        )

    def test_long_script_does_not_override_manual_subtitle_style(self):
        resolved = _apply_long_caption_preset(
            140,
            words_per_line=7,
            font_size=46,
            margin_v=320,
            margin_l=90,
            margin_r=150,
        )

        self.assertEqual(resolved, (7, 46, 320, 90, 150))

    def test_adaptive_long_caption_remains_available_when_explicitly_enabled(self):
        resolved = _apply_long_caption_preset(
            140,
            words_per_line=7,
            font_size=64,
            margin_v=320,
            margin_l=90,
            margin_r=150,
            adaptive_long_caption=True,
        )

        self.assertEqual(resolved, (6, 58, 460, 110, 180))

    def test_long_intro_text_auto_fits_instead_of_aborting_render(self):
        title = (
            "Giá vàng trong nước thấp hơn thế giới nhưng nhà đầu tư cần "
            "hiểu rõ nguyên nhân trước khi quyết định mua vào hôm nay"
        )

        layout = plan_text_layout(
            title,
            font_size=64,
            max_width=720,
        )

        self.assertLessEqual(len(layout.lines), 2)
        self.assertLess(layout.font_size, 64)

    def test_manual_title_y_is_stable_for_one_or_two_lines(self):
        one_line = plan_text_layout(
            "MỘT DÒNG TITLE",
            font_size=50,
            preferred_y=1344,
            max_width=918,
            clamp_to_safe_zone=False,
        )
        two_lines = plan_text_layout(
            "LUẬT SƯ XIN GIẢM NHẸ HÌNH PHẠT CHO CHỊ DÂN VÀ AN TÂY",
            font_size=50,
            preferred_y=1344,
            max_width=918,
            clamp_to_safe_zone=False,
        )

        self.assertEqual(one_line.y, 1344)
        self.assertEqual(two_lines.y, 1344)
        self.assertEqual(one_line.width, 918)
        self.assertEqual(two_lines.width, 918)

    def test_pathologically_long_overlay_is_shortened_not_rejected(self):
        layout = plan_text_layout(
            " ".join(["thông tin"] * 120),
            font_size=64,
            max_width=720,
        )

        self.assertLessEqual(len(layout.lines), 2)
        self.assertTrue(layout.truncated)

    def test_persistent_title_wraps_without_ellipsis_when_requested(self):
        title = " ".join(["TIÊU ĐỀ ĐƯỢC GIỮ ĐẦY ĐỦ"] * 8)
        layout = plan_text_layout(
            title,
            font_size=64,
            preferred_y=1200,
            max_width=720,
            clamp_to_safe_zone=False,
            allow_extra_lines=True,
        )

        self.assertGreater(len(layout.lines), 2)
        self.assertFalse(layout.truncated)
        self.assertNotIn("…", " ".join(layout.lines))
        self.assertEqual(
            " ".join(" ".join(layout.lines).split()),
            " ".join(title.split()),
        )

    def test_render_failure_is_saved_outside_worker_temp(self):
        with tempfile.TemporaryDirectory() as project_root:
            worker_temp = os.path.join(project_root, "worker-temp")
            os.makedirs(worker_temp)
            with patch.object(video_remix, "PROJECT_ROOT", project_root):
                report_path = video_remix._record_render_failure(
                    "segment.mkv",
                    ["ffmpeg", "-i", "source.mp4", "segment.mkv"],
                    b"filter graph failed",
                    worker_temp,
                    error_type="FFmpegError",
                )

            self.assertTrue(os.path.isfile(report_path))
            self.assertTrue(
                os.path.isfile(os.path.join(worker_temp, "render_errors.log"))
            )
            with open(report_path, "r", encoding="utf-8") as handle:
                report = handle.read()
            self.assertIn("error_type=FFmpegError", report)
            self.assertIn("filter graph failed", report)
            self.assertIn("source.mp4", report)


if __name__ == "__main__":
    unittest.main()
