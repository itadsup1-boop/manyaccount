import json
import unittest
from unittest.mock import patch

from shared.core.channel_editorial import load_channel_editorials
from shared.core.prompt_builder import (
    build_output_schema,
    build_prompt,
    extract_operator_overrides,
    get_content_profile,
    get_tone_preset,
    get_video_style,
    get_voice_preset,
)


REQUIRED_PROFILE_FIELDS = {
    "brand_voice",
    "tone_by_context",
    "audience_pains",
    "content_pillars",
    "allowed_story_types",
    "preferred_hook_types",
    "banned_phrases",
    "cta_styles",
    "evidence_standard",
    "video_style",
    "winning_examples",
    "losing_examples",
}


class PromptBuilderTests(unittest.TestCase):
    def setUp(self):
        self.runtime_patch = patch(
            "shared.core.prompt_builder.load_runtime_content_profile",
            return_value={},
        )
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)

    def test_all_editorial_profiles_have_phase_two_presets(self):
        editorials = load_channel_editorials()

        self.assertGreaterEqual(len(editorials), 8)
        for channel_id, editorial in editorials.items():
            profile = editorial.get("content_profile", {})
            self.assertTrue(
                REQUIRED_PROFILE_FIELDS.issubset(profile),
                f"{channel_id} thiếu field Đợt 2",
            )
            self.assertIn("default", editorial.get("voice_presets", {}))
            self.assertIn(
                "color_preset",
                profile.get("video_style", {}),
            )
            self.assertIn(
                "text_preset",
                profile.get("video_style", {}),
            )
            self.assertIn(
                "motion_preset",
                profile.get("video_style", {}),
            )

    def test_channels_keep_distinct_voice_tone_and_visual_identity(self):
        finance = get_content_profile("taichinh24444h")
        showbiz = get_content_profile("showbiz124h")
        sport = get_content_profile("adsup_sport")

        self.assertNotEqual(finance["brand_voice"], showbiz["brand_voice"])
        self.assertNotEqual(
            finance["tone_by_context"]["warning"],
            showbiz["tone_by_context"]["entertainment_drama"],
        )
        self.assertNotEqual(
            get_video_style("taichinh24444h")["color_preset"]["primary"],
            get_video_style("adsup_sport")["color_preset"]["primary"],
        )
        self.assertIn("sports_moment", sport["allowed_story_types"])

    def test_sensitive_context_overrides_story_tone_and_voice_speed(self):
        tone = get_tone_preset(
            "Adsupnews",
            story_type="breaking_update",
            is_sensitive=True,
        )
        voice = get_voice_preset(
            "Adsupnews",
            story_type="breaking_update",
            is_sensitive=True,
        )

        self.assertIn("đồng cảm", tone.lower())
        self.assertEqual(voice["speed"], 0.97)
        self.assertIn("nạn nhân", voice["direction"].lower())

    def test_prompt_contains_profile_operator_instruction_and_shared_schema(self):
        prompt = build_prompt(
            "PROMPT NỀN",
            "gbn.car.24h",
            source_type="tiktok",
            task_input="Caption gốc",
            operator_profiles=("Ưu tiên nói về chi phí bảo dưỡng.",),
            performance_lessons={
                "winning_hook_types": ["result"],
                "weak_patterns": ["mở đầu bằng bối cảnh"],
            },
        )

        self.assertIn("HỒ SƠ KÊNH BẮT BUỘC", prompt)
        self.assertIn("Thực dụng", prompt)
        self.assertIn("Ưu tiên nói về chi phí bảo dưỡng.", prompt)
        self.assertIn("HỢP ĐỒNG OUTPUT BẮT BUỘC", prompt)
        self.assertIn("BÀI HỌC HIỆU SUẤT ĐÃ ĐỦ MẪU", prompt)
        self.assertIn("mở đầu bằng bối cảnh", prompt)
        self.assertIn('"hook_type": "result"', prompt)
        self.assertIn('"have_frame": false', prompt)

    def test_output_schema_changes_source_type_without_changing_contract(self):
        article = json.loads(build_output_schema("article"))
        video = json.loads(build_output_schema("video"))

        self.assertEqual(article["source_type"], "article")
        self.assertEqual(video["source_type"], "video")
        self.assertNotIn("have_frame", article)
        self.assertFalse(video["have_frame"])
        self.assertEqual(
            [item["hook_type"] for item in article["hook_variants"]],
            ["result", "conflict", "impact"],
        )

    def test_prompt_pins_exactly_one_experiment_variable(self):
        assignment = {
            "experiment_id": "subtitle-normal-vs-highlight",
            "experiment_variant": "normal",
            "experiment_variable": "subtitle_style",
            "experiment_value": "normal",
        }
        prompt = build_prompt(
            "PROMPT NỀN",
            "Adsupnews",
            source_type="article",
            task_input="Nguồn A",
            experiment_assignment=assignment,
        )

        self.assertIn("CHỈ ĐỔI MỘT BIẾN", prompt)
        self.assertIn("subtitle_style=normal", prompt)
        schema_text = prompt.split("Chỉ trả JSON thuần, không bỏ hoặc đổi tên field:\n", 1)[1]
        schema = json.loads(schema_text)
        self.assertEqual("normal", schema["subtitle_style"])
        self.assertEqual("normal", schema["experiment_variant"])

    @patch(
        "shared.core.channel_learning.load_prompt_learning",
        return_value=["Ưu tiên hook result theo median cùng story type."],
    )
    def test_prompt_automatically_loads_operator_approved_learning(self, mocked_load):
        prompt = build_prompt(
            "PROMPT NỀN",
            "Adsupnews",
            source_type="article",
            task_input="Nguồn A",
        )

        mocked_load.assert_called_once_with("Adsupnews")
        self.assertIn("BÀI HỌC HIỆU SUẤT ĐÃ ĐỦ MẪU", prompt)
        self.assertIn("median cùng story type", prompt)

    def test_operator_storage_only_keeps_real_legacy_overrides(self):
        central = get_content_profile("Adsupnews", include_runtime=False)
        submitted = {
            **central,
            "tone_style": "Giọng operator muốn thử trong một chiến dịch.",
            "video_style": {"color_preset": {"primary": "#000000"}},
        }

        overrides = extract_operator_overrides("Adsupnews", submitted)

        self.assertEqual(
            overrides,
            {"tone_style": "Giọng operator muốn thử trong một chiến dịch."},
        )

    def test_video_style_returns_copy(self):
        first = get_video_style("showbiz124h")
        first["color_preset"]["primary"] = "#000000"

        second = get_video_style("showbiz124h")
        self.assertNotEqual(second["color_preset"]["primary"], "#000000")


if __name__ == "__main__":
    unittest.main()
