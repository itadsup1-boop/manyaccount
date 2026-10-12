#!/usr/bin/env python3
import os
import sys
import json
import re

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)
from shared.core.experiment_manager import apply_experiment_metadata
from shared.core.prompt_builder import build_prompt, resolve_prompt_experiment

CONFIG_DIR = os.path.join(PROJECT_ROOT, "config", "prompts")
PROMPT_FILE = os.path.join(CONFIG_DIR, "prompt_article.txt")

def load_prompt() -> str:
    if os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    
    # Mặc định nếu chưa có file
    return """Bạn là một Biên tập viên TikTok/Shorts chuyên nghiệp. Hãy đọc bài báo dưới đây và viết 1 kịch bản video.
Yêu cầu trả về chuẩn định dạng JSON, TUYỆT ĐỐI không có văn bản nào ngoài JSON.
{
  "hook": "1-2 câu giật gân, thu hút sự chú ý",
  "script_voice": "Nội dung chi tiết tóm tắt bài báo (dưới 150 chữ)",
  "title_tiktok": "Tiêu đề để đăng lên TikTok (có hashtag)",
  "image_prompts": ["mô tả ảnh 1", "mô tả ảnh 2", "mô tả ảnh 3"]
}
Chú ý: Biến image_prompts là mảng chứa các câu tiếng Việt miêu tả các bức ảnh để công cụ tự động lên mạng tìm ảnh minh họa."""

def analyze_article_with_ai(
    article_text: str,
    id_tiktok: str,
    api_key: str,
    repair_instruction: str = "",
) -> dict | None:
    try:
        import google.generativeai as genai
    except ImportError:
        print("      ❌ Chưa cài google-generativeai: pip install google-generativeai")
        return None

    if not api_key:
        print("      ❌ GEMINI_API_KEY chưa điền trong .env")
        return None

    genai.configure(api_key=api_key)
    
    user_message = f"""BÀI BÁO:
{article_text}

Hãy xử lý và BẮT BUỘC trả về JSON, và BẮT BUỘC thêm trường "id_tiktok": "{id_tiktok}" vào trong JSON kết quả của bạn!"""
    experiment_assignment = resolve_prompt_experiment(
        id_tiktok,
        source_type="article",
        task_input=user_message,
    )
    prompt = build_prompt(
        load_prompt(),
        id_tiktok,
        source_type="article",
        task_input=user_message,
        repair_instruction=repair_instruction,
        experiment_assignment=experiment_assignment,
    )

    model = genai.GenerativeModel("gemini-2.0-flash")

    print(f"      🤖 Gửi bài báo cho AI xử lý...")
    try:
        response = model.generate_content(
            [prompt],
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )

        raw_text = response.text.strip()
        raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
        raw_text = re.sub(r'\s*```$', '', raw_text)
        raw_text = raw_text.strip()

        result = apply_experiment_metadata(
            json.loads(raw_text),
            experiment_assignment,
        )
        
        # Ép cứng id_tiktok nếu AI quên
        result["id_tiktok"] = id_tiktok

        print(f"      ✅ AI trả về JSON thành công")
        print(f"         Hook: {result.get('hook', '')[:60]}...")
        print(f"         Số lượng ảnh yêu cầu: {len(result.get('image_prompts', []))}")

        return result

    except json.JSONDecodeError as e:
        print(f"      ❌ AI trả về JSON không hợp lệ: {e}")
        return None
    except Exception as e:
        print(f"      ❌ Gemini AI lỗi: {e}")
        return None
