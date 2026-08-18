#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  fb_ai_script.py — Gửi video + caption cho Gemini AI
  Nhận lại JSON kịch bản: hook, script_voice, scenes...

  Flow:
  1. Upload file video lên Gemini Files API
  2. Gửi prompt + video + caption cho Gemini
  3. Parse JSON response → trả về dict
═══════════════════════════════════════════════════════
"""

import os
import json
import time
import re

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")
PROMPT_FILE = os.path.join(CONFIG_DIR, "prompt_script.txt")


def load_prompt() -> str:
    """Đọc prompt từ file config/prompt_script.txt (bạn có thể sửa trực tiếp)"""
    if os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    raise FileNotFoundError(f"Không tìm thấy prompt: {PROMPT_FILE}")


def analyze_video_with_ai(video_path: str, caption: str, api_key: str) -> dict | None:
    """
    Gửi video + caption cho Gemini AI để phân tích.
    Trả về dict JSON với: hook, script_voice, title_tiktok, scenes...
    """
    try:
        import google.generativeai as genai
    except ImportError:
        print("      ❌ Chưa cài google-generativeai: pip install google-generativeai")
        return None

    if not api_key:
        print("      ❌ GEMINI_API_KEY chưa điền trong .env")
        return None

    genai.configure(api_key=api_key)

    print(f"      🤖 Upload video lên Gemini...")

    try:
        # Bước 1: Upload video file
        video_file = genai.upload_file(
            path=video_path,
            mime_type="video/mp4",
            display_name=os.path.basename(video_path),
        )

        # Đợi xử lý xong
        print(f"      ⏳ Đợi Gemini xử lý video...")
        while video_file.state.name == "PROCESSING":
            time.sleep(3)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            print(f"      ❌ Gemini xử lý video thất bại")
            return None

        print(f"      ✅ Video đã upload xong")

        # Bước 2: Gửi prompt + video + caption
        prompt = load_prompt()

        user_message = f"""VIDEO GỐC:
Caption/Tiêu đề gốc: {caption}

Hãy xem video trên và phân tích nội dung, sau đó tạo kịch bản remake theo yêu cầu."""

        model = genai.GenerativeModel("gemini-2.0-flash")

        print(f"      🤖 Gửi yêu cầu phân tích...")
        response = model.generate_content(
            [video_file, prompt + "\n\n" + user_message],
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=4096,
            ),
        )

        # Bước 3: Parse JSON
        raw_text = response.text.strip()

        # Loại bỏ markdown code block nếu có
        raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
        raw_text = re.sub(r'\s*```$', '', raw_text)
        raw_text = raw_text.strip()

        result = json.loads(raw_text)

        print(f"      ✅ AI trả về JSON thành công")
        print(f"         Title: {result.get('title_tiktok', '')[:60]}")
        print(f"         Hook: {result.get('hook', '')[:60]}")

        # Xóa file trên Gemini
        try:
            genai.delete_file(video_file.name)
        except:
            pass

        return result

    except json.JSONDecodeError as e:
        print(f"      ❌ AI trả về JSON không hợp lệ: {e}")
        print(f"         Raw: {raw_text[:200]}")
        return None
    except Exception as e:
        print(f"      ❌ Gemini AI lỗi: {e}")
        return None


# ── CLI TEST ──
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Cách dùng: python3 fb_ai_script.py <video.mp4> <caption> [api_key]")
        sys.exit(1)

    video = sys.argv[1]
    cap = sys.argv[2]
    key = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("GEMINI_API_KEY", "")

    result = analyze_video_with_ai(video, cap, key)
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
