#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  Facebook News Auto Remix — Pipeline chính

  FLOW:
  1. Cào 10 video (reels) từ Facebook page
  2. Lọc video mới (so sánh last_video_id)
  3. Với mỗi video mới:
     a. Download video
     b. Gửi video + caption cho ChatGPT → nhận JSON
     c. Ghi JSON lên Google Sheet (hook→B+E, script_voice→C, title→I)
     d. Tạo voice hook (cột E)
     e. Nếu CÓ FRAME → tạo thêm voice script (cột C) → edit giống TikTok
        Nếu KHÔNG FRAME → hook intro (mute+voice) + body (audio gốc) + logo xuyên suốt
     f. Cập nhật last_video_id
═══════════════════════════════════════════════════════
"""

import os
import sys
import time
import json
import shutil
import uuid
import subprocess
from datetime import datetime, timezone

# Thêm project chính vào path
# apps/creator_facebook/fb_pipeline.py → apps/creator_facebook → apps → mannyAccount (project root)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# Import từ project chính
from shared.services.supabase_api import SupabaseAPI, supabase
from shared.services.tts_api import create_voice_full_pipeline
from shared.core.channel_editorial import get_channel_voice_speed, load_channel_editorial

# Import từ fb-news-pipeline
from fb_crawler import crawl_facebook_videos
from fb_downloader import download_video
from chatgpt_automator import analyze_video_with_chatgpt
from fb_sheet_api import save_fb_to_sheet, update_fb_finished_time, update_fb_drive_link, update_fb_status, update_fb_status_m

TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Đọc config từ .env
def _env(key, default=""):
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    return default

VOICE_PROFILE_ID = _env("VOICEBOX_PROFILE_ID", "cb6f4c6a-2617-4eeb-a148-909f0084d8c8")
GDRIVE_FOLDER_ID = _env("DRIVE_FOLDER_ID", _env("GDRIVE_FOLDER_ID", "1VgkkbUJ82kxzWXJH8cfn7UFMMFBKQkzS"))

# Logo/frame paths
LOGO_PATH = os.path.join(PROJECT_ROOT, "assets", "logo.png")
FRAME_PATH = os.path.join(PROJECT_ROOT, "assets", "frame.png")
FACEBOOK_DEFAULT_TARGET_CHANNEL = "Adsupnews"
FACEBOOK_DEFAULT_CONTENT_PROFILE = {
    "Adsupnews": {
        "channel_name": "Adsup News - kênh tin tức tổng hợp nhanh, sắc, dễ bàn luận",
        "topic": "Tin tức tổng hợp đa lĩnh vực từ Facebook, báo và mạng xã hội: xã hội, pháp luật, đời sống, kinh tế, showbiz, thể thao, công nghệ, sức khỏe và các câu chuyện đang được quan tâm.",
        "audience": "Người Việt 18-45 dùng TikTok/Facebook để nắm tin nhanh; thích nội dung rõ bối cảnh, có tác động thực tế, có chi tiết đáng bàn luận và dễ chia sẻ; không thích đọc lại caption dài hoặc tin chung chung.",
        "content_promise": "Mỗi video giúp người xem hiểu nhanh: chuyện gì đang xảy ra, vì sao đáng chú ý, chi tiết nào đắt nhất, tác động tới ai và câu hỏi còn bỏ ngỏ.",
        "primary_goal": "view",
        "tone_style": "Tin nhanh kiểu TikTok: câu ngắn, nhịp dồn, rõ bối cảnh, trung lập nhưng có góc nhìn biên tập; tạo tò mò bằng chi tiết thật, không giật tít sai sự thật.",
        "video_length": "45-60s",
        "format_style": "Cấu trúc mặc định: 1 câu hook mạnh trong 3 giây đầu -> bối cảnh cực ngắn -> 2-3 dữ kiện quan trọng -> vì sao chuyện này đáng chú ý -> kết bằng câu hỏi quan điểm hoặc hệ quả gần người xem.",
        "hook_style": "Hook phải nêu thẳng sự kiện/nhân vật/tác động chính, ưu tiên chi tiết bất thường, điểm gây tranh luận hoặc hệ quả thực tế. Tránh mở đầu mờ như 'mới đây', 'được biết', 'câu chuyện đang gây xôn xao' nếu chưa nói rõ xôn xao vì điều gì.",
        "source_preference": "Ưu tiên video có hình ảnh rõ, sự kiện cụ thể, nguồn/caption có dữ kiện kiểm chứng được, có mâu thuẫn, cảm xúc, tác động xã hội hoặc chi tiết khiến người xem muốn xem tiếp. Bỏ qua video chỉ mang tính PR, recap nhạt, thiếu nhân vật/sự kiện trung tâm hoặc không có điểm mới.",
        "comment_strategy": "Kết tự nhiên bằng một câu hỏi mở, không dẫn dắt quá đà: hỏi quan điểm, hỏi người xem đứng về luồng ý kiến nào, hoặc hỏi tác động gần đời sống. Ví dụ: 'Bạn nghĩ điểm đáng chú ý nhất là gì?', 'Nếu là bạn, bạn sẽ xử lý thế nào?', 'Theo bạn bên nào cần lên tiếng rõ hơn?'.",
        "avoid": "Không bịa chi tiết, không khẳng định tin chưa kiểm chứng, không kết tội khi chưa có kết luận, không dùng từ kích động/thù ghét, không khai thác bi kịch quá đà, không copy nguyên caption, không nhồi số liệu, không viết như báo giấy dài dòng.",
        "winning_examples": "Tham chiếu chất lượng theo nhóm kênh tin tức TikTok kiểu Theanh28: hook nhanh, có nhân vật/sự kiện rõ, chọn đúng chi tiết khiến người xem muốn bàn luận. Mẫu hook: 'Chi tiết này mới là điểm khiến nhiều người tranh luận...'; 'Không chỉ là một đoạn clip, vụ này đáng chú ý vì...'; 'Nếu thông tin này được xác nhận, người bị ảnh hưởng nhiều nhất có thể là...'; 'Từ một tình huống nhỏ, câu chuyện đang mở ra 3 vấn đề lớn...'.",
        "custom_instruction": "Đóng vai biên tập viên tin tức ngắn. Trước khi viết, tự đánh giá video có đáng làm không; chỉ chọn khi có sự kiện cụ thể, hình ảnh rõ, thông tin đủ bám và có lý do để người xem quan tâm. Script_voice phải nói như người dẫn tin TikTok/Facebook: mỗi câu một ý, nhịp nhanh, không lê thê. Hook/on-screen text tối đa khoảng 12-18 từ, ưu tiên rõ ý hơn chơi chữ. Với thông tin chưa chắc chắn, dùng 'theo caption/nguồn/đoạn clip cho thấy' thay vì khẳng định tuyệt đối. Luôn giữ cân bằng giữa hấp dẫn và an toàn pháp lý."
    }
}


QUALITY_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "quality_log.jsonl")


def _build_logo_blur_chain(pre_label: str, regions: list) -> list:
    """
    Generate filter_complex lines to blur detected logo regions.
    Input label: pre_label.  Output label: always [bg] (ready to use as current).
    Each region is (x, y, w, h) in 1080x1920 space.
    """
    parts = []
    prev = pre_label
    for i, (x, y, w, h) in enumerate(regions):
        out = "[bg]" if i == len(regions) - 1 else f"[lb{i}]"
        parts.append(f"{prev}split=2[lbbg{i}][lbfg{i}]")
        parts.append(f"[lbfg{i}]crop={w}:{h}:{x}:{y},avgblur=15[lbb{i}]")
        parts.append(f"[lbbg{i}][lbb{i}]overlay={x}:{y}{out}")
        prev = out
    return parts


def _append_quality_log(pipeline: str, source_name: str, quality_score: int, status: str, reason: str = ""):
    """Ghi 1 dòng JSON vào quality_log.jsonl để Telegram bot đọc báo cáo."""
    try:
        entry = json.dumps({
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "pl": pipeline,
            "src": source_name,
            "score": quality_score,
            "st": status,
            "reason": reason,
        }, ensure_ascii=False)
        with open(QUALITY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass


def _get_source_target_channel(source: dict) -> str:
    value = str(source.get("id_tiktok") or "").strip()
    return value or FACEBOOK_DEFAULT_TARGET_CHANNEL


CONTENT_PROFILE_FIELDS = [
    ("Tên kênh", "channel_name"),
    ("Chủ đề chính", "topic"),
    ("Tệp người xem", "audience"),
    ("Lời hứa nội dung", "content_promise"),
    ("Mục tiêu chính", "primary_goal"),
    ("Giọng văn/phong cách", "tone_style"),
    ("Độ dài video mong muốn", "video_length"),
    ("Format lặp lại", "format_style"),
    ("Kiểu hook phù hợp", "hook_style"),
    ("Ưu tiên chọn nguồn/video", "source_preference"),
    ("Cách kéo bình luận", "comment_strategy"),
    ("Điều cần tránh", "avoid"),
    ("Ví dụ từng hiệu quả", "winning_examples"),
    ("Chỉ đạo tùy biến thêm", "custom_instruction"),
]


def _merge_content_profiles(*profiles):
    merged = {}
    for profile in profiles:
        if isinstance(profile, str):
            if profile.strip():
                merged["custom_instruction"] = profile.strip()
            continue
        if not isinstance(profile, dict):
            continue
        for _label, key in CONTENT_PROFILE_FIELDS:
            value = profile.get(key)
            if str(value or "").strip():
                merged[key] = value
    return merged


def _load_tiktok_synced_content_profile(id_tiktok: str) -> dict:
    clean_id = str(id_tiktok or "").replace("@", "").strip()
    if not clean_id:
        return {}
    try:
        profiles = SupabaseAPI.get_tiktok_content_profiles()
        synced = profiles.get(clean_id, {})
        return synced if isinstance(synced, dict) else {}
    except Exception:
        return {}


def _format_channel_content_profile(profile: dict) -> str:
    lines = []
    for label, key in CONTENT_PROFILE_FIELDS:
        value = str(profile.get(key, "")).strip()
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _load_channel_content_profile(id_tiktok: str) -> str:
    if not id_tiktok:
        return ""

    clean_id = str(id_tiktok).replace("@", "").strip()
    config_path = os.path.join(PROJECT_ROOT, "assets", "channels", clean_id, "config.json")
    local_profile = {}

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            local_profile = config.get("content_profile") or {}
        except Exception:
            local_profile = {}

    profile = _merge_content_profiles(
        FACEBOOK_DEFAULT_CONTENT_PROFILE.get(clean_id, {}),
        _load_tiktok_synced_content_profile(clean_id),
        local_profile,
        load_channel_editorial(clean_id).get("content_profile", {}),
    )
    return _format_channel_content_profile(profile)


def _get_duration(file_path: str) -> float:
    """Lấy duration file media bằng ffprobe"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", file_path],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except:
        return 0.0

def _is_horizontal(file_path: str) -> bool:
    """Kiểm tra xem video có phải là video ngang không (width > height)"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0", 
             "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", file_path],
            capture_output=True, text=True, timeout=10
        )
        w, h = map(int, result.stdout.strip().split('x'))
        return w > h
    except:
        return False


class FBNewsPipeline:
    def __init__(self):
        os.makedirs(TEMP_DIR, exist_ok=True)
        self.stats = {"scanned": 0, "new": 0, "completed": 0, "failed": 0}

    # ═══════════════════════════════════════════════════
    #  CHẠY PIPELINE 1 LẦN
    # ═══════════════════════════════════════════════════
    def run(self):
        self.stats = {"scanned": 0, "new": 0, "completed": 0, "failed": 0}

        print("═" * 55)
        print("  🚀 BẮT ĐẦU PIPELINE FACEBOOK NEWS")
        print("═" * 55)

        sources = self._get_active_sources()
        print(f"📋 {len(sources)} nguồn Facebook active")

        if not sources:
            print("💤 Chưa có nguồn nào. Thêm trên giao diện.")
            return

        for source in sources:
            try:
                self._process_source(source)
            except Exception as e:
                print(f"🔥 Lỗi nguồn {source.get('source_name')}: {e}")

        print()
        print("═" * 55)
        s = self.stats
        print(f"📊 KẾT QUẢ: {s['scanned']} nguồn | {s['new']} mới | {s['completed']} xong | {s['failed']} lỗi")
        print("═" * 55)

    # ═══════════════════════════════════════════════════
    #  XỬ LÝ 1 NGUỒN
    # ═══════════════════════════════════════════════════
    def _process_source(self, source: dict):
        name = source.get("source_name", "")
        url = source.get("source_url", "")
        last_vid = source.get("last_video_id")

        print(f"\n📡 ── {name} ──")
        print(f"   URL: {url}")
        print(f"   Last video: {last_vid or '(chưa có)'}")
        self.stats["scanned"] += 1

        # BƯỚC 1: Cào 10 video đầu
        all_videos = crawl_facebook_videos(url, max_videos=10)

        if not all_videos:
            print("   💤 Không cào được video nào.")
            self._update_scan_time(source["id"])
            return

        # BƯỚC 2: Lọc video mới
        new_videos = []
        if not last_vid:
            print(f"   📌 Lần đầu quét — lấy tất cả {len(all_videos)} video")
            new_videos = all_videos
        else:
            for v in all_videos:
                if v["video_id"] == last_vid:
                    print(f"   📌 Gặp last_video_id [{last_vid}] → dừng")
                    break
                new_videos.append(v)

        if not new_videos:
            print("   💤 Không có video mới.")
            self._update_scan_time(source["id"])
            return

        print(f"   ✨ {len(new_videos)} video MỚI")
        self.stats["new"] += len(new_videos)

        # BƯỚC 3: Xử lý từng video
        latest_done_id = None

        for i, video in enumerate(new_videos, 1):
            print(f"\n   ▶️ Video {i}/{len(new_videos)}: [{video['video_id']}]")
            print(f"      Caption: {video['caption'][:80]}...")

            result = self._process_one_video(video, source)

            if result == True:
                self.stats["completed"] += 1
                if not latest_done_id:
                    latest_done_id = video["video_id"]
            else:
                self.stats["failed"] += 1

        # BƯỚC 4: Cập nhật last_video_id
        self._update_scan_time(source["id"], latest_done_id)
        if latest_done_id:
            print(f"   ☁️ last_video_id = {latest_done_id}")

    # ═══════════════════════════════════════════════════
    #  XỬ LÝ 1 VIDEO
    # ═══════════════════════════════════════════════════
    def _process_one_video(self, video: dict, source: dict, on_success=None, on_error=None) -> bool:
        job_id = uuid.uuid4().hex[:8]
        work_dir = os.path.join(TEMP_DIR, f"job_{job_id}")
        os.makedirs(work_dir, exist_ok=True)

        try:
            caption = video.get("caption", "").strip()

            # ── [1/6] Download video ──
            print(f"      📥 [1/6] Download...")
            dl = download_video(video["url"], video["video_id"])
            if not dl:
                raise Exception("Download thất bại")

            if self._check_hash_exists(dl["hash"]):
                print(f"      ⏭️ Trùng file hash → skip")
                return "duplicate"

            # Ghi đè caption từ crawler (thường là "34K") bằng title xịn từ yt-dlp
            if dl.get("title") and len(dl["title"]) > 5:
                real_title = dl["title"]
                parts = real_title.split(" | ")
                if len(parts) >= 2 and ("views" in parts[0].lower() or "lượt xem" in parts[0].lower()):
                    caption = parts[1].strip()
                elif len(parts) >= 1:
                    caption = parts[0].strip()
                else:
                    caption = real_title
                print(f"      📝 Tìm thấy Caption xịn: \"{caption[:60]}...\"")

            # ── [2/6] ChatGPT phân tích ──
            print(f"      🤖 [2/6] ChatGPT phân tích video...")
            target_tiktok_id = _get_source_target_channel(source)
            channel_profile = _load_channel_content_profile(target_tiktok_id)
            ai_result = analyze_video_with_chatgpt(
                dl["path"], 
                caption, 
                is_tele_bot=source.get("is_telegram_bot", False),
                extra_content=channel_profile or source.get("extra_content", ""),
                profile_id=target_tiktok_id
            )

            if not ai_result:
                print(f"      ℹ️ AI không khả dụng — dùng caption gốc")
                ai_result = {
                    "title_tiktok": caption[:100],
                    "hook": caption[:80],
                    "script_voice": caption[:200],
                    "main_idea": caption[:150],
                    "have_frame": False,
                    "should_make_video": True,
                    "scenes": [],
                }
                
            should_make_video = ai_result.get("should_make_video", True)
            if source.get("is_telegram_bot"):
                should_make_video = True

            topic_fit = ai_result.get("topic_fit", True)
            if not source.get("is_telegram_bot") and (str(topic_fit).lower() == "false" or not topic_fit):
                topic_fit_reason = ai_result.get("topic_fit_reason") or ai_result.get("skip_reason", "")
                print(f"      ⏭️ Video không đúng định vị kênh → skip. {topic_fit_reason}")
                _append_quality_log("facebook", source.get("source_name", ""), int(ai_result.get("quality_score", 0)), "skip", topic_fit_reason)
                return "skip"

            # Ép kiểu an toàn (nếu ChatGPT trả về chuỗi "false" hoặc boolean False)
            if str(should_make_video).lower() == "false" or not should_make_video:
                skip_reason = ai_result.get("skip_reason", "")
                print(f"      ⏭️ AI đánh giá: KHÔNG NÊN làm video này. {f'Lý do: {skip_reason}' if skip_reason else ''}")
                return "skip"

            # Quality gate: bỏ qua video chất lượng thấp
            quality_score = int(ai_result.get("quality_score", 5))
            skip_reason = ai_result.get("skip_reason", "")
            quality_threshold = int(os.environ.get("QUALITY_THRESHOLD", "6"))
            if not source.get("is_telegram_bot") and quality_score < quality_threshold:
                print(f"      ⏭️ Quality score {quality_score}/10 dưới ngưỡng {quality_threshold} → skip. {f'Lý do: {skip_reason}' if skip_reason else ''}")
                _append_quality_log("facebook", source.get("source_name", ""), quality_score, "skip", skip_reason)
                return "skip"
            print(f"      ✅ Quality score: {quality_score}/10")
            _append_quality_log("facebook", source.get("source_name", ""), quality_score, "done")

            hook = ai_result.get("hook", "").strip()
            script_voice = ai_result.get("script_voice", "").strip()
            
            # Xử lý trường hợp AI trả về script_voice bị lặp lại hook ở đầu
            if hook and script_voice:
                hook_clean = ''.join(c for c in hook.lower() if c.isalnum() or c.isspace()).strip()
                script_clean = ''.join(c for c in script_voice.lower() if c.isalnum() or c.isspace()).strip()
                
                if hook_clean and script_clean.startswith(hook_clean):
                    hook_words = hook.split()
                    script_words = script_voice.split()
                    if len(script_words) > len(hook_words):
                        script_voice = " ".join(script_words[len(hook_words):]).strip()
                        while script_voice and script_voice[0] in ".,!?:; -":
                            script_voice = script_voice[1:].strip()
                        if script_voice:
                            script_voice = script_voice[0].upper() + script_voice[1:]
                            
            title = ai_result.get("title_tiktok", "")
            have_frame = ai_result.get("have_frame", False)
            tone = ai_result.get("tone", "Trung tính").strip()

            print(f"      📋 have_frame = {have_frame} | tone = {tone}")

            # Đọc Voice config chung từ global_voice_settings.json
            voice_config = {}
            settings_path = os.path.join(APP_DIR, "data", "global_voice_settings.json")
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, "r", encoding="utf-8") as fs:
                        voice_config = json.load(fs)
                except:
                    pass

            channel_voice_speed = get_channel_voice_speed(target_tiktok_id)
            channel_dir = os.path.join(PROJECT_ROOT, "assets", "channels", target_tiktok_id)
            channel_voice_path = os.path.join(channel_dir, "voice_config.json")
            channel_config_path = os.path.join(channel_dir, "config.json")
            try:
                if os.path.exists(channel_voice_path):
                    with open(channel_voice_path, "r", encoding="utf-8") as fs:
                        channel_voice_config = json.load(fs)
                    if isinstance(channel_voice_config, dict):
                        voice_config.update(channel_voice_config)
                if os.path.exists(channel_config_path):
                    with open(channel_config_path, "r", encoding="utf-8") as fs:
                        channel_voice_speed = float(json.load(fs).get("voice_speed", channel_voice_speed))
            except Exception as voice_config_error:
                print(f"      ⚠️ Không đọc được cấu hình voice kênh: {voice_config_error}")

            # Chọn Voice ID dựa trên tone
            selected_voice_id = voice_config.get(tone)
            
            # Nếu không cấu hình giọng cho tone này, lùi về dùng giọng Trung tính
            if not selected_voice_id:
                selected_voice_id = voice_config.get("Trung tính")
                
            # Nếu chưa cấu hình cả giọng Trung tính, lùi về mặc định hệ thống
            if not selected_voice_id:
                selected_voice_id = VOICE_PROFILE_ID
                
            print(f"      🎵 Chọn Voice ID: {selected_voice_id} | Speed: {channel_voice_speed}")

            # ── [3/6] Tạo voice ──
            # Luôn tạo voice cho hook (cột E)
            print(f"      🗣️ [3/6] Tạo voice hook: \"{hook[:50]}...\"")
            hook_voice_path = None
            script_voice_path = None

            if hook:
                try:
                    hook_voice_path = create_voice_full_pipeline(
                        text=hook, save_dir=work_dir,
                        filename=f"hook_{job_id}.wav",
                        profile_id=selected_voice_id,
                        speed=channel_voice_speed,
                    )
                    if hook_voice_path and os.path.exists(hook_voice_path):
                        print(f"      ✅ Hook voice OK: {os.path.getsize(hook_voice_path) / 1024:.0f}KB")
                    else:
                        hook_voice_path = None
                except Exception as e:
                    print(f"      ⚠️ Hook voice lỗi: {e}")

            # Nếu CÓ FRAME → tạo voice script (không gộp hook vì hook đã có voice riêng)
            # Nếu KHÔNG FRAME → không cần script_voice, chỉ dùng voice hook và audio gốc
            if have_frame and script_voice:
                print(f"      🗣️ Tạo voice script (cột C): \"{script_voice[:50]}...\"")
                try:
                    script_voice_path = create_voice_full_pipeline(
                        text=script_voice, save_dir=work_dir,
                        filename=f"script_{job_id}.wav",
                        profile_id=selected_voice_id,
                        speed=channel_voice_speed,
                    )
                    if script_voice_path and os.path.exists(script_voice_path):
                        print(f"      ✅ Script voice OK: {os.path.getsize(script_voice_path) / 1024:.0f}KB")
                    else:
                        script_voice_path = None
                except Exception as e:
                    print(f"      ⚠️ Script voice lỗi: {e}")

            # ── [4/6] Dựng video ──
            mode_name = "CÓ FRAME" if have_frame else "KHÔNG FRAME"
            print(f"      🎬 [4/6] Dựng video (mode: {mode_name})...")

            if have_frame:
                final_path = self._edit_video_with_frame(
                    source_video=dl["path"],
                    hook_voice_path=hook_voice_path,
                    script_voice_path=script_voice_path,
                    title=title, hook_text=hook,
                    work_dir=work_dir, job_id=job_id,
                    source=source, tone=tone
                )
            else:
                final_path = self._edit_video_no_frame(
                    source_video=dl["path"],
                    hook_voice_path=hook_voice_path,
                    hook_text=hook or title,
                    work_dir=work_dir, job_id=job_id,
                    source=source, tone=tone
                )

            # ── [5/6] Upload Google Drive ──
            drive_link = None
            if final_path and os.path.exists(final_path):
                print(f"      ☁️ [5/6] Đang upload video lên Google Drive...")
                from shared.modules.upload_drive import upload_video_to_drive
                drive_link = upload_video_to_drive(final_path, GDRIVE_FOLDER_ID)

            if not drive_link:
                raise Exception("Upload video lên Google Drive thất bại hoặc link trống.")

            # ── [6/6] Ghi dữ liệu khi đã hoàn tất mọi bước thành công ──
            print(f"      📊 [6/6] Lưu kết quả lên Google Sheet & Database...")
            
            # 1. Lưu Google Sheet
            sheet_type = source.get("sheet_type", "facebook")
            if source.get("is_telegram_bot") and sheet_type == "tong":
                from shared.services.sheet_api import save_to_sheet
                SHEET_URL_TONG = _env("GOOGLE_SHEET_URL", _env("SHEET_URL", "https://script.google.com/macros/s/AKfycbyW2cMY-3kh2qUMWwc2Tta8BrqrZY1mZLhDyQ1i8G94J9QX7LCr7LY2Brri54PVWmcC/exec"))
                sheet_result = save_to_sheet(
                    script_url=SHEET_URL_TONG,
                    link=video["url"],
                    title=ai_result.get("title_tiktok", ""),
                    script=ai_result.get("script_voice", ""),
                    combined_hints=ai_result.get("hook", ""),
                    original_video=video.get("video_id", ""),
                    title_tiktok=ai_result.get("title_tiktok", ""),
                    tiktok_id=_get_source_target_channel(source),
                    file_path=drive_link
                )
                sheet_row = sheet_result.get("row") if isinstance(sheet_result, dict) else None
                if sheet_row:
                    print(f"      ✅ Đã ghi Sheet Tổng dòng {sheet_row}")
                    # Đối với sheet tổng chạy từ telebot, cột M phải là đăng ngay lập tức
                    update_fb_status_m(sheet_row, "đăng ngay lập tức", sheet_name="tổng")
            else:
                sheet_result = save_fb_to_sheet(
                    ai_result=ai_result,
                    video_url=video["url"],
                    source_name=source.get("source_name", ""),
                    id_tiktok=_get_source_target_channel(source),
                )
                sheet_row = sheet_result.get("row") if sheet_result else None
                
                if sheet_row:
                    update_fb_status(sheet_row, "completed")
                    if source.get("is_telegram_bot"):
                        update_fb_status_m(sheet_row, "đăng ngay lập tức")
                    update_fb_drive_link(sheet_row, drive_link)
                    update_fb_finished_time(sheet_row, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    print(f"      ✅ Đã đẩy link Drive vào Google Sheet dòng {sheet_row}")

            # 2. Lưu Supabase (chỉ lưu nếu không phải chạy từ bot Telegram vì ID từ bot không phải UUID hợp lệ)
            if not source.get("is_telegram_bot"):
                record_id = self._insert_video_record(source.get("id"), video, dl, ai_result, final_path)
                if record_id:
                    print(f"      ✅ Đã lưu record Supabase ID: {record_id}")

            print(f"      🎉 XONG!")
            print(f"      📁 Video: {final_path}")
            print(f"      🔗 Link Drive: {drive_link}")
                
            if on_success:
                try:
                    on_success(drive_link, final_path, sheet_row)
                except Exception as e:
                    print(f"      ⚠️ Lỗi callback on_success: {e}")
                
            # Giải phóng bộ nhớ sau khi upload thành công
            print(f"      🧹 Đang dọn dẹp bộ nhớ tạm...")
            try:
                import shutil
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir)
                if dl and dl.get("path") and os.path.exists(dl["path"]):
                    os.remove(dl["path"])
                print(f"      ✅ Đã giải phóng bộ nhớ cho job {job_id}")
            except Exception as e:
                print(f"      ⚠️ Lỗi khi dọn dẹp: {e}")
                    
            return True

        except Exception as e:
            print(f"      ❌ Lỗi: {e}")
            import traceback
            traceback.print_exc()
            if on_error:
                on_error(str(e))
            return False

    # ═══════════════════════════════════════════════════
    #  MODE 1: CÓ FRAME
    #  → Giống TikTok: dùng video_remix.create_video_from_source_video
    #  → Intro: hook voice (cột E) + frame + logo + text
    #  → Body:  script voice (cột C) + frame + logo
    # ═══════════════════════════════════════════════════
    def _edit_video_with_frame(self, source_video, hook_voice_path, script_voice_path,
                                title, hook_text, work_dir, job_id, source, tone="Trung tính"):
        # NATIVE FFmpeg implementation cho chế độ CÓ FRAME
        # Sử dụng 1 pass duy nhất: Loop video gốc + chèn full script_voice
        
        final_path = os.path.join(work_dir, f"final_{job_id}.mp4")

        def download_asset_safe(folder, filename):
            if not filename or filename == "-- Trống --":
                return None
            if os.path.isabs(filename):
                return filename if os.path.exists(filename) else None
            local_dir = os.path.join(PROJECT_ROOT, "assets", folder)
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, filename)
            if not os.path.exists(local_path):
                print(f"      📥 Đang tải {filename} từ Supabase Storage...")
                from shared.services.supabase_api import SupabaseAPI
                SupabaseAPI.download_asset("assets", folder, local_dir, filename)
            return local_path if os.path.exists(local_path) else None

        hook_duration = 5.0
        if hook_voice_path and os.path.exists(hook_voice_path):
            d = _get_duration(hook_voice_path)
            if d > 0:
                hook_duration = d + 0.5

        is_tele_bot = source.get("is_telegram_bot", False)
        
        raw_title_frame = source.get("title_frame_path")
        title_frame_path = download_asset_safe("frame", raw_title_frame) if is_tele_bot else (raw_title_frame if raw_title_frame else FRAME_PATH)
        
        raw_content_frame = source.get("content_frame_path")
        content_frame_path = download_asset_safe("frame", raw_content_frame) if is_tele_bot else (raw_content_frame if raw_content_frame else FRAME_PATH)
        
        raw_logo = source.get("logo_path")
        logo_path = download_asset_safe("logo", raw_logo) if is_tele_bot else (raw_logo if raw_logo else LOGO_PATH)
        
        has_title_frame = title_frame_path and os.path.exists(title_frame_path)
        has_content_frame = content_frame_path and os.path.exists(content_frame_path)
        has_logo = False # Tắt lắp logo

        # ── XÂY DỰNG FFMPEG COMMAND (1 PASS) ──
        inputs = []
        input_idx = 0
        
        # Nối audio hook và script TRƯỚC KHI gọi FFmpeg chính (để tránh lỗi -shortest bị treo)
        final_audio_path = None
        if hook_voice_path and os.path.exists(hook_voice_path) and script_voice_path and os.path.exists(script_voice_path):
            final_audio_path = os.path.join(work_dir, f"merged_audio_{job_id}.wav")
            subprocess.run(["ffmpeg", "-y", "-i", hook_voice_path, "-i", script_voice_path, 
                            "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[aout]", 
                            "-map", "[aout]", final_audio_path], capture_output=True)
        elif hook_voice_path and os.path.exists(hook_voice_path):
            final_audio_path = hook_voice_path
        elif script_voice_path and os.path.exists(script_voice_path):
            final_audio_path = script_voice_path
            
        has_ai_audio = final_audio_path and os.path.exists(final_audio_path)
        
        audio_dur = 0.0
        if has_ai_audio:
            audio_dur = _get_duration(final_audio_path)
            
        # Dùng -stream_loop -1 để lặp lại video gốc nếu nó ngắn hơn voice
        if has_ai_audio:
            inputs += ["-stream_loop", "-1"]
            
        inputs += ["-i", source_video]
        input_idx += 1
        
        if has_ai_audio:
            inputs += ["-i", final_audio_path]
            main_audio_idx = input_idx
            input_idx += 1
        else:
            main_audio_idx = None
            
        if has_title_frame:
            inputs += ["-i", title_frame_path]
            t_frame_idx = input_idx
            input_idx += 1

        if has_content_frame:
            inputs += ["-i", content_frame_path]
            c_frame_idx = input_idx
            input_idx += 1

        if has_logo:
            inputs += ["-i", logo_path]
            logo_idx = input_idx
            input_idx += 1

        is_horiz = _is_horizontal(source_video)

        import random
        contrast = round(random.uniform(0.97, 1.03), 3)
        saturation = round(random.uniform(0.97, 1.03), 3)
        brightness = round(random.uniform(-0.03, 0.03), 3)
        eq_filter = f",eq=contrast={contrast}:saturation={saturation}:brightness={brightness}"

        # Auto-detect logo/watermark regions per video
        _logo_regions = []
        try:
            from shared.modules.logo_detector import detect_logo_regions
            _logo_regions = detect_logo_regions(source_video)
            if _logo_regions:
                print(f"   🔍 Phát hiện {len(_logo_regions)} vùng logo → tự động blur")
        except Exception as _le:
            print(f"   ⚠️ Logo detection lỗi: {_le}")
        _bg_init = "[bg_pre]" if _logo_regions else "[bg]"

        if is_horiz:
            filters = [
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:2[bg_blur]",
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease{eq_filter}[fg]",
                f"[bg_blur][fg]overlay=(W-w)/2:(H-h)/2-150{_bg_init}"
            ]
        else:
            filters = [f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:100{eq_filter}{_bg_init}"]

        if _logo_regions:
            filters.extend(_build_logo_blur_chain("[bg_pre]", _logo_regions))

        current = "[bg]"

        if has_title_frame and has_content_frame:
            filters.append(f"[{t_frame_idx}:v]scale=1080:1920[tf]")
            filters.append(f"[{c_frame_idx}:v]scale=1080:1920[cf]")
            filters.append(f"{current}[tf]overlay=0:0:enable='between(t,0,{hook_duration})'[with_tf]")
            filters.append(f"[with_tf][cf]overlay=0:0:enable='gt(t,{hook_duration})'[with_frame]")
            current = "[with_frame]"
        elif has_title_frame:
            filters.append(f"[{t_frame_idx}:v]scale=1080:1920[tf]")
            filters.append(f"{current}[tf]overlay=0:0[with_frame]")
            current = "[with_frame]"
        elif has_content_frame:
            filters.append(f"[{c_frame_idx}:v]scale=1080:1920[cf]")
            filters.append(f"{current}[cf]overlay=0:0[with_frame]")
            current = "[with_frame]"

        if has_logo:
            filters.append(f"[{logo_idx}:v]scale=1080:1920[logo]")
            filters.append(f"{current}[logo]overlay=0:0[with_logo]")
            current = "[with_logo]"

        import textwrap
        raw_font = source.get("font_path")
        font_path = download_asset_safe("font", raw_font) if is_tele_bot else raw_font
        if not font_path or not os.path.exists(font_path):
            font_path = os.path.join(PROJECT_ROOT, "assets", "font", "RobotoCondensed-Bold.ttf")
        has_font = font_path and os.path.exists(font_path)
        
        wrapped_lines = []
        try:
            font_size = int(source.get("text_size", 65))
        except:
            font_size = 65
            
        try:
            text_y1_val = float(source.get("text_y1", 0))
            if text_y1_val > 0:
                start_y = int(1920 * text_y1_val)
            else:
                start_y = 1920 - 690
        except:
            start_y = 1920 - 690 
        line_spacing = int(font_size * 1.2)
        
        if has_font and hook_text:
            safe_text = str(hook_text).replace("'", "").replace(":", "\\:").replace("%", "\\%").strip().upper()
            max_width_px = 950
            avg_char_width = font_size * 0.55
            max_chars = int(max_width_px / avg_char_width)
            wrapped_lines = textwrap.wrap(safe_text, width=max_chars)
            
            try: text_x_val = int(source.get("text_x", 65))
            except: text_x_val = 65
            
            try: text_color_val = source.get("text_color", "white").strip()
            except: text_color_val = "white"
            if not text_color_val: text_color_val = "white"
            
            for i, line in enumerate(wrapped_lines):
                y_pos = start_y + (i * line_spacing)
                # Text hiển thị xuyên suốt video
                draw_filter = (
                    f"drawtext=fontfile='{font_path}':text='{line}':"
                    f"fontsize={font_size}:fontcolor={text_color_val}:bordercolor=black:borderw=3:"
                    f"shadowcolor=black:shadowx=3:shadowy=3:x={text_x_val}:y={y_pos}"
                )
                filters.append(f"{current}{draw_filter}[vout{i}]")
                current = f"[vout{i}]"

        noise_lvl = round(random.uniform(1.0, 2.0), 1)
        filters.append(f"{current}noise=alls={noise_lvl}:allf=t+u[vout]")

                # Map audio
        import glob
        def _get_random_bgm(tone_name):
            bgm_dir = os.path.join(PROJECT_ROOT, "assets", "bgm")
            if not os.path.exists(bgm_dir): return None
            safe_tone = tone_name.lower().replace(" ", "_").replace("à", "a").replace("á", "a").replace("ẹ", "e").replace("ể", "e").replace("ồ", "o").replace("ộ", "o").replace("ị", "i").replace("í", "i").replace("ũ", "u").capitalize()
            files = glob.glob(os.path.join(bgm_dir, f"{safe_tone}_*.mp3")) + glob.glob(os.path.join(bgm_dir, f"{safe_tone}_*.wav"))
            if not files:
                files = glob.glob(os.path.join(bgm_dir, "*.mp3")) + glob.glob(os.path.join(bgm_dir, "*.wav"))
            return random.choice(files) if files else None

        bgm_path = _get_random_bgm(tone)
        
        has_audio = False
        try:
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", source_video], capture_output=True, text=True)
            has_audio = bool(probe.stdout.strip())
        except: pass

        if main_audio_idx is not None:
            main_audio = f"[{main_audio_idx}:a]"
        elif has_audio:
            main_audio = "[0:a]"
        else:
            main_audio = None

        if bgm_path:
            inputs += ["-stream_loop", "-1", "-i", bgm_path]
            bgm_idx = input_idx
            input_idx += 1
            if main_audio:
                filters.append(f"{main_audio}volume=1.0[a_main];[{bgm_idx}:a]volume=0.20[a_bgm];[a_main][a_bgm]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-14:LRA=11:TP=-1.5[aout]")
                audio_map = "[aout]"
            else:
                filters.append(f"[{bgm_idx}:a]volume=0.20,loudnorm=I=-14:LRA=11:TP=-1.5[aout]")
                audio_map = "[aout]"
        else:
            if main_audio:
                filters.append(f"{main_audio}loudnorm=I=-14:LRA=11:TP=-1.5[aout]")
                audio_map = "[aout]"
            else:
                inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
                audio_map = f"{input_idx}:a"
                input_idx += 1

        cmd = ["ffmpeg", "-y"] + inputs
        cmd += ["-filter_complex", ";".join(filters), "-map", "[vout]"]
        cmd += ["-map", f"{audio_map}"]
        
        if audio_dur > 0:
            cmd += ["-t", str(audio_dur + 0.2)]
            
        # Dùng -shortest để dự phòng
        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-threads", "0", "-r", "30",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest", final_path]

        print(f"         Tạo video CÓ FRAME (1 pass: Voice full + loop video)...")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if res.returncode != 0:
                print(f"         ⚠️ FFmpeg lỗi: {res.stderr}")
            else:
                try:
                    with open(final_path, "ab") as f:
                        f.write(os.urandom(random.randint(20, 100)))
                except Exception as e:
                    pass
        except Exception as e:
            print(f"         ⚠️ FFmpeg lỗi exception: {e}")

        if not os.path.exists(final_path):
            import shutil
            shutil.copy2(source_video, final_path)
            print(f"         ℹ️ Dùng video gốc (FFmpeg thất bại)")

        if os.path.exists(final_path):
            size_mb = os.path.getsize(final_path) / 1024 / 1024
            print(f"         ✅ Video CÓ FRAME: {size_mb:.1f}MB")

        # (Đã loại bỏ subtitle cho chế độ Facebook, chỉ giữ lại trên Article Video)

        return final_path

    # ═══════════════════════════════════════════════════
    #  MODE 2: KHÔNG FRAME (trong video_remix)
    #  → Đoạn đầu: video gốc (mute) + hook voice + frame + logo
    #  → Đoạn sau: video gốc (giữ audio gốc) + logo
    #  → Logo xuyên suốt toàn bộ video
    # ═══════════════════════════════════════════════════
    def _edit_video_no_frame(self, source_video, hook_voice_path, hook_text,
                              work_dir, job_id, source, tone="Trung tính"):
        # 3 PASS: Intro (có frame/text) -> Body (video gốc từ 0s) -> Concat
        final_path = os.path.join(work_dir, f"final_{job_id}.mp4")
        temp_intro = os.path.join(work_dir, f"intro_{job_id}.mp4")
        temp_body = os.path.join(work_dir, f"body_{job_id}.mp4")
        concat_txt = os.path.join(work_dir, f"concat_{job_id}.txt")

        def download_asset_safe(folder, filename):
            if not filename or filename == "-- Trống --":
                return None
            if os.path.isabs(filename):
                return filename if os.path.exists(filename) else None
            local_dir = os.path.join(PROJECT_ROOT, "assets", folder)
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, filename)
            if not os.path.exists(local_path):
                print(f"      📥 Đang tải {filename} từ Supabase Storage...")
                from shared.services.supabase_api import SupabaseAPI
                SupabaseAPI.download_asset("assets", folder, local_dir, filename)
            return local_path if os.path.exists(local_path) else None

        hook_duration = 5.0
        has_hook_voice = hook_voice_path and os.path.exists(hook_voice_path)
        if has_hook_voice:
            d = _get_duration(hook_voice_path)
            if d > 0: hook_duration = d + 0.5

        is_tele_bot = source.get("is_telegram_bot", False)
        
        raw_title_frame = source.get("title_frame_path")
        title_frame_path = download_asset_safe("frame", raw_title_frame) if is_tele_bot else (raw_title_frame if raw_title_frame else FRAME_PATH)
        
        raw_logo = source.get("logo_path")
        logo_path = download_asset_safe("logo", raw_logo) if is_tele_bot else (raw_logo if raw_logo else LOGO_PATH)
        
        has_frame = title_frame_path and os.path.exists(title_frame_path)
        has_logo = False # Tắt lắp logo
        is_horiz = _is_horizontal(source_video)

        import random
        contrast = round(random.uniform(0.97, 1.03), 3)
        saturation = round(random.uniform(0.97, 1.03), 3)
        brightness = round(random.uniform(-0.03, 0.03), 3)
        eq_filter = f",eq=contrast={contrast}:saturation={saturation}:brightness={brightness}"

        # Auto-detect logo/watermark regions (run once, used for both intro & body)
        _logo_regions = []
        try:
            from shared.modules.logo_detector import detect_logo_regions
            _logo_regions = detect_logo_regions(source_video)
            if _logo_regions:
                print(f"   🔍 Phát hiện {len(_logo_regions)} vùng logo → tự động blur")
        except Exception as _le:
            print(f"   ⚠️ Logo detection lỗi: {_le}")
        _bg_init = "[bg_pre]" if _logo_regions else "[bg]"

        # Cài đặt chung FFmpeg để đảm bảo đồng bộ khi concat
        COMMON_VIDEO = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-video_track_timescale", "90000", "-preset", "fast", "-crf", "18", "-threads", "0"]
        COMMON_AUDIO = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]

        # Kiểm tra video gốc có audio không
        has_audio = False
        try:
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", source_video], capture_output=True, text=True)
            has_audio = bool(probe.stdout.strip())
        except: pass

        print(f"         Tạo video KHÔNG FRAME - Bước 1: Dựng Intro (Độ dài: {hook_duration}s)...")
        # 1. DỰNG INTRO (Dùng đoạn đầu của video, cắt đúng hook_duration)
        intro_inputs = ["-stream_loop", "-1", "-i", source_video]
        if has_hook_voice: intro_inputs += ["-i", hook_voice_path]
        else: intro_inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        if has_frame: intro_inputs += ["-i", title_frame_path]
        if has_logo: intro_inputs += ["-i", logo_path]

        intro_filters = []
        if is_horiz:
            intro_filters.extend([
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:2[bg_blur]",
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease{eq_filter}[fg]",
                f"[bg_blur][fg]overlay=(W-w)/2:(H-h)/2-150{_bg_init}"
            ])
        else:
            intro_filters.append(f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:100{eq_filter}{_bg_init}")
        if _logo_regions:
            intro_filters.extend(_build_logo_blur_chain("[bg_pre]", _logo_regions))
        curr_intro = "[bg]"
        in_idx = 2
        
        if has_frame:
            intro_filters.append(f"[{in_idx}:v]scale=1080:1920[frame];{curr_intro}[frame]overlay=0:0[v_f]")
            curr_intro = "[v_f]"
            in_idx += 1
            
        if has_logo:
            intro_filters.append(f"[{in_idx}:v]scale=1080:1920[logo];{curr_intro}[logo]overlay=0:0[v_l]")
            curr_intro = "[v_l]"
            
        import textwrap
        raw_font = source.get("font_path")
        font_path = download_asset_safe("font", raw_font) if is_tele_bot else raw_font
        if not font_path or not os.path.exists(font_path):
            font_path = os.path.join(PROJECT_ROOT, "assets", "font", "RobotoCondensed-Bold.ttf")
        has_font = font_path and os.path.exists(font_path)
        
        if has_font and hook_text:
            safe_text = str(hook_text).replace("'", "").replace(":", "\\:").replace("%", "\\%").strip().upper()
            try:
                font_size = int(source.get("text_size", 65))
            except:
                font_size = 65
                
            try:
                text_y1_val = float(source.get("text_y1", 0))
                if text_y1_val > 0:
                    start_y = int(1920 * text_y1_val)
                else:
                    start_y = 1920 - 690
            except:
                start_y = 1920 - 690
            max_chars = int(950 / (font_size * 0.55))
            wrapped_lines = textwrap.wrap(safe_text, width=max_chars)
            line_spacing = int(font_size * 1.2)
            
            for i, line in enumerate(wrapped_lines):
                y_pos = start_y + (i * line_spacing)
                draw_filter = f"drawtext=fontfile='{font_path}':text='{line}':fontsize={font_size}:fontcolor=white:bordercolor=black:borderw=3:shadowcolor=black:shadowx=3:shadowy=3:x=65:y={y_pos}"
                intro_filters.append(f"{curr_intro}{draw_filter}[vt{i}]")
                curr_intro = f"[vt{i}]"

        noise_lvl = round(random.uniform(1.0, 2.0), 1)
        intro_filters.append(f"{curr_intro}noise=alls={noise_lvl}:allf=t+u[vout]")
        intro_filters.append("[1:a]loudnorm=I=-14:LRA=11:TP=-1.5[aout]")

        cmd_intro = ["ffmpeg", "-y"] + intro_inputs + ["-filter_complex", ";".join(intro_filters), "-map", "[vout]", "-map", "[aout]", "-t", str(hook_duration)] + COMMON_VIDEO + COMMON_AUDIO + [temp_intro]
        try:
            subprocess.run(cmd_intro, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            print(f"❌ Lỗi render Intro: {e.stderr}")

        print(f"         Tạo video KHÔNG FRAME - Bước 2: Dựng Body (Full video gốc từ 0:00)...")
        # 2. DỰNG BODY (từ giây 0 của video gốc, center, không frame/text)
        body_inputs = ["-i", source_video]
        src_dur = _get_duration(source_video)
        if not has_audio: 
            d_str = f":d={src_dur}" if src_dur > 0 else ""
            body_inputs += ["-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100{d_str}"]
        if has_logo: body_inputs += ["-i", logo_path]

        body_filters = []
        if is_horiz:
            body_filters.extend([
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:2[bg_blur]",
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease{eq_filter}[fg]",
                f"[bg_blur][fg]overlay=(W-w)/2:(H-h)/2{_bg_init}"
            ])
        else:
            body_filters.append(f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2{eq_filter}{_bg_init}")
        if _logo_regions:
            body_filters.extend(_build_logo_blur_chain("[bg_pre]", _logo_regions))
        curr_body = "[bg]"
        in_idx = 2 if not has_audio else 1
        
        if has_logo:
            body_filters.append(f"[{in_idx}:v]scale=1080:1920[logo];{curr_body}[logo]overlay=0:0[v_l]")
            curr_body = "[v_l]"

        noise_lvl2 = round(random.uniform(1.0, 2.0), 1)
        body_filters.append(f"{curr_body}noise=alls={noise_lvl2}:allf=t+u[vout]")
        
        audio_map = "0:a" if has_audio else "1:a"
        body_filters.append(f"[{audio_map}]loudnorm=I=-14:LRA=11:TP=-1.5[aout]")
        audio_map = "[aout]"
        
        cmd_body = ["ffmpeg", "-y"] + body_inputs + ["-filter_complex", ";".join(body_filters), "-map", "[vout]", "-map", audio_map] + COMMON_VIDEO + COMMON_AUDIO + ["-shortest", temp_body]
        
        try:
            subprocess.run(cmd_body, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            print(f"❌ Lỗi render Body: {e.stderr}")

        print(f"         Tạo video KHÔNG FRAME - Bước 3: Ghép nối (Concat)...")
        # 3. CONCAT
        with open(concat_txt, "w") as f:
            if os.path.exists(temp_intro): f.write(f"file '{temp_intro}'\n")
            if os.path.exists(temp_body): f.write(f"file '{temp_body}'\n")
            
        cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", final_path]
        try:
            subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            print(f"❌ Lỗi Concat: {e.stderr}")
        
        try:
            os.remove(temp_intro)
            os.remove(temp_body)
            os.remove(concat_txt)
        except: pass
        
        # Bơm rác đổi MD5
        try:
            with open(final_path, "ab") as f:
                f.write(os.urandom(random.randint(20, 100)))
        except: pass
        
        # Fallback
        if not os.path.exists(final_path):
            import shutil
            shutil.copy2(source_video, final_path)
            print(f"         ℹ️ Dùng video gốc (FFmpeg thất bại)")

        if os.path.exists(final_path):
            size_mb = os.path.getsize(final_path) / 1024 / 1024
            print(f"         ✅ Video NO FRAME: {size_mb:.1f}MB")
            
        return final_path

    # ═══════════════════════════════════════════════════
    #  SUPABASE HELPERS
    # ═══════════════════════════════════════════════════
    def _get_active_sources(self) -> list:
        try:
            result = supabase.table("facebook_sources") \
                .select("*").eq("is_active", True) \
                .order("created_at").execute()
            return result.data or []
        except Exception as e:
            print(f"❌ Lỗi load sources: {e}")
            return []

    def _update_scan_time(self, source_id: str, last_video_id: str = None):
        try:
            update = {"last_scan_at": datetime.now(timezone.utc).isoformat()}
            if last_video_id:
                update["last_video_id"] = last_video_id
            supabase.table("facebook_sources").update(update).eq("id", source_id).execute()
        except:
            pass

    def _insert_video_record(self, source_id: str, video: dict, dl: dict, ai_result: dict, final_path: str) -> str | None:
        try:
            result = supabase.table("facebook_videos").insert({
                "source_id": source_id,
                "facebook_video_id": video.get("video_id"),
                "original_url": video["url"],
                "caption": video.get("caption", "")[:500],
                "status": "completed",
                "file_hash": dl.get("hash"),
                "file_size_bytes": dl.get("size"),
                "downloaded_path": dl.get("path"),
                "ai_title": ai_result.get("title_tiktok", ""),
                "ai_script": ai_result.get("script_voice", ""),
                "processed_path": final_path,
            }).execute()
            return result.data[0]["id"] if result.data else None
        except Exception as e:
            if "23505" in str(e):
                return None
            print(f"      ⚠️ DB insert lỗi: {e}")
            return None

    def _check_hash_exists(self, file_hash: str) -> bool:
        try:
            result = supabase.table("facebook_videos") \
                .select("id").eq("file_hash", file_hash).limit(1).execute()
            return bool(result.data)
        except:
            return False


# ═══════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Facebook News Auto Remix Pipeline")
    parser.add_argument("command", nargs="?", default="run-once",
                       choices=["run-once", "start", "login"],
                       help="run-once: chạy 1 lần | start: chạy liên tục | login: login Facebook")
    parser.add_argument("--interval", type=int, default=30,
                       help="Khoảng cách giữa các lần quét (phút)")
    args = parser.parse_args()

    if args.command == "login":
        from fb_crawler import login_facebook_interactive
        login_facebook_interactive()
        return

    pipeline = FBNewsPipeline()

    if args.command == "run-once":
        pipeline.run()
    elif args.command == "start":
        print(f"⏱️ Chạy liên tục, quét mỗi {args.interval} phút")
        while True:
            pipeline.run()
            print(f"\n📅 Đợi {args.interval} phút...\n")
            time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
