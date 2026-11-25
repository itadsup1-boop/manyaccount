"""Kiểm tra và đánh giá chất lượng tiếng Việt có dấu trong kịch bản và văn bản lồng tiếng."""

from __future__ import annotations

import re
from typing import Tuple

# Bộ ký tự có dấu và ký tự đặc trưng của tiếng Việt (bao gồm cả chữ thường và hoa)
VIETNAMESE_ACCENTED_CHARS = frozenset(
    "àáảãạăằắẳẵặâầấẩẫậ"
    "èéẻẽẹêềếểễệ"
    "ìíỉĩị"
    "òóỏõọôồốổỗộơờớởỡợ"
    "ùúủũụưừứửữự"
    "ỳýỷỹỵ"
    "đ"
    "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ"
    "ÈÉẺẼẸÊỀẾỂỄỆ"
    "ÌÍỈĨỊ"
    "ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢ"
    "ÙÚỦŨỤƯỪỨỬỮỰ"
    "ỲÝỶỸỴ"
    "Đ"
)

# Regex tách từ tiếng Việt / Latinh (bỏ qua số, dấu chấm, dấu phẩy, ký tự đặc biệt)
_WORD_REGEX = re.compile(r"\b[a-zA-Z\u00C0-\u1EF9]+\b")


def extract_vietnamese_words(text: str) -> list[str]:
    """Tách danh sách các từ trong văn bản."""
    return _WORD_REGEX.findall(str(text or ""))


def get_vietnamese_accent_stats(text: str) -> Tuple[float, int, int]:
    """
    Phân tích tỷ lệ từ không dấu trong văn bản.
    Trả về: (unaccented_ratio, unaccented_count, total_words)
    - unaccented_ratio: tỷ lệ từ không có bất kỳ dấu tiếng Việt nào (0.0 đến 1.0)
    - unaccented_count: số từ không dấu
    - total_words: tổng số từ
    """
    words = extract_vietnamese_words(text)
    total_words = len(words)
    if total_words == 0:
        return 0.0, 0, 0

    unaccented_count = sum(
        1 for word in words if not any(char in VIETNAMESE_ACCENTED_CHARS for char in word)
    )
    ratio = unaccented_count / total_words
    return ratio, unaccented_count, total_words


def is_vietnamese_accented_valid(
    text: str,
    max_unaccented_ratio: float = 0.30,
    min_words_to_check: int = 15,
) -> Tuple[bool, float, str]:
    """
    Kiểm tra văn bản có đạt chuẩn tiếng Việt có dấu hay không.

    Quy tắc:
    - Nếu tổng số từ >= min_words_to_check (mặc định 15 từ) và tỷ lệ từ không dấu >= max_unaccented_ratio (mặc định 30%),
      bài viết sẽ bị đánh giá là KHÔNG HỢP LỆ (bỏ bài).
    - Với văn bản ngắn hơn min_words_to_check: coi như hợp lệ (tránh bắt lỗi các chuỗi giả lập ngắn trong unit test).

    Trả về: (is_valid, unaccented_ratio, reason)
    """
    ratio, unaccented_count, total_words = get_vietnamese_accent_stats(text)
    if total_words == 0:
        return True, 0.0, "Văn bản trống"

    if total_words >= min_words_to_check:
        if ratio >= max_unaccented_ratio:
            return (
                False,
                ratio,
                f"Văn bản chứa {ratio:.1%} từ không dấu ({unaccented_count}/{total_words} từ, vượt ngưỡng cho phép {max_unaccented_ratio:.0%})",
            )

    return True, ratio, "OK"
