"""Đọc hồ sơ biên tập ổn định, tách khỏi config hình ảnh runtime."""

import json
import os
from functools import lru_cache


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EDITORIAL_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "channel_editorial_profiles.json")
TARGET_VOICE_SPEED = 1.03
TARGET_VIDEO_DURATION_SECONDS = 52


@lru_cache(maxsize=1)
def load_channel_editorials() -> dict:
    """Trả về toàn bộ hồ sơ kênh từ nguồn cấu hình biên tập duy nhất."""
    if not os.path.exists(EDITORIAL_CONFIG_PATH):
        return {}
    try:
        with open(EDITORIAL_CONFIG_PATH, "r", encoding="utf-8") as f:
            profiles = json.load(f)
        return profiles if isinstance(profiles, dict) else {}
    except Exception as exc:
        print(f"⚠️ Không đọc được hồ sơ biên tập: {exc}")
        return {}


def load_channel_editorial(id_tiktok: str) -> dict:
    clean_id = str(id_tiktok or "").replace("@", "").strip()
    if not clean_id:
        return {}
    channel_config = load_channel_editorials().get(clean_id, {})
    return channel_config if isinstance(channel_config, dict) else {}


def get_channel_voice_speed(
    id_tiktok: str,
    default: float = 1.05,
    story_type: str = "",
    tone: str = "",
    is_sensitive: bool = False,
) -> float:
    """Tốc độ voice thống nhất cho mọi nguồn theo chính sách sản xuất."""
    return TARGET_VOICE_SPEED
