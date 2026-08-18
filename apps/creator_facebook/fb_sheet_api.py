#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  fb_sheet_api.py — Ghi dữ liệu lên Google Sheet
  Dùng Apps Script URL có sẵn, ghi vào sheet "facebook"

  Cột trên sheet "facebook":
  A: main_idea
  B: link gốc Facebook
  C: script_voice
  D: (trống)
  E: hook
  F: have_frame (true/false)
  G: scenes (JSON string)
  H: source_name
  I: title_tiktok
  J: drive_link
  K: voice_link
  L: status
═══════════════════════════════════════════════════════
"""

import os
import sys
import json
import requests
import time
import random
from datetime import datetime

# Tái sử dụng safe_post_json từ project chính
# apps/creator_facebook/fb_sheet_api.py → creator_facebook → apps → mannyAccount
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
from shared.services.sheet_api import safe_post_json

SHEET_URL = "https://script.google.com/macros/s/AKfycbyW2cMY-3kh2qUMWwc2Tta8BrqrZY1mZLhDyQ1i8G94J9QX7LCr7LY2Brri54PVWmcC/exec"


def save_fb_to_sheet(ai_result: dict, video_url: str, source_name: str = "", id_tiktok: str = "") -> dict | None:
    """
    Lưu kết quả AI phân tích lên Google Sheet tab "facebook".
    Mapping: A=link, B=hook, C=script_voice, E=hook, F=have_frame, I=title_tiktok, J=drive, N=id_tiktok
    """
    payload = {
        "action": "save_facebook",
        "sheet_name": "facebook",
        "link": video_url,                                          # A
        "hook": ai_result.get("hook", ""),                          # B + E
        "script_voice": ai_result.get("script_voice", ""),          # C
        "have_frame": "Có frame" if ai_result.get("have_frame", False) else "Không frame",  # F
        "scenes": json.dumps(ai_result.get("scenes", []), ensure_ascii=False),  # G
        "source_name": source_name,                                 # H
        "title_tiktok": ai_result.get("title_tiktok", ""),          # I
        "finished_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # K
        "id_tiktok": id_tiktok,                                     # N
        "quality_score": ai_result.get("quality_score", ""),
        "skip_reason": ai_result.get("skip_reason", ""),
    }

    print(f"      📊 Ghi Sheet 'facebook': link→A, hook→B+E, script_voice→C, have_frame→F, title→I, time→K")

    result = safe_post_json(SHEET_URL, payload)

    if result and result.get("status") == "success":
        row = result.get("row", "?")
        print(f"      ✅ Đã ghi Sheet dòng {row}")
        return result
    else:
        print(f"      ⚠️ Sheet response: {result}")
        return result


def update_fb_finished_time(row: int, time_str: str) -> bool:
    """Mượn API update_fb_voice (cột K) để cập nhật thời gian làm xong, khỏi cần sửa Apps Script"""
    payload = {
        "action": "update_fb_voice",
        "sheet_name": "facebook",
        "row": int(row),
        "voice_link": time_str,
    }
    result = safe_post_json(SHEET_URL, payload)
    return result.get("status") == "success" if result else False


def update_fb_drive_link(row: int, drive_link: str) -> bool:
    """Cập nhật link Drive vào cột J (cột 10)"""
    payload = {
        "action": "update_fb_drive",
        "sheet_name": "facebook",
        "row": int(row),
        "drive_link": drive_link,
    }
    result = safe_post_json(SHEET_URL, payload)
    return result.get("status") == "success" if result else False


def update_fb_status(row: int, status: str) -> bool:
    """Cập nhật status vào cột L"""
    payload = {
        "action": "update_fb_status",
        "sheet_name": "facebook",
        "row": int(row),
        "status": status,
    }
    result = safe_post_json(SHEET_URL, payload)
    return result.get("status") == "success" if result else False


def update_fb_status_m(row: int, status: str, sheet_name: str = "facebook") -> bool:
    """Cập nhật status vào cột M"""
    payload = {
        "action": "update_fb_status_m",
        "sheet_name": sheet_name,
        "row": int(row),
        "status": status,
    }
    result = safe_post_json(SHEET_URL, payload)
    return result.get("status") == "success" if result else False
