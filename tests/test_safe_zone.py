import tempfile
import unittest
from pathlib import Path

from shared.core.safe_zone import (
    get_subtitle_constraints,
    plan_text_layout,
    validate_ass_file,
    validate_element_box,
    validate_subtitle_layout,
)
from shared.modules.subtitle_renderer import generate_text_ass


class SafeZoneTests(unittest.TestCase):
    def test_text_layout_clamps_legacy_bottom_position(self):
        layout = plan_text_layout(
            "Tin nóng thay đổi trực tiếp người dùng",
            font_size=60,
            preferred_y=1450,
            max_width=950,
        )
        self.assertLessEqual(layout.y + layout.height, 1320)
        self.assertGreaterEqual(layout.x, 60)
        self.assertLessEqual(layout.x + layout.width, 900)

    def test_text_layout_rejects_more_than_two_lines(self):
        with self.assertRaisesRegex(ValueError, "SAFE_ZONE_TOO_MANY_LINES"):
            plan_text_layout(" ".join(["nội dung"] * 80), font_size=65)

    def test_hook_inside_zone_passes_and_right_controls_fail(self):
        valid = validate_element_box(
            "hook",
            {"x": 80, "y": 300, "width": 700, "height": 180},
        )
        blocked = validate_element_box(
            "hook",
            {"x": 850, "y": 300, "width": 180, "height": 180},
        )
        self.assertTrue(valid.passed)
        self.assertFalse(blocked.passed)

    def test_subtitle_margins_block_platform_ui_overlap(self):
        result = validate_subtitle_layout(
            font_size=64,
            margin_v=100,
            margin_l=90,
            margin_r=40,
        )
        self.assertFalse(result.passed)
        self.assertIn("SUBTITLE_OVER_BOTTOM_CAPTION", result.errors)
        self.assertIn("SUBTITLE_UNDER_RIGHT_CONTROLS", result.errors)

    def test_long_caption_has_smaller_fallback(self):
        normal = get_subtitle_constraints()
        long_caption = get_subtitle_constraints(long_caption=True)
        self.assertLess(long_caption["font_size"], normal["max_font_size"])
        self.assertLess(long_caption["max_words"], normal["max_words"])

    def test_generated_ass_stays_inside_safe_zone(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "safe.ass")
            generate_text_ass(
                "Một nội dung đủ dài để tạo phụ đề kiểm tra an toàn.",
                path,
                duration=4,
            )
            result = validate_ass_file(path)
        self.assertTrue(result.passed, result.errors)


if __name__ == "__main__":
    unittest.main()
