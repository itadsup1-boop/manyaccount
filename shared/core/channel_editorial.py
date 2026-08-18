"""Đọc hồ sơ biên tập ổn định, tách khỏi config hình ảnh đồng bộ từ Storage."""

import json
import os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EDITORIAL_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "channel_editorial_profiles.json")


def load_channel_editorial(id_tiktok: str) -> dict:
    clean_id = str(id_tiktok or "").replace("@", "").strip()
    if not clean_id or not os.path.exists(EDITORIAL_CONFIG_PATH):
        return {}
    try:
        with open(EDITORIAL_CONFIG_PATH, "r", encoding="utf-8") as f:
            profiles = json.load(f)
        channel_config = profiles.get(clean_id, {})
        return channel_config if isinstance(channel_config, dict) else {}
    except Exception as exc:
        print(f"⚠️ Không đọc được hồ sơ biên tập {clean_id}: {exc}")
        return {}


def get_channel_voice_speed(id_tiktok: str, default: float = 1.05) -> float:
    try:
        return float(load_channel_editorial(id_tiktok).get("voice_speed", default))
    except (TypeError, ValueError):
        return default
