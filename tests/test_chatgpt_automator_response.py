import json
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from apps.creator_article.article_chatgpt_automator import (
    _extract_last_json_object,
    _looks_like_generated_result,
    build_article_plugin_package,
    ensure_work_mode_selected,
)


def test_prompt_schema_is_not_treated_as_generated_result():
    prompt = '''Hãy trả JSON:
    {"title_tiktok": "", "hook": "", "script_voice": "", "should_make_video": true}
    '''
    candidate = _extract_last_json_object(prompt)

    assert candidate
    assert not _looks_like_generated_result(candidate)


def test_generated_result_with_content_is_accepted():
    result = {
        "title_tiktok": "Cảnh báo trước khi làm đẹp",
        "hook": "Chi tiết này có thể thay đổi quyết định của bạn.",
        "script_voice": "Hãy kiểm tra thông tin trước khi quyết định.",
        "should_make_video": True,
    }

    assert _looks_like_generated_result(json.dumps(result, ensure_ascii=False))


class ChatGPTAutomatorPluginTests(unittest.TestCase):
    def test_prompt_schema_and_generated_result(self):
        test_prompt_schema_is_not_treated_as_generated_result()
        test_generated_result_with_content_is_accepted()

    def test_build_article_plugin_package_creates_expected_blocks(self):
        path, content = build_article_plugin_package(
            id_tiktok="Adsupnews",
            source_url="https://example.com/tin-tuc-1",
            source_title="Tiêu đề bài báo mẫu",
            source_content="Nội dung bài báo đã được làm sạch.",
            source_name="Báo Mẫu",
            published_at="2026-11-10",
            operator_instruction="Nhấn mạnh số liệu chính.",
        )
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(os.path.basename(path), "article_input.txt")
        self.assertIn("[HỒ SƠ KÊNH]", content)
        self.assertIn("[CHỈ ĐẠO BIÊN TẬP]", content)
        self.assertIn("[NGUỒN]", content)
        self.assertIn("[BÀI BÁO]", content)
        self.assertIn("https://example.com/tin-tuc-1", content)
        self.assertIn("Nội dung bài báo đã được làm sạch.", content)

    def test_ensure_work_mode_selected_clicks_when_not_pressed(self):
        clicked = []

        class FakeButton:
            def __init__(self, pressed: str):
                self._pressed = pressed

            def count(self):
                return 1

            @property
            def first(self):
                return self

            def is_visible(self, timeout=0):
                return True

            def get_attribute(self, name):
                if name == "aria-pressed":
                    return self._pressed
                return None

            def click(self, timeout=0, force=False):
                clicked.append(True)
                self._pressed = "true"

        class FakePage:
            def __init__(self, pressed: str):
                self.btn = FakeButton(pressed)

            def locator(self, selector: str):
                if "Công việc" in selector:
                    return self.btn
                return self.btn

        page = FakePage("false")
        self.assertTrue(ensure_work_mode_selected(page, timeout_seconds=1.0))
        self.assertEqual(len(clicked), 1)


if __name__ == "__main__":
    unittest.main()

