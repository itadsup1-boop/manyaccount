#!/usr/bin/env python3
import os
import sys
import time
import random
import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit, urlunsplit

# Import các module vừa viết
from category_crawler import CategoryCrawler
from article_crawler import ArticleCrawler
from image_searcher import ImageSearcher
from article_sheet_api import save_article_to_sheet
from article_ffmpeg import create_article_video

# Import từ project chính (mannyAccount)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.core.ai_provider_factory import analyze_article_content, get_configured_ai_provider
from shared.services.tts_api import create_voice_full_pipeline, probe_audio_duration
from shared.core.channel_editorial import (
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
from shared.core.rights_guard import guard_image_assets
from shared.core.visual_grounding import (
    guard_visual_grounding,
    summarize_visual_grounding,
)
from shared.core.quality_gate import (
    evaluate_editorial_quality,
    summarize_quality_gate,
)
from shared.core.source_ranker import rank_candidates, should_process_candidate
from shared.core.pipeline_state import PipelineLifecycle, PipelineStageError
from shared.core.quality_log import append_pipeline_event, append_quality_event
from shared.core.video_qa import run_video_qa

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        # UTF-8 tường minh: Windows mặc định cp1252 nên một ký tự tiếng Việt
        # trong .env (kể cả ở dòng ghi chú) sẽ làm pipeline crash lúc import.
        with open(ENV_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip()
    return env

ENV = load_env()
SUPABASE_URL = ENV.get("SUPABASE_URL", "")
SUPABASE_KEY = ENV.get("SUPABASE_KEY", "")
# ID cu "c2d78da2-..." khong con ton tai tren server voice.adsup.vn (API tra
# 400 "not found") - da xac minh va doi sang ID con hoat dong that.
VOICE_PROFILE_ID = ENV.get("VOICEBOX_PROFILE_ID", "3fb3db24-b0af-4db4-b75f-b897f0431843")

# Khoảng nghỉ giữa hai bài trong cùng một kênh. ChatGPT chặn khi nhận quá
# nhiều yêu cầu liên tiếp; nghỉ ngắn giữa các bài giúp giảm hẳn tình trạng đó.
try:
    ARTICLE_DELAY_SECONDS = max(0, int(ENV.get("ARTICLE_DELAY_SECONDS", "25")))
except (TypeError, ValueError):
    ARTICLE_DELAY_SECONDS = 25

# Mỗi lượt chỉ sản xuất từng này video thành công cho một kênh rồi chuyển
# profile. Bài bị loại hoặc xử lý lỗi không được tính vào hạn mức này.
try:
    ARTICLE_SUCCESS_BATCH_SIZE = max(
        1, int(ENV.get("ARTICLE_SUCCESS_BATCH_SIZE", "5"))
    )
except (TypeError, ValueError):
    ARTICLE_SUCCESS_BATCH_SIZE = 5

try:
    from supabase import create_client
    if SUPABASE_URL and SUPABASE_KEY and not SUPABASE_KEY.startswith("your_"):
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    else:
        from shared.services.supabase_api import supabase as supabase_client
except Exception as e:
    print(f"❌ Lỗi Supabase: {e}")
    sys.exit(1)

QUALITY_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "quality_log.jsonl")
ARTICLE_PROCESSED_LINKS_FALLBACK_PATH = os.path.join(PROJECT_ROOT, "data", "article_processed_links.json")
ARTICLE_PROCESSED_LINKS_CONFIG_KEY = "article_processed_links"
ARTICLE_LINK_LOCK = threading.Lock()
ARTICLE_LINKS_IN_PROGRESS = set()
# The local fallback and the ``system_configs`` aggregate are shared by all
# channel workers. Serialize their read/modify/write cycle so parallel
# channels cannot overwrite each other's processed-link entry.
ARTICLE_PROCESSED_STORE_LOCK = threading.RLock()


def _trace_pipeline_step(
    channel_id: str,
    article_url: str,
    stage: str,
    event: str,
    *,
    message: str = "",
    error_code: str = "",
    retryable: bool | None = None,
    metadata: dict | None = None,
) -> None:
    """Print and persist one human-readable pipeline checkpoint."""
    try:
        append_pipeline_event(
            "article",
            article_url,
            stage,
            event,
            channel_id=channel_id,
            message=message,
            error_code=error_code,
            retryable=retryable,
            metadata=metadata,
        )
    except Exception:
        # Tracing must never stop content production.
        pass
    suffix = f" — {message}" if message else ""
    print(
        f"[TRACE][{channel_id}] {event.upper()} stage={stage} "
        f"url={_normalize_article_url(article_url)}{suffix}",
        flush=True,
    )

def _normalize_article_url(url: str) -> str:
    clean_url = str(url or "").strip()
    if not clean_url:
        return ""
    if not clean_url.startswith(("http://", "https://")):
        return clean_url
    try:
        parts = urlsplit(clean_url)
        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()
        path = parts.path.rstrip("/") if parts.path != "/" else parts.path
        return urlunsplit((scheme, netloc, path, "", ""))
    except Exception:
        return clean_url.split("#", 1)[0].split("?", 1)[0].rstrip("/")

def _reserve_article_link(url: str) -> str:
    normalized_url = _normalize_article_url(url)
    if not normalized_url:
        return ""
    with ARTICLE_LINK_LOCK:
        if normalized_url in ARTICLE_LINKS_IN_PROGRESS:
            return ""
        ARTICLE_LINKS_IN_PROGRESS.add(normalized_url)
    return normalized_url

def _release_article_link(url: str):
    normalized_url = _normalize_article_url(url)
    if not normalized_url:
        return
    with ARTICLE_LINK_LOCK:
        ARTICLE_LINKS_IN_PROGRESS.discard(normalized_url)

def _load_db_processed_links():
    for attempt in range(3):
        try:
            res = supabase_client.table("system_configs").select("config_value").eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
            if not res.data:
                return []
            value = res.data[0].get("config_value") or []
            if isinstance(value, list):
                return [_normalize_article_url(item) for item in value if _normalize_article_url(item)]
            break
        except Exception as e:
            if attempt == 2:
                print(f"⚠️ Lỗi đọc article_processed_links trong database: {e}")
            else:
                import time, random
                time.sleep(random.uniform(0.5, 1.5))
    return []

def _save_db_processed_links(links):
    clean_links = []
    seen = set()
    for link in links:
        clean_link = _normalize_article_url(link)
        if clean_link and clean_link not in seen:
            seen.add(clean_link)
            clean_links.append(clean_link)
    for attempt in range(3):
        try:
            existing = supabase_client.table("system_configs").select("config_name").eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
            payload = {"config_value": clean_links}
            if existing.data:
                supabase_client.table("system_configs").update(payload).eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
            else:
                supabase_client.table("system_configs").insert({"config_name": ARTICLE_PROCESSED_LINKS_CONFIG_KEY, **payload}).execute()
            return True
        except Exception as e:
            if attempt == 2:
                print(f"⚠️ Lỗi lưu article_processed_links trong database: {e}")
                return False
            else:
                import time, random
                time.sleep(random.uniform(0.5, 1.5))
    return False

def _mark_link_db_processed(url: str):
    clean_url = _normalize_article_url(url)
    if not clean_url:
        return
    links = _load_db_processed_links()
    if clean_url not in links:
        links.append(clean_url)
        _save_db_processed_links(links)

def _load_local_processed_links():
    try:
        if not os.path.exists(ARTICLE_PROCESSED_LINKS_FALLBACK_PATH):
            return []
        with open(ARTICLE_PROCESSED_LINKS_FALLBACK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []

def _is_link_in_local_processed(url: str) -> bool:
    clean_url = _normalize_article_url(url)
    if not clean_url:
        return False
    for item in _load_local_processed_links():
        if isinstance(item, str) and _normalize_article_url(item) == clean_url:
            return True
        if isinstance(item, dict) and _normalize_article_url(item.get("url")) == clean_url:
            return True
    return False

def _mark_link_local_processed(url: str, source: str = "pipeline"):
    clean_url = _normalize_article_url(url)
    if not clean_url:
        return
    try:
        os.makedirs(os.path.dirname(ARTICLE_PROCESSED_LINKS_FALLBACK_PATH), exist_ok=True)
        links = []
        seen = set()
        for item in _load_local_processed_links():
            item_url = item if isinstance(item, str) else item.get("url") if isinstance(item, dict) else ""
            item_url = _normalize_article_url(item_url)
            if item_url and item_url not in seen:
                seen.add(item_url)
                links.append(item_url)
        if clean_url not in seen:
            links.append(clean_url)
        temp_path = ARTICLE_PROCESSED_LINKS_FALLBACK_PATH + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(links, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, ARTICLE_PROCESSED_LINKS_FALLBACK_PATH)
    except Exception as e:
        print(f"⚠️ Lỗi lưu local processed links: {e}")

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

class ArticlePipelineCore:
    def __init__(self):
        self.cat_crawler = CategoryCrawler()
        self.art_crawler = ArticleCrawler()
        self.img_searcher = ImageSearcher()
        self.temp_dir = os.path.join(PROJECT_ROOT, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

    def _is_article_processed(self, url):
        normalized_url = _normalize_article_url(url)
        if not normalized_url:
            return False
        for attempt in range(3):
            try:
                res = supabase_client.table("processed_links").select("url").eq("url", normalized_url).execute()
                if len(res.data) > 0:
                    return True
                break
            except Exception as e:
                if attempt == 2:
                    print(f"⚠️ Lỗi check processed_links trên Supabase: {e}")
                else:
                    import time, random
                    time.sleep(random.uniform(0.5, 1.5))
        if _is_link_in_local_processed(normalized_url):
            return True
        return normalized_url in set(_load_db_processed_links())

    def _mark_article_processed(self, url):
        normalized_url = _normalize_article_url(url)
        if not normalized_url:
            return
        with ARTICLE_PROCESSED_STORE_LOCK:
            _mark_link_local_processed(normalized_url)
            _mark_link_db_processed(normalized_url)
            for attempt in range(3):
                try:
                    existing = supabase_client.table("processed_links").select("url").eq("url", normalized_url).execute()
                    if not existing.data:
                        supabase_client.table("processed_links").insert({"url": normalized_url}).execute()
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"⚠️ Supabase chặn lưu processed_links, đã lưu database system_configs/local fallback: {e}")
                    else:
                        import time, random
                        time.sleep(random.uniform(0.5, 1.5))

    def process_channel_independently(
        self,
        id_tiktok,
        channel_sources,
        success_limit=ARTICLE_SUCCESS_BATCH_SIZE,
    ):
        """Chạy một profile đến khi đủ số video thành công rồi nhường kênh.

        ``success_limit`` chỉ đếm bài đã upload Drive và ghi Sheet xong. Các
        bài được loại có chủ đích vẫn được đánh dấu đã xem nhưng không làm
        giảm phần sản lượng của kênh.
        """
        completed_count = 0
        print(
            f"\n[KÊNH {id_tiktok}] 🟢 Mở lượt xử lý với "
            f"{len(channel_sources)} danh mục báo; mục tiêu "
            f"{success_limit} video thành công."
        )
        
        for source in channel_sources:
            if completed_count >= success_limit:
                break
            sid = source["id"]
            category_url = source["category_url"]
            last_article_url = source.get("last_article_url")
            
            print(f"\n[KÊNH {id_tiktok}] 📡 Quét danh mục: {category_url}")
            
            # Lấy metadata nhẹ của 20 bài để xếp hạng trước khi crawl/AI.
            candidates = self.cat_crawler.get_latest_article_candidates(
                category_url,
                max_links=20,
            )
            if not candidates:
                print(f"[KÊNH {id_tiktok}] ⚠️ Không tìm thấy bài báo nào trong danh mục.")
                continue

            batch_urls = []
            handled_urls = set()
            eligible_candidates = []
            normalized_last_article_url = _normalize_article_url(last_article_url)
            for candidate in candidates:
                link = candidate.get("url", "")
                normalized_link = _normalize_article_url(link)
                if normalized_link and normalized_link == normalized_last_article_url:
                    break
                if not normalized_link:
                    continue
                batch_urls.append(normalized_link)
                if self._is_article_processed(normalized_link):
                    print(f"[KÊNH {id_tiktok}] ⏭️ Bỏ qua link đã tồn tại: {normalized_link}")
                    handled_urls.add(normalized_link)
                    continue
                eligible_candidates.append(candidate)

            editorial_profile = get_content_profile(id_tiktok)
            ranked_candidates = rank_candidates(
                eligible_candidates,
                editorial_profile,
                source_type="article",
            )
            links_to_process = []
            for candidate in ranked_candidates:
                link = candidate.get("url", "")
                source_rank = candidate.get("source_rank", {})
                if not should_process_candidate(candidate):
                    print(
                        f"[KÊNH {id_tiktok}] ⏭️ SourceRanker loại bài "
                        f"{source_rank.get('total_score', 0)}/100: {link}"
                    )
                    handled_urls.add(_normalize_article_url(link))
                    continue
                rights = guard_source_rights(candidate, source)
                if not rights.passed:
                    print(
                        f"[KÊNH {id_tiktok}] ⛔ RightsGuard chặn nguồn: "
                        f"{' '.join(rights.errors)}"
                    )
                    handled_urls.add(_normalize_article_url(link))
                    continue
                if rights.requires_review:
                    print(
                        f"[KÊNH {id_tiktok}] ⚠️ RightsGuard: "
                        f"{' '.join(rights.warnings)}"
                    )
                links_to_process.append(candidate)
                
            if links_to_process:
                print(
                    f"[KÊNH {id_tiktok}] 🔥 SourceRanker chọn "
                    f"{len(links_to_process)} bài; xử lý điểm cao trước."
                )
            else:
                print(f"[KÊNH {id_tiktok}] ✅ Không còn bài cần sản xuất trong batch.")
            
            for article_index, candidate in enumerate(links_to_process):
                if completed_count >= success_limit:
                    print(
                        f"[KÊNH {id_tiktok}] 🔄 Đã hoàn thành đủ "
                        f"{success_limit} video; chuyển sang profile kế tiếp."
                    )
                    break
                # Nghỉ giữa các bài để ChatGPT không bị dồn request liên tục
                # (nguyên nhân chính của popup "Too many requests"). Điều chỉnh
                # bằng ARTICLE_DELAY_SECONDS trong .env; 0 = không nghỉ.
                if article_index > 0 and ARTICLE_DELAY_SECONDS > 0:
                    print(
                        f"[KÊNH {id_tiktok}] ⏸️ Nghỉ {ARTICLE_DELAY_SECONDS}s "
                        "trước bài kế tiếp để tránh quá tải ChatGPT..."
                    )
                    time.sleep(ARTICLE_DELAY_SECONDS)
                article_url = candidate["url"]
                source_rank = candidate.get("source_rank", {})
                processed_url = _reserve_article_link(article_url)
                if not processed_url:
                    print(
                        f"[KÊNH {id_tiktok}] ⏭️ Bỏ qua link đang được "
                        f"luồng khác xử lý: {_normalize_article_url(article_url)}"
                    )
                    continue
                print(f"\n[KÊNH {id_tiktok}] 🕷️ Đang xử lý: {article_url}")
                print(
                    f"[KÊNH {id_tiktok}] 🧭 SourceRanker: "
                    f"{source_rank.get('total_score', 0)}/100 "
                    f"({source_rank.get('status', 'unscored')})"
                )
                try:
                    if self._is_article_processed(processed_url):
                        print(f"[KÊNH {id_tiktok}] ⏭️ Link vừa được lưu bởi tiến trình khác, bỏ qua: {processed_url}")
                        continue

                    result = self.process_single_article(id_tiktok, sid, article_url)
                    
                    if not result:
                        print(
                            f"[KÊNH {id_tiktok}] ❌ Xử lý thất bại bài "
                            f"{article_url}. Giữ lại để thử ở vòng sau và "
                            "tiếp tục tìm bài khác cho đủ sản lượng."
                        )
                        continue
                    else:
                        # Lưu chống trùng ngay; checkpoint danh mục cập nhật sau cả batch.
                        try:
                            self._mark_article_processed(processed_url)
                            handled_urls.add(processed_url)
                            print(f"[KÊNH {id_tiktok}] ✅ Đã lưu link đã xử lý: {processed_url}")
                        except Exception as e:
                            print(f"[KÊNH {id_tiktok}] ⚠️ Lỗi cập nhật DB: {e}")
                        if result is True:
                            completed_count += 1
                            print(
                                f"[KÊNH {id_tiktok}] 🎬 Sản lượng lượt này: "
                                f"{completed_count}/{success_limit} video."
                            )
                finally:
                    _release_article_link(processed_url)

            batch_fully_handled = batch_urls and all(
                url in handled_urls for url in batch_urls
            )
            if batch_fully_handled:
                safe_checkpoint = batch_urls[0]
                try:
                    supabase_client.table("article_sources").update({
                        "last_article_url": safe_checkpoint,
                    }).eq("id", sid).execute()
                    print(
                        f"[KÊNH {id_tiktok}] ☁️ Batch hoàn tất, cập nhật "
                        f"last_article_url an toàn: {safe_checkpoint}"
                    )
                except Exception as e:
                    print(f"[KÊNH {id_tiktok}] ⚠️ Lỗi cập nhật checkpoint: {e}")
            elif batch_urls:
                print(
                    f"[KÊNH {id_tiktok}] 📥 Giữ nguyên last_article_url vì "
                    f"batch còn bài chưa xử lý."
                )
                        
            print(f"[KÊNH {id_tiktok}] 🏁 Hoàn thành danh mục: {category_url}. Chuyển sang danh mục tiếp theo...")
            
        print(
            f"\n[KÊNH {id_tiktok}] 🛑 Kết thúc lượt: "
            f"{completed_count}/{success_limit} video thành công."
        )
        return completed_count

    def process_single_article(
        self,
        id_tiktok,
        sid,
        article_url,
        *,
        operator_instruction="",
        manual_approval=False,
        on_success=None,
        on_error=None,
    ):
        """Xử lý 1 bài báo từ A-Z. Trả về True nếu upload thành công, False nếu lỗi."""
        if self._is_article_processed(article_url):
            print(f"   [KÊNH {id_tiktok}] ⏭️ Link đã tồn tại trong kho chống trùng, không xử lý lại: {_normalize_article_url(article_url)}")
            return True

        job_dir = os.path.join(self.temp_dir, f"article_{int(time.time())}_{id_tiktok}")
        lifecycle = PipelineLifecycle("article", article_url)
        _trace_pipeline_step(id_tiktok, article_url, "selected", "start")
        quality_score = 0
        qa_result = None
        source_metadata = {
            "source_url": article_url,
            "content_hash": "",
        }
        try:
            # 1. Cào nội dung & Ảnh của bài báo
            _trace_pipeline_step(id_tiktok, article_url, "crawl", "started")
            article_data = self.art_crawler.crawl(article_url, job_dir)
            if not article_data:
                raise PipelineStageError(
                    "selected", "ARTICLE_CRAWL_FAILED",
                    "Không cào được nội dung bài báo.",
                )

            source_content = str(
                article_data.get("clean_content")
                or article_data.get("content")
                or ""
            ).strip()
            source_verification_text = str(
                article_data.get("clean_content_full")
                or source_content
            ).strip()
            source_metadata = {
                "source_url": article_data.get("source_url") or article_url,
                "content_hash": article_data.get("content_hash") or "",
            }
            if len(source_content) < 200:
                raise PipelineStageError(
                    "selected", "ARTICLE_CONTENT_TOO_THIN",
                    "Nội dung sạch của bài báo quá ngắn để kiểm chứng và viết kịch bản.",
                    retryable=False,
                )

            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "crawl",
                "completed",
                metadata={
                    "content_chars": len(source_content),
                    "images": len(article_data.get("images") or []),
                    "videos": len(article_data.get("videos") or []),
                },
            )

            # 2. Gửi nội dung cho AI phân tích qua AI Provider đã chọn (Gemini / ChatGPT)
            active_provider = get_configured_ai_provider().upper()
            _trace_pipeline_step(id_tiktok, article_url, "ai_script", "started")
            art_title = str(article_data.get("title") or "")
            art_content = str(article_data.get("clean_content") or article_data.get("content") or "")
            ai_result = analyze_article_content(
                article_title=art_title,
                article_content=art_content,
                article_url=article_url,
                id_tiktok=id_tiktok,
                extra_content=operator_instruction,
            )
            if not ai_result:
                raise PipelineStageError(
                    "scripted", "SCRIPT_GENERATION_FAILED",
                    f"AI Provider ({active_provider}) phân tích thất bại.",
                )
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "ai_script",
                "completed",
                metadata={"hook_chars": len(str(ai_result.get("hook") or ""))},
            )
            lifecycle.advance("scripted")

            editorial_profile = get_content_profile(id_tiktok)
            _trace_pipeline_step(id_tiktok, article_url, "content_validation", "started")
            prepared_content = prepare_content_with_single_repair(
                ai_result,
                source_type="article",
                channel_id=id_tiktok,
                source_url=article_url,
                profile=editorial_profile,
                repair_callback=lambda instruction: analyze_article_content(
                    article_title=art_title,
                    article_content=art_content,
                    article_url=article_url,
                    id_tiktok=id_tiktok,
                    extra_content=operator_instruction,
                    repair_instruction=instruction,
                ),
            )
            ai_result = prepared_content.content
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "content_validation",
                "completed" if prepared_content.report.passed else "failed",
                message=summarize_validation(prepared_content.report),
                metadata={
                    "score": prepared_content.report.content_score,
                    "repair_attempts": prepared_content.repair_attempts,
                },
            )
            if prepared_content.repair_attempts:
                repair_status = "đạt" if prepared_content.repaired else "chưa đạt"
                print(
                    f"   [KÊNH {id_tiktok}] 🔧 Đã sửa kịch bản 1 lần: "
                    f"{repair_status}."
                )

            should_make_video = ai_result.get("should_make_video", True)
            if manual_approval:
                should_make_video = True
            if str(should_make_video).lower() == "false" or not should_make_video:
                skip_reason = ai_result.get("skip_reason", "")
                _trace_pipeline_step(
                    id_tiktok, article_url, "topic_fit", "skipped", message=skip_reason
                )
                print(
                    f"   [KÊNH {id_tiktok}] ⏭️ AI đánh giá không nên làm "
                    f"video này. {skip_reason}"
                )
                _append_quality_log(
                    "article",
                    id_tiktok,
                    int(ai_result.get("quality_score", 0)),
                    "skip",
                    skip_reason,
                    **source_metadata,
                )
                return "skipped"

            topic_fit = ai_result.get("topic_fit", True)
            # TẠM THỜI TẮT LỌC NỘI DUNG THEO YÊU CẦU
            topic_fit = True
            if str(topic_fit).lower() == "false" or not topic_fit:
                topic_fit_reason = ai_result.get("topic_fit_reason") or ai_result.get("skip_reason", "")
                _trace_pipeline_step(
                    id_tiktok,
                    article_url,
                    "topic_fit",
                    "skipped",
                    message=topic_fit_reason,
                )
                print(f"   [KÊNH {id_tiktok}] ⏭️ Bài không đúng định vị kênh → bỏ qua. {topic_fit_reason}")
                _append_quality_log(
                    "article", id_tiktok,
                    int(ai_result.get("quality_score", 0)),
                    "skip", topic_fit_reason,
                    **source_metadata,
                )
                return "skipped"

            if not prepared_content.report.passed:
                validation_reason = summarize_validation(prepared_content.report)
                print(
                    f"   [KÊNH {id_tiktok}] ⏭️ ContentValidator không đạt "
                    f"→ bỏ qua. {validation_reason}"
                )
                _append_quality_log(
                    "article",
                    id_tiktok,
                    int(ai_result.get("quality_score", 0)),
                    "skip",
                    validation_reason,
                    **source_metadata,
                )
                # Không đánh dấu link là đã xử lý khi nội dung bị quality
                # gate từ chối; sau khi sửa prompt/AI, pipeline cần thử lại.
                return False
            print(
                f"   [KÊNH {id_tiktok}] ✅ ContentValidator: "
                f"{prepared_content.report.content_score}/100"
            )

            source_evidence_text = " ".join(
                str(value or "")
                for value in (
                    article_data.get("title"),
                    source_verification_text,
                )
            )
            _trace_pipeline_step(id_tiktok, article_url, "evidence_guard", "started")
            evidence_report = guard_evidence(
                ai_result,
                source_type="article",
                source_url=article_url,
                source_text=source_evidence_text,
                profile=editorial_profile,
            )
            try:
                quality_threshold = int(
                    os.environ.get("EDITORIAL_QUALITY_THRESHOLD", "70")
                )
            except (TypeError, ValueError):
                quality_threshold = 70
            _trace_pipeline_step(id_tiktok, article_url, "source_rights", "started")
            rights_report = guard_source_rights(article_data)
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "source_rights",
                "completed" if rights_report.passed else "failed",
                message="; ".join(rights_report.errors or rights_report.warnings),
                metadata={"status": rights_report.status},
            )
            editorial_report = evaluate_editorial_quality(
                ai_result,
                validation_report=prepared_content.report,
                evidence_report=evidence_report,
                rights_report=rights_report,
                threshold=quality_threshold,
            )
            # ``score`` is a legacy Telegram/dashboard field that is displayed
            # on a 0-10 scale. Keep it compatible while exposing the actual
            # deterministic gate result in ``editorial_score``.
            legacy_editorial_score = max(
                0, min(10, int(round(editorial_report.score / 10)))
            )
            ai_quality_score = int(ai_result.get("quality_score", 0) or 0)
            quality_metadata = {
                **source_metadata,
                "editorial_score": editorial_report.score,
                "ai_quality_score": ai_quality_score,
                "quality_breakdown": editorial_report.breakdown,
            }
            if not EVIDENCE_GUARD_ENABLED:
                print(
                    f"   [KÊNH {id_tiktok}] ⏭️ EvidenceGuard đã tắt; "
                    "tiếp tục xử lý bài báo."
                )
            elif not evidence_report.passed:
                evidence_reason = summarize_evidence(evidence_report)
                _trace_pipeline_step(
                    id_tiktok,
                    article_url,
                    "evidence_guard",
                    "failed",
                    message=evidence_reason,
                )
                print(
                    f"   [KÊNH {id_tiktok}] ⏭️ EvidenceGuard không đạt "
                    f"→ bỏ qua. {evidence_reason}"
                )
                _append_quality_log(
                    "article",
                    id_tiktok,
                    legacy_editorial_score,
                    "skip",
                    evidence_reason,
                    **quality_metadata,
                )
                return False
            else:
                print(
                    f"   [KÊNH {id_tiktok}] ✅ EvidenceGuard: "
                    f"{evidence_report.score}/100"
                )

            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "evidence_guard",
                "completed",
                metadata={"score": evidence_report.score},
            )
            _trace_pipeline_step(id_tiktok, article_url, "visual_grounding", "started")
            visual_report = guard_visual_grounding(
                ai_result,
                source_type="article",
                source_text=source_evidence_text,
            )
            quality_metadata.update({
                "visual_grounding_score": visual_report.score,
                "visual_grounding": visual_report.to_dict(),
            })
            if not visual_report.passed:
                visual_reason = summarize_visual_grounding(visual_report)
                _trace_pipeline_step(
                    id_tiktok,
                    article_url,
                    "visual_grounding",
                    "failed",
                    message=visual_reason,
                )
                print(
                    f"   [KÊNH {id_tiktok}] ⏭️ Visual grounding không đạt "
                    f"→ bỏ qua. {visual_reason}"
                )
                _append_quality_log(
                    "article", id_tiktok, legacy_editorial_score,
                    "skip", visual_reason, **quality_metadata,
                )
                return False

            # Quality gate độc lập: không đọc ai_result["quality_score"] để quyết định.
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "visual_grounding",
                "completed",
                metadata={"score": visual_report.score},
            )
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "quality_gate",
                "started",
                metadata={"score": editorial_report.score},
            )
            if not editorial_report.passed:
                gate_reason = summarize_quality_gate(editorial_report)
                _trace_pipeline_step(
                    id_tiktok,
                    article_url,
                    "quality_gate",
                    "failed",
                    message=gate_reason,
                    metadata={"score": editorial_report.score},
                )
                print(
                    f"   [KÊNH {id_tiktok}] ⏭️ Editorial Quality Gate: "
                    f"{gate_reason}"
                )
                _append_quality_log(
                    "article", id_tiktok, legacy_editorial_score, "skip", gate_reason,
                    **quality_metadata,
                )
                return False
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "quality_gate",
                "completed",
                metadata={"score": editorial_report.score},
            )
            quality_score = legacy_editorial_score
            source_metadata = quality_metadata
            print(
                f"   [KÊNH {id_tiktok}] ✅ Editorial Quality Gate: "
                f"{editorial_report.score}/100 "
                f"(AI tham khảo: {ai_quality_score}/10)"
            )
            lifecycle.advance("validated")
            _append_quality_log(
                "article", id_tiktok, quality_score, "validated",
                stage="validated", item_id=article_url,
                **source_metadata,
            )

            # 3. Gom ảnh gốc & Tìm thêm ảnh
            # Giữ ảnh lead vì thường là ảnh đúng nhân vật/sự kiện nhất.
            _trace_pipeline_step(id_tiktok, article_url, "media_assets", "started")
            downloaded_imgs = article_data.get("images", [])[:7]
            downloaded_image_assets = [
                asset for asset in (article_data.get("image_assets") or [])
                if isinstance(asset, dict)
            ][:7]
            asset_by_path = {
                str(asset.get("path") or asset.get("local_path")): asset
                for asset in downloaded_image_assets
                if str(asset.get("path") or asset.get("local_path") or "").strip()
            }
            for image_path in downloaded_imgs:
                asset_by_path.setdefault(
                    str(image_path),
                    {
                        "path": image_path,
                        "source_url": article_data.get("source_url") or article_url,
                        "source_name": article_data.get("source_name") or "article",
                        "rights_status": "unknown",
                    },
                )
            downloaded_videos = article_data.get("videos", [])
            
            if not downloaded_imgs:
                print(f"   [KÊNH {id_tiktok}] ⚠️ Bài báo không có ảnh gốc, sẽ tìm toàn bộ ảnh từ DuckDuckGo...")
            
            # 9-10 ảnh giúp video 22-30 giây đổi hình gần mỗi 2-3 giây.
            TARGET_IMAGES = 10
            if len(downloaded_imgs) < TARGET_IMAGES:
                scenes = ai_result.get("scenes", [])
                search_prompts = [s.get("visual_description", "") for s in scenes if len(s.get("visual_description", "")) > 10]
                needed = TARGET_IMAGES - len(downloaded_imgs)
                if search_prompts:
                    search_prompts = search_prompts[:needed]
                    print(f"   [KÊNH {id_tiktok}] 🔎 Thiếu ảnh, đang tìm thêm {needed} ảnh từ DuckDuckGo...")
                    extra_imgs = self.img_searcher.download_missing_images(
                        search_prompts, job_dir, channel_id=id_tiktok,
                    )
                    downloaded_imgs.extend(extra_imgs)
                    for asset in getattr(self.img_searcher, "last_download_metadata", []):
                        if isinstance(asset, dict):
                            asset_path = str(asset.get("path") or asset.get("local_path") or "")
                            if asset_path:
                                asset_by_path[asset_path] = asset
                    for image_path in downloaded_imgs:
                        asset_by_path.setdefault(
                            str(image_path),
                            {
                                "path": image_path,
                                "source_url": article_data.get("source_url") or article_url,
                                "source_name": article_data.get("source_name") or "article",
                                "rights_status": "unknown",
                            },
                        )
            
            if not downloaded_imgs:
                raise PipelineStageError(
                    "rendered", "MEDIA_ASSETS_MISSING",
                    "Không tìm được ảnh phù hợp để dựng video.",
                )
            
            downloaded_image_assets = [
                asset_by_path[str(image_path)]
                for image_path in downloaded_imgs
                if str(image_path) in asset_by_path
            ]
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "media_assets",
                "completed",
                metadata={"images": len(downloaded_imgs), "videos": len(downloaded_videos)},
            )
            _trace_pipeline_step(id_tiktok, article_url, "image_rights", "started")
            image_rights_report = guard_image_assets(downloaded_image_assets)
            source_metadata.update({"image_rights": image_rights_report.to_dict()})
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "image_rights",
                "completed" if image_rights_report.passed else "failed",
                message="; ".join(image_rights_report.errors),
                metadata={"status": image_rights_report.status},
            )
            if image_rights_report.warnings:
                print(
                    f"   [KÊNH {id_tiktok}] ⚠️ Image rights review: "
                    + "; ".join(image_rights_report.warnings)
                )
            if not image_rights_report.passed:
                raise PipelineStageError(
                    "selected",
                    "IMAGE_RIGHTS_FAILED",
                    "Image rights không đạt: " + "; ".join(image_rights_report.errors),
                    retryable=False,
                )

            print(f"   [KÊNH {id_tiktok}] 📸 Tổng số ảnh để làm video: {len(downloaded_imgs)}, Số video: {len(downloaded_videos)}")
            
            # 4. Sinh Voice
            print(f"   [KÊNH {id_tiktok}] 🗣️ Bắt đầu sinh Voice OmniVoice...")
            _trace_pipeline_step(id_tiktok, article_url, "voice", "started")
            # The opening voice is the AI hook (not the raw source title).  Keep
            # the text stable and visible in logs so a short TTS response can be
            # distinguished from an intentionally short hook.
            hook_text = str(ai_result.get('hook', '') or '').strip()
            script_text = str(ai_result.get('script_voice', '') or '').strip()
            print(
                f"   [KÊNH {id_tiktok}] 📝 Hook voice: {len(hook_text.split())} từ, "
                f"{len(hook_text)} ký tự | Script voice: {len(script_text.split())} từ, "
                f"{len(script_text)} ký tự | Nội dung hook: {hook_text[:180]}",
                flush=True,
            )
            
            tone = ai_result.get("tone", "Trung tính")
            music_mood = ai_result.get("music_mood")
            music_energy = ai_result.get("music_energy", 2)
            is_sensitive = ai_result.get("is_sensitive", False)
            channel_voice_id = VOICE_PROFILE_ID
            channel_voice_speed = get_channel_voice_speed(
                id_tiktok,
                story_type=ai_result.get("story_type", ""),
                tone=tone,
                is_sensitive=bool(is_sensitive),
            )
            try:
                channel_dir = os.path.join(PROJECT_ROOT, "assets", "channels", id_tiktok)
                voice_cfg_path = os.path.join(channel_dir, "voice_config.json")
                if os.path.exists(voice_cfg_path):
                    with open(voice_cfg_path, "r", encoding="utf-8") as f:
                        voice_cfg = json.load(f)
                        
                        tone_id = voice_cfg.get(tone, "").strip()
                        neutral_id = voice_cfg.get("Trung tính", "").strip()
                        
                        if tone_id:
                            channel_voice_id = tone_id
                        elif neutral_id:
                            channel_voice_id = neutral_id
            except Exception: pass
            channel_voice_speed = TARGET_VOICE_SPEED
            
            print(f"   [KÊNH {id_tiktok}] 🎵 Tone: {tone} -> Voice ID: {channel_voice_id} | Speed: {channel_voice_speed}")

            voice_hook_path = None
            voice_script_path = None
            
            try:
                if hook_text:
                    voice_hook_path = create_voice_full_pipeline(
                        hook_text, job_dir, "hook_voice.wav", channel_voice_id, speed=channel_voice_speed
                    )
                if script_text:
                    voice_script_path = create_voice_full_pipeline(
                        script_text, job_dir, "script_voice.wav", channel_voice_id, speed=channel_voice_speed
                    )
            except Exception as e:
                raise PipelineStageError(
                    "voiced", "TTS_FAILED", f"Lỗi sinh voice: {e}",
                ) from e
                
            # Không được âm thầm bỏ qua một đoạn voice đã có trong kịch bản.
            # Trước đây TTS lỗi/trả file cụt vẫn cho pipeline chạy tiếp nếu
            # đoạn còn lại tồn tại, khiến video mở đầu bị mất tiếng.
            if hook_text and not voice_hook_path:
                raise PipelineStageError(
                    "voiced", "TTS_FAILED",
                    "Không tạo được hook_voice; không tiếp tục dựng video bị mất câu mở đầu.",
                )
            if script_text and not voice_script_path:
                raise PipelineStageError(
                    "voiced", "TTS_FAILED",
                    "Không tạo được script_voice; không tiếp tục dựng video thiếu lời đọc.",
                )

            # 5. Dựng Video
            if not downloaded_imgs or (not voice_hook_path and not voice_script_path):
                raise PipelineStageError(
                    "voiced", "TTS_FAILED", "Thiếu ảnh hoặc voice để dựng video.",
                )
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "voice",
                "completed",
                metadata={
                    "hook_voice": bool(voice_hook_path),
                    "script_voice": bool(voice_script_path),
                    "hook_words": len(hook_text.split()),
                    "script_words": len(script_text.split()),
                    "hook_duration": round(probe_audio_duration(voice_hook_path), 3),
                    "script_duration": round(probe_audio_duration(voice_script_path), 3),
                },
            )
            lifecycle.advance("voiced")
                
            print(f"   [KÊNH {id_tiktok}] 🎬 Đang dựng FFmpeg...")
            _trace_pipeline_step(id_tiktok, article_url, "render", "started")
            output_video_path = os.path.join(job_dir, f"final_{id_tiktok}_{int(time.time())}.mp4")
            
            # Nếu có video gốc từ báo, truyền video đầu tiên vào (nếu có nhiều lấy 1)
            appended_video_path = downloaded_videos[0] if downloaded_videos else None
            try:
                create_article_video(
                    id_tiktok=id_tiktok,
                    image_paths=downloaded_imgs,
                    hook_voice_path=voice_hook_path,
                    script_voice_path=voice_script_path,
                    output_path=output_video_path,
                    hook_text=hook_text,
                    appended_video_path=appended_video_path,
                    tone=tone,
                    script_text=script_text,
                    music_mood=music_mood,
                    music_energy=music_energy,
                    is_sensitive=is_sensitive,
                    beats=ai_result.get("beats"),
                    subtitle_style=ai_result.get(
                        "subtitle_style", "keyword_highlight",
                    ),
                )
            except Exception as error:
                raise PipelineStageError(
                    "rendered", "RENDER_FAILED", f"Render FFmpeg lỗi: {error}",
                ) from error

            if not os.path.exists(output_video_path):
                raise PipelineStageError(
                    "rendered", "RENDER_FAILED",
                    "Render FFmpeg không tạo ra file MP4.",
                )
            lifecycle.advance("rendered")
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "render",
                "completed",
                metadata={"output": output_video_path},
            )

            subtitle_ass_path = output_video_path.replace(".mp4", "_body.ass")
            _trace_pipeline_step(id_tiktok, article_url, "video_qa", "started")
            qa_result = run_video_qa(
                output_video_path,
                subtitle_ass_path=(
                    subtitle_ass_path if os.path.exists(subtitle_ass_path) else ""
                ),
                watermark_detected=bool(article_data.get("watermark_detected")),
            )
            # Một số video nhúng từ bài báo có đoạn mở đầu đen hoặc PTS lỗi.
            # Thử bản slideshow không chèn video nhúng trước khi bỏ hẳn bài;
            # không hạ ngưỡng VideoQA và chỉ áp dụng khi bản có video nhúng bị
            # đúng lỗi BLACK_FRAME_DETECTED.
            if (
                not qa_result.passed
                and "BLACK_FRAME_DETECTED" in qa_result.blocking_errors
                and appended_video_path
            ):
                print(
                    f"   [KÊNH {id_tiktok}] ⚠️ Video chèn có khung đen; "
                    "đang dựng lại bản slideshow không chèn video nguồn...",
                    flush=True,
                )
                try:
                    create_article_video(
                        id_tiktok=id_tiktok,
                        image_paths=downloaded_imgs,
                        hook_voice_path=voice_hook_path,
                        script_voice_path=voice_script_path,
                        output_path=output_video_path,
                        hook_text=hook_text,
                        appended_video_path=None,
                        tone=tone,
                        script_text=script_text,
                        music_mood=music_mood,
                        music_energy=music_energy,
                        is_sensitive=is_sensitive,
                        beats=ai_result.get("beats"),
                        subtitle_style=ai_result.get(
                            "subtitle_style", "keyword_highlight",
                        ),
                    )
                    qa_result = run_video_qa(
                        output_video_path,
                        subtitle_ass_path=(
                            subtitle_ass_path if os.path.exists(subtitle_ass_path) else ""
                        ),
                        watermark_detected=bool(article_data.get("watermark_detected")),
                    )
                except Exception as fallback_error:
                    print(
                        f"   [KÊNH {id_tiktok}] ⚠️ Không dựng được bản slideshow dự phòng: "
                        f"{fallback_error}",
                        flush=True,
                    )
            if not qa_result.passed:
                _trace_pipeline_step(
                    id_tiktok,
                    article_url,
                    "video_qa",
                    "failed",
                    message=", ".join(qa_result.blocking_errors),
                    error_code=qa_result.error_code or "VIDEO_QA_FAILED",
                )
                # Ghi lại toàn bộ số liệu QA trước khi ném lỗi; nếu không,
                # video bị dọn cùng thư mục job và không còn cách nào biết
                # thông số thật đã sai ở đâu.
                print(
                    f"   [KÊNH {id_tiktok}] 🔍 QA thực tế: "
                    f"codec={qa_result.video_codec} pix_fmt={qa_result.pixel_format} "
                    f"res={qa_result.resolution} fps={qa_result.fps} "
                    f"audio={qa_result.audio_codec}/{qa_result.audio_sample_rate}/"
                    f"{qa_result.audio_channels} lufs={qa_result.integrated_lufs}"
                )
                _append_quality_log(
                    "article", id_tiktok, quality_score, "failed",
                    stage="qa_passed", item_id=article_url,
                    qa=qa_result.to_dict(),
                    **source_metadata,
                )
                raise PipelineStageError(
                    "qa_passed",
                    qa_result.error_code or "VIDEO_QA_FAILED",
                    "VideoQA chặn upload: " + ", ".join(qa_result.blocking_errors),
                )
            lifecycle.advance("qa_passed")
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "video_qa",
                "completed",
                metadata=qa_result.to_dict(),
            )
            _append_quality_log(
                "article", id_tiktok, quality_score, "qa_passed",
                stage="qa_passed", item_id=article_url,
                qa=qa_result.to_dict(),
                **source_metadata,
            )
            
            # 6. Upload & Lưu Google Sheet
            _trace_pipeline_step(id_tiktok, article_url, "upload", "started")
            drive_link = None
            print(f"   [KÊNH {id_tiktok}] ☁️ Đang upload Google Drive...")
            try:
                from shared.modules.upload_drive import upload_video_to_drive
                gdrive_folder_id = ENV.get("DRIVE_FOLDER_ID", ENV.get("GDRIVE_FOLDER_ID", "1VgkkbUJ82kxzWXJH8cfn7UFMMFBKQkzS"))
                drive_link = upload_video_to_drive(output_video_path, gdrive_folder_id)
            except Exception as error:
                raise PipelineStageError(
                    "uploaded", "UPLOAD_FAILED", f"Lỗi upload Drive: {error}",
                ) from error
            if not drive_link:
                raise PipelineStageError(
                    "uploaded", "UPLOAD_FAILED", "Google Drive trả về link rỗng.",
                )
            lifecycle.advance("uploaded")
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                "upload",
                "completed",
                metadata={"drive_link": drive_link},
            )
            _append_quality_log(
                "article", id_tiktok, quality_score, "uploaded",
                stage="uploaded", item_id=article_url,
                qa=qa_result.to_dict(),
                **source_metadata,
            )
            print(f"   [KÊNH {id_tiktok}] ✅ Upload xong: {drive_link}")
                
            if drive_link:
                print(f"   [KÊNH {id_tiktok}] 📊 Ghi Sheet...")
                _trace_pipeline_step(id_tiktok, article_url, "sheet", "started")
                sheet_result = save_article_to_sheet(ai_result, article_url, id_tiktok)
                if not sheet_result or sheet_result.get("status") != "success":
                    raise PipelineStageError(
                        "uploaded",
                        "SHEET_SAVE_FAILED",
                        "Video đã lên Drive nhưng chưa ghi được Google Sheet.",
                    )
                _trace_pipeline_step(
                    id_tiktok,
                    article_url,
                    "sheet",
                    "completed",
                    metadata={"row": sheet_result.get("row") if sheet_result else None},
                )
                sheet_row = sheet_result.get("row") if sheet_result else None
                if not sheet_row:
                    raise PipelineStageError(
                        "uploaded",
                        "SHEET_ROW_MISSING",
                        "Google Sheet báo thành công nhưng không trả về dòng dữ liệu.",
                    )
                from article_sheet_api import update_article_drive_link
                try:
                    sheet_name = "facebook" if id_tiktok == "Adsupnews" else "tổng"
                    link_saved = update_article_drive_link(
                        sheet_row, drive_link, sheet_name
                    )
                except Exception as error:
                    raise PipelineStageError(
                        "uploaded",
                        "SHEET_DRIVE_LINK_FAILED",
                        f"Chưa ghi được link Drive vào Google Sheet: {error}",
                    ) from error
                if not link_saved:
                    raise PipelineStageError(
                        "uploaded",
                        "SHEET_DRIVE_LINK_FAILED",
                        "Google Sheet chưa xác nhận lưu link Drive.",
                    )
                # Manual Telegram jobs do not pass through
                # ``process_channel_independently``; persist the dedupe marker
                # here as well so the same URL cannot be queued repeatedly.
                try:
                    self._mark_article_processed(article_url)
                except Exception as marker_error:
                    print(f"   [KÊNH {id_tiktok}] ⚠️ Không lưu được link đã xử lý: {marker_error}")
                if on_success:
                    try:
                        on_success(drive_link, output_video_path, sheet_row)
                    except Exception as callback_error:
                        print(
                            f"   [KÊNH {id_tiktok}] ⚠️ Gửi thông báo thành công thất bại: "
                            f"{callback_error}"
                        )
                # Notifications are best-effort; a Telegram outage must not
                # turn an already uploaded article into a failed pipeline job.
                _trace_pipeline_step(id_tiktok, article_url, "done", "completed")
                return True
            raise PipelineStageError(
                "uploaded", "UPLOAD_FAILED", "Không có link Drive sau upload.",
            )

        except Exception as error:
            failure = lifecycle.fail_from_exception(error)
            _trace_pipeline_step(
                id_tiktok,
                article_url,
                failure.stage,
                "failed",
                message=failure.message,
                error_code=failure.error_code,
                retryable=failure.retryable,
            )
            _append_quality_log(
                "article", id_tiktok, quality_score, "failed",
                stage=failure.stage, item_id=article_url,
                error_code=failure.error_code,
                retryable=failure.retryable,
                message=failure.message,
                qa=qa_result.to_dict() if qa_result else None,
                **source_metadata,
            )
            print(
                f"   [KÊNH {id_tiktok}] ❌ {failure.error_code} "
                f"({failure.stage}): {failure.message}"
            )
            if on_error:
                try:
                    on_error(f"{failure.error_code}: {failure.message}")
                except Exception as callback_error:
                    print(
                        f"   [KÊNH {id_tiktok}] ⚠️ Gửi thông báo lỗi thất bại: "
                        f"{callback_error}"
                    )
            return False
        finally:
            self._cleanup_job(job_dir)

    def run_once(self):
        print("\n" + "="*50)
        print("🚀 KHỞI ĐỘNG CỖ MÁY BÁO MẠNG -> VIDEO (CHẠY SONG SONG THEO KÊNH)")
        print("="*50)
        
        try:
            res = supabase_client.table("article_sources").select("*").eq("is_active", True).execute()
            sources = res.data or []
        except Exception as e:
            print(f"❌ Lỗi lấy nguồn Database: {e}")
            return

        if not sources:
            print("📭 Không có nguồn báo nào đang bật.")
            return

        # Lọc theo danh sách kênh được chọn (nếu có tham số --channels)
        channels_arg = None
        if "--channels" in sys.argv:
            idx = sys.argv.index("--channels")
            channels_arg = sys.argv[idx+1].split(",")
            
        channels_map = {}
        # Thứ tự cố định giúp vòng quay profile không thay đổi ngẫu nhiên theo
        # thứ tự phản hồi của Supabase.
        ordered_sources = sorted(
            sources,
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("id_tiktok") or ""),
                str(item.get("id") or ""),
            ),
        )
        for source in ordered_sources:
            tid = source["id_tiktok"]
            if channels_arg and tid not in channels_arg:
                continue
            if tid not in channels_map:
                channels_map[tid] = []
            channels_map[tid].append(source)
            
        print(f"🌐 Tìm thấy {len(channels_map)} Kênh Tiktok cần chạy.")
        
        # Mỗi kênh có một worker và một ArticlePipelineCore riêng. Điều này
        # giữ crawler, thư mục tạm và vòng đời xử lý độc lập, đồng thời cho
        # phép các Chrome Article profile chạy song song.
        try:
            configured_workers = int(ENV.get("ARTICLE_MAX_CHANNEL_WORKERS", "0"))
        except (TypeError, ValueError):
            configured_workers = 0
        max_workers = min(
            len(channels_map),
            configured_workers if configured_workers > 0 else len(channels_map),
        )
        print(
            f"⚙️ Chạy song song {max_workers}/{len(channels_map)} kênh; "
            f"mỗi kênh tối đa {ARTICLE_SUCCESS_BATCH_SIZE} video thành công."
        )

        def run_channel(channel_item):
            id_tiktok, channel_sources = channel_item
            print(f"\n🔁 Khởi động worker độc lập cho kênh: {id_tiktok}")
            # Không dùng chung các crawler/editor state giữa các kênh.
            worker = ArticlePipelineCore()
            return id_tiktok, worker.process_channel_independently(
                id_tiktok,
                channel_sources,
                success_limit=ARTICLE_SUCCESS_BATCH_SIZE,
            )

        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="article-channel",
        ) as executor:
            futures = [
                executor.submit(run_channel, channel_item)
                for channel_item in channels_map.items()
            ]
            for future in as_completed(futures):
                try:
                    channel_id, completed_count = future.result()
                    print(
                        f"\n✅ Worker kênh {channel_id} kết thúc: "
                        f"{completed_count}/{ARTICLE_SUCCESS_BATCH_SIZE} video thành công."
                    )
                except Exception as exc:
                    # Một kênh lỗi không được làm dừng các kênh còn lại.
                    print(f"\n❌ Worker Article lỗi nhưng các kênh khác vẫn tiếp tục: {exc}")
            
        print("\n✅ TẤT CẢ CÁC KÊNH ĐÃ HOÀN THÀNH CHU TRÌNH.")

    def _cleanup_job(self, job_dir):
        if not os.path.exists(job_dir):
            return
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(job_dir):
                for f in filenames:
                    total_size += os.path.getsize(os.path.join(dirpath, f))
            size_mb = total_size / (1024 * 1024)
            shutil.rmtree(job_dir)
            print(f"   🧹 Dọn {size_mb:.1f} MB tạm của {os.path.basename(job_dir)}")
        except Exception as e:
            pass

    def _cleanup_old_jobs(self):
        if not os.path.exists(self.temp_dir):
            return
        old_jobs = [d for d in os.listdir(self.temp_dir) if os.path.isdir(os.path.join(self.temp_dir, d)) and d.startswith("article_")]
        total_freed = 0
        for job_name in old_jobs:
            job_path = os.path.join(self.temp_dir, job_name)
            try:
                for dirpath, dirnames, filenames in os.walk(job_path):
                    for f in filenames:
                        total_freed += os.path.getsize(os.path.join(dirpath, f))
                shutil.rmtree(job_path)
            except:
                pass
        if total_freed > 0:
            print(f"🧹 Đã dọn dẹp {len(old_jobs)} job cũ, giải phóng {total_freed / (1024*1024):.1f} MB")

    def run_loop(self):
        self._cleanup_old_jobs()
        while True:
            self.run_once()
            print("\n⏳ Chờ 30 phút để quét lại...")
            time.sleep(30 * 60)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run-once"
    core = ArticlePipelineCore()
    if mode == "start":
        core.run_loop()
    else:
        core.run_once()
