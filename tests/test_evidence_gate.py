"""Unit test evidence gate (Giai đoạn 5) — thuần Python, không network.

Gate số liệu theo KE_HOACH §8.1: câu có số trong hook/script/voice_over và
label số phải được hỗ trợ bởi ``source_text``; thiếu hoặc lệch số ->
``passed=False`` (job rơi vào hàng chờ duyệt ``needs_review``).
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.core.evidence_gate import evaluate_evidence, high_risk_category, numeric_claims


def _storyboard() -> dict:
    return {
        "hook": "Vừa qua, gói cứu trợ 21 nghìn tỷ đồng đã được phê duyệt.",
        "script_voice": "Ngân hàng nhà nước cho biết 3 căn nhà bị xoá sổ.",
        "beats": [
            {
                "beat_number": 1,
                "voice_over": "Gói cứu trợ trị giá 21 nghìn tỷ đồng.",
                "on_screen_text": "21 nghìn tỷ",
                "must_show": ["3 căn"],
            },
            {
                "beat_number": 2,
                "voice_over": "Câu này hoàn toàn không có chữ số nào.",
                "on_screen_text": "Tổng kết",
                "must_show": [],
            },
        ],
    }


_SOURCE_TEXT = (
    "Trích bài nguồn: Vừa qua, gói cứu trợ 21 nghìn tỷ đồng đã được phê duyệt. "
    "Ngân hàng nhà nước cho biết 3 căn nhà bị xoá sổ. Gói cứu trợ trị giá 21 nghìn tỷ đồng."
)


class TestNumericClaims(unittest.TestCase):
    def test_finds_prose_sentences_and_labels_with_digits(self):
        prose, labels = numeric_claims(_storyboard())
        self.assertEqual(len(prose), 3)
        self.assertTrue(any("21 nghìn tỷ" in sentence for sentence in prose))
        self.assertTrue(any("3 căn nhà" in sentence for sentence in prose))
        self.assertFalse(any("chữ số" in sentence for sentence in prose))
        self.assertEqual(labels, ["21 nghìn tỷ", "3 căn"])

    def test_empty_storyboard_has_no_claims(self):
        self.assertEqual(numeric_claims({}), ([], []))


class TestHighRiskCategory(unittest.TestCase):
    def test_finance_channel_is_high_risk(self):
        self.assertTrue(high_risk_category({"topic": "Tài chính cá nhân"}))

    def test_health_channel_is_high_risk(self):
        self.assertTrue(high_risk_category({"channel_name": "Tin tức thẩm mỹ 24h"}))

    def test_plain_news_is_not_high_risk(self):
        self.assertFalse(high_risk_category({"topic": "Giao thông hôm nay"}))

    def test_none_profile_is_not_high_risk(self):
        self.assertFalse(high_risk_category(None))


class TestEvaluateEvidence(unittest.TestCase):
    def test_no_numbers_and_no_risk_not_required(self):
        storyboard = {"hook": "Chào mừng quý vị.", "script_voice": "", "beats": []}
        report = evaluate_evidence(storyboard, source_text="", profile={"topic": "du lịch"})
        self.assertFalse(report.required)
        self.assertTrue(report.passed)

    def test_numbers_without_source_text_fails_gate(self):
        report = evaluate_evidence(_storyboard(), source_text="", source_url="https://x.vn/a")
        self.assertTrue(report.required)
        self.assertFalse(report.passed)
        self.assertEqual(report.reason, "EVIDENCE_MISSING")
        self.assertEqual(report.prose_claim_count, 3)
        self.assertEqual(report.label_claim_count, 2)
        self.assertTrue(len(report.unsupported) == 5)

    def test_matching_source_text_passes(self):
        report = evaluate_evidence(
            _storyboard(), source_text=_SOURCE_TEXT, source_url="https://x.vn/a"
        )
        self.assertTrue(report.required)
        self.assertTrue(report.passed)
        self.assertEqual(report.unsupported, ())
        self.assertEqual(report.warnings, ())

    def test_wrong_numbers_in_source_fail_gate(self):
        wrong_source = _SOURCE_TEXT.replace("21 nghìn tỷ", "35 nghìn tỷ").replace(
            "3 căn nhà", "7 căn nhà"
        )
        report = evaluate_evidence(
            _storyboard(), source_text=wrong_source, source_url="https://x.vn/a"
        )
        self.assertFalse(report.passed)
        self.assertEqual(report.reason, "EVIDENCE_UNSUPPORTED")
        self.assertTrue(any("21 nghìn tỷ" in item for item in report.unsupported))

    def test_label_number_not_in_source_fails_gate(self):
        source = _SOURCE_TEXT.replace("3 căn nhà bị xoá sổ. Gói", "5 căn nhà bị xoá sổ. Gói")
        storyboard = _storyboard()
        storyboard["beats"][0]["voice_over"] = "Không có con số trong câu này."
        storyboard["hook"] = "Cảnh báo mới được đưa ra hôm qua."
        storyboard["script_voice"] = "Chính quyền địa phương xác nhận thông tin."
        report = evaluate_evidence(storyboard, source_text=source, source_url="https://x.vn/a")
        self.assertFalse(report.passed)
        self.assertEqual(report.unsupported, ("3 căn",))

    def test_missing_source_url_adds_warning(self):
        report = evaluate_evidence(_storyboard(), source_text=_SOURCE_TEXT, source_url="")
        self.assertTrue(report.passed)
        self.assertIn("SOURCE_URL_MISSING", report.warnings)

    def test_high_risk_channel_requires_evidence_even_without_numbers(self):
        storyboard = {"hook": "Chào quý vị.", "script_voice": "", "beats": []}
        profile = {"topic": "Tài chính investing"}
        report = evaluate_evidence(storyboard, source_text="", profile=profile)
        self.assertTrue(report.required)
        self.assertTrue(report.high_risk)
        self.assertFalse(report.passed)

    def test_high_risk_with_valid_source_passes(self):
        storyboard = {"hook": "Chào quý vị.", "script_voice": "", "beats": []}
        profile = {"topic": "sức khỏe cộng đồng"}
        report = evaluate_evidence(
            storyboard, source_text="Bộ Y tế khuyến cáo người dân.", source_url="https://x.vn/b",
            profile=profile,
        )
        self.assertTrue(report.required)
        self.assertTrue(report.passed)

    def test_to_dict_shape(self):
        report = evaluate_evidence(_storyboard(), source_text="")
        payload = report.to_dict()
        for key in (
            "required", "passed", "high_risk", "prose_claim_count",
            "label_claim_count", "unsupported", "reason", "warnings",
        ):
            self.assertIn(key, payload)
        self.assertIsInstance(payload["unsupported"], list)


if __name__ == "__main__":
    unittest.main()
