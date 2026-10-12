"""Regression coverage for the TikTok/Facebook video-source phase."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.core.beat_timeline import plan_beat_timeline
from shared.core.prompt_builder import build_prompt
from shared.core.social_evidence import build_social_evidence_pack
from shared.core.social_quality_gate import (
    evaluate_social_quality,
    evaluate_social_render_contract,
)


def _reports():
    validation = SimpleNamespace(
        passed=True,
        score_breakdown={
            "hook": 25,
            "evidence": 20,
            "structure": 25,
            "clarity": 15,
            "safety": 10,
            "brand_fit": 5,
        },
    )
    evidence = SimpleNamespace(passed=True, score=100)
    visual = SimpleNamespace(passed=True, score=100)
    rights = SimpleNamespace(passed=True, requires_review=False, status="permission")
    return validation, evidence, visual, rights


class SocialVideoRegressionTests(unittest.TestCase):
    def test_tiktok_manual_source_approval_overrides_topic_prompt(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("TIKTOK_TOPIC_GATE", None)
            prompt = build_prompt(
                "BASE",
                "showbiz124h",
                source_type="tiktok",
                include_output_schema=False,
            )
        self.assertIn("DUYỆT NGUỒN TIKTOK BỞI OPERATOR", prompt)

    def test_evidence_pack_keeps_caption_transcript_and_ocr_separate(self):
        pack = build_social_evidence_pack(
            source_type="tiktok",
            source_url="https://www.tiktok.com/@creator/video/1",
            caption="Caption nguồn",
            transcript="Lời nói trong video",
            ocr_text="Chữ trên màn hình",
            metadata={"author": "creator", "published_at": "2026-08-24"},
        )
        self.assertEqual(pack.coverage_score, 100)
        self.assertTrue(pack.has_transcript)
        self.assertTrue(pack.has_ocr)
        self.assertIn("Lời nói trong video", pack.source_text)

    def test_social_gate_ignores_ai_quality_score(self):
        validation, evidence, visual, rights = _reports()
        content = {
            "quality_score": 1,
            "topic_fit": True,
            "should_make_video": True,
            "selected_hook": "Tin mới ảnh hưởng người xem",
            "audience_payoff": "Biết điều cần chú ý",
            "beats": [{
                "voice_over": "Tin mới ảnh hưởng người xem.",
                "visual_query": "Tin mới ảnh hưởng người xem",
            }],
        }
        pack = build_social_evidence_pack(
            source_type="facebook",
            caption="Tin mới ảnh hưởng người xem",
            transcript="Tin mới ảnh hưởng người xem",
            ocr_text="Tin mới",
        )
        first = evaluate_social_quality(
            content,
            source_type="facebook",
            validation_report=validation,
            evidence_report=evidence,
            visual_report=visual,
            rights_report=rights,
            evidence_pack=pack.to_dict(),
        )
        second = evaluate_social_quality(
            {**content, "quality_score": 10},
            source_type="facebook",
            validation_report=validation,
            evidence_report=evidence,
            visual_report=visual,
            rights_report=rights,
            evidence_pack=pack.to_dict(),
        )
        self.assertEqual(first.score, second.score)
        self.assertEqual(first.passed, second.passed)

    def test_source_video_without_beats_gets_sentence_timeline(self):
        timeline = plan_beat_timeline(
            None,
            total_duration=12,
            hook_duration=2,
            media_count=1,
            hook_text="Mở đầu đáng chú ý",
            script_text="Mở đầu đáng chú ý. Chi tiết thứ nhất. Đây là kết luận.",
        )
        self.assertGreaterEqual(len(timeline.segments), 3)
        self.assertTrue(timeline.segments[1].voice_over)
        self.assertEqual(timeline.segments[-1].role, "payoff")

    def test_legacy_render_contract_requires_title_and_script(self):
        failed = evaluate_social_render_contract(
            source_type="tiktok",
            source_url="https://www.tiktok.com/video/1",
            title="Tin",
            script="Ngắn",
            frame_mode=True,
            title_frame_available=True,
            content_frame_available=False,
        )
        self.assertFalse(failed.passed)
        passed = evaluate_social_render_contract(
            source_type="facebook",
            source_url="https://facebook.com/reel/1",
            title="Tin mới ảnh hưởng người xem",
            script="Đây là nội dung đủ dài để tạo voice và phụ đề cho video.",
            frame_mode=True,
            title_frame_available=True,
            content_frame_available=True,
        )
        self.assertTrue(passed.passed)


if __name__ == "__main__":
    unittest.main()
