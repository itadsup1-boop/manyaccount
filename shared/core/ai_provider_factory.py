#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  ai_provider_factory.py — Bộ điều phối chọn AI Provider (ChatGPT / Gemini)

  Quản lý tập trung việc chọn AI Engine dựa theo cấu hình
  giao diện (UI Checkbox/Radio) hoặc biến môi trường AI_PROVIDER.
═══════════════════════════════════════════════════════
"""

from __future__ import annotations

import os
import sys
from typing import Any

import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "ai_provider.json")

from apps.creator_facebook.chatgpt_automator import analyze_video_with_chatgpt
from apps.creator_facebook.gemini_automator import analyze_video_with_gemini


def get_configured_ai_provider() -> str:
    """Đọc AI Provider từ môi trường hoặc file cấu hình hệ thống (mặc định 'chatgpt')."""
    provider = os.environ.get("AI_PROVIDER", "").strip().lower()
    if not provider:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    provider = str(data.get("provider", "chatgpt")).strip().lower()
            except Exception:
                provider = "chatgpt"
        else:
            provider = "chatgpt"

    if provider in {"gemini", "google_gemini", "gemini_web"}:
        return "gemini"
    return "chatgpt"


def save_configured_ai_provider(provider: str) -> str:
    """Lưu AI Provider vào file cấu hình trên đĩa và cập nhật biến môi trường."""
    clean_provider = "gemini" if str(provider).strip().lower() in {"gemini", "google_gemini", "gemini_web"} else "chatgpt"
    os.environ["AI_PROVIDER"] = clean_provider
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"provider": clean_provider}, f, indent=4)
    except Exception as e:
        print(f"⚠️ Lỗi lưu cấu hình AI Provider: {e}")
    return clean_provider


def analyze_video_content(
    video_path: str,
    caption: str,
    provider: str | None = None,
    is_tele_bot: bool = False,
    extra_content: str = "",
    profile_id: str | None = None,
    repair_instruction: str = "",
    source_type: str = "tiktok",
    experiment_content_key: str = "",
    edit_mode: str = "",
    whisper_transcript: str = "",
    enable_auto_fallback: bool = True,
) -> dict[str, Any] | None:
    """
    Hàm giao diện chung sinh kịch bản video qua AI Provider được lựa chọn.
    Tự động chọn ChatGPT hoặc Gemini dựa trên tham số 'provider' hoặc cấu hình hệ thống.
    """
    selected_provider = (provider or get_configured_ai_provider()).lower()
    print(f"   🤖 AI Factory: Đã kích hoạt nhà cung cấp '[{selected_provider.upper()}]'")

    result = None

    if selected_provider == "gemini":
        result = analyze_video_with_gemini(
            video_path=video_path,
            caption=caption,
            extra_content=extra_content,
            profile_id=profile_id,
            repair_instruction=repair_instruction,
            source_type=source_type,
            experiment_content_key=experiment_content_key,
            edit_mode=edit_mode,
            whisper_transcript=whisper_transcript,
        )
        if not result:
            print("   ⚠️ Gemini không trả về kịch bản hợp lệ. Giữ nguyên lựa chọn Gemini (không mở ChatGPT)...")
    else:
        # Default: ChatGPT
        result = analyze_video_with_chatgpt(
            video_path=video_path,
            caption=caption,
            is_tele_bot=is_tele_bot,
            extra_content=extra_content,
            profile_id=profile_id,
            repair_instruction=repair_instruction,
            source_type=source_type,
            experiment_content_key=experiment_content_key,
            edit_mode=edit_mode,
            whisper_transcript=whisper_transcript,
        )
        if not result and enable_auto_fallback:
            print("   ⚠️ ChatGPT gặp lỗi hoặc bận, tự động chuyển sang Gemini (Web/API) dự phòng...")
            result = analyze_video_with_gemini(
                video_path=video_path,
                caption=caption,
                extra_content=extra_content,
                profile_id=profile_id,
                repair_instruction=repair_instruction,
                source_type=source_type,
                experiment_content_key=experiment_content_key,
                edit_mode=edit_mode,
                whisper_transcript=whisper_transcript,
            )

    return result


def analyze_article_content(
    article_title: str,
    article_content: str,
    article_url: str = "",
    id_tiktok: str = "",
    repair_instruction: str = "",
    provider: str | None = None,
    enable_auto_fallback: bool = True,
    extra_content: str = "",
) -> dict[str, Any] | None:
    """
    Hàm giao diện chung sinh kịch bản cho bài viết báo chí qua AI Provider được lựa chọn.
    """
    selected_provider = (provider or get_configured_ai_provider()).lower()
    print(f"   🤖 AI Factory (Article): Đã kích hoạt nhà cung cấp '[{selected_provider.upper()}]'")

    try:
        from apps.creator_article.article_chatgpt_automator import analyze_article_with_chatgpt
    except ImportError:
        analyze_article_with_chatgpt = None

    if selected_provider == "gemini":
        result = analyze_video_with_gemini(
            video_path="",
            caption=f"Tiêu đề: {article_title}\n\nNội dung bài báo:\n{article_content}",
            extra_content=extra_content,
            profile_id=id_tiktok,
            repair_instruction=repair_instruction,
            source_type="article",
            experiment_content_key=article_url,
        )
        if not result:
            print("   ⚠️ Gemini không trả về kịch bản cho bài viết. Giữ nguyên lựa chọn Gemini (không mở ChatGPT)...")
        return result
    else:
        if analyze_article_with_chatgpt:
            result = analyze_article_with_chatgpt(
                article_url=article_url,
                id_tiktok=id_tiktok,
                extra_content=extra_content,
                repair_instruction=repair_instruction,
                article_data={
                    "title": article_title,
                    "clean_content": article_content,
                    "source_url": article_url,
                },
            )
        else:
            result = None

        if not result and enable_auto_fallback:
            print("   ⚠️ ChatGPT gặp lỗi, tự động chuyển sang Gemini làm dự phòng cho bài viết...")
            result = analyze_video_with_gemini(
                video_path="",
                caption=f"Tiêu đề: {article_title}\n\nNội dung bài báo:\n{article_content}",
                extra_content=extra_content,
                profile_id=id_tiktok,
                repair_instruction=repair_instruction,
                source_type="article",
                experiment_content_key=article_url,
            )
        return result
