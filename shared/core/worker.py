import sys
import os
import time
import json
import requests
import re
import shutil

# =========================================================================
# 1. THIẾT LẬP ĐƯỜNG DẪN HỆ THỐNG TRƯỚC TIÊN (Để chống lỗi ModuleNotFoundError)
# =========================================================================
SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(SHARED_DIR)
sys.path.insert(0, WORKSPACE_ROOT)
sys.path.insert(0, SHARED_DIR)
PROJECT_ROOT = SHARED_DIR

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(WORKSPACE_ROOT, ".env"), override=False)
except Exception:
    pass

# Đảm bảo các thư mục assets tồn tại
TEMP_VOICE_DIR = os.path.join(PROJECT_ROOT, "assets", "temp_voice")
FRAME_DIR = os.path.join(PROJECT_ROOT, "assets", "frame")
LOGO_DIR = os.path.join(PROJECT_ROOT, "assets", "logo")
FONT_DIR = os.path.join(PROJECT_ROOT, "assets", "font")
CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "config", "credentials.json")

for d in [TEMP_VOICE_DIR, FRAME_DIR, LOGO_DIR, FONT_DIR]:
    if not os.path.exists(d): os.makedirs(d)

try:
    from services.tele_reporter import TeleReporter
    from core.context import AccountContext
    from modules.video_handler import (
        download_tiktok_video,
        get_channel_video_candidates,
    )
    from services.tiktok_clipssaver import title_dedupe_key
    from modules.whisper_transcriber import extract_transcript_from_media
    from shared.core.ai_provider_factory import analyze_video_content, get_configured_ai_provider
    from modules.video_remix import create_video_from_source_video
    from modules.upload_drive import upload_video_to_drive
    from services.sheet_api import get_latest_row_by_id, save_to_sheet, update_final_result, update_voice_links, update_source_link
    from services.tts_api import create_voice_default, create_voice_clone, create_voice_full_pipeline
    from services.supabase_api import SupabaseAPI
    from core.channel_editorial import get_channel_voice_speed
    from core.content_repair import (
        prepare_content_with_single_repair,
        summarize_validation,
    )
    from core.prompt_builder import build_channel_instruction, get_content_profile
    from core.evidence_guard import (
        EVIDENCE_GUARD_ENABLED,
        guard_evidence,
        summarize_evidence,
    )
    from core.rights_guard import guard_source_rights
    from core.visual_grounding import guard_visual_grounding, summarize_visual_grounding
    from core.social_evidence import build_social_evidence_pack
    from core.social_quality_gate import evaluate_social_quality, summarize_social_quality
    from core.source_ranker import rank_candidates, should_process_candidate
    from core.pipeline_state import PipelineLifecycle, PipelineStageError
    from core.quality_log import append_quality_event
    from core.video_qa import run_video_qa
except ImportError as e:
    print(f"❌ Lỗi Import thư viện: {e}")
    sys.exit(1)


def is_valid_vietnamese(text):
    if not text: return False
    vn_chars_pattern = re.compile(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]', re.IGNORECASE)
    return bool(vn_chars_pattern.search(text))


def retry_pending_sheet_results(ctx, sheet_url, state):
    """Ghi bù link Drive đã upload nhưng Sheet từng trả lỗi/rỗng.

    Video đã có trên Drive thì không render/upload lại. Chỉ retry thao tác
    lưu kết quả và đánh dấu candidate đã xử lý sau khi Sheet xác nhận success.
    """
    pending = ctx.load_pending_results()
    if not pending:
        return 0

    remaining = []
    recovered = 0
    for item in pending:
        row = item.get("row")
        drive_link = str(item.get("drive_link") or "").strip()
        if not row or not drive_link:
            remaining.append(item)
            continue
        if update_final_result(sheet_url, row, drive_link):
            candidate_url = str(item.get("candidate_url") or "").strip()
            title_key = str(item.get("title_key") or "").strip()
            if candidate_url and candidate_url not in state.setdefault("crawled_videos", []):
                state["crawled_videos"].append(candidate_url)
            if title_key and title_key not in state.setdefault("crawled_video_titles", []):
                state["crawled_video_titles"].append(title_key)
            source_url = str(item.get("source_url") or "").strip()
            if source_url:
                counts = state.setdefault("pending_video_index_increments", {})
                counts[source_url] = int(counts.get(source_url, 0)) + 1
            local_path = str(item.get("local_path") or "").strip()
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            recovered += 1
            ctx.logger.info(
                f"✅ Đã khôi phục kết quả pending: dòng {row} -> {drive_link}"
            )
        else:
            remaining.append(item)

    ctx.save_pending_results(remaining)
    if recovered:
        ctx.save_state(state)
    if remaining:
        ctx.logger.warning(
            f"⚠️ Còn {len(remaining)} kết quả Drive chờ ghi lại vào Sheet."
        )
    return recovered

def load_credentials():
    if not os.path.exists(CREDENTIALS_FILE): return {}
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def handle_tts_and_update_sheet(
    api_key, text, voice_id, row_idx, sheet_url, is_title=False, save_dir=None, speed=1.03
):
    if not text: return None, None

    label = "Tiêu đề" if is_title else "Nội dung"
    actual_save_dir = save_dir if save_dir else TEMP_VOICE_DIR
    file_name = f"tts_{row_idx}_{int(time.time())}_{'title' if is_title else 'content'}.wav"

    print(f"   🔊 Đang xử lý TTS {label} (Gọi qua VieNeu Server)...")

    try:
        local_path = create_voice_full_pipeline(
            text=text,
            save_dir=actual_save_dir,
            filename=file_name,
            profile_id=voice_id,
            rvc_model=voice_id,
            rvc_pitch=0,
            emotion="binh_thuong",
            speed=speed,
            api_key=api_key,
        )

        if local_path and os.path.exists(local_path):
            print(f"   ✅ TTS Server Thành công: {local_path}")

            if sheet_url and row_idx:
                if is_title: update_voice_links(sheet_url, row_idx, title_voice_link="local_file", content_voice_link=None)
                else: update_voice_links(sheet_url, row_idx, title_voice_link=None, content_voice_link="local_file")

            return "local_file", local_path

        return None, None

    except Exception as e:
        print(f"   ❌ Lỗi tạo TTS Local: {e}", flush=True)
        return None, None

def run_worker_process(account_id):
    ctx = AccountContext(account_id)
    ctx.logger.info(f"🚀 WORKER STARTED: {account_id}")

    cfg = ctx.config
    if not cfg:
        ctx.logger.error("❌ Không lấy được config từ Supabase. Dừng worker.")
        return

    tiktok_id = cfg.get("tiktok_id")
    profile_name = cfg.get("chrome_profile")
    acc_email = cfg.get("email")
    acc_password = cfg.get("password")
    setting_folder = load_credentials()
    folder_id = setting_folder.get("id_folder")
    settings = SupabaseAPI.get_system_config("app_settings") or {}
    sheet_url = settings.get("sheet_url") or settings.get("google_sheet_url")
    tts_api_key = settings.get("api_key") or settings.get("everai_api_key")
    # Voice ID: ưu tiên voice_id riêng của từng account, nếu không có thì dùng voice chung
    tts_voice_id = cfg.get("voice_id") or settings.get("voice_id") or settings.get("everai_voice_id", "1")

    if not sheet_url or not tts_api_key:
        ctx.logger.error("❌ Lỗi: Thiếu Sheet URL hoặc API Key.")
        return

    state = ctx.load_state()
    if "crawled_videos" not in state: state["crawled_videos"] = []
    if "crawled_video_titles" not in state:
        state["crawled_video_titles"] = []
    if "pending_video_index_increments" not in state:
        state["pending_video_index_increments"] = {}

    retry_pending_sheet_results(ctx, sheet_url, state)
    pending_results = ctx.load_pending_results()
    pending_urls = {str(item.get("candidate_url") or "") for item in pending_results}
    pending_titles = {str(item.get("title_key") or "") for item in pending_results}

    processed_count = 0
    acc_limit = cfg.get("video_limit_per_run", 3)

    for channel in cfg.get("channels", []):
        if processed_count >= acc_limit:
            ctx.logger.info(f"🛑 Đã đạt giới hạn tài khoản ({acc_limit} video). Dừng quét kênh tiếp theo.")
            break

        if not channel.get("active", True): continue

        src_url = channel.get("url") or channel.get("channel_url")
        if not src_url: continue

        # ClipSaver chỉ lấy tối đa ba video mới nhất cho mỗi kênh nguồn.
        limit = max(1, min(int(channel.get("limit", 3) or 3), 3))
        render_settings = channel.get("render_settings", {})

        ctx.logger.info(
            f"🔍 Quét ClipSaver: {src_url} (Lấy tối đa {limit} video)"
        )

        try:
            all_videos = get_channel_video_candidates(src_url, limit=limit)
        except Exception as e:
            ctx.logger.error(f"   ⚠️ Lỗi quét video: {e}")
            continue

        new_videos_batch = []
        for candidate in all_videos:
            candidate_title_key = str(
                candidate.get("title_key")
                or title_dedupe_key(
                    src_url,
                    candidate.get("title") or candidate.get("caption") or "",
                )
            )
            if not candidate_title_key:
                ctx.logger.info("   ⏭️ Bỏ qua video không có tiêu đề.")
                continue
            candidate["title_key"] = candidate_title_key
            if candidate.get("url") in pending_urls or candidate_title_key in pending_titles:
                ctx.logger.info("   ⏳ Video đã upload Drive, đang chờ ghi link vào Sheet.")
                continue
            if candidate_title_key in state["crawled_video_titles"]:
                ctx.logger.info(
                    f"   ⏭️ Tiêu đề đã xử lý: "
                    f"{candidate.get('title') or candidate.get('caption') or ''}"
                )
                continue
            new_videos_batch.append(candidate)

        if not new_videos_batch: continue

        clean_tid = tiktok_id.replace("@", "").strip()
        operator_profiles = (
            cfg.get("content_profile"),
            cfg.get("extra_content"),
            cfg.get("content_instruction"),
            cfg.get("profile_instruction"),
        )
        resolved_content_profile = get_content_profile(
            clean_tid,
            *operator_profiles,
        )
        manual_topic_approval = str(
            os.environ.get("TIKTOK_TOPIC_GATE", "off")
        ).strip().lower() not in {"1", "true", "yes", "on"}
        ranked_videos = rank_candidates(
            new_videos_batch,
            resolved_content_profile,
            source_type="tiktok",
            # TikTok sources are manually approved by the operator.  Keep
            # SourceRanker for ordering, but do not reject a candidate merely
            # because its metadata does not match the output-channel topic.
            thresholds={"reject": 0} if manual_topic_approval else None,
        )
        videos_to_process = ranked_videos[:limit]

        def mark_candidate_handled(handled_candidate):
            video_url = handled_candidate.get("url", "")
            handled_title_key = handled_candidate.get("title_key", "")
            if video_url not in state["crawled_videos"]:
                state["crawled_videos"].append(video_url)
            if (
                handled_title_key
                and handled_title_key not in state["crawled_video_titles"]
            ):
                state["crawled_video_titles"].append(handled_title_key)
            # Giữ state gọn khi tiến trình chạy lâu.
            state["crawled_videos"] = state["crawled_videos"][-2000:]
            state["crawled_video_titles"] = state["crawled_video_titles"][-2000:]
            ctx.save_state(state)

        for candidate in videos_to_process:
            vid_url = candidate["url"]
            if processed_count >= acc_limit:
                ctx.logger.info(f"🛑 Đã đạt giới hạn tài khoản ({acc_limit} video). Ngừng xử lý các video còn lại trong kênh.")
                break

            ctx.logger.info(f"▶️ BẮT ĐẦU VIDEO: {vid_url}")
            source_rank = candidate.get("source_rank", {})
            ctx.logger.info(
                f"   🧭 SourceRanker: {source_rank.get('total_score', 0)}/100 "
                f"({source_rank.get('status', 'unscored')})"
            )
            if not should_process_candidate(candidate):
                ctx.logger.info("   ⏭️ SourceRanker loại video không phù hợp kênh.")
                mark_candidate_handled(candidate)
                continue

            rights = guard_source_rights(candidate, channel)
            if not rights.passed:
                ctx.logger.info(f"   ⛔ RightsGuard chặn: {' '.join(rights.errors)}")
                mark_candidate_handled(candidate)
                continue
            if rights.requires_review:
                ctx.logger.info(f"   ⚠️ RightsGuard: {' '.join(rights.warnings)}")

            lifecycle = PipelineLifecycle("tiktok_matrix", vid_url)
            quality_score = 0
            qa_result = None
            try:
                paths = download_tiktok_video(
                    vid_url,
                    ctx.temp_dir,
                    candidate=candidate,
                )
                if not paths: continue

                up_path = paths.get('ai_studio') or paths.get('original')

                whisper_transcript = ""
                if up_path and os.path.exists(up_path):
                    ctx.logger.info("   🎙️ Đang bóc tách thoại video gốc bằng Faster-Whisper...")
                    whisper_transcript = extract_transcript_from_media(up_path, model_name="base")

                active_provider = get_configured_ai_provider().upper()
                ctx.logger.info(f"   🤖 Gửi video cho {active_provider} phân tích, bỏ qua Google AI Studio...")
                content_instruction = build_channel_instruction(
                    clean_tid,
                    source_type="tiktok",
                    operator_profiles=operator_profiles,
                )
                caption = str(
                    candidate.get("caption")
                    or candidate.get("title")
                    or f"Nguồn TikTok: {vid_url}"
                )
                evidence_pack = build_social_evidence_pack(
                    source_type="tiktok",
                    source_url=vid_url,
                    caption=caption,
                    transcript=whisper_transcript,
                    metadata=candidate,
                )
                ai_result = analyze_video_content(
                    up_path,
                    caption,
                    is_tele_bot=False,
                    extra_content=content_instruction,
                    profile_id=clean_tid,
                    source_type="tiktok",
                    experiment_content_key=vid_url,
                    whisper_transcript=whisper_transcript,
                )

                if not ai_result:
                    raise PipelineStageError(
                        "scripted", "SCRIPT_GENERATION_FAILED",
                        "AI Provider không trả về kịch bản hợp lệ.",
                    )

                # Apply the manual TikTok source approval before the content
                # repair/validator step; otherwise a topic-only decline would
                # leave a permanently skipped validation report.
                if manual_topic_approval and (
                    str(ai_result.get("topic_fit", True)).lower() == "false"
                    or not ai_result.get("topic_fit", True)
                ):
                    topic_text = str(
                        ai_result.get("topic_fit_reason")
                        or ai_result.get("skip_reason")
                        or ""
                    ).lower()
                    topic_markers = (
                        "chủ đề", "định vị", "không phù hợp", "tệp người xem",
                        "showbiz", "topic", "channel",
                    )
                    is_topic_decline = any(
                        marker in topic_text for marker in topic_markers
                    )
                    ctx.logger.info(
                        "   ✅ TikTok source đã được operator duyệt; "
                        "bỏ qua topic_fit của AI."
                    )
                    ai_result["topic_fit"] = True
                    ai_result["topic_fit_reason"] = (
                        "Nguồn TikTok đã được operator duyệt thủ công."
                    )
                    if is_topic_decline:
                        if (
                            str(ai_result.get("should_make_video", True)).lower() == "false"
                            or not ai_result.get("should_make_video", True)
                        ):
                            ai_result["should_make_video"] = True
                            ai_result["skip_reason"] = ""
                lifecycle.advance("scripted")

                prepared_content = prepare_content_with_single_repair(
                    ai_result,
                    source_type="tiktok",
                    channel_id=clean_tid,
                    source_url=vid_url,
                    profile=resolved_content_profile,
                    repair_callback=lambda instruction: analyze_video_content(
                        up_path,
                        caption,
                        is_tele_bot=False,
                        extra_content=content_instruction,
                        profile_id=clean_tid,
                        repair_instruction=instruction,
                        source_type="tiktok",
                        experiment_content_key=vid_url,
                        whisper_transcript=whisper_transcript,
                    ),
                )
                ai_result = prepared_content.content
                if prepared_content.repair_attempts:
                    repair_status = (
                        "đạt" if prepared_content.repaired else "chưa đạt"
                    )
                    ctx.logger.info(
                        f"   🔧 Đã sửa kịch bản 1 lần: {repair_status}."
                    )

                should_make_video = ai_result.get("should_make_video", True)

                if str(should_make_video).lower() == "false" or not should_make_video:
                    active_provider = get_configured_ai_provider().upper()
                    ctx.logger.info(f"   ⏭️ {active_provider} đánh giá không nên làm video này: {ai_result.get('skip_reason', '')}")
                    mark_candidate_handled(candidate)
                    continue

                # TẠM THỜI TẮT LỌC NỘI DUNG
                ai_result["topic_fit"] = True
                if str(ai_result.get("topic_fit", True)).lower() == "false":
                    if manual_topic_approval:
                        ctx.logger.info(
                            "   ✅ TikTok topic_fit được bỏ qua theo duyệt thủ công."
                        )
                    else:
                        topic_fit_reason = (
                            ai_result.get("topic_fit_reason")
                            or ai_result.get("skip_reason", "")
                        )
                        ctx.logger.info(
                            f"   ⏭️ Video không đúng định vị kênh: {topic_fit_reason}"
                        )
                        mark_candidate_handled(candidate)
                        continue

                if not prepared_content.report.passed:
                    validation_reason = summarize_validation(
                        prepared_content.report
                    )
                    ctx.logger.info(
                        f"   ⏭️ ContentValidator không đạt: "
                        f"{validation_reason}"
                    )
                    # Keep validator failures retryable.  A repair attempt may
                    # have been based on a false-positive (for example one
                    # sentence combining two registered visual claims); marking
                    # the URL as handled here permanently discarded the video
                    # after a transient/model-format issue.
                    ctx.logger.info(
                        "   🔁 Giữ video để retry ở đợt kế tiếp sau khi sửa nội dung."
                    )
                    continue
                ctx.logger.info(
                    f"   ✅ ContentValidator: "
                    f"{prepared_content.report.content_score}/100"
                )

                evidence_report = guard_evidence(
                    ai_result,
                    source_type="tiktok",
                    source_url=vid_url,
                    source_text=evidence_pack.source_text,
                    profile=resolved_content_profile,
                )
                if not EVIDENCE_GUARD_ENABLED:
                    ctx.logger.info("   ⏭️ EvidenceGuard đã tắt; tiếp tục xử lý video.")
                elif not evidence_report.passed:
                    ctx.logger.info(
                        f"   ⏭️ EvidenceGuard không đạt: "
                        f"{summarize_evidence(evidence_report)}"
                    )
                    mark_candidate_handled(candidate)
                    continue
                else:
                    ctx.logger.info(
                        f"   ✅ EvidenceGuard: {evidence_report.score}/100"
                    )
                visual_report = guard_visual_grounding(
                    ai_result,
                    source_type="tiktok",
                    source_text=evidence_pack.source_text,
                )
                if not visual_report.passed:
                    ctx.logger.info(
                        f"   ⏭️ VisualGrounding không đạt: "
                        f"{summarize_visual_grounding(visual_report)}"
                    )
                    mark_candidate_handled(candidate)
                    continue
                ctx.logger.info(
                    f"   ✅ VisualGrounding: {visual_report.score}/100"
                )
                social_report = evaluate_social_quality(
                    ai_result,
                    source_type="tiktok",
                    validation_report=prepared_content.report,
                    evidence_report=evidence_report,
                    visual_report=visual_report,
                    rights_report=rights,
                    evidence_pack=evidence_pack.to_dict(),
                    frame_mode=bool(ai_result.get("have_frame")),
                    threshold=int(os.environ.get("SOCIAL_QUALITY_THRESHOLD", "70")),
                )
                if not social_report.passed:
                    ctx.logger.info(
                        f"   ⏭️ Social Quality Gate: "
                        f"{summarize_social_quality(social_report)}"
                    )
                    mark_candidate_handled(candidate)
                    continue
                ctx.logger.info(
                    f"   ✅ Social Quality Gate: {social_report.score}/100"
                )
                quality_score = int(ai_result.get("quality_score", 0) or 0)
                lifecycle.advance("validated")
                append_quality_event(
                    "tiktok_matrix", clean_tid, quality_score, "validated",
                    stage="validated", item_id=vid_url,
                    source_url=vid_url,
                    editorial_score=social_report.score,
                    ai_quality_score=quality_score,
                    quality_breakdown=social_report.breakdown,
                )

                sheet_result = save_to_sheet(
                    script_url=sheet_url,
                    link=vid_url,
                    title=ai_result.get("hook", "") or ai_result.get("title_tiktok", "Video Viral"),
                    script=ai_result.get("script_voice", ""),
                    combined_hints=ai_result.get("hook", ""),
                    original_video=vid_url,
                    title_tiktok=ai_result.get("title_tiktok", ""),
                    tiktok_id=clean_tid,
                    file_path="",
                )
                row_idx = sheet_result.get("row") if isinstance(sheet_result, dict) else None
                if not row_idx:
                    ctx.logger.error(f"   ❌ Không ghi được kịch bản vào Google Sheet: {sheet_result}")
                    continue

                row_data = {
                    "row": row_idx,
                    "title_text": ai_result.get("hook", "") or ai_result.get("title_tiktok", "Video Viral"),
                    "content_text": ai_result.get("script_voice", ""),
                    "tone": ai_result.get("tone", "Trung tính"),
                    "music_mood": ai_result.get("music_mood"),
                    "music_energy": ai_result.get("music_energy", 2),
                    "is_sensitive": ai_result.get("is_sensitive", False),
                    "tiktok_id_sheet": clean_tid,
                }

                raw_content = row_data.get("content_text", "")
                raw_title = row_data.get("title_text", "")
                if not is_valid_vietnamese(raw_content) and is_valid_vietnamese(raw_title):
                    ctx.logger.error("   ❌ LỖI AI: Content trả về là tiếng Việt không dấu (hoặc bị rỗng). BỎ QUA video này!")
                    update_final_result(sheet_url, row_data['row'], "LỖI: AI TRẢ TEXT KHÔNG DẤU")
                    continue
                # Lấy tone từ row_data và tra cứu Voice ID
                tone = row_data.get("tone", "Trung tính")
                selected_voice_id = tts_voice_id
                voice_config = {}
                settings_paths = [
                    os.path.join(WORKSPACE_ROOT, "apps", "creator_facebook", "data", "global_voice_settings.json"),
                    os.path.join(WORKSPACE_ROOT, "assets", "channels", clean_tid, "voice_config.json"),
                ]
                for settings_path in settings_paths:
                    if not os.path.exists(settings_path):
                        continue
                    try:
                        with open(settings_path, "r", encoding="utf-8") as fs:
                            loaded_voice_config = json.load(fs)
                        if isinstance(loaded_voice_config, dict):
                            voice_config.update(loaded_voice_config)
                    except Exception:
                        pass

                tone_id = str(voice_config.get(tone, "")).strip()
                neutral_id = str(voice_config.get("Trung tính", "")).strip()
                if tone_id:
                    selected_voice_id = tone_id
                elif neutral_id:
                    selected_voice_id = neutral_id
                channel_voice_speed = get_channel_voice_speed(
                    clean_tid,
                    story_type=ai_result.get("story_type", ""),
                    tone=ai_result.get("tone", ""),
                    is_sensitive=bool(ai_result.get("is_sensitive", False)),
                )

                ctx.logger.info(
                    f"   🎵 Tone: {tone} -> Voice ID: {selected_voice_id} | Speed: {channel_voice_speed}"
                )

                link_ct, local_content = handle_tts_and_update_sheet(
                    tts_api_key, raw_content, selected_voice_id, row_data['row'], sheet_url,
                    False, save_dir=ctx.temp_dir, speed=channel_voice_speed
                )
                local_title = None
                if row_data.get("title_text"):
                    _, local_title = handle_tts_and_update_sheet(
                        tts_api_key, row_data["title_text"], selected_voice_id, row_data['row'],
                        sheet_url, True, save_dir=ctx.temp_dir, speed=channel_voice_speed
                    )
                
                if not local_content:
                    raise PipelineStageError(
                        "voiced", "TTS_FAILED",
                        "Không tạo được Voice Content.",
                    )
                lifecycle.advance("voiced")

                ctx.logger.info("   🎬 Chuẩn bị Remixing...")

                assets_conf = render_settings.get("assets", {})

                t_frame_name = assets_conf.get("title_frame_filename")
                c_frame_name = assets_conf.get("content_frame_filename")
                logo_name = assets_conf.get("logo_filename")
                font_name = render_settings.get("text_overlay_settings", {}).get("font_filename")

                def download_if_missing(folder_type, local_dir, file_name):
                    if not file_name: return None
                    full_path = os.path.join(local_dir, file_name)
                    if not os.path.exists(full_path):
                        ctx.logger.info(f"   📥 Không có file '{file_name}'. Đang tải từ Supabase...")
                        SupabaseAPI.download_asset("assets", folder_type, local_dir, file_name)
                    else:
                        ctx.logger.info(f"   ✅ Đã có file '{file_name}' trong máy.")
                    return full_path

                title_frame_full_path = download_if_missing("frame", FRAME_DIR, t_frame_name)
                content_frame_full_path = download_if_missing("frame", FRAME_DIR, c_frame_name)
                
                t_logo_name = assets_conf.get("title_logo_filename", assets_conf.get("logo_filename"))
                c_logo_name = assets_conf.get("content_logo_filename", assets_conf.get("logo_filename"))
                title_logo_full_path = download_if_missing("logo", LOGO_DIR, t_logo_name)
                content_logo_full_path = download_if_missing("logo", LOGO_DIR, c_logo_name)
                
                download_if_missing("font", FONT_DIR, font_name)

                render_result = create_video_from_source_video(
                    audio_url=local_content,
                    source_video_url=paths['original'],
                    title_audio_url=local_title,
                    title_tiktok=row_data.get("title_text", "Video Viral"),
                    content_text=row_data.get("title_text", "Video Viral"),
                    script_url=sheet_url,
                    row_index=row_data['row'],
                    tiktok_id=clean_tid,
                    override_config=render_settings,
                    output_filename=f"final_{account_id}_{int(time.time())}.mp4",
                    temp_dir=ctx.temp_dir,
                    title_frame_path=title_frame_full_path,
                    content_frame_path=content_frame_full_path,
                    title_logo_path=title_logo_full_path,
                    content_logo_path=content_logo_full_path,
                    target_channel_url=src_url,
                    tone=tone,
                    music_mood=row_data.get("music_mood"),
                    music_energy=row_data.get("music_energy", 2),
                    is_sensitive=row_data.get("is_sensitive", False),
                    beats=ai_result.get("beats"),
                    script_text=ai_result.get("script_voice", ""),
                    subtitle_style=ai_result.get(
                        "subtitle_style", "keyword_highlight",
                    ),
                    have_frame=bool(ai_result.get("have_frame")),
                    frame_end_sec=ai_result.get(
                        "detected_competitor_frame_end_sec"
                    ),
                )
                final_path = (
                    render_result.get("final_path")
                    if isinstance(render_result, dict) else render_result
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

                render_subtitle_path = (
                    render_result.get("subtitle_ass_path", "")
                    if isinstance(render_result, dict) else ""
                )
                render_watermark_detected = (
                    bool(render_result.get("watermark_detected"))
                    if isinstance(render_result, dict) else False
                )
                qa_result = run_video_qa(
                    final_path,
                    subtitle_ass_path=render_subtitle_path or "",
                    watermark_detected=render_watermark_detected,
                )
                if render_subtitle_path and os.path.exists(render_subtitle_path):
                    try:
                        os.remove(render_subtitle_path)
                    except OSError:
                        pass
                if not qa_result.passed:
                    raise PipelineStageError(
                        "qa_passed",
                        qa_result.error_code or "VIDEO_QA_FAILED",
                        "VideoQA chặn upload: "
                        + ", ".join(qa_result.blocking_errors),
                    )
                lifecycle.advance("qa_passed")
                append_quality_event(
                    "tiktok_matrix", clean_tid, quality_score, "qa_passed",
                    stage="qa_passed", item_id=vid_url,
                    qa=qa_result.to_dict(),
                )

                try:
                    drv_link = upload_video_to_drive(final_path, folder_id=folder_id)
                except Exception as error:
                    raise PipelineStageError(
                        "uploaded", "UPLOAD_FAILED",
                        f"Lỗi upload Drive: {error}",
                    ) from error
                if not drv_link:
                    raise PipelineStageError(
                        "uploaded", "UPLOAD_FAILED",
                        "Google Drive trả về link rỗng.",
                    )
                lifecycle.advance("uploaded")
                append_quality_event(
                    "tiktok_matrix", clean_tid, quality_score, "uploaded",
                    stage="uploaded", item_id=vid_url,
                    qa=qa_result.to_dict(),
                )

                # Lưu phiếu khôi phục trước khi gọi Apps Script. Nếu kết nối
                # rớt hoặc tiến trình dừng, lượt sau chỉ ghi bù link.
                preserved_path = ""
                if final_path and os.path.exists(final_path):
                    preserved_path = os.path.join(
                        ctx.outbox_dir, os.path.basename(final_path)
                    )
                    try:
                        shutil.copy2(final_path, preserved_path)
                    except OSError as copy_error:
                        ctx.logger.warning(
                            f"⚠️ Không sao lưu được MP4 chờ Sheet: {copy_error}"
                        )
                        preserved_path = ""
                ctx.enqueue_pending_result({
                    "candidate_url": vid_url,
                    "title_key": candidate.get("title_key", ""),
                    "source_url": src_url,
                    "row": row_data["row"],
                    "drive_link": drv_link,
                    "local_path": preserved_path,
                    "created_at": time.time(),
                })

                if update_final_result(sheet_url, row_data['row'], drv_link):
                    ctx.logger.info("   ✅ HOÀN TẤT!")

                    ctx.remove_pending_result(vid_url, row_data["row"])
                    if preserved_path and os.path.exists(preserved_path):
                        os.remove(preserved_path)

                    mark_candidate_handled(candidate)
                    pending_counts = state["pending_video_index_increments"]
                    pending_counts[src_url] = int(pending_counts.get(src_url, 0)) + 1
                    ctx.save_state(state)
                    if os.path.exists(final_path):
                        os.remove(final_path)

                    processed_count += 1

                    try:
                        TeleReporter.log_success_video(tiktok_id, src_url)
                    except Exception as e:
                        ctx.logger.error(f"   ⚠️ Lỗi ghi nháp Telegram: {e}")
                else:
                    raise PipelineStageError(
                        "uploaded", "RESULT_PERSIST_FAILED",
                        "Đã upload Drive nhưng không ghi được link vào Sheet.",
                    )

            except Exception as e:
                failure = lifecycle.fail_from_exception(e)
                append_quality_event(
                    "tiktok_matrix", clean_tid, quality_score, "failed",
                    stage=failure.stage, item_id=vid_url,
                    error_code=failure.error_code,
                    retryable=failure.retryable,
                    message=failure.message,
                    qa=qa_result.to_dict() if qa_result else None,
                )
                try:
                    TeleReporter.log_pipeline_failure(clean_tid, failure)
                except Exception as report_error:
                    ctx.logger.error(
                        f"   ⚠️ Không ghi được failure stats: {report_error}"
                    )
                ctx.logger.error(
                    f"   🔥 {failure.error_code} ({failure.stage}): "
                    f"{failure.message}"
                )
            finally:
                ctx.cleanup_temp()
                time.sleep(5)

        batch_title_keys = [
            item.get("title_key", "") for item in new_videos_batch
        ]
        batch_fully_handled = batch_title_keys and all(
            item_key in state["crawled_video_titles"]
            for item_key in batch_title_keys
        )
        if batch_fully_handled:
            safe_checkpoint = new_videos_batch[0]["url"]
            try:
                pending_counts = state["pending_video_index_increments"]
                pending_increment = int(pending_counts.get(src_url, 0))
                new_index = channel.get("video_index", 0) + pending_increment
                checkpoint_updated = SupabaseAPI.update_channel_tracking(
                    tiktok_id,
                    src_url,
                    safe_checkpoint,
                    new_index,
                )
                if not checkpoint_updated:
                    raise RuntimeError("Không tìm thấy channel để cập nhật checkpoint")
                ctx.logger.info(
                    f"   ☁️ Batch tiêu đề đã xử lý xong; giữ mốc tương thích: "
                    f"{safe_checkpoint}"
                )
                pending_counts.pop(src_url, None)
                ctx.save_state(state)
            except Exception as e:
                ctx.logger.error(f"   ⚠️ Lỗi cập nhật checkpoint Supabase: {e}")
        elif batch_title_keys:
            ctx.logger.info(
                "   📥 Còn tiêu đề chưa xử lý; chưa cập nhật mốc tương thích."
            )

    ctx.logger.info(f"🏁 WORKER FINISHED. Tổng video thành công: {processed_count}/{acc_limit}")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    account_id = None

    for arg in args:
        arg = arg.strip()
        if not arg.startswith("--"):
            account_id = arg

    if not account_id:
        print("\n❌ LỖI: Thiếu ID tài khoản! (Ví dụ: @tai_khoan)")
    else:
        try:
            run_worker_process(account_id)
        except Exception as e:
            print(f"🔥 WORKER CRASHED: {e}")
            import traceback
            traceback.print_exc()
