"""Regression coverage for evidence, visual grounding, rights, and quality gates."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.core.content_normalizer import normalize_content
from shared.core.content_validator import validate_content
from shared.core.channel_editorial import get_channel_voice_speed
from shared.core.evidence_guard import guard_evidence
from shared.core.quality_gate import evaluate_editorial_quality
from shared.core.rights_guard import guard_image_assets
from shared.core.visual_grounding import guard_visual_grounding


def _content() -> dict:
    return {
        "quality_score": 1,
        "topic_fit": True,
        "should_make_video": True,
        "story_type": "explainer",
        "title_tiktok": "Cầu mới mở tại Hà Nội",
        "main_idea": "Cây cầu mới mở giúp kết nối hai khu vực.",
        "audience_payoff": "Biết tuyến đường nào được rút ngắn.",
        "selected_hook": "Cây cầu mới đã mở tại Hà Nội.",
        "script_voice": "Cây cầu mới mở hôm nay và kết nối hai khu vực.",
        "fact_sheet": {
            "who": "Sở giao thông",
            "what": "mở cầu mới",
            "confirmed_facts": ["Cầu mới mở tại Hà Nội"],
            "unknowns": [],
        },
        "claim_register": [
            {
                "claim_id": "claim_1",
                "claim": "Cầu mới mở tại Hà Nội",
                "claim_type": "fact",
                "numeric_values": [],
            }
        ],
        "evidence": [
            {
                "claim_id": "claim_1",
                "claim": "Cầu mới mở tại Hà Nội",
                "source_text": "Bài báo xác nhận cầu mới mở tại Hà Nội.",
                "source_url": "https://example.com/article",
                "confidence": "high",
            }
        ],
        "beats": [
            {
                "beat_number": 1,
                "role": "hook",
                "voice_over": "Cầu mới mở tại Hà Nội.",
                "visual_query": "cầu mới Hà Nội",
                "on_screen_text": "Cầu mới mở",
                "must_show": ["cầu mới", "Hà Nội"],
            },
            {
                "beat_number": 2,
                "role": "close",
                "voice_over": "Tuyến đường được kết nối.",
                "visual_query": "cầu nối hai khu vực Hà Nội",
                "on_screen_text": "Kết nối khu vực",
                "must_show": ["cầu", "Hà Nội"],
            },
        ],
    }


class EvidenceRegressionTests(unittest.TestCase):
    def test_normalizer_keeps_claim_ids_and_numeric_values(self) -> None:
        normalized = normalize_content(
            {
                **_content(),
                "claim_register": [
                    {
                        "claim_id": "claim_1",
                        "claim": "Cầu dài 1,2 km",
                        "claim_type": "number",
                    }
                ],
            },
            source_type="article",
            channel_id="test-channel",
            source_url="https://example.com/article",
        )
        claim = normalized["claim_register"][0]
        self.assertEqual(claim["claim_id"], "claim_1")
        self.assertEqual(claim["numeric_values"], ["1,2 km"])

    def test_evidence_guard_disabled_returns_neutral_pass(self) -> None:
        content = _content()
        content["claim_register"] = [{
            "claim_id": "claim_1",
            "claim": "Cầu dài 1,2 km",
            "claim_type": "number",
            "numeric_values": ["1,2 km"],
        }]
        content["evidence"] = [{
            "claim_id": "claim_1",
            "claim": "Cầu dài 1,2 km",
            "source_text": "Nguồn chỉ ghi cầu dài 1 km.",
            "source_url": "https://example.com/article",
            "confidence": "high",
        }]
        report = guard_evidence(
            content,
            source_type="article",
            source_url="https://example.com/article",
            source_text="Nguồn chỉ ghi cầu dài 1 km.",
        )
        self.assertTrue(report.passed)
        self.assertEqual(report.score, 100)
        self.assertFalse(report.errors)

    def test_validator_rejects_short_or_frame_by_frame_script(self) -> None:
        short_content = _content()
        short_report = validate_content(
            short_content,
            source_type="article",
            profile={"video_length": "50-55 giây"},
        )
        short_codes = {issue.code for issue in short_report.errors}
        self.assertIn("SCRIPT_TOO_SHORT", short_codes)

        visual_content = _content()
        visual_content["script_voice"] = " ".join([
            "Video cho thấy nhân vật bước vào căn phòng để bắt đầu sự việc.",
            "Phần mô tả tiếp tục nhắc lại thông tin đang hiện trên màn hình.",
            "Máy quay chuyển sang góc khác rồi ghi nhận nhân vật rời đi.",
        ] * 8)
        visual_report = validate_content(
            visual_content,
            source_type="article",
            profile={"video_length": "50-55 giây"},
        )
        visual_codes = {issue.code for issue in visual_report.errors}
        self.assertIn("SCRIPT_VISUAL_RECAP", visual_codes)

    def test_visual_grounding_blocks_unanchored_must_show(self) -> None:
        content = _content()
        content["beats"][0]["must_show"] = ["máy bay ngoài hành tinh"]
        with patch("shared.core.visual_grounding.VISUAL_GROUNDING_ENABLED", True):
            report = guard_visual_grounding(
                content,
                source_text="Bài báo xác nhận cầu mới mở tại Hà Nội.",
            )
        self.assertFalse(report.passed)
        self.assertTrue(any("MUST_SHOW_UNGROUNDED" in error for error in report.errors))

    def test_visual_grounding_accepts_evidence_anchored_beats(self) -> None:
        with patch("shared.core.visual_grounding.VISUAL_GROUNDING_ENABLED", True):
            report = guard_visual_grounding(
                _content(),
                source_text="Bài báo xác nhận cầu mới mở tại Hà Nội và kết nối hai khu vực.",
            )
        self.assertTrue(report.passed)
        self.assertEqual(report.grounded_beats, 2)

    def test_image_rights_requires_provenance_and_blocks_denial(self) -> None:
        missing = guard_image_assets([{"path": "image.jpg", "rights_status": "unknown"}])
        self.assertFalse(missing.passed)
        self.assertTrue(any("provenance" in error for error in missing.errors))

        denied = guard_image_assets([{
            "path": "image.jpg",
            "source_url": "https://example.com/image.jpg",
            "rights_status": "denied",
        }])
        self.assertFalse(denied.passed)
        self.assertTrue(denied.errors)

    def test_quality_gate_does_not_read_ai_quality_score(self) -> None:
        validation = SimpleNamespace(
            passed=True,
            errors=(),
            warnings=(),
            score_breakdown={"hook": 25, "clarity": 15},
        )
        evidence = SimpleNamespace(passed=True, score=100)
        rights = SimpleNamespace(passed=True, requires_review=False, status="licensed")
        high_ai = {**_content(), "quality_score": 10}
        low_ai = {**_content(), "quality_score": 1}
        first = evaluate_editorial_quality(
            high_ai,
            validation_report=validation,
            evidence_report=evidence,
            rights_report=rights,
        )
        second = evaluate_editorial_quality(
            low_ai,
            validation_report=validation,
            evidence_report=evidence,
            rights_report=rights,
        )
        self.assertEqual(first.score, second.score)
        self.assertEqual(first.passed, second.passed)

    def test_content_validator_skips_claim_contract_when_guard_is_disabled(self) -> None:
        content = _content()
        content.pop("claim_register")
        report = validate_content(content, source_type="article", profile={})
        codes = {issue.code for issue in report.errors}
        self.assertNotIn("CLAIM_REGISTER_MISSING", codes)
        self.assertNotIn("CLAIM_SURFACE_UNREGISTERED", codes)
        self.assertNotIn("EVIDENCE_MISSING", codes)

    def test_pipeline_wiring_and_ci_contract_remain_present(self) -> None:
        root = Path(__file__).resolve().parents[1]
        article_pipeline = (root / "apps/creator_article/article_pipeline_core.py").read_text(encoding="utf-8")
        facebook_pipeline = (root / "apps/creator_facebook/fb_pipeline.py").read_text(encoding="utf-8")
        worker = (root / "shared/core/worker.py").read_text(encoding="utf-8")
        hub_backend = (root / "adsup_central_hub/backend/main.py").read_text(encoding="utf-8")
        workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("guard_visual_grounding", article_pipeline)
        self.assertIn("guard_image_assets", article_pipeline)
        self.assertIn("guard_visual_grounding", facebook_pipeline)
        self.assertIn("guard_visual_grounding", worker)
        self.assertIn("evaluate_social_quality", facebook_pipeline)
        self.assertIn("evaluate_social_quality", worker)
        self.assertIn(
            "FACEBOOK_KARAOKE_SUBTITLES_ENABLED = False",
            facebook_pipeline,
        )
        self.assertIn(
            "FACEBOOK_KARAOKE_SUBTITLES_ENABLED\n            and script_voice_path",
            facebook_pipeline,
        )
        self.assertIn("script_text=", worker)
        self.assertIn("python_exe = sys.executable", hub_backend)
        self.assertNotIn('.venv", "bin", "python"', hub_backend)
        self.assertIn("compileall", workflow)
        self.assertIn("unittest discover", workflow)
        self.assertIn("npm run build", workflow)

    def test_global_video_policy_targets_news_bulletin_length(self) -> None:
        from shared.core.prompt_builder import (
            build_output_schema,
            get_content_profile,
            get_voice_preset,
        )
        from shared.services.tts_api import DEFAULT_SPEED

        profile = get_content_profile(
            "showbiz124h",
            {"video_length": "20-25s"},
            include_runtime=False,
        )
        self.assertIn("50-55 giây", profile["video_length"])
        self.assertEqual(get_channel_voice_speed("showbiz124h"), 1.03)
        self.assertEqual(get_voice_preset("showbiz124h")["speed"], 1.03)
        self.assertEqual(DEFAULT_SPEED, 1.03)
        self.assertIn('"target_duration_seconds": 52', build_output_schema())


if __name__ == "__main__":
    unittest.main()
