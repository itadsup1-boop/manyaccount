"""Đọc hồ sơ biên tập ổn định, tách khỏi config hình ảnh runtime."""

import json
import os
from functools import lru_cache


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EDITORIAL_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "channel_editorial_profiles.json")


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
    """Lấy tốc độ đọc theo kênh và ngữ cảnh, giữ tương thích lời gọi cũ."""
    try:
        from shared.core.prompt_builder import get_voice_preset

        preset = get_voice_preset(
            id_tiktok,
            story_type=story_type,
            tone=tone,
            is_sensitive=is_sensitive,
        )
        return float(preset.get("speed", default))
    except (TypeError, ValueError):
        return default
    except ImportError:
        try:
            return float(load_channel_editorial(id_tiktok).get("voice_speed", default))
        except (TypeError, ValueError):
            return default
