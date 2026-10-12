import unittest

from shared.services.gemini_response_reader import (
    extract_json_from_text,
    is_refusal_response,
    select_latest_script_response,
)


class GeminiResponseReaderTests(unittest.TestCase):
    def test_extracts_nested_json_from_code_block(self):
        text = """JSON
```json
{
  "title_tiktok": "Bản tin mới",
  "beats": [{"beat_number": 1, "must_show": ["Học sinh nữ"]}],
  "retention_risks": [],
  "have_frame": false
}
```
"""

        payload = extract_json_from_text(text)

        self.assertEqual(payload["title_tiktok"], "Bản tin mới")
        self.assertEqual(payload["beats"][0]["beat_number"], 1)

    def test_reads_json_when_gemini_ui_removes_markdown_fence(self):
        text = 'JSON\n{\n  "hook": "Tin mới",\n  "script_voice": "Nội dung"\n}'

        payload = extract_json_from_text(text)

        self.assertEqual(payload["hook"], "Tin mới")

    def test_selects_complete_root_instead_of_last_small_dom_fragment(self):
        full_response = (
            '{"title_tiktok":"Tin mới","beats":'
            '[{"beat_number":8,"voice_over":"Kết"}],"have_frame":false}'
        )
        fragments_in_dom_order = [full_response, '"have_frame": false']

        payload, selected_text = select_latest_script_response(fragments_in_dom_order)

        self.assertEqual(payload["title_tiktok"], "Tin mới")
        self.assertEqual(selected_text, full_response)

    def test_tolerates_trailing_comma(self):
        payload = extract_json_from_text(
            '{"hook":"Tin nóng","beats":[{"beat_number":1,}],}'
        )

        self.assertEqual(payload["beats"][0]["beat_number"], 1)

    def test_recognizes_capability_refusal_from_screenshot(self):
        self.assertTrue(
            is_refusal_response(
                "Tôi là một mô hình ngôn ngữ nên điều đó nằm ngoài mục đích mà tôi được tạo ra."
            )
        )

    def test_recognizes_alternate_capability_refusal(self):
        self.assertTrue(
            is_refusal_response(
                "Tôi không thể giúp bạn việc đó, vì tôi chỉ là một mô hình ngôn ngữ "
                "nên không có khả năng hiểu cũng như trả lời yêu cầu đó."
            )
        )

    def test_does_not_treat_normal_script_as_refusal(self):
        self.assertFalse(
            is_refusal_response(
                "Gemini không thể xác minh thêm dữ kiện này, vì vậy bản tin chỉ sử dụng nội dung nguồn."
            )
        )


if __name__ == "__main__":
    unittest.main()
