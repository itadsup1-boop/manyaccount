import unittest

from shared.core.content_normalizer import normalize_content
from shared.core.content_repair import prepare_content_with_single_repair
from shared.core.content_validator import validate_content


def valid_content():
    hook = "Giá xăng mới tăng mạnh từ chiều nay trên toàn quốc"
    script = (
        "Mức điều chỉnh được công bố sau kỳ rà soát mới nhất. "
        "Xăng phổ biến tăng thêm năm trăm đồng mỗi lít. "
        "Một người đi làm bằng xe máy có thể tốn thêm mỗi tháng. "
        "Khoản chênh lệch không lớn trong một lần đổ. "
        "Nhưng tổng chi phí sẽ rõ hơn với người di chuyển thường xuyên. "
        "Bạn thấy mức tăng này ảnh hưởng nhiều nhất đến khoản chi nào?"
    )
    return {
        "schema_version": 1,
        "story_type": "comparison",
        "title_tiktok": "Giá xăng tăng và khoản chi thay đổi",
        "main_idea": "Giá xăng tăng làm chi phí đi lại thay đổi.",
        "main_angle": "Tác động của giá xăng mới tới chi phí đi lại.",
        "audience_payoff": "Người xem biết nhóm nào chịu tác động rõ nhất.",
        "hook_variants": [
            {
                "text": hook,
                "hook_type": "result",
                "promise": "Giải thích mức tăng và thời điểm áp dụng.",
                "score": 9,
            },
            {
                "text": "Năm trăm đồng mỗi lít tạo ra tranh luận gì",
                "hook_type": "conflict",
                "promise": "Làm rõ vì sao mức tăng gây tranh luận.",
                "score": 8,
            },
            {
                "text": "Người đi làm sẽ tốn thêm bao nhiêu tiền xăng",
                "hook_type": "impact",
                "promise": "Ước lượng tác động tới chi phí đi lại.",
                "score": 8,
            },
        ],
        "selected_hook": hook,
        "selected_hook_reason": "Nêu thẳng sự kiện mới và phạm vi tác động.",
        "hook": hook,
        "script_voice": script,
        "evidence": [
            {
                "claim": "Xăng tăng năm trăm đồng mỗi lít.",
                "source_text": "Mức điều chỉnh tăng 500 đồng mỗi lít.",
                "source_url": "https://example.com/article",
                "confidence": "high",
            },
            {
                "claim": "Mức giá mới áp dụng từ chiều nay.",
                "source_text": "Giá mới có hiệu lực từ 15 giờ.",
                "source_url": "https://example.com/article",
                "confidence": "high",
            },
        ],
        "beats": [
            {
                "beat_number": 1,
                "role": "hook",
                "duration_hint": 2,
                "voice_over": hook,
                "visual_query": "bảng giá xăng mới tại cây xăng",
                "on_screen_text": "GIÁ XĂNG TĂNG",
            },
            {
                "beat_number": 2,
                "role": "context",
                "duration_hint": 3,
                "voice_over": "Mức điều chỉnh vừa được công bố.",
                "visual_query": "nhân viên cây xăng điều chỉnh bảng giá",
                "on_screen_text": "ÁP DỤNG CHIỀU NAY",
            },
            {
                "beat_number": 3,
                "role": "evidence",
                "duration_hint": 4,
                "voice_over": "Xăng tăng thêm năm trăm đồng mỗi lít.",
                "visual_query": "con số 500 đồng trên bảng giá xăng",
                "on_screen_text": "TĂNG 500 ĐỒNG",
            },
            {
                "beat_number": 4,
                "role": "development",
                "duration_hint": 5,
                "voice_over": "Người di chuyển thường xuyên chịu tác động rõ.",
                "visual_query": "người đi làm đổ xăng xe máy",
                "on_screen_text": "CHI PHÍ ĐI LẠI",
            },
            {
                "beat_number": 5,
                "role": "development",
                "duration_hint": 3,
                "voice_over": "Khoản chênh lệch cộng dồn theo số lần đổ xăng.",
                "visual_query": "người đi làm xem hóa đơn tại cây xăng",
                "on_screen_text": "CỘNG DỒN CHI PHÍ",
            },
            {
                "beat_number": 6,
                "role": "payoff",
                "duration_hint": 4,
                "voice_over": "Tổng chi phí theo tháng mới là điều đáng chú ý.",
                "visual_query": "hóa đơn đổ xăng và người đi làm",
                "on_screen_text": "TÍNH THEO THÁNG",
            },
        ],
        "music_mood": "neutral_news",
        "music_energy": 2,
        "is_sensitive": False,
        "topic_fit": True,
        "should_make_video": True,
        "quality_score": 8,
    }


class ContentNormalizerTests(unittest.TestCase):
    def test_legacy_scenes_are_preserved_as_beats(self):
        raw = {
            "hook": "Pha bóng phút cuối đã thay đổi hoàn toàn trận đấu",
            "script_voice": "Đội chủ nhà ghi bàn ở phút bù giờ và giành chiến thắng.",
            "tone": "Tích cực",
            "music_mood": "sports_energy",
            "scenes": [
                {
                    "scene_number": 1,
                    "voice_over": "Pha bóng phút cuối.",
                    "visual_description": "cầu thủ ghi bàn phút bù giờ",
                },
                {
                    "scene_number": 2,
                    "voice_over": "Khán giả ăn mừng.",
                    "visual_description": "khán giả trên sân ăn mừng bàn thắng",
                },
            ],
        }

        result = normalize_content(
            raw,
            source_type="article",
            channel_id="adsup_sport",
            source_url="https://example.com/sport",
        )

        self.assertEqual(result["schema_version"], 1)
        self.assertTrue(result["content_id"])
        self.assertEqual(result["story_type"], "sports_moment")
        self.assertEqual(result["selected_hook"], raw["hook"])
        self.assertEqual(result["hook"], raw["hook"])
        self.assertEqual(len(result["beats"]), 2)
        self.assertEqual(result["beats"][0]["role"], "hook")
        self.assertEqual(result["beats"][-1]["role"], "payoff")
        self.assertEqual(result["scenes"][0]["visual_description"], "cầu thủ ghi bàn phút bù giờ")

    def test_pipeline_context_overrides_ai_identity(self):
        result = normalize_content(
            {
                "channel_id": "sai-kenh",
                "source_type": "sai-loai",
                "source_url": "https://invalid.example",
                "hook": "Bão lớn khiến nhiều khu vực phải sơ tán khẩn cấp",
                "script_voice": "Nạn nhân đang được hỗ trợ tại khu vực an toàn.",
                "is_sensitive": False,
            },
            source_type="article",
            channel_id="Adsupnews",
            source_url="https://example.com/real",
        )

        self.assertEqual(result["channel_id"], "Adsupnews")
        self.assertEqual(result["source_type"], "article")
        self.assertEqual(result["source_url"], "https://example.com/real")
        self.assertTrue(result["is_sensitive"])


class ContentValidatorTests(unittest.TestCase):
    def test_valid_content_passes(self):
        normalized = normalize_content(
            valid_content(),
            source_type="article",
            channel_id="taichinh24444h",
            source_url="https://example.com/article",
        )
        report = validate_content(normalized, source_type="article")

        self.assertTrue(report.passed, [item.code for item in report.errors])
        self.assertGreaterEqual(report.content_score, 80)

    def test_missing_variants_evidence_and_beats_fail(self):
        normalized = normalize_content(
            {
                "hook": "Câu chuyện này đang được nhiều người chú ý",
                "script_voice": "Nội dung quá ngắn.",
                "main_idea": "Một câu chuyện.",
            },
            source_type="facebook",
        )
        report = validate_content(normalized, source_type="facebook")
        error_codes = {item.code for item in report.errors}

        self.assertFalse(report.passed)
        self.assertIn("HOOK_VARIANTS_INVALID_COUNT", error_codes)
        self.assertIn("HOOK_GENERIC", error_codes)
        self.assertIn("EVIDENCE_MISSING", error_codes)
        self.assertIn("BEATS_TOO_FEW", error_codes)

    def test_sensitive_content_needs_two_reliable_evidence_items(self):
        raw = valid_content()
        raw["is_sensitive"] = True
        raw["music_mood"] = "sensitive_empathy"
        raw["music_energy"] = 1
        raw["evidence"] = raw["evidence"][:1]
        normalized = normalize_content(raw, source_type="facebook")

        report = validate_content(normalized, source_type="facebook")

        self.assertFalse(report.passed)
        self.assertIn(
            "HIGH_RISK_EVIDENCE_THIN",
            {item.code for item in report.errors},
        )

    def test_sensitive_content_requires_safe_music(self):
        content = valid_content()
        content.update(
            {
                "is_sensitive": True,
                "music_mood": "breaking_tension",
                "music_energy": 3,
            }
        )
        normalized = normalize_content(content, source_type="article")
        report = validate_content(normalized, source_type="article")
        error_codes = {item.code for item in report.errors}

        self.assertIn("SENSITIVE_MUSIC_INVALID", error_codes)
        self.assertIn("SENSITIVE_ENERGY_INVALID", error_codes)

    def test_experiment_output_must_match_assigned_variant(self):
        content = valid_content()
        content.update({
            "experiment_id": "beats-6-vs-8",
            "experiment_variant": "eight",
            "experiment_variable": "visual_beat_count",
            "experiment_value": 8,
            "visual_beat_count": 8,
        })
        normalized = normalize_content(content, source_type="article")
        report = validate_content(normalized, source_type="article")

        self.assertFalse(report.passed)
        self.assertIn(
            "EXPERIMENT_VARIANT_MISMATCH",
            {item.code for item in report.errors},
        )


class ContentRepairTests(unittest.TestCase):
    def test_repair_callback_is_called_once(self):
        calls = []

        def repair_callback(instruction):
            calls.append(instruction)
            return valid_content()

        prepared = prepare_content_with_single_repair(
            {
                "hook": "Câu chuyện này đang gây chú ý",
                "script_voice": "Nội dung quá ngắn.",
            },
            source_type="article",
            channel_id="Adsupnews",
            source_url="https://example.com/article",
            repair_callback=repair_callback,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(prepared.repair_attempts, 1)
        self.assertTrue(prepared.repaired)
        self.assertTrue(prepared.report.passed)
        self.assertTrue(prepared.content["content_validation_repaired"])
        self.assertIn("YÊU CẦU SỬA KỊCH BẢN", calls[0])

    def test_declined_content_is_not_repaired(self):
        calls = []

        prepared = prepare_content_with_single_repair(
            {
                "topic_fit": False,
                "should_make_video": False,
                "topic_fit_reason": "Sai chủ đề kênh.",
            },
            source_type="tiktok",
            repair_callback=lambda instruction: calls.append(instruction),
        )

        self.assertEqual(calls, [])
        self.assertTrue(prepared.report.skipped)
        self.assertEqual(prepared.repair_attempts, 0)

    def test_invalid_repair_is_not_retried(self):
        calls = []

        def repair_callback(instruction):
            calls.append(instruction)
            return {"hook": "Kết quả vẫn thiếu toàn bộ cấu trúc bắt buộc"}

        prepared = prepare_content_with_single_repair(
            {"hook": "Kịch bản đầu tiên không đủ cấu trúc bắt buộc"},
            source_type="facebook",
            repair_callback=repair_callback,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(prepared.repair_attempts, 1)
        self.assertFalse(prepared.report.passed)
        self.assertFalse(prepared.repaired)


if __name__ == "__main__":
    unittest.main()
