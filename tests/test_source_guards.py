import unittest

from shared.core.evidence_guard import guard_evidence
from shared.core.rights_guard import guard_music_rights, guard_source_rights
from shared.core.source_ranker import rank_candidates, should_process_candidate


class SourceRankerTests(unittest.TestCase):
    def test_ranker_puts_strong_channel_match_first(self):
        profile = {
            "topic": "ô tô xe điện",
            "content_pillars": ["giá xe", "an toàn giao thông"],
            "audience_pains": ["chi phí", "rủi ro"],
        }
        candidates = [
            {
                "url": "https://example.com/entertainment",
                "title": "Một nghệ sĩ chia sẻ bộ ảnh mới",
                "position": 0,
            },
            {
                "url": "https://example.com/car",
                "title": "Giá xe điện giảm 20%, người mua tiết kiệm bao nhiêu chi phí?",
                "thumbnail": "https://example.com/car.jpg",
                "view_count": 100_000,
                "position": 1,
            },
        ]

        ranked = rank_candidates(candidates, profile, source_type="article")

        self.assertEqual(ranked[0]["url"], "https://example.com/car")
        self.assertGreater(
            ranked[0]["source_rank"]["total_score"],
            ranked[1]["source_rank"]["total_score"],
        )

    def test_missing_metadata_fails_open(self):
        ranked = rank_candidates(
            ["https://www.tiktok.com/@channel/video/123"],
            {"topic": "tin tức"},
            source_type="tiktok",
        )
        self.assertEqual(ranked[0]["source_rank"]["status"], "unscored")
        self.assertTrue(should_process_candidate(ranked[0]))


class EvidenceGuardTests(unittest.TestCase):
    def test_grounded_normal_story_passes(self):
        source_url = "https://example.com/technology-story"
        source_text = (
            "Hãng A giới thiệu mẫu điện thoại B tại Hà Nội. "
            "Thiết bị có pin 5000 mAh và được bán từ ngày 20 tháng 8."
        )
        content = {
            "title": "Điện thoại B ra mắt",
            "script_voice": "Hãng A vừa giới thiệu điện thoại B với pin 5000 mAh.",
            "evidence": [{
                "claim": "Điện thoại B có pin 5000 mAh",
                "source_text": "Thiết bị có pin 5000 mAh",
                "source_url": source_url,
                "confidence": "high",
            }],
            "beats": [{"must_show": ["điện thoại B"]}],
        }

        report = guard_evidence(
            content,
            source_type="article",
            source_url=source_url,
            source_text=source_text,
            profile={"topic": "công nghệ"},
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.valid_evidence_count, 1)

    def test_sensitive_finance_story_requires_two_evidence_items(self):
        content = {
            "title": "Cảnh báo đầu tư",
            "script_voice": "Một mã cổ phiếu đã tăng 10 phần trăm.",
            "evidence": [{
                "claim": "Mã cổ phiếu tăng 10 phần trăm",
                "source_text": "Mã cổ phiếu tăng 10 phần trăm",
                "source_url": "https://example.com/finance",
                "confidence": "high",
            }],
        }

        report = guard_evidence(
            content,
            source_type="article",
            source_url="https://example.com/finance",
            source_text="Mã cổ phiếu tăng 10 phần trăm trong phiên hôm nay.",
            profile={"topic": "tài chính đầu tư"},
        )

        self.assertFalse(report.passed)
        self.assertEqual(report.required_evidence_count, 2)
        self.assertIn("insufficient_evidence", {item.code for item in report.errors})

    def test_unconfirmed_source_cannot_be_stated_as_fact(self):
        report = guard_evidence(
            {
                "script_voice": "Công ty A đã mua công ty B.",
                "evidence": [{
                    "claim": "Công ty A mua công ty B",
                    "source_text": "Tin đồn công ty A mua công ty B",
                    "source_url": "https://example.com/rumor",
                    "confidence": "medium",
                }],
            },
            source_type="article",
            source_url="https://example.com/rumor",
            source_text="Tin đồn công ty A mua công ty B chưa được xác nhận.",
        )
        self.assertFalse(report.passed)
        self.assertIn("unconfirmed_as_fact", {item.code for item in report.errors})


class RightsGuardTests(unittest.TestCase):
    def test_unknown_source_warns_but_does_not_block_basic_mode(self):
        report = guard_source_rights(
            {"url": "https://example.com/video"},
            policy={"mode": "warn"},
        )
        self.assertTrue(report.passed)
        self.assertTrue(report.requires_review)

    def test_explicit_denial_is_blocked(self):
        report = guard_source_rights({"rights_status": "denied"})
        self.assertFalse(report.passed)

    def test_music_needs_approved_status_and_license_source(self):
        self.assertFalse(guard_music_rights({
            "license_status": "approved",
            "license_source": "",
        }).passed)
        self.assertTrue(guard_music_rights({
            "license_status": "approved",
            "license_source": "license/invoice-001.pdf",
        }).passed)


if __name__ == "__main__":
    unittest.main()
