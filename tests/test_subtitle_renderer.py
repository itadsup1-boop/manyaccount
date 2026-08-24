import tempfile
import unittest
from pathlib import Path

from shared.modules.subtitle_renderer import (
    chunk_phrase_words,
    format_ass_phrase,
    generate_text_ass,
)


class SubtitleRendererTests(unittest.TestCase):
    def test_phrase_chunking_prefers_punctuation_and_caps_length(self):
        words = "Giá vàng tăng mạnh, người mua cần lưu ý rủi ro mới".split()
        chunks = chunk_phrase_words(words, max_words=6)
        self.assertEqual(" ".join(chunks[0]), "Giá vàng tăng mạnh,")
        self.assertTrue(all(len(chunk) <= 6 for chunk in chunks))

    def test_phrase_has_at_most_two_lines_and_highlights_number(self):
        phrase = format_ass_phrase(
            "Giá vàng tăng 20 phần trăm hôm nay".split(),
            word_duration_cs=20,
        )
        self.assertEqual(phrase.count(r"\N"), 1)
        self.assertIn("20", phrase)
        self.assertIn(r"\c&H", phrase)

    def test_multiword_keyword_highlights_each_matching_word(self):
        phrase = format_ass_phrase(
            "Ngân hàng Nhà nước công bố".split(),
            word_duration_cs=20,
            keywords=["Ngân hàng Nhà nước"],
        )
        self.assertGreaterEqual(phrase.count(r"\c&H"), 4)

    def test_text_fallback_writes_safe_ass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "subtitle.ass"
            result = generate_text_ass(
                "Một câu ngắn. Con số 25 phần trăm cần được chú ý.",
                str(output),
                duration=5,
                margin_v=100,
            )
            data = output.read_text(encoding="utf-8")
        self.assertEqual(result, str(output))
        self.assertIn("MarginL, MarginR, MarginV", data)
        self.assertIn(",320,0", data)
        dialogue_lines = [line for line in data.splitlines() if line.startswith("Dialogue:")]
        self.assertTrue(dialogue_lines)
        self.assertTrue(all(line.count(r"\N") <= 1 for line in dialogue_lines))

    def test_long_script_uses_safe_compact_preset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "long.ass"
            generate_text_ass(
                " ".join(["nội dung"] * 100),
                str(output),
                duration=30,
                words_per_line=7,
                font_size=70,
                margin_v=420,
                margin_l=90,
                margin_r=150,
            )
            data = output.read_text(encoding="utf-8")
        style = next(line for line in data.splitlines() if line.startswith("Style: Default"))
        self.assertIn(",58,", style)
        self.assertIn(",110,180,460,", style)


if __name__ == "__main__":
    unittest.main()
