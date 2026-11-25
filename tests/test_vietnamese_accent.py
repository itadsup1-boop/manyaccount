"""Unit test kiểm tra phát hiện tiếng Việt không dấu và cơ chế bỏ bài."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.core.vietnamese_accent import (
    extract_vietnamese_words,
    get_vietnamese_accent_stats,
    is_vietnamese_accented_valid,
)
from shared.core.content_validator import validate_content


class TestVietnameseAccentDetection(unittest.TestCase):
    def test_proper_vietnamese_news_passes(self):
        text = (
            "Vật thể bằng gỗ dài gần chín mét vừa được người dân trục vớt từ độ sâu "
            "mười mét dưới lòng sông Cổ Chiên thuộc địa bàn tỉnh Bến Tre. Theo thông tin "
            "từ cơ quan chức năng, chiếc thuyền cổ này có niên đại ước tính hàng trăm năm, "
            "được chế tác từ một thân cây gỗ nguyên khối vô cùng quý hiếm."
        )
        is_valid, ratio, reason = is_vietnamese_accented_valid(text, max_unaccented_ratio=0.30)
        self.assertTrue(is_valid)
        self.assertLess(ratio, 0.20)
        self.assertEqual(reason, "OK")

    def test_unaccented_vietnamese_blocked(self):
        # Trường hợp lỗi thực tế từ screenshot người dùng
        text = (
            "Vat the bang go dai gan chin met duoc truc vot tu do sau muoi met "
            "duoi long song Co Chien thuoc dia ban tinh Ben Tre."
        )
        is_valid, ratio, reason = is_vietnamese_accented_valid(text, max_unaccented_ratio=0.30)
        self.assertFalse(is_valid)
        self.assertGreaterEqual(ratio, 0.90)
        self.assertIn("vượt ngưỡng cho phép 30%", reason)

    def test_mixed_accent_above_30_percent_blocked(self):
        # 10 từ có dấu + 6 từ không dấu -> 6/16 = 37.5% >= 30%
        text = (
            "Chiếc thuyền cổ có niên đại hàng trăm năm đã được bảo tồn. "
            "nguoi dan phat hien chiec thuyen tren song."
        )
        is_valid, ratio, reason = is_vietnamese_accented_valid(text, max_unaccented_ratio=0.30)
        self.assertFalse(is_valid)
        self.assertGreaterEqual(ratio, 0.30)

    def test_empty_or_tiny_text_safe(self):
        is_valid, ratio, reason = is_vietnamese_accented_valid("")
        self.assertTrue(is_valid)
        self.assertEqual(ratio, 0.0)

        # Chuỗi giả lập ngắn dưới 15 từ không bị chặn oan
        is_valid, ratio, reason = is_vietnamese_accented_valid("hook text")
        self.assertTrue(is_valid)


class TestContentValidatorAccentRule(unittest.TestCase):
    def test_unaccented_script_fails_validation(self):
        unaccented_script = (
            "Vat the bang go dai gan chin met duoc truc vot tu do sau muoi met "
            "duoi long song Co Chien thuoc dia ban tinh Ben Tre. Theo thong tin "
            "tu co quan chuc nang, chiec thuyen co nay co nien dai uoc tinh hang "
            "tram nam, duoc che tac tu mot than cay go nguyen khoi vo cung quy hiem. "
            "Khi nguoi dan dang tien hanh cao ngheu tren song thi phat hien vat the la "
            "bi vui lap sau trong bun cat. Ngay sau do, chinh quyen dia phuong da huy "
            "dong luc luong cung phuong tien chuyen dung de bao ve hien truong va tien "
            "hanh truc vot an toan. Hien hien vat da duoc ban giao cho bao tang tinh "
            "de phuc vu cong tac giam dinh nien dai cung nhu bao ton gia tri van hoa. "
            "Day la phat hien khao co hoc vo cung quy gia cho vung dat phuong Nam."
        )
        content = {
            "story_type": "explainer",
            "hook_variants": [
                {"text": "Vật thể bằng gỗ dài gần chín mét được trục vớt dưới lòng sông.", "hook_type": "result", "promise": "Chi tiết thuyền cổ"},
                {"text": "Bí ẩn chiếc thuyền gỗ cổ trăm năm dưới đáy sông sâu mười mét.", "hook_type": "conflict", "promise": "Nguồn gốc thuyền"},
                {"text": "Phát hiện chấn động đáy sông khiến giới khảo cổ xôn xao.", "hook_type": "impact", "promise": "Giá trị lịch sử"},
            ],
            "selected_hook": "Vật thể bằng gỗ dài gần chín mét được trục vớt dưới lòng sông.",
            "selected_hook_reason": "Nêu thẳng sự kiện phát hiện chiếc thuyền cổ.",
            "script_voice": unaccented_script,
            "main_angle": "Phát hiện thuyền cổ dưới lòng sông",
            "audience_payoff": "Hiểu thêm về di sản văn hóa",
            "fact_sheet": {
                "who": ["người dân", "chính quyền"],
                "what": "Trục vớt thuyền cổ",
                "confirmed_facts": ["Dài gần 9m", "Sâu 10m"],
            },
        }

        report = validate_content(content, source_type="article")
        error_codes = [issue.code for issue in report.errors]
        self.assertIn("UNACCENTED_VIETNAMESE", error_codes)
        self.assertFalse(report.passed)

    def test_tts_api_rejects_unaccented_text(self):
        from shared.services.tts_api import create_voice_full_pipeline
        unaccented_text = (
            "Vat the bang go dai gan chin met duoc truc vot tu do sau muoi met "
            "duoi long song Co Chien thuoc dia ban tinh Ben Tre."
        )
        result = create_voice_full_pipeline(
            unaccented_text, "/tmp", "dummy.wav"
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
