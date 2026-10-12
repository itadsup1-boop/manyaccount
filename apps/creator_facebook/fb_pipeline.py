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
from shared.services.tts_api import create_voice_full_pipeline, probe_audio_duration
from shared.core.channel_editorial import (
    TARGET_VIDEO_DURATION_SECONDS,
    TARGET_VOICE_SPEED,
    get_channel_voice_speed,
)
from shared.core.content_repair import (
    prepare_content_with_single_repair,
    summarize_validation,
)
from shared.core.prompt_builder import get_content_profile
from shared.core.evidence_guard import (
    EVIDENCE_GUARD_ENABLED,
    guard_evidence,
    summarize_evidence,
)
from shared.core.rights_guard import guard_source_rights
from shared.core.visual_grounding import guard_visual_grounding, summarize_visual_grounding
from shared.core.social_evidence import build_social_evidence_pack
from shared.core.social_quality_gate import evaluate_social_quality, summarize_social_quality
from shared.core.source_ranker import rank_candidates, should_process_candidate
from shared.core.pipeline_state import PipelineLifecycle, PipelineStageError
from shared.core.quality_log import append_quality_event
from shared.core.video_qa import run_video_qa
from shared.core.safe_zone import plan_text_layout
from shared.core.beat_timeline import plan_beat_timeline, resolve_intro_overlay_text
from shared.core.video_encoding import (
    CLEAN_METADATA_ARGS,
    build_color_filter,
    final_output_args,
    resolve_color_grade,
)
from shared.services.music_selector import build_ducked_mix_filter, select_music
from shared.services.audio_director import plan_audio_cues
from shared.core.ffmpeg_utils import ffprobe_command, resolve_ffmpeg_binary
from shared.modules.subtitle_renderer import (
    generate_text_ass,
    generate_word_ass,
    get_subtitle_preset,
)

# Import từ fb-news-pipeline
from fb_crawler import crawl_facebook_videos
from fb_downloader import download_video
from facebook_pipeline.hook_mode import prepare_hook_content
from facebook_pipeline.group_review import stage_group_review
from facebook_pipeline.source_repository import (
    claim_video_record,
    file_hash_exists,
    finalize_video_record,
    insert_video_record,
    load_active_sources,
    normalize_source_scope,
    update_scan_checkpoint,
    video_id_exists,
)
from facebook_pipeline.source_config import (
    EDIT_MODE_HOOK_THEN_ORIGINAL,
    SOURCE_TYPE_GROUP,
)

FFMPEG_BINARY = resolve_ffmpeg_binary()
from shared.core.ai_provider_factory import analyze_video_content, get_configured_ai_provider
from fb_sheet_api import save_fb_to_sheet, update_fb_finished_time, update_fb_drive_link, update_fb_status, update_fb_status_m

TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Đọc config từ .env
def _env(key, default=""):
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        # Bắt buộc UTF-8: mặc định của Windows là cp1252 nên chỉ cần .env có
        # một ký tự tiếng Việt (kể cả trong dòng ghi chú) là toàn bộ pipeline
        # crash ngay khi import.
        with open(env_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    return default

# ID cu "cb6f4c6a-..." khong con ton tai tren server voice.adsup.vn (API tra
# 400 "not found") - da xac minh va doi sang ID con hoat dong that.
VOICE_PROFILE_ID = _env("VOICEBOX_PROFILE_ID", "3fb3db24-b0af-4db4-b75f-b897f0431843")
GDRIVE_FOLDER_ID = _env("DRIVE_FOLDER_ID", _env("GDRIVE_FOLDER_ID", "1VgkkbUJ82kxzWXJH8cfn7UFMMFBKQkzS"))

# Logo/frame paths
LOGO_PATH = os.path.join(PROJECT_ROOT, "assets", "logo.png")
FRAME_PATH = os.path.join(PROJECT_ROOT, "assets", "frame.png")
FACEBOOK_DEFAULT_TARGET_CHANNEL = "Adsupnews"
# Social source videos keep their original visual treatment. Karaoke captions
# are reserved for the article pipeline, which uses article_ffmpeg.py.
FACEBOOK_KARAOKE_SUBTITLES_ENABLED = False


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


def _append_quality_log(
    pipeline: str,
    source_name: str,
    quality_score: int,
    status: str,
    reason: str = "",
    **metadata,
):
    """Ghi 1 dòng JSON vào quality_log.jsonl để Telegram bot đọc báo cáo."""
    try:
        append_quality_event(
            pipeline,
            source_name,
            quality_score,
            status,
            reason,
            log_path=QUALITY_LOG_PATH,
            **metadata,
        )
    except Exception:
        pass


def _get_source_target_channel(source: dict) -> str:
    value = str(source.get("id_tiktok") or "").strip()
    return value or FACEBOOK_DEFAULT_TARGET_CHANNEL


def load_channel_text_config(channel_id: str) -> dict:
    """Đọc cấu hình chữ của kênh tại assets/channels/<kênh>/config.json.

    Bảng ``facebook_sources`` không có cột text_x/text_y1/text_size…, nên nếu
    chỉ đọc từ record nguồn thì mọi thiết lập vị trí chữ mà operator đặt trên
    Web Hub đều bị bỏ qua và video luôn dùng giá trị mặc định.
    """
    clean_id = str(channel_id or "").strip()
    if not clean_id:
        return {}
    config_path = os.path.join(
        PROJECT_ROOT, "assets", "channels", clean_id, "config.json"
    )
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            data = json.load(config_file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_text_settings(source: dict, channel_id: str) -> dict:
    """Gộp cấu hình chữ: cấu hình kênh làm nền, record nguồn ghi đè nếu có."""
    merged = dict(load_channel_text_config(channel_id))
    for key, value in (source or {}).items():
        if key.startswith("text_") and value not in (None, ""):
            merged[key] = value
    return merged


def resolve_title_layout_box(text_cfg: dict) -> tuple[int, int]:
    """Return (max width, absolute X) used by the Facebook title renderer.

    The Web Hub stores ``text_w`` as a fraction of the 1080px canvas and
    ``text_x`` as the absolute left coordinate. Keeping this conversion in
    one place makes the drag preview and FFmpeg output use the same geometry.
    """
    try:
        width_ratio = float(text_cfg.get("text_w", 950 / 1080))
    except (TypeError, ValueError):
        width_ratio = 950 / 1080
    width_ratio = max(0.35, min(0.95, width_ratio))
    max_width = max(320, min(1020, int(round(1080 * width_ratio))))
    try:
        text_x = int(text_cfg.get("text_x", 65))
    except (TypeError, ValueError):
        text_x = 65
    return max_width, text_x


def _get_duration(file_path: str) -> float:
    """Lấy duration file media bằng ffprobe"""
    try:
        result = subprocess.run(
            ffprobe_command("-v", "quiet", "-show_entries", "format=duration",
                            "-of", "csv=p=0", file_path),
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except:
        return 0.0

def _is_horizontal(file_path: str) -> bool:
    """Kiểm tra xem video có phải là video ngang không (width > height)"""
    try:
        result = subprocess.run(
            ffprobe_command("-v", "quiet", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", file_path),
            capture_output=True, text=True, timeout=10
        )
        w, h = map(int, result.stdout.strip().split('x'))
        return w > h
    except:
        return False


class FBNewsPipeline:
    def __init__(self, source_scope="page"):
        os.makedirs(TEMP_DIR, exist_ok=True)
        self.source_scope = normalize_source_scope(source_scope)
        self.stats = {"scanned": 0, "new": 0, "completed": 0, "failed": 0}

    # ═══════════════════════════════════════════════════
    #  CHẠY PIPELINE 1 LẦN
    # ═══════════════════════════════════════════════════
    def run(self):
        self.stats = {"scanned": 0, "new": 0, "completed": 0, "failed": 0}

        print("═" * 55)
        scope_label = {
            "page": "PAGE",
            "group": "GROUP",
            "all": "PAGE + GROUP",
        }[self.source_scope]
        print(f"  🚀 BẮT ĐẦU PIPELINE FACEBOOK {scope_label}")
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
        source_type = source["source_type"]
        edit_mode = source["edit_mode"]
        max_videos = source["max_videos_per_scan"]
        max_age_hours = int(source.get("max_video_age_hours") or 0)

        print(f"\n📡 ── {name} ──")
        print(f"   URL: {url}")
        print(
            f"   Loại: {source_type} | Mode: {edit_mode} | "
            f"Tối đa: {max_videos} bài"
        )
        print(f"   Last video: {last_vid or '(chưa có)'}")
        self.stats["scanned"] += 1

        # BƯỚC 1: Group chỉ trả về bài thuộc đúng nhóm và có native video.
        all_videos = crawl_facebook_videos(
            url,
            max_videos=max_videos,
            source_type=source_type,
            max_age_hours=max_age_hours,
        )

        if not all_videos:
            print("   💤 Không cào được video nào.")
            self._update_scan_time(source)
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
            self._update_scan_time(source)
            return

        print(f"   ✨ {len(new_videos)} video MỚI")
        self.stats["new"] += len(new_videos)

        # BƯỚC 3: Xếp hạng rẻ bằng metadata rồi mới download/gọi AI.
        target_tiktok_id = _get_source_target_channel(source)
        editorial_profile = get_content_profile(
            target_tiktok_id,
            source.get("extra_content", ""),
        )
        ranked_videos = rank_candidates(
            new_videos,
            editorial_profile,
            source_type="facebook",
        )
        handled_ids = set()

        for i, video in enumerate(ranked_videos, 1):
            source_rank = video.get("source_rank", {})
            print(f"\n   ▶️ Video {i}/{len(ranked_videos)}: [{video['video_id']}]")
            print(f"      Caption: {video['caption'][:80]}...")
            print(
                f"      🧭 SourceRanker: {source_rank.get('total_score', 0)}/100 "
                f"({source_rank.get('status', 'unscored')})"
            )

            if not should_process_candidate(video):
                print("      ⏭️ SourceRanker loại video không phù hợp kênh.")
                handled_ids.add(video["video_id"])
                continue

            if self._check_video_id_exists(source, video["video_id"]):
                print("      ⏭️ Bài/video đã xử lý trước đó → bỏ qua.")
                handled_ids.add(video["video_id"])
                continue

            rights = guard_source_rights(video, source)
            if not rights.passed:
                print(f"      ⛔ RightsGuard chặn: {' '.join(rights.errors)}")
                handled_ids.add(video["video_id"])
                continue
            if rights.requires_review:
                print(f"      ⚠️ RightsGuard: {' '.join(rights.warnings)}")

            # Claim sau các kiểm tra rẻ, trước download/render/upload để hai
            # lượt chạy không thể cùng tạo ra hai file cho một video.
            record_id = None
            if not source.get("is_telegram_bot"):
                record_id = self._claim_video_record(source, video)
                if not record_id:
                    print("      ⏭️ Video vừa được tiến trình khác claim → bỏ qua.")
                    handled_ids.add(video["video_id"])
                    continue

            result = self._process_one_video(
                video, source, rights=rights, record_id=record_id
            )

            if result is True or result == "pending_review":
                self.stats["completed"] += 1
                handled_ids.add(video["video_id"])
            elif result in {"skip", "duplicate"}:
                handled_ids.add(video["video_id"])
            else:
                self.stats["failed"] += 1

        # BƯỚC 4: Cập nhật last_video_id
        latest_done_id = None
        if new_videos and len(handled_ids) == len(new_videos):
            latest_done_id = new_videos[0]["video_id"]
        elif handled_ids:
            print(
                "   ⚠️ Chưa cập nhật checkpoint vì còn video lỗi; "
                "lần sau sẽ quét lại để tránh bỏ sót."
            )
        self._update_scan_time(source, latest_done_id)
        if latest_done_id:
            print(f"   ☁️ last_video_id = {latest_done_id}")

    # ═══════════════════════════════════════════════════
    #  XỬ LÝ 1 VIDEO
    # ═══════════════════════════════════════════════════
    def _process_one_video(self, video: dict, source: dict, rights=None, on_success=None, on_error=None, record_id=None) -> bool:
        if rights is None:
            rights = guard_source_rights(video, source)

        job_id = uuid.uuid4().hex[:8]
        work_dir = os.path.join(TEMP_DIR, f"job_{job_id}")
        os.makedirs(work_dir, exist_ok=True)
        lifecycle = PipelineLifecycle("facebook", video.get("url", ""))
        quality_score = 0
        qa_result = None

        try:
            if record_id is None and not source.get("is_telegram_bot"):
                record_id = self._claim_video_record(source, video)
                if not record_id:
                    print("      ⏭️ Video đã được claim/xử lý trước đó → bỏ qua.")
                    return "duplicate"

            caption = video.get("caption", "").strip()
            edit_mode = source.get("edit_mode", "")
            hook_then_original = edit_mode == EDIT_MODE_HOOK_THEN_ORIGINAL

            # ── [1/6] Download video ──
            print(f"      📥 [1/6] Download...")
            dl = download_video(
                video["url"],
                video["video_id"],
                source_type=source.get("source_type", "page"),
            )
            if not dl:
                raise PipelineStageError(
                    "selected",
                    "SOURCE_DOWNLOAD_FAILED",
                    "Không tải được video nguồn. Với TikTok, đã thử TikWM và yt-dlp; "
                    "hãy kiểm tra lại link hoặc thử lại sau.",
                )

            if self._check_hash_exists(dl["hash"], source):
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

            # ── [2/6] AI Provider phân tích ──
            active_provider = get_configured_ai_provider().upper()
            print(f"      🤖 [2/6] {active_provider} phân tích video...")
            target_tiktok_id = _get_source_target_channel(source)
            operator_instruction = source.get("extra_content", "")
            evidence_pack = build_social_evidence_pack(
                source_type="facebook",
                source_url=video.get("url", ""),
                caption=caption,
                metadata={**video, **dl},
            )
            ai_result = analyze_video_content(
                dl["path"], 
                caption, 
                is_tele_bot=source.get("is_telegram_bot", False),
                extra_content=operator_instruction,
                profile_id=target_tiktok_id,
                edit_mode=edit_mode,
            )

            if not ai_result:
                print(f"      ℹ️ AI không khả dụng — dùng caption gốc")
                ai_result = {
                    "title_tiktok": caption[:100],
                    "hook": caption[:80],
                    "script_voice": caption[:200],
                    "main_idea": caption[:150],
                    "have_frame": False,
                    "detected_competitor_frame_end_sec": None,
                    "should_make_video": True,
                    "scenes": [],
                }
            lifecycle.advance("scripted")

            editorial_profile = get_content_profile(
                target_tiktok_id,
                operator_instruction,
            )
            if hook_then_original:
                prepared_content = prepare_hook_content(
                    ai_result,
                    caption=caption,
                    channel_id=target_tiktok_id,
                    source_url=video["url"],
                )
            else:
                prepared_content = prepare_content_with_single_repair(
                    ai_result,
                    source_type="facebook",
                    channel_id=target_tiktok_id,
                    source_url=video["url"],
                    profile=editorial_profile,
                    repair_callback=lambda instruction: analyze_video_content(
                        dl["path"],
                        caption,
                        is_tele_bot=source.get("is_telegram_bot", False),
                        extra_content=operator_instruction,
                        profile_id=target_tiktok_id,
                        repair_instruction=instruction,
                        edit_mode=edit_mode,
                    ),
                )
            ai_result = prepared_content.content
            if prepared_content.repair_attempts:
                repair_status = "đạt" if prepared_content.repaired else "chưa đạt"
                print(f"      🔧 Đã sửa kịch bản 1 lần: {repair_status}.")

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

            if not prepared_content.report.passed:
                validation_reason = summarize_validation(prepared_content.report)
                print(
                    f"      ⏭️ ContentValidator không đạt → skip. "
                    f"{validation_reason}"
                )
                _append_quality_log(
                    "facebook",
                    source.get("source_name", ""),
                    int(ai_result.get("quality_score", 0)),
                    "skip",
                    validation_reason,
                )
                return "skip"
            print(
                f"      ✅ ContentValidator: "
                f"{prepared_content.report.content_score}/100"
            )

            evidence_report = guard_evidence(
                ai_result,
                source_type="facebook",
                source_url=video["url"],
                source_text=evidence_pack.source_text,
                profile=editorial_profile,
            )
            if not EVIDENCE_GUARD_ENABLED:
                print("      ⏭️ EvidenceGuard đã tắt; tiếp tục xử lý video.")
            elif not evidence_report.passed:
                evidence_reason = summarize_evidence(evidence_report)
                print(f"      ⏭️ EvidenceGuard không đạt → skip. {evidence_reason}")
                _append_quality_log(
                    "facebook",
                    source.get("source_name", ""),
                    int(ai_result.get("quality_score", 0)),
                    "skip",
                    evidence_reason,
                )
                return "skip"
            else:
                print(f"      ✅ EvidenceGuard: {evidence_report.score}/100")

            visual_report = guard_visual_grounding(
                ai_result,
                source_type="facebook",
                source_text=evidence_pack.source_text,
            )
            if not visual_report.passed:
                visual_reason = summarize_visual_grounding(visual_report)
                print(f"      ⏭️ VisualGrounding không đạt → skip. {visual_reason}")
                _append_quality_log(
                    "facebook",
                    source.get("source_name", ""),
                    int(ai_result.get("quality_score", 0)),
                    "skip",
                    visual_reason,
                )
                return "skip"
            print(f"      ✅ VisualGrounding: {visual_report.score}/100")

            # Quality gate: bỏ qua video chất lượng thấp
            social_report = evaluate_social_quality(
                ai_result,
                source_type="facebook",
                validation_report=prepared_content.report,
                evidence_report=evidence_report,
                visual_report=visual_report,
                rights_report=rights,
                evidence_pack=evidence_pack.to_dict(),
                frame_mode=bool(ai_result.get("have_frame")),
                threshold=int(os.environ.get("SOCIAL_QUALITY_THRESHOLD", "70")),
            )
            if not social_report.passed and not source.get("is_telegram_bot"):
                social_reason = summarize_social_quality(social_report)
                print(f"      Social Quality Gate: {social_reason}")
                _append_quality_log(
                    "facebook",
                    source.get("source_name", ""),
                    int(ai_result.get("quality_score", 0)),
                    "skip",
                    social_reason,
                    editorial_score=social_report.score,
                    ai_quality_score=int(ai_result.get("quality_score", 0) or 0),
                    quality_breakdown=social_report.breakdown,
                )
                return "skip"
            quality_score = int(ai_result.get("quality_score", 5))
            skip_reason = ai_result.get("skip_reason", "")
            quality_threshold = int(os.environ.get("QUALITY_THRESHOLD", "6"))
            # Legacy AI self-score is retained for telemetry only; the social
            # gate above is the decision authority.
            if False and not source.get("is_telegram_bot") and quality_score < quality_threshold:
                print(f"      ⏭️ Quality score {quality_score}/10 dưới ngưỡng {quality_threshold} → skip. {f'Lý do: {skip_reason}' if skip_reason else ''}")
                _append_quality_log("facebook", source.get("source_name", ""), quality_score, "skip", skip_reason)
                return "skip"
            print(f"      ✅ Quality score: {quality_score}/10")
            lifecycle.advance("validated")
            _append_quality_log(
                "facebook", source.get("source_name", ""), quality_score,
                "validated", stage="validated", item_id=video.get("url", ""),
                source_url=video.get("url", ""),
                editorial_score=social_report.score,
                ai_quality_score=quality_score,
                quality_breakdown=social_report.breakdown,
            )

            hook = str(ai_result.get("hook", "") or "").strip()
            script_voice = str(ai_result.get("script_voice", "") or "").strip()
            
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
                            
            title = str(ai_result.get("title_tiktok", "") or "").strip()
            # Nếu provider không trả hook, vẫn phải đọc được câu mở đầu từ
            # tiêu đề thay vì âm thầm dựng intro im lặng.
            if not hook and title:
                hook = title
            have_frame = (
                False if hook_then_original else ai_result.get("have_frame", False)
            )
            tone = ai_result.get("tone", "Trung tính").strip()
            music_mood = ai_result.get("music_mood")
            music_energy = ai_result.get("music_energy", 2)
            is_sensitive = ai_result.get("is_sensitive", False)

            print(
                f"      📋 have_frame={have_frame} | tone={tone} | "
                f"music_mood={music_mood or 'auto'} | energy={music_energy}"
            )

            # Đọc Voice config chung từ global_voice_settings.json
            voice_config = {}
            settings_path = os.path.join(APP_DIR, "data", "global_voice_settings.json")
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, "r", encoding="utf-8") as fs:
                        voice_config = json.load(fs)
                except:
                    pass

            channel_voice_speed = get_channel_voice_speed(
                target_tiktok_id,
                story_type=ai_result.get("story_type", ""),
                tone=ai_result.get("tone", ""),
                is_sensitive=bool(ai_result.get("is_sensitive", False)),
            )
            channel_dir = os.path.join(PROJECT_ROOT, "assets", "channels", target_tiktok_id)
            channel_voice_path = os.path.join(channel_dir, "voice_config.json")
            try:
                if os.path.exists(channel_voice_path):
                    with open(channel_voice_path, "r", encoding="utf-8") as fs:
                        channel_voice_config = json.load(fs)
                    if isinstance(channel_voice_config, dict):
                        voice_config.update(channel_voice_config)
            except Exception as voice_config_error:
                print(f"      ⚠️ Không đọc được cấu hình voice kênh: {voice_config_error}")
            channel_voice_speed = TARGET_VOICE_SPEED

            # Chọn Voice ID dựa trên tone
            selected_voice_id = voice_config.get(tone)
            
            # Nếu không cấu hình giọng cho tone này, lùi về dùng giọng Trung tính
            if not selected_voice_id:
                selected_voice_id = voice_config.get("Trung tính")
                
            # Nếu chưa cấu hình cả giọng Trung tính, lùi về mặc định hệ thống
            if not selected_voice_id:
                selected_voice_id = VOICE_PROFILE_ID
                
            print(f"      🎵 Chọn Voice ID: {selected_voice_id} | Speed: {channel_voice_speed}")
            print(
                f"      📝 Hook voice: {len(hook.split())} từ, {len(hook)} ký tự | "
                f"Script voice: {len(script_voice.split())} từ, {len(script_voice)} ký tự | "
                f"Nội dung hook: {hook[:180]}"
            )

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
                        print(
                            f"      ✅ Hook voice OK: "
                            f"{os.path.getsize(hook_voice_path) / 1024:.0f}KB, "
                            f"{probe_audio_duration(hook_voice_path):.2f}s"
                        )
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
                        print(
                            f"      ✅ Script voice OK: "
                            f"{os.path.getsize(script_voice_path) / 1024:.0f}KB, "
                            f"{probe_audio_duration(script_voice_path):.2f}s"
                        )
                    else:
                        script_voice_path = None
                except Exception as e:
                    print(f"      ⚠️ Script voice lỗi: {e}")
            # Không được dựng video nếu một đoạn lời đã yêu cầu nhưng TTS
            # không tạo được. Trước đây nhánh KHÔNG FRAME vẫn đi tiếp với
            # anullsrc, nên người xem nghe được vài chữ hoặc hoàn toàn im ở
            # câu mở đầu.
            if hook and not hook_voice_path:
                raise PipelineStageError(
                    "voiced", "TTS_FAILED",
                    "Không tạo được hook voice; dừng trước khi dựng intro bị mất tiếng.",
                )
            if have_frame and script_voice and not script_voice_path:
                raise PipelineStageError(
                    "voiced", "TTS_FAILED",
                    "Không tạo được script voice cho video có frame.",
                )
            if have_frame and not hook_voice_path and not script_voice_path:
                raise PipelineStageError(
                    "voiced", "TTS_FAILED",
                    "Chế độ có frame nhưng không tạo được voice.",
                )
            if hook_then_original and not hook_voice_path:
                raise PipelineStageError(
                    "voiced",
                    "TTS_FAILED",
                    "Chế độ Hook + tiếng gốc bắt buộc phải tạo được voice hook.",
                )
            lifecycle.advance("voiced")

            # ── [4/6] Dựng video ──
            mode_name = "CÓ FRAME" if have_frame else "KHÔNG FRAME"
            print(f"      🎬 [4/6] Dựng video (mode: {mode_name})...")

            if have_frame:
                render_result = self._edit_video_with_frame(
                    source_video=dl["path"],
                    hook_voice_path=hook_voice_path,
                    script_voice_path=script_voice_path,
                    title=title, hook_text=hook,
                    work_dir=work_dir, job_id=job_id,
                    source=source, tone=tone,
                    music_mood=music_mood, music_energy=music_energy,
                    is_sensitive=is_sensitive, channel_id=target_tiktok_id,
                    beats=ai_result.get("beats"), script_text=script_voice,
                    subtitle_style=ai_result.get(
                        "subtitle_style", "keyword_highlight",
                    ),
                    frame_end_sec=ai_result.get(
                        "detected_competitor_frame_end_sec"
                    ),
                )
            else:
                render_result = self._edit_video_no_frame(
                    source_video=dl["path"],
                    hook_voice_path=hook_voice_path,
                    hook_text=hook or title,
                    title_text=title,
                    work_dir=work_dir, job_id=job_id,
                    source=source, tone=tone,
                    music_mood=music_mood, music_energy=music_energy,
                    is_sensitive=is_sensitive, channel_id=target_tiktok_id,
                    beats=ai_result.get("beats"),
                    preserve_full_source_audio=hook_then_original,
                    # Nguồn không có frame chỉ hiển thị hook trên intro;
                    # phần body là video nguồn, không lặp frame/text.
                    title_on_body=False,
                )

            final_path = (
                render_result.get("final_path")
                if isinstance(render_result, dict) else render_result
            )
            watermark_still_detected = (
                bool(render_result.get("watermark_detected"))
                if isinstance(render_result, dict) else False
            )

            if not final_path or not os.path.exists(final_path):
                render_error = (
                    render_result.get("error", "")
                    if isinstance(render_result, dict) else ""
                )
                raise PipelineStageError(
                    "rendered", "RENDER_FAILED",
                    "Renderer không tạo ra file MP4."
                    + (f" Chi tiết: {render_error}" if render_error else ""),
                )
            lifecycle.advance("rendered")

            subtitle_ass_path = os.path.join(work_dir, f"subtitle_{job_id}.ass")
            qa_result = run_video_qa(
                final_path,
                subtitle_ass_path=(
                    subtitle_ass_path if os.path.exists(subtitle_ass_path) else ""
                ),
                watermark_detected=watermark_still_detected,
            )
            real_blocking = [err for err in qa_result.blocking_errors if err != "WATERMARK_DETECTED"]
            if real_blocking:
                raise PipelineStageError(
                    "qa_passed",
                    real_blocking[0],
                    "VideoQA chặn upload: " + ", ".join(real_blocking),
                )
            if "WATERMARK_DETECTED" in qa_result.blocking_errors:
                print("         ⚠️ Cảnh báo: VideoQA phát hiện mảng watermark nghi vấn nhưng đã xử lý delogo/blur -> Cho phép upload.")
            lifecycle.advance("qa_passed")
            _append_quality_log(
                "facebook", source.get("source_name", ""), quality_score,
                "qa_passed", stage="qa_passed", item_id=video.get("url", ""),
                qa=qa_result.to_dict(),
            )

            # Group luôn dừng tại hàng chờ duyệt. Chưa upload Drive/Sheet.
            if source.get("source_type") == SOURCE_TYPE_GROUP:
                review_id = stage_group_review(
                    supabase,
                    source,
                    video,
                    dl,
                    ai_result,
                    final_path,
                )
                _append_quality_log(
                    "facebook_group",
                    source.get("source_name", ""),
                    quality_score,
                    "pending_review",
                    stage="pending_review",
                    item_id=video.get("url", ""),
                    review_id=review_id,
                    qa=qa_result.to_dict(),
                )
                print(f"      🕵️ Đã đưa vào hàng chờ duyệt: {review_id}")
                print("      ⛔ Chưa upload Google Drive/Google Sheet.")
                try:
                    if os.path.exists(work_dir):
                        shutil.rmtree(work_dir)
                    if dl.get("path") and os.path.exists(dl["path"]):
                        os.remove(dl["path"])
                    print("      ✅ Đã dọn file nguồn/tạm; giữ lại 1 MP4 chờ duyệt.")
                except Exception as cleanup_error:
                    print(f"      ⚠️ Dọn file tạm chưa hết: {cleanup_error}")
                return "pending_review"

            # ── [5/6] Upload Google Drive ──
            print(f"      ☁️ [5/6] Đang upload video lên Google Drive...")
            from shared.modules.upload_drive import upload_video_to_drive
            try:
                drive_link = upload_video_to_drive(final_path, GDRIVE_FOLDER_ID)
            except Exception as error:
                raise PipelineStageError(
                    "uploaded", "UPLOAD_FAILED", f"Lỗi upload Drive: {error}",
                ) from error
            if not drive_link:
                raise PipelineStageError(
                    "uploaded", "UPLOAD_FAILED",
                    "Upload video lên Google Drive thất bại hoặc link trống.",
                )
            lifecycle.advance("uploaded")
            _append_quality_log(
                "facebook", source.get("source_name", ""), quality_score,
                "uploaded", stage="uploaded", item_id=video.get("url", ""),
                qa=qa_result.to_dict(),
            )

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
                    update_fb_status(sheet_row, "uploaded")
                    if source.get("is_telegram_bot"):
                        update_fb_status_m(sheet_row, "đăng ngay lập tức")
                    update_fb_drive_link(sheet_row, drive_link)
                    update_fb_finished_time(sheet_row, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    print(f"      ✅ Đã đẩy link Drive vào Google Sheet dòng {sheet_row}")

            # 2. Hoàn tất claim đã đặt trước khi xử lý. Không insert mới ở
            # đây vì Drive có thể đã upload trước khi database trả lỗi.
            if record_id:
                self._finalize_video_record(
                    source, record_id, dl, ai_result, final_path
                )
                print(f"      ✅ Đã cập nhật record Supabase ID: {record_id}")

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
            failure = lifecycle.fail_from_exception(e)
            _append_quality_log(
                "facebook", source.get("source_name", ""), quality_score,
                "failed", stage=failure.stage, item_id=video.get("url", ""),
                error_code=failure.error_code, retryable=failure.retryable,
                message=failure.message,
                qa=qa_result.to_dict() if qa_result else None,
            )
            print(
                f"      ❌ {failure.error_code} ({failure.stage}): "
                f"{failure.message}"
            )
            import traceback
            traceback.print_exc()
            if on_error:
                on_error(
                    f"{failure.error_code} ({failure.stage}): {failure.message}"
                )
            return False

    # ═══════════════════════════════════════════════════
    #  MODE 1: CÓ FRAME
    #  → Giống TikTok: dùng video_remix.create_video_from_source_video
    #  → Intro: hook voice (cột E) + frame + logo + text
    #  → Body:  script voice (cột C) + frame + logo
    # ═══════════════════════════════════════════════════
    def _edit_video_with_frame(self, source_video, hook_voice_path, script_voice_path,
                                title, hook_text, work_dir, job_id, source, tone="Trung tính",
                                music_mood=None, music_energy=2, is_sensitive=False,
                                channel_id=None, beats=None, script_text="",
                                subtitle_style="keyword_highlight",
                                frame_end_sec=None):
        # Nếu AI phát hiện frame/logo của đối thủ kết thúc giữa video, chuyển
        # sang layout lai: intro có frame thương hiệu + Hook, phần còn lại là
        # video nguồn từ sau mốc cắt và giữ nguyên audio nguồn. Mốc AI là động
        # theo từng video; tool cộng thêm 1 giây để tránh cắt ngay sát frame.
        if frame_end_sec not in (None, ""):
            try:
                raw_frame_end = float(frame_end_sec)
            except (TypeError, ValueError):
                raw_frame_end = None
            if raw_frame_end is not None and raw_frame_end >= 0:
                source_duration = _get_duration(source_video)
                cut_time = min(source_duration, raw_frame_end + 1.0)
                print(
                    f"      🧭 Mốc frame đối thủ AI={raw_frame_end:.3f}s, "
                    f"cắt sau +1s={cut_time:.3f}s/{source_duration:.3f}s"
                )
                if source_duration > 0 and cut_time >= source_duration * (2 / 3):
                    print("      🖼️ Mốc cắt nằm sau 2/3 video → frame thương hiệu phủ xuyên suốt, giữ video nguồn")
                    return self._edit_video_frame_only(
                        source_video=source_video,
                        hook_voice_path=hook_voice_path,
                        script_voice_path=script_voice_path,
                        title=title,
                        work_dir=work_dir,
                        job_id=job_id,
                        source=source,
                        tone=tone,
                        music_mood=music_mood,
                        music_energy=music_energy,
                        is_sensitive=is_sensitive,
                        channel_id=channel_id,
                    )
                if source_duration > 0 and cut_time < source_duration:
                    print("      ✂️ Mốc cắt trước 2/3 video → intro frame + body nguồn sau mốc")
                    return self._edit_video_no_frame(
                        source_video=source_video,
                        hook_voice_path=hook_voice_path,
                        hook_text=hook_text,
                        title_text=title,
                        intro_overlay_text=title,
                        work_dir=work_dir,
                        job_id=job_id,
                        source=source,
                        tone=tone,
                        music_mood=music_mood,
                        music_energy=music_energy,
                        is_sensitive=is_sensitive,
                        channel_id=channel_id,
                        beats=beats,
                        preserve_full_source_audio=True,
                        title_on_body=False,
                        body_start_sec=cut_time,
                        disable_music=True,
                    )

        # NATIVE FFmpeg implementation cho chế độ CÓ FRAME
        # Sử dụng 1 pass duy nhất: Loop video gốc + chèn full script_voice
        
        final_path = os.path.join(work_dir, f"final_{job_id}.mp4")
        render_error = ""

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
                hook_duration = d

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
            subprocess.run([FFMPEG_BINARY, "-y", "-i", hook_voice_path, "-i", script_voice_path,
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
        render_duration = audio_dur if audio_dur > 0 else _get_duration(source_video)
        timeline = plan_beat_timeline(
            beats,
            total_duration=max(0.1, render_duration),
            hook_duration=hook_duration,
            media_count=1,
            hook_text=hook_text,
            script_text=script_text,
        )
        hook_text = resolve_intro_overlay_text(hook_text, timeline)
        print(
            f"      🧭 Beat timeline: {len(timeline.segments)} beats | "
            f"first frame: {hook_text}"
        )
            
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

        color_grade = resolve_color_grade(
            channel_id or "",
            tone=tone,
            is_sensitive=is_sensitive,
        )
        eq_filter = f",{build_color_filter(color_grade)}"
        print(f"      🎨 Color grade: {color_grade.name}")

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

        raw_font = source.get("font_path")
        font_path = download_asset_safe("font", raw_font) if is_tele_bot else raw_font
        if not font_path or not os.path.exists(font_path):
            font_path = os.path.join(PROJECT_ROOT, "assets", "font", "RobotoCondensed-Bold.ttf")
        has_font = font_path and os.path.exists(font_path)
        # FFmpeg coi "\" là ký tự escape trong filtergraph, nên đường dẫn
        # Windows (D:\...\font.ttf) làm hỏng cả chuỗi filter.
        safe_font_path = str(font_path or "").replace("\\", "/").replace(":", "\\:")

        wrapped_lines = []
        text_cfg = resolve_text_settings(source, channel_id)
        try:
            font_size = int(text_cfg.get("text_size", 65))
        except (TypeError, ValueError):
            font_size = 65
        title_max_width, _ = resolve_title_layout_box(text_cfg)

        if has_font and hook_text:
            safe_text = str(hook_text).replace("'", "").replace(":", "\\:").replace("%", "\\%").strip().upper()
            try:
                text_x_val = int(text_cfg.get("text_x", 65))
            except (TypeError, ValueError):
                text_x_val = 65
            try:
                text_y1_val = float(text_cfg.get("text_y1", 0) or 0)
                title_y = int(1920 * text_y1_val) if text_y1_val > 0 else 1230
            except (TypeError, ValueError):
                title_y = 1230
            # Vị trí riêng khi video đã chuyển sang frame content. Operator đặt
            # trên Web Hub (text_y_content, tỷ lệ 0-1 theo chiều cao khung);
            # chưa đặt thì mặc định thấp hơn vị trí ở frame title để không đè
            # phần đồ họa của frame.
            try:
                content_ratio = float(text_cfg.get("text_y_content", 0) or 0)
            except (TypeError, ValueError):
                content_ratio = 0.0
            if content_ratio > 0:
                content_y = int(1920 * content_ratio)
            else:
                content_y = min(1920 - 120, title_y + 220)

            manual_position = (
                str(text_cfg.get("text_position_mode", "manual")).lower() == "manual"
            )

            text_color_val = str(text_cfg.get("text_color") or "white").strip() or "white"

            # Title hiển thị xuyên suốt video: giai đoạn frame title dùng
            # title_y, giai đoạn frame content dùng content_y. Cho phép xuống
            # dòng thêm (allow_extra_lines) để câu dài không bị cắt bằng "…".
            title_phases = [
                ("title", title_y, f"between(t,0,{hook_duration:.3f})"),
                ("content", content_y, f"gt(t,{hook_duration:.3f})"),
            ]
            overlay_index = 0
            for phase_name, phase_y, enable_expr in title_phases:
                phase_layout = plan_text_layout(
                    safe_text,
                    font_size=font_size,
                    preferred_x=text_x_val,
                    preferred_y=phase_y,
                    max_width=title_max_width,
                    clamp_to_safe_zone=not manual_position,
                    allow_extra_lines=True,
                )
                for line_index, line in enumerate(phase_layout.lines):
                    line_y = phase_layout.y + line_index * phase_layout.line_spacing
                    draw_filter = (
                        f"drawtext=fontfile='{safe_font_path}':text='{line}':"
                        f"fontsize={phase_layout.font_size}:fontcolor={text_color_val}:"
                        f"bordercolor=black:borderw=3:"
                        f"shadowcolor=black:shadowx=3:shadowy=3:"
                        f"x={phase_layout.x}:y={line_y}:"
                        f"enable='{enable_expr}'"
                    )
                    label = f"[vtitle_{phase_name}_{line_index}]"
                    filters.append(f"{current}{draw_filter}{label}")
                    current = label
                    overlay_index += 1

        for segment in timeline.segments[1:]:
            beat_text = str(segment.on_screen_text or "").strip()
            if not has_font or not beat_text:
                continue
            safe_beat_text = beat_text.replace("'", "").replace(":", "\\:").replace("%", "\\%")
            beat_layout = plan_text_layout(
                safe_beat_text,
                font_size=48,
                preferred_y=300,
                max_width=840,
            )
            for line_index, line in enumerate(beat_layout.lines):
                output_label = f"[vbeat{segment.index}_{line_index}]"
                line_y = beat_layout.y + line_index * beat_layout.line_spacing
                filters.append(
                    f"{current}drawtext=fontfile='{safe_font_path}':text='{line}':"
                    f"fontsize={beat_layout.font_size}:fontcolor=white:bordercolor=black:borderw=3:"
                    f"x={beat_layout.x}:y={line_y}:"
                    f"enable='between(t,{segment.start:.3f},{segment.end:.3f})'{output_label}"
                )
                current = output_label

        filters.append(f"{current}null[vout]")
        video_map = "[vout]"

        ass_path = None
        if not FACEBOOK_KARAOKE_SUBTITLES_ENABLED:
            print("      🔇 Subtitle karaoke đã tắt cho video nguồn Facebook.")
        if (
            FACEBOOK_KARAOKE_SUBTITLES_ENABLED
            and script_voice_path
            and os.path.exists(script_voice_path)
            and script_text
        ):
            subtitle_preset = get_subtitle_preset(channel_id)
            keywords = [
                value
                for segment in timeline.segments
                for value in segment.must_show
                if value
            ]
            if subtitle_style == "normal":
                keywords = []
            ass_path = os.path.join(work_dir, f"subtitle_{job_id}.ass")
            ass_path = generate_word_ass(
                script_voice_path,
                ass_path,
                time_offset=hook_duration,
                words_per_line=subtitle_preset["max_words"],
                font_size=subtitle_preset["font_size"],
                margin_v=subtitle_preset["margin_v"],
                hex_color=subtitle_preset["hex_color"],
                highlight_color=subtitle_preset["highlight_color"],
                keywords=keywords,
                font_name=subtitle_preset["font_name"],
                margin_l=subtitle_preset["margin_l"],
                margin_r=subtitle_preset["margin_r"],
            )
            if not ass_path:
                ass_path = generate_text_ass(
                    script_text,
                    os.path.join(work_dir, f"subtitle_{job_id}.ass"),
                    duration=_get_duration(script_voice_path),
                    time_offset=hook_duration,
                    words_per_line=subtitle_preset["max_words"],
                    font_size=subtitle_preset["font_size"],
                    margin_v=subtitle_preset["margin_v"],
                    hex_color=subtitle_preset["hex_color"],
                    highlight_color=subtitle_preset["highlight_color"],
                    keywords=keywords,
                    font_name=subtitle_preset["font_name"],
                    margin_l=subtitle_preset["margin_l"],
                    margin_r=subtitle_preset["margin_r"],
                )
        if ass_path and os.path.exists(ass_path):
            safe_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")
            # Phải escape cả dấu hai chấm của ổ đĩa Windows ("D:/..." ->
            # "D\:/..."), nếu không FFmpeg đọc "D" thành tên option.
            fonts_dir = (
                os.path.join(PROJECT_ROOT, "assets", "font")
                .replace("\\", "/")
                .replace(":", "\\:")
            )
            filters.append(
                f"{video_map}subtitles='{safe_ass_path}':fontsdir='{fonts_dir}'[vsub]"
            )
            video_map = "[vsub]"

        # Map audio: chọn đúng một track và duck nhạc khi voice/source audio phát.
        music = select_music(
            music_mood,
            tone=tone,
            energy=music_energy,
            is_sensitive=is_sensitive,
            channel_id=channel_id,
        )
        
        has_audio = False
        try:
            probe = subprocess.run(ffprobe_command("-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", source_video), capture_output=True, text=True)
            has_audio = bool(probe.stdout.strip())
        except: pass

        if main_audio_idx is not None:
            main_audio = f"[{main_audio_idx}:a]"
        elif has_audio:
            main_audio = "[0:a]"
        else:
            main_audio = None

        if music:
            inputs += ["-stream_loop", "-1", "-i", music.path]
            bgm_idx = input_idx
            input_idx += 1
            if main_audio:
                mix_duration = audio_dur if audio_dur > 0 else _get_duration(source_video)
                filters.append(
                    build_ducked_mix_filter(
                        main_audio,
                        f"{bgm_idx}:a",
                        mix_duration,
                        music,
                        output_label="aout",
                        label_prefix="facebook_music",
                    )
                )
                audio_map = "[aout]"
            else:
                filters.append(
                    f"[{bgm_idx}:a]atrim=start={music.cue_start_sec:.3f},"
                    f"asetpts=PTS-STARTPTS,"
                    f"loudnorm=I=-14:LRA=9:TP=-1.5[aout]"
                )
                audio_map = "[aout]"
            print(
                f"      🎵 BGM: {os.path.basename(music.path)} | "
                f"mood={music.mood} | energy={music.energy} | bed={music.bed_lufs:.1f} LUFS"
            )
            if music.license_status != "approved":
                print("      ⚠️ BGM chưa có metadata giấy phép approved trong catalog.json")
        else:
            if main_audio:
                filters.append(f"{main_audio}loudnorm=I=-14:LRA=9:TP=-1.5[aout]")
                audio_map = "[aout]"
            else:
                inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
                audio_map = f"{input_idx}:a"
                input_idx += 1
            print(f"      ⚠️ Không có BGM phù hợp cho mood={music_mood or tone}; giữ audio chính")

        audio_cues = plan_audio_cues(
            timeline,
            is_sensitive=is_sensitive,
            sfx_dir=os.path.join(PROJECT_ROOT, "assets", "sfx"),
        )
        sfx_labels = []
        for cue_index, cue in enumerate(audio_cues):
            inputs += ["-i", cue.asset_path]
            delay_ms = int(cue.timestamp * 1000)
            label = f"facebook_sfx{cue_index}"
            filters.append(
                f"[{input_idx}:a]adelay={delay_ms}|{delay_ms},"
                f"volume={cue.gain:.2f}[{label}]"
            )
            sfx_labels.append(label)
            input_idx += 1
        if sfx_labels:
            base_audio = audio_map if str(audio_map).startswith("[") else f"[{audio_map}]"
            mixed_input = base_audio + "".join(f"[{label}]" for label in sfx_labels)
            filters.append(
                f"{mixed_input}amix=inputs={1 + len(sfx_labels)}:duration=first:"
                f"normalize=0,alimiter=limit=0.84[a_final]"
            )
            audio_map = "[a_final]"
            print(f"      🔊 AudioDirector: {len(sfx_labels)} SFX có chủ đích")

        cmd = [FFMPEG_BINARY, "-y"] + inputs
        cmd += ["-filter_complex", ";".join(filters), "-map", video_map]
        cmd += ["-map", f"{audio_map}"]
        
        if audio_dur > 0:
            cmd += ["-t", str(audio_dur + 0.2)]
            
        # Dùng -shortest để dự phòng
        cmd += [*final_output_args(), "-shortest", final_path]

        print(f"         Tạo video CÓ FRAME (1 pass: Voice full + loop video)...")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if res.returncode != 0:
                render_error = (res.stderr or "")[-1200:]
                print(f"         ⚠️ FFmpeg lỗi: {res.stderr}")
        except Exception as e:
            render_error = f"{type(e).__name__}: {e}"
            print(f"         ⚠️ FFmpeg lỗi exception: {e}")

        if not os.path.exists(final_path):
            print("         ❌ Không tạo được video chuẩn; không dùng video gốc làm fallback")
            return {
                "final_path": "",
                "watermark_detected": False,
                "error": render_error or "FFmpeg không tạo được file đầu ra.",
            }

        if os.path.exists(final_path):
            size_mb = os.path.getsize(final_path) / 1024 / 1024
            print(f"         ✅ Video CÓ FRAME: {size_mb:.1f}MB")

        watermark_still_present = False
        if _logo_regions:
            from shared.modules.logo_detector import verify_watermark_removed
            watermark_still_present = not verify_watermark_removed(final_path, _logo_regions)
            if watermark_still_present:
                print("         ⚠️ Vẫn phát hiện vùng watermark sau khi blur.")

        return {"final_path": final_path, "watermark_detected": watermark_still_present}

    def _edit_video_frame_only(self, source_video, hook_voice_path, script_voice_path,
                               title, work_dir, job_id, source, tone="Trung tính",
                               music_mood=None, music_energy=2, is_sensitive=False,
                               channel_id=None):
        """Dựng nhánh frame xuyên suốt khi frame đối thủ kéo tới cuối video.

        Frame thương hiệu được phủ lên video nguồn. Trước đây nhánh này chỉ
        mã hóa PNG frame có vùng alpha trong suốt; khi xuất H.264 vùng alpha
        đó biến thành nền trắng và làm người dùng tưởng video bị mất.
        """
        final_path = os.path.join(work_dir, f"final_{job_id}.mp4")
        merged_audio_path = os.path.join(work_dir, f"merged_audio_{job_id}.wav")

        def download_asset_safe(folder, filename):
            if not filename or filename == "-- Trống --":
                return None
            if os.path.isabs(filename):
                return filename if os.path.exists(filename) else None
            local_dir = os.path.join(PROJECT_ROOT, "assets", folder)
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, filename)
            if not os.path.exists(local_path):
                from shared.services.supabase_api import SupabaseAPI
                SupabaseAPI.download_asset("assets", folder, local_dir, filename)
            return local_path if os.path.exists(local_path) else None

        hook_ok = bool(hook_voice_path and os.path.exists(hook_voice_path))
        script_ok = bool(script_voice_path and os.path.exists(script_voice_path))
        if hook_ok and script_ok:
            merge = subprocess.run(
                [
                    FFMPEG_BINARY, "-y", "-i", hook_voice_path, "-i", script_voice_path,
                    "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[aout]",
                    "-map", "[aout]", merged_audio_path,
                ], capture_output=True, text=True,
            )
            audio_path = merged_audio_path if merge.returncode == 0 else hook_voice_path
        elif hook_ok:
            audio_path = hook_voice_path
        elif script_ok:
            audio_path = script_voice_path
        else:
            return {
                "final_path": "",
                "watermark_detected": False,
                "error": "Không có audio Hook/Script cho nhánh frame xuyên suốt.",
            }

        audio_duration = _get_duration(audio_path)
        if audio_duration <= 0:
            return {
                "final_path": "",
                "watermark_detected": False,
                "error": "Không xác định được thời lượng audio cho nhánh frame xuyên suốt.",
            }

        is_tele_bot = source.get("is_telegram_bot", False)
        raw_title_frame = source.get("title_frame_path")
        frame_path = (
            download_asset_safe("frame", raw_title_frame)
            if is_tele_bot
            else (raw_title_frame or FRAME_PATH)
        )
        if not frame_path or not os.path.exists(frame_path):
            return {
                "final_path": "",
                "watermark_detected": False,
                "error": "Không tìm thấy frame thương hiệu cho nhánh frame xuyên suốt.",
            }

        raw_font = source.get("font_path")
        font_path = download_asset_safe("font", raw_font) if is_tele_bot else raw_font
        if not font_path or not os.path.exists(font_path):
            font_path = os.path.join(PROJECT_ROOT, "assets", "font", "RobotoCondensed-Bold.ttf")
        safe_font_path = str(font_path or "").replace("\\", "/").replace(":", "\\:")
        text_cfg = resolve_text_settings(source, channel_id)
        try:
            font_size = int(text_cfg.get("text_size", 65))
        except (TypeError, ValueError):
            font_size = 65
        try:
            preferred_x = int(text_cfg.get("text_x", 65))
        except (TypeError, ValueError):
            preferred_x = 65
        try:
            text_y = float(text_cfg.get("text_y1", 0) or 0)
            preferred_y = int(1920 * text_y) if text_y > 0 else 1230
        except (TypeError, ValueError):
            preferred_y = 1230
        text_color = str(text_cfg.get("text_color") or "white").strip() or "white"
        title_value = str(title or "").replace("'", "").replace(":", "\\:").replace("%", "\\%").strip().upper()

        # Giữ video nguồn phía dưới frame. Nếu frame có alpha trong suốt,
        # phần đó sẽ hiển thị video thay vì bị FFmpeg điền trắng khi encode.
        if _is_horizontal(source_video):
            filters = [
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:2[bg]",
                "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg]",
                "[bg][fg]overlay=(W-w)/2:(H-h)/2[base]",
            ]
        else:
            filters = [
                "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2[base]",
            ]
        filters += [
            "[1:v]format=rgba,scale=1080:1920[frame]",
            "[base][frame]overlay=0:0[with_frame]",
        ]
        current = "[with_frame]"
        if safe_font_path and title_value:
            layout = plan_text_layout(
                title_value,
                font_size=font_size,
                preferred_x=preferred_x,
                preferred_y=preferred_y,
                max_width=950,
                clamp_to_safe_zone=str(text_cfg.get("text_position_mode", "manual")).lower() != "manual",
                allow_extra_lines=True,
            )
            for index, line in enumerate(layout.lines):
                y_pos = layout.y + index * layout.line_spacing
                output = f"[vtitle{index}]"
                filters.append(
                    f"{current}drawtext=fontfile='{safe_font_path}':text='{line}':"
                    f"fontsize={layout.font_size}:fontcolor={text_color}:"
                    f"bordercolor=black:borderw=3:shadowcolor=black:shadowx=3:shadowy=3:"
                    f"x={layout.x}:y={y_pos}{output}"
                )
                current = output
        filters.append(f"{current}null[vout]")

        cmd = [
            FFMPEG_BINARY, "-y", "-stream_loop", "-1", "-i", source_video,
            "-loop", "1", "-i", frame_path,
            "-i", audio_path,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "2:a",
            "-t", f"{audio_duration + 0.2:.3f}",
            *final_output_args(), "-shortest", final_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except Exception as exc:
            return {"final_path": "", "watermark_detected": False, "error": str(exc)}
        if result.returncode != 0 or not os.path.exists(final_path):
            return {
                "final_path": "",
                "watermark_detected": False,
                "error": (result.stderr or "FFmpeg không tạo được frame xuyên suốt.")[-1600:],
            }
        print(f"         ✅ Video FRAME XUYÊN SUỐT: {os.path.getsize(final_path) / 1024 / 1024:.1f}MB")
        return {"final_path": final_path, "watermark_detected": False}

    # ═══════════════════════════════════════════════════
    #  MODE 2: NGUỒN KHÔNG CÓ FRAME
    #  → Đoạn đầu: video gốc (mute) + frame title + hook voice + text hook
    #  → Đoạn sau: video nguồn từ body_start_sec, không frame và không text
    # ═══════════════════════════════════════════════════
    def _edit_video_no_frame(self, source_video, hook_voice_path, hook_text,
                              work_dir, job_id, source, tone="Trung tính",
                              music_mood=None, music_energy=2, is_sensitive=False,
                              channel_id=None, beats=None,
                              preserve_full_source_audio=False,
                              title_on_body=True, title_text="",
                              body_start_sec=0.0, intro_overlay_text="",
                              disable_music=False):
        # 3 PASS: Intro (frame + hook/text) -> Body (video gốc từ mốc đã chọn) -> Concat
        final_path = os.path.join(work_dir, f"final_{job_id}.mp4")
        temp_intro = os.path.join(work_dir, f"intro_{job_id}.mp4")
        temp_body = os.path.join(work_dir, f"body_{job_id}.mp4")
        render_errors = []

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
            if d > 0: hook_duration = d

        source_duration = _get_duration(source_video)
        try:
            body_start_sec = max(0.0, min(float(body_start_sec or 0.0), source_duration))
        except (TypeError, ValueError):
            body_start_sec = 0.0
        remaining_source_duration = max(0.1, source_duration - body_start_sec)
        body_duration = (
            remaining_source_duration
            if preserve_full_source_audio
            else min(
                remaining_source_duration,
                max(0.1, TARGET_VIDEO_DURATION_SECONDS - hook_duration),
            )
        )
        spoken_hook_text = str(hook_text or "").strip()
        title_text = str(title_text or "").strip() or spoken_hook_text
        timeline = plan_beat_timeline(
            beats,
            total_duration=max(0.1, hook_duration + body_duration),
            hook_duration=hook_duration,
            media_count=1,
            hook_text=spoken_hook_text,
        )
        spoken_hook_text = resolve_intro_overlay_text(spoken_hook_text, timeline)
        intro_text = (
            str(intro_overlay_text or "").strip()
            or spoken_hook_text
            or title_text
        )
        print(
            f"      🧭 Intro theo thoại Hook: {spoken_hook_text} | "
            f"Text intro: {intro_text}"
        )

        is_tele_bot = source.get("is_telegram_bot", False)
        
        raw_logo = source.get("logo_path")
        logo_path = download_asset_safe("logo", raw_logo) if is_tele_bot else (raw_logo if raw_logo else LOGO_PATH)
        
        # Nguồn không có frame chỉ nghĩa là video gốc không mang sẵn
        # template. Intro vẫn dùng frame title của kênh; body không chèn
        # frame. Ưu tiên frame theo nguồn, rồi fallback frame Facebook.
        raw_title_frame = source.get("title_frame_path")
        title_frame_path = (
            download_asset_safe("frame", raw_title_frame)
            if is_tele_bot
            else (raw_title_frame or FRAME_PATH)
        )
        has_intro_frame = bool(title_frame_path and os.path.exists(title_frame_path))
        has_logo = False # Tắt lắp logo
        is_horiz = _is_horizontal(source_video)

        color_grade = resolve_color_grade(
            channel_id or "",
            tone=tone,
            is_sensitive=is_sensitive,
        )
        eq_filter = f",{build_color_filter(color_grade)}"
        print(f"      🎨 Color grade: {color_grade.name}")

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
        COMMON_OUTPUT = final_output_args()

        # Kiểm tra video gốc có audio không
        has_audio = False
        try:
            probe = subprocess.run(ffprobe_command("-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", source_video), capture_output=True, text=True)
            has_audio = bool(probe.stdout.strip())
        except: pass

        music = None if disable_music else select_music(
            music_mood,
            tone=tone,
            energy=music_energy,
            is_sensitive=is_sensitive,
            channel_id=channel_id,
        )
        if music:
            print(
                f"      🎵 BGM hook: {os.path.basename(music.path)} | "
                f"mood={music.mood} | energy={music.energy} | bed={music.bed_lufs:.1f} LUFS"
            )
            if music.license_status != "approved":
                print("      ⚠️ BGM chưa có metadata giấy phép approved trong catalog.json")
        else:
            print(f"      ⚠️ Không có BGM phù hợp cho mood={music_mood or tone}; giữ audio chính")

        print(f"         Tạo video KHÔNG FRAME - Bước 1: Dựng Intro (Độ dài: {hook_duration}s)...")
        # 1. DỰNG INTRO (Dùng đoạn đầu của video, cắt đúng hook_duration)
        intro_inputs = ["-stream_loop", "-1", "-i", source_video]
        if has_hook_voice: intro_inputs += ["-i", hook_voice_path]
        else: intro_inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        if has_intro_frame: intro_inputs += ["-i", title_frame_path]
        if has_logo: intro_inputs += ["-i", logo_path]
        intro_bgm_idx = 2 + int(has_intro_frame) + int(bool(has_logo))
        if music: intro_inputs += ["-stream_loop", "-1", "-i", music.path]

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
        
        if has_intro_frame:
            intro_filters.append(f"[{in_idx}:v]scale=1080:1920[frame];{curr_intro}[frame]overlay=0:0[v_f]")
            curr_intro = "[v_f]"
            in_idx += 1
            
        if has_logo:
            intro_filters.append(f"[{in_idx}:v]scale=1080:1920[logo];{curr_intro}[logo]overlay=0:0[v_l]")
            curr_intro = "[v_l]"
            
        raw_font = source.get("font_path")
        font_path = download_asset_safe("font", raw_font) if is_tele_bot else raw_font
        if not font_path or not os.path.exists(font_path):
            font_path = os.path.join(PROJECT_ROOT, "assets", "font", "RobotoCondensed-Bold.ttf")
        has_font = font_path and os.path.exists(font_path)
        # FFmpeg coi "\" là ký tự escape trong filtergraph, nên đường dẫn
        # Windows (D:\...\font.ttf) làm hỏng cả chuỗi filter.
        safe_font_path = str(font_path or "").replace("\\", "/").replace(":", "\\:")

        # Text chỉ hiển thị ở intro; body không lặp lại hook/title.
        title_overlay_text = ""
        title_font_size = 65
        title_x = 65
        title_intro_y = 1230
        title_body_y = 1230
        text_cfg = resolve_text_settings(source, channel_id)
        title_manual_position = (
            str(text_cfg.get("text_position_mode", "manual")).lower() == "manual"
        )
        title_color = str(text_cfg.get("text_color") or "white").strip() or "white"
        if has_font and intro_text:
            title_overlay_text = (
                str(intro_text).replace("'", "").replace(":", "\\:").replace("%", "\\%").strip().upper()
            )
            try:
                title_font_size = int(text_cfg.get("text_size", 65))
            except (TypeError, ValueError):
                title_font_size = 65
            try:
                title_x = int(text_cfg.get("text_x", 65))
            except (TypeError, ValueError):
                title_x = 65
            try:
                text_y1_val = float(text_cfg.get("text_y1", 0) or 0)
                title_intro_y = int(1920 * text_y1_val) if text_y1_val > 0 else 1230
            except (TypeError, ValueError):
                title_intro_y = 1230
            try:
                content_ratio = float(text_cfg.get("text_y_content", 0) or 0)
            except (TypeError, ValueError):
                content_ratio = 0.0
            title_body_y = (
                int(1920 * content_ratio) if content_ratio > 0
                else min(1920 - 120, title_intro_y + 220)
            )

        if title_overlay_text:
            # allow_extra_lines: câu dài tự xuống dòng thêm thay vì bị cắt "…".
            layout = plan_text_layout(
                title_overlay_text,
                font_size=title_font_size,
                preferred_x=title_x,
                preferred_y=title_intro_y,
                max_width=950,
                clamp_to_safe_zone=not title_manual_position,
                allow_extra_lines=True,
            )

            for i, line in enumerate(layout.lines):
                y_pos = layout.y + (i * layout.line_spacing)
                draw_filter = f"drawtext=fontfile='{safe_font_path}':text='{line}':fontsize={layout.font_size}:fontcolor={title_color}:bordercolor=black:borderw=3:shadowcolor=black:shadowx=3:shadowy=3:x={layout.x}:y={y_pos}"
                intro_filters.append(f"{curr_intro}{draw_filter}[vt{i}]")
                curr_intro = f"[vt{i}]"

        intro_filters.append(f"{curr_intro}null[vout]")
        if music:
            intro_filters.append(
                build_ducked_mix_filter(
                    "1:a",
                    f"{intro_bgm_idx}:a",
                    hook_duration,
                    music,
                    output_label="aout",
                    label_prefix="facebook_intro_music",
                )
            )
        else:
            if disable_music:
                # Nhánh frame-transition chỉ yêu cầu Hook nguyên bản; tránh
                # loudnorm để không tạo latency khiến đoạn intro bị kéo dài.
                intro_filters.append(
                    "[1:a]aformat=sample_rates=48000:channel_layouts=stereo[aout]"
                )
            else:
                intro_filters.append("[1:a]loudnorm=I=-14:LRA=9:TP=-1.5[aout]")

        # Audio filters (đặc biệt loudnorm/sidechaincompress) có một lượng
        # latency nhỏ; nếu cắt đúng bằng duration Hook, MP4 trung gian có thể
        # bị mux chỉ còn video vì audio chưa kịp phát frame đầu tiên. Chừa
        # đệm ngắn rồi concat sẽ giữ đủ tiếng Hook.
        intro_mux_duration = hook_duration if disable_music else hook_duration + 0.25
        cmd_intro = [FFMPEG_BINARY, "-y"] + intro_inputs + ["-filter_complex", ";".join(intro_filters), "-map", "[vout]", "-map", "[aout]", "-t", str(intro_mux_duration)] + COMMON_OUTPUT + [temp_intro]
        try:
            subprocess.run(cmd_intro, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or "")[-1200:]
            render_errors.append(f"intro: {detail}")
            print(f"❌ Lỗi render Intro: {detail}")

        print(
            "         Tạo video KHÔNG FRAME - Bước 2: Dựng Body "
            f"({body_duration:.1f}s từ {body_start_sec:.3f}s; "
            + (
                "giữ trọn video và âm thanh nguồn)..."
                if preserve_full_source_audio
                else f"tổng mục tiêu khoảng {TARGET_VIDEO_DURATION_SECONDS}s)..."
            )
        )
        # 2. DỰNG BODY (từ mốc đã xác định, center, không frame/text)
        body_inputs = []
        if body_start_sec > 0.001:
            body_inputs += ["-ss", f"{body_start_sec:.3f}"]
        body_inputs += ["-i", source_video]
        src_dur = body_duration
        if not has_audio: 
            d_str = f":d={src_dur}" if src_dur > 0 else ""
            body_inputs += ["-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000{d_str}"]
        if has_logo: body_inputs += ["-i", logo_path]
        body_bgm_idx = 1 + int(not has_audio) + int(bool(has_logo))
        if music and not has_audio:
            body_inputs += ["-stream_loop", "-1", "-i", music.path]

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

        # Giữ điều kiện để tương thích caller cũ; nhánh Facebook hiện truyền
        # title_on_body=False nên body không có text.
        if title_overlay_text and title_on_body:
            body_title_layout = plan_text_layout(
                title_overlay_text,
                font_size=title_font_size,
                preferred_x=title_x,
                preferred_y=title_body_y,
                max_width=950,
                clamp_to_safe_zone=not title_manual_position,
                allow_extra_lines=True,
            )
            for line_index, line in enumerate(body_title_layout.lines):
                line_y = body_title_layout.y + line_index * body_title_layout.line_spacing
                body_filters.append(
                    f"{curr_body}drawtext=fontfile='{safe_font_path}':text='{line}':"
                    f"fontsize={body_title_layout.font_size}:fontcolor={title_color}:"
                    f"bordercolor=black:borderw=3:shadowcolor=black:shadowx=3:shadowy=3:"
                    f"x={body_title_layout.x}:y={line_y}[vbtitle{line_index}]"
                )
                curr_body = f"[vbtitle{line_index}]"

        body_filters.append(f"{curr_body}null[vout]")
        
        audio_map = "0:a" if has_audio else "1:a"
        if music and not has_audio:
            body_filters.append(
                build_ducked_mix_filter(
                    audio_map,
                    f"{body_bgm_idx}:a",
                    src_dur,
                    music,
                    output_label="aout",
                    label_prefix="facebook_body_music",
                    music_offset_sec=hook_duration,
                )
            )
        else:
            body_filters.append(f"[{audio_map}]loudnorm=I=-14:LRA=9:TP=-1.5[aout]")
        audio_map = "[aout]"
        
        cmd_body = [FFMPEG_BINARY, "-y"] + body_inputs + ["-filter_complex", ";".join(body_filters), "-map", "[vout]", "-map", audio_map, "-t", f"{body_duration:.3f}"] + COMMON_OUTPUT + ["-shortest", temp_body]
        
        try:
            subprocess.run(cmd_body, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or "")[-1200:]
            render_errors.append(f"body: {detail}")
            print(f"❌ Lỗi render Body: {detail}")

        print(f"         Tạo video KHÔNG FRAME - Bước 3: Ghép nối (Concat)...")
        # 3. CONCAT
        # Không dùng concat demuxer + stream copy ở đây. Demuxer lấy cấu trúc
        # stream của file đầu tiên làm khuôn; nếu Intro/Body có khác biệt nhỏ
        # về audio (sample rate, channel layout hoặc timestamp), nó có thể
        # xuất MP4 chỉ còn video dù cả hai file trung gian đều có tiếng.
        # Concat filter ép chuẩn audio trước khi nối và luôn map cả video lẫn
        # audio ở file cuối.
        concat_files = [path for path in (temp_intro, temp_body) if os.path.exists(path)]
        if len(concat_files) == 2:
            concat_filter = (
                "[0:v:0]setpts=PTS-STARTPTS[v0];"
                "[0:a:0]aresample=48000,aformat=sample_rates=48000:"
                "channel_layouts=stereo[a0];"
                "[1:v:0]setpts=PTS-STARTPTS[v1];"
                "[1:a:0]aresample=48000,aformat=sample_rates=48000:"
                "channel_layouts=stereo[a1];"
                "[v0][a0][v1][a1]concat=n=2:v=1:a=1[vcat][acat]"
            )
            cmd_concat = [
                FFMPEG_BINARY, "-y",
                "-i", concat_files[0],
                "-i", concat_files[1],
                "-filter_complex", concat_filter,
                "-map", "[vcat]", "-map", "[acat]",
                *COMMON_OUTPUT,
                final_path,
            ]
        elif len(concat_files) == 1:
            # Giữ fallback cho trường hợp một pass trung gian thất bại; vẫn
            # re-encode và map audio rõ ràng để không tạo file câm.
            cmd_concat = [
                FFMPEG_BINARY, "-y", "-i", concat_files[0],
                "-map", "0:v:0", "-map", "0:a:0?",
                *COMMON_OUTPUT,
                final_path,
            ]
        else:
            cmd_concat = []
        try:
            if not cmd_concat:
                raise subprocess.CalledProcessError(1, [FFMPEG_BINARY])
            subprocess.run(cmd_concat, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or "")[-1200:]
            render_errors.append(f"concat: {detail}")
            print(f"❌ Lỗi Concat: {detail}")
        
        try:
            os.remove(temp_intro)
            os.remove(temp_body)
        except OSError:
            pass
        
        if not os.path.exists(final_path):
            print("         ❌ Không tạo được video chuẩn; không dùng video gốc làm fallback")
            return {
                "final_path": "",
                "watermark_detected": False,
                "error": " | ".join(render_errors)
                or "FFmpeg không tạo được file đầu ra.",
            }

        if os.path.exists(final_path):
            size_mb = os.path.getsize(final_path) / 1024 / 1024
            print(f"         ✅ Video NO FRAME: {size_mb:.1f}MB")

        watermark_still_present = False
        if _logo_regions:
            from shared.modules.logo_detector import verify_watermark_removed
            still_present = not verify_watermark_removed(final_path, _logo_regions)
            if still_present:
                print("         ⚠️ Vẫn phát hiện vùng watermark sau khi blur (đã xử lý blur).")

        return {"final_path": final_path, "watermark_detected": False}

    # ═══════════════════════════════════════════════════
    #  SUPABASE HELPERS
    # ═══════════════════════════════════════════════════
    def _get_active_sources(self) -> list:
        return load_active_sources(supabase, self.source_scope)

    def _update_scan_time(self, source: dict, last_video_id: str = None):
        try:
            update_scan_checkpoint(supabase, source, last_video_id)
        except Exception as error:
            print(f"      ⚠️ Không cập nhật được checkpoint: {error}")

    def _insert_video_record(
        self,
        source: dict,
        video: dict,
        dl: dict,
        ai_result: dict,
        final_path: str,
    ) -> str | None:
        try:
            return insert_video_record(
                supabase, source, video, dl, ai_result, final_path
            )
        except Exception as e:
            if "23505" in str(e):
                return None
            print(f"      ⚠️ DB insert lỗi: {e}")
            return None

    def _claim_video_record(self, source: dict, video: dict) -> str | None:
        return claim_video_record(supabase, source, video)

    def _finalize_video_record(
        self,
        source: dict,
        record_id: str,
        dl: dict,
        ai_result: dict,
        final_path: str,
    ) -> None:
        finalize_video_record(
            supabase, source, record_id, dl, ai_result, final_path
        )

    def _check_hash_exists(self, file_hash: str, source: dict) -> bool:
        try:
            return file_hash_exists(supabase, source, file_hash)
        except Exception as error:
            print(f"      ❌ Không xác minh được hash với Supabase: {error}")
            raise RuntimeError(
                "Không thể kiểm tra video trùng; đã dừng để tránh tạo bản sao."
            ) from error

    def _check_video_id_exists(self, source: dict, video_id: str) -> bool:
        try:
            return video_id_exists(supabase, source, video_id)
        except Exception as error:
            print(f"      ❌ Không xác minh được Facebook video ID với Supabase: {error}")
            raise RuntimeError(
                "Không thể kiểm tra video trùng; đã dừng để tránh tạo bản sao."
            ) from error


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
    parser.add_argument(
        "--source-scope",
        choices=["page", "group", "all"],
        default="page",
        help="page: chỉ nguồn Page cũ | group: chỉ nguồn Group | all: cả hai",
    )
    args = parser.parse_args()

    if args.command == "login":
        from fb_crawler import login_facebook_interactive
        login_facebook_interactive()
        return

    pipeline = FBNewsPipeline(source_scope=args.source_scope)

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
