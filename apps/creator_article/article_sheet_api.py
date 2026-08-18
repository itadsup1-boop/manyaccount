#!/usr/bin/env python3
import os
import sys
import json
import requests

# Lùi 3 cấp để về thư mục mannyAccount (nơi chứa thư mục services)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
from shared.services.sheet_api import safe_post_json

SHEET_URL = "https://script.google.com/macros/s/AKfycbyW2cMY-3kh2qUMWwc2Tta8BrqrZY1mZLhDyQ1i8G94J9QX7LCr7LY2Brri54PVWmcC/exec"

def save_article_to_sheet(ai_result: dict, article_url: str, id_tiktok: str) -> dict | None:
    """
    Ghi dữ liệu Báo Mạng vào sheet 'tổng'.
    - B, E: hook
    - C: script_voice
    - G: image_prompts (danh sách mô tả ảnh)
    - I: title_tiktok
    - N: id_tiktok
    """
    sheet_name = "facebook" if id_tiktok == "Adsupnews" else "tổng"
    
    payload = {
        "action": "save",
        "sheet_name": sheet_name,
        "link": article_url,
        "title": ai_result.get("hook", ""),                          # Map hook to title (Col B)
        "script": ai_result.get("script_voice", ""),                 # Map script_voice to script (Col C)
        "combined_hints": json.dumps(ai_result.get("scenes", []), ensure_ascii=False), # Map scenes to combined_hints (Col G)
        "original_video": "Bài Báo",                                 # Map source to original_video (Col H)
        "title_tiktok": ai_result.get("title_tiktok", ""),           # Title TikTok (Col I)
        "tiktok_id": id_tiktok,                                      # ID TikTok (Col N)
        "quality_score": ai_result.get("quality_score", ""),
        "skip_reason": ai_result.get("skip_reason", ""),
    }

    print(f"      📊 Ghi Sheet '{sheet_name}': id_tiktok→N, hook→B+E, voice→C, image_prompts→G")

    result = safe_post_json(SHEET_URL, payload)

    if result and result.get("status") == "success":
        row = result.get("row", "?")
        print(f"      ✅ Đã ghi Sheet dòng {row}")
        return result
    else:
        print(f"      ⚠️ Lỗi ghi Sheet: {result}")
        return result

def update_article_drive_link(row: int, drive_link: str, sheet_name: str = "tổng") -> bool:
    payload = {
        "action": "update_fb_drive",
        "sheet_name": sheet_name,
        "row": int(row),
        "drive_link": drive_link,
    }
    result = safe_post_json(SHEET_URL, payload)
    return result.get("status") == "success" if result else False
