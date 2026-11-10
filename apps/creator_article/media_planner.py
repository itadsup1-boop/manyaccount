"""Lập kế hoạch tư liệu cho từng beat của storyboard kịch bản khoá.

Theo ``BRIEF_AGENT_DUNG_VIDEO_TIN_TUC.md`` §5/§6/§7:

- ``visual_query`` là brief, không phải lệnh: ``DATA GRAPHIC:``/``MAP GRAPHIC:``
  chuyển sang đồ hoạ, phần còn lại tìm B-roll thật trên Pexels.
- Không có asset đạt ngưỡng liên quan → ``no_asset_found`` (renderer dùng
  graphic fallback), không ép asset yếu vào cảnh.
- Mỗi asset tải về phải có record manifest đủ field theo §4; thiếu
  ``local_path``/provenance là bị loại.
- Một asset không dùng quá 2 lần trong một video.
- Asset tải về được quét logo/watermark thật trên pixel (KE_HOACH §8.3);
  phát hiện là bị loại về graphic fallback, lỗi quét cũng coi như phát hiện.

Module không chạm network khi test — ``http_get``/``http_download`` có thể bị
thay bằng fake qua tham số; ``watermark_scanner`` cũng inject được khi test.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from adsup_central_hub.backend.production_jobs import (
    JOB_ID_RE,
    JOBS_DIR,
    _atomic_write_json,
    load_job_artifact,
)
from apps.creator_article.stock_provider import (
    DEFAULT_USER_AGENT,
    HttpGet,
    get_pexels_api_key,
    get_stock_provider_config,
    search_pexels,
    search_stock,
)
from shared.modules.logo_scanner import scan_asset_watermark

PLAN_VERSION = "media_plan_v1"

MAX_USES_PER_ASSET = 2
DEFAULT_RELEVANCE_THRESHOLD = 0.3
MIN_DIMENSION = 1080
MAX_DIMENSION = 1920

PER_PAGE_CANDIDATES = 15

KIND_BROLL = "broll"
KIND_DATA_GRAPHIC = "data_graphic"
KIND_MAP_GRAPHIC = "map_graphic"
KIND_QUOTE_CARD = "quote_card"
KIND_FACT_CARD = "fact_card"
KIND_NO_ASSET = "no_asset_found"

GRAPHIC_KINDS = (
    KIND_DATA_GRAPHIC,
    KIND_MAP_GRAPHIC,
    KIND_QUOTE_CARD,
    KIND_FACT_CARD,
)

_DOWNLOAD_TIMEOUT_SECONDS = 60

HttpDownload = Callable[[str, str], int]
WatermarkScanner = Callable[[str, str], Any]

_STOPWORDS = {
    "the", "a", "an", "of", "at", "on", "in", "with", "for", "and", "to",
    "by", "from", "is", "are", "và", "va", "của", "cua", "các", "cac",
    "những", "nhung", "cho", "trong", "với", "voi",
    # Các từ mô tả phong cách/thông số này hữu ích với người viết prompt, nhưng
    # không phải tín hiệu ngữ nghĩa tốt để đối chiếu title/description ngắn từ
    # Pexels. Giữ chúng trong query thường làm asset thật bị loại oan.
    "real", "realistic", "authentic", "modern", "generic", "contextual",
    "vietnam", "vietnamese", "daylight", "indoor", "outdoor", "close",
    "up", "wide", "shot", "footage", "video", "photo", "image", "stock",
    "no", "logo", "logos", "watermark", "watermarks", "without",
}

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def classify_visual_query(query: str) -> tuple[str, str]:
    """Trả về ``(kind, search_query)`` theo quy ước tiền tố BRIEF §5."""

    text = str(query or "").strip()
    lowered = text.lower()
    for prefix, kind in (
        ("data graphic:", KIND_DATA_GRAPHIC),
        ("map graphic:", KIND_MAP_GRAPHIC),
        ("quote card:", KIND_QUOTE_CARD),
        ("fact card:", KIND_FACT_CARD),
    ):
        if lowered.startswith(prefix):
            cleaned = text[len(prefix):].strip()
            return kind, cleaned
    return KIND_BROLL, text


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in (match.group(0).lower() for match in _TOKEN_RE.finditer(str(text or "")))
        if token and token not in _STOPWORDS
    }


def _candidate_text(candidate: Mapping[str, Any]) -> str:
    parts = [
        str(candidate.get("description") or ""),
        " ".join(candidate.get("tags") or []) if isinstance(candidate.get("tags"), list) else "",
        str(candidate.get("author") or ""),
    ]
    return " ".join(parts)


def score_relevance(query: str, candidate: Mapping[str, Any]) -> float:
    """Điểm lexical 0..1: tỷ lệ token của query xuất hiện trong mô tả asset."""

    if candidate.get("provider") == "serpapi_google":
        query_tokens = _tokens(query)
        text_tokens = _tokens(_candidate_text(candidate))
        if query_tokens and text_tokens and (query_tokens & text_tokens):
            return 0.95
        return 0.85

    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    text_tokens = _tokens(_candidate_text(candidate))
    if not text_tokens:
        return 0.0
    denom = min(len(query_tokens), 3)
    return min(1.0, len(query_tokens & text_tokens) / denom)


def relevance_threshold() -> float:
    raw = os.getenv("MEDIA_RELEVANCE_MIN_SCORE") or ""
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_RELEVANCE_THRESHOLD
    return value if 0.0 <= value <= 1.0 else DEFAULT_RELEVANCE_THRESHOLD


def _technically_ok(candidate: Mapping[str, Any]) -> bool:
    width, height = int(candidate.get("width") or 0), int(candidate.get("height") or 0)
    if candidate.get("provider") == "serpapi_google":
        return width >= 300 and height >= 300
    if min(width, height) < MIN_DIMENSION or max(width, height) < MAX_DIMENSION:
        return False
    if candidate.get("media_type") == "video" and float(candidate.get("duration_seconds") or 0) <= 0:
        return False
    return True


def _ext_from_url(url: str, media_type: str) -> str:
    from urllib.parse import urlparse

    suffix = os.path.splitext(urlparse(url or "").path)[1].lower().lstrip(".")
    if suffix in {"mp4", "mov", "webm"}:
        return "mp4"
    if suffix in {"jpg", "jpeg", "png"}:
        return suffix
    return "mp4" if media_type == "video" else "jpg"


def _default_http_download(url: str, dest_path: str) -> int:
    import requests

    written = 0
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.google.com/",
    }
    with requests.get(
        url, headers=headers, stream=True, timeout=_DOWNLOAD_TIMEOUT_SECONDS
    ) as response:
        response.raise_for_status()
        with open(dest_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 16):
                if chunk:
                    handle.write(chunk)
                    written += len(chunk)
    return written


def _job_directory(job_id: str, jobs_dir: str | None) -> str:
    directory = os.path.join(jobs_dir or JOBS_DIR, str(job_id or ""))
    if not JOB_ID_RE.match(str(job_id or "")) or not os.path.isdir(directory):
        raise ValueError("JOB_NOT_FOUND")
    return directory


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ordered_query_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for match in _TOKEN_RE.finditer(str(text or "")):
        token = match.group(0).lower()
        if token and token not in _STOPWORDS and token not in seen:
            seen.append(token)
    return seen


def _search_candidates(
    search_query: str,
    *,
    api_key: str,
    http_get: HttpGet | None,
) -> list[dict[str, Any]]:
    """Lấy cả video và ảnh để lựa chọn theo độ liên quan.

    Trước đây ảnh chỉ được tìm khi API video trả về danh sách rỗng. Pexels có
    thể trả về clip không liên quan, trong khi ảnh cho đúng ngữ cảnh lại có
    sẵn; do đó pipeline vô tình rơi về card chữ. Video vẫn được ưu tiên khi
    điểm liên quan bằng nhau.
    """

    videos = search_stock(
        search_query, media_type="video", per_page=PER_PAGE_CANDIDATES,
        api_key=api_key, http_get=http_get,
    )
    photos = search_stock(
        search_query, media_type="photo", per_page=PER_PAGE_CANDIDATES,
        api_key=api_key, http_get=http_get,
    )
    combined = [*videos, *photos]
    if not combined and http_get is None:
        ordered = _ordered_query_tokens(search_query)
        if len(ordered) > 3:
            short_query = " ".join(ordered[:3])
            videos = search_stock(
                short_query, media_type="video", per_page=PER_PAGE_CANDIDATES,
                api_key=api_key, http_get=http_get,
            )
            photos = search_stock(
                short_query, media_type="photo", per_page=PER_PAGE_CANDIDATES,
                api_key=api_key, http_get=http_get,
            )
            combined = [*videos, *photos]
    return combined


def _pick_beat_asset(
    beat: Mapping[str, Any],
    *,
    api_key: str,
    http_get: HttpGet | None,
    usage: dict[str, int],
    threshold: float,
) -> dict[str, Any]:
    """Tìm asset tốt nhất cho một beat B-roll. Trả về entry kết quả."""

    visual_query = str(beat.get("visual_query") or "").strip()
    required_country = str(beat.get("required_country") or "").strip()
    country_strict = bool(beat.get("country_strict"))

    entry: dict[str, Any] = {
        "beat_number": beat.get("beat_number"),
        "kind": KIND_BROLL,
        "visual_query": visual_query,
        "search_query": visual_query,
        "media_type": None,
        "candidates_evaluated": 0,
        "selected": None,
        "reason": "",
    }
    if required_country:
        entry["required_country"] = required_country
        entry["country_strict"] = country_strict

    if not visual_query:
        entry["kind"] = KIND_NO_ASSET
        entry["reason"] = "empty_visual_query"
        return entry

    raw_queries = [visual_query]
    extra_queries = beat.get("asset_search_queries")
    if isinstance(extra_queries, list):
        for q in extra_queries:
            q_str = str(q or "").strip()
            if q_str and q_str not in raw_queries:
                raw_queries.append(q_str)

    candidates: list[dict[str, Any]] = []
    chosen_query = visual_query
    for q in raw_queries:
        try:
            found = _search_candidates(q, api_key=api_key, http_get=http_get)
        except RuntimeError as exc:
            entry["kind"] = KIND_NO_ASSET
            entry["reason"] = f"search_error: {exc}"
            return entry
        if found:
            candidates = found
            chosen_query = q
            break

    entry["search_query"] = chosen_query
    eligible: list[tuple[float, int, int, dict[str, Any]]] = []
    cap_excluded = False
    technical_excluded = False
    country_excluded = False
    for index, candidate in enumerate(candidates):
        if not _technically_ok(candidate):
            technical_excluded = True
            continue
        if country_strict and required_country:
            cand_country = str(candidate.get("country") or "").strip().lower()
            text_desc = _candidate_text(candidate).lower()
            req_lower = required_country.lower()
            if cand_country != req_lower and req_lower not in text_desc:
                country_excluded = True
                continue
        asset_key = str(candidate.get("provider_asset_id") or "")
        if usage.get(asset_key, 0) >= MAX_USES_PER_ASSET:
            cap_excluded = True
            continue
        score = score_relevance(chosen_query, candidate)
        if score < threshold:
            continue
        # Video thắng ảnh khi relevance bằng nhau; index ổn định kết quả.
        media_preference = 1 if candidate.get("media_type") == "video" else 0
        eligible.append((score, media_preference, -index, candidate))
    entry["candidates_evaluated"] = len(candidates)

    if not eligible:
        entry["kind"] = KIND_NO_ASSET
        if not candidates:
            entry["reason"] = "no_candidates"
        elif country_excluded:
            entry["reason"] = "country_unverified"
        elif cap_excluded:
            entry["reason"] = "usage_cap_reached"
        elif technical_excluded:
            entry["reason"] = "below_technical_requirement"
        else:
            entry["reason"] = "below_threshold"
        return entry

    eligible.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    best_score, _, _, best = eligible[0]
    asset_key = str(best.get("provider_asset_id") or "")
    usage[asset_key] = usage.get(asset_key, 0) + 1
    selected = dict(best)
    selected["relevance_score"] = round(best_score, 4)
    entry["selected"] = selected
    entry["media_type"] = selected.get("media_type")
    entry["eligible_candidates"] = [
        dict(c, relevance_score=round(s, 4)) for s, _, _, c in eligible
    ]
    return entry


def _download_beat_asset(
    entry: dict[str, Any], directory: str, asset_id: str, http_download: HttpDownload | None
) -> dict[str, Any] | None:
    """Tải asset vào ``directory/assets``; trả về record manifest hoặc None khi lỗi."""

    selected = entry.get("selected") or {}
    url = str(selected.get("asset_url") or "")
    if not url:
        return None
    ext = _ext_from_url(url, str(selected.get("media_type") or "video"))
    dest_path = os.path.join(directory, "assets", f"{asset_id}.{ext}")
    downloader = http_download or _default_http_download
    size = 0
    try:
        size = downloader(url, dest_path)
    except Exception:
        size = 0
    if not size or not os.path.isfile(dest_path):
        thumb_url = str(selected.get("thumbnail_url") or "")
        if thumb_url and thumb_url != url:
            try:
                size = downloader(thumb_url, dest_path)
            except Exception:
                size = 0
    if not size or not os.path.isfile(dest_path):
        return None
    return {
        "asset_id": asset_id,
        "beat_number": entry.get("beat_number"),
        "provider": selected.get("provider"),
        "provider_asset_id": selected.get("provider_asset_id"),
        "asset_url": url,
        "page_url": selected.get("page_url"),
        "local_path": os.path.relpath(dest_path, directory),
        "media_type": selected.get("media_type"),
        "license_status": "licensed",
        "license_source": str(selected.get("license_source") or "pexels_license"),
        "downloaded_at": _now_iso(),
        "relevance_score": selected.get("relevance_score"),
        "country": selected.get("country") or None,
        "country_verification": selected.get("country_verification") or "unverified",
        "city": selected.get("city") or None,
        "logo_scan": "pending",
        "watermark_scan": "pending",
        "is_ai_generated": False,
        "publisher_asset": False,
    }


def _scan_downloaded_asset(
    record: Mapping[str, Any], directory: str, watermark_scanner: WatermarkScanner
) -> dict[str, Any]:
    """Quét watermark trên file đã tải. Lỗi quét coi như phát hiện (bảo thủ §8)."""

    local_path = os.path.join(directory, str(record.get("local_path") or ""))
    media_type = str(record.get("media_type") or "video")
    try:
        result = watermark_scanner(local_path, media_type)
        scan_dict = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    except Exception as exc:
        return {
            "detected": True,
            "reason": "watermark_scan_error",
            "logo_scan": "error",
            "watermark_scan": {"error": str(exc)[:200]},
        }
    detected = bool(scan_dict.get("detected"))
    return {
        "detected": detected,
        "reason": "watermark_detected" if detected else "",
        "logo_scan": "detected" if detected else "passed",
        "watermark_scan": scan_dict,
    }


def plan_media_for_job(
    job_id: str,
    *,
    jobs_dir: str | None = None,
    api_key: str | None = None,
    http_get: HttpGet | None = None,
    http_download: HttpDownload | None = None,
    watermark_scanner: WatermarkScanner | None = None,
    allow_missing_api_key: bool = False,
) -> dict[str, Any]:
    """Dựng media plan + manifest cho job và ghi vào thư mục job.

    Trả về ``{"plan": ..., "manifest": [...]}``. Ném ``ValueError("JOB_NOT_FOUND")``
    khi job/storyboard không tồn tại và ``RuntimeError("PEXELS_API_KEY_MISSING")``
    khi chưa cấu hình key (trừ khi ``http_get`` bị fake hoặc ``allow_missing_api_key=True``).
    """

    directory = _job_directory(job_id, jobs_dir)
    storyboard = load_job_artifact(job_id, "storyboard", jobs_dir=jobs_dir)
    if not storyboard or not isinstance(storyboard.get("beats"), list) or not storyboard["beats"]:
        raise ValueError("STORYBOARD_MISSING")
    assets_dir = os.path.join(directory, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    _, configured_key = get_stock_provider_config()
    key = str(api_key or "").strip() or configured_key
    needs_search = any(
        classify_visual_query(str(beat.get("visual_query") or ""))[0] == KIND_BROLL
        for beat in storyboard["beats"]
        if isinstance(beat, Mapping)
    )
    if not key and http_get is None and needs_search and not allow_missing_api_key:
        raise RuntimeError("PEXELS_API_KEY_MISSING")

    usage: dict[str, int] = {}
    beat_entries: list[dict[str, Any]] = []
    for beat in storyboard["beats"]:
        if not isinstance(beat, Mapping):
            continue
        kind, cleaned = classify_visual_query(str(beat.get("visual_query") or ""))
        if kind in GRAPHIC_KINDS:
            entry = {
                "beat_number": beat.get("beat_number"),
                "kind": kind,
                "visual_query": str(beat.get("visual_query") or ""),
                "search_query": cleaned,
                "media_type": None,
                "candidates_evaluated": 0,
                "selected": None,
                "reason": "graphic_fallback_per_brief",
            }
        elif not key and http_get is None and allow_missing_api_key:
            entry = {
                "beat_number": beat.get("beat_number"),
                "kind": KIND_NO_ASSET,
                "visual_query": str(beat.get("visual_query") or ""),
                "search_query": cleaned,
                "media_type": None,
                "candidates_evaluated": 0,
                "selected": None,
                "reason": "pexels_api_key_missing",
            }
        else:
            entry = _pick_beat_asset(
                beat, api_key=key, http_get=http_get, usage=usage,
                threshold=relevance_threshold(),
            )
        beat_entries.append(entry)

    manifest: list[dict[str, Any]] = []
    scanner = watermark_scanner or scan_asset_watermark
    for index, entry in enumerate(beat_entries, start=1):
        if not entry.get("selected"):
            continue
        asset_id = f"stock_{index:03d}"
        candidates_to_try = entry.get("eligible_candidates") or [entry["selected"]]
        downloaded_clean = False
        last_reason = "download_failed"
        initial_selected_key = str(entry["selected"].get("provider_asset_id") or "")

        for cand_idx, cand in enumerate(candidates_to_try[:6]):
            cand_key = str(cand.get("provider_asset_id") or "")
            if cand_idx > 0 and usage.get(cand_key, 0) >= MAX_USES_PER_ASSET:
                continue

            entry["selected"] = cand
            entry["media_type"] = cand.get("media_type")
            record = _download_beat_asset(entry, directory, asset_id, http_download)
            if record is None:
                last_reason = "download_failed"
                continue
            scan = _scan_downloaded_asset(record, directory, scanner)
            record["logo_scan"] = scan["logo_scan"]
            record["watermark_scan"] = scan["watermark_scan"]
            if scan["detected"]:
                last_reason = scan["reason"]
                try:
                    os.remove(os.path.join(directory, str(record.get("local_path") or "")))
                except OSError:
                    pass
                continue

            # Tải thành công và sạch watermark
            if cand_key != initial_selected_key:
                if initial_selected_key:
                    usage[initial_selected_key] = max(0, usage.get(initial_selected_key, 0) - 1)
                usage[cand_key] = usage.get(cand_key, 0) + 1

            entry["asset_id"] = asset_id
            manifest.append(record)
            downloaded_clean = True
            break

        if not downloaded_clean:
            entry["kind"] = KIND_NO_ASSET
            entry["reason"] = last_reason
            entry["selected"] = None
            entry["media_type"] = None
            if initial_selected_key:
                usage[initial_selected_key] = max(0, usage.get(initial_selected_key, 0) - 1)

    counts = {
        "broll": 0,
        "data_graphic": 0,
        "map_graphic": 0,
        "quote_card": 0,
        "fact_card": 0,
        "no_asset_found": 0,
    }
    for entry in beat_entries:
        kind = entry.get("kind")
        counts[kind if kind in counts else KIND_BROLL] += 1
    broll_total = counts["broll"] + counts["no_asset_found"]
    status = "ready" if broll_total and counts["no_asset_found"] == 0 else (
        "partial" if counts["broll"] else "graphics_only"
    )

    plan = {
        "plan_version": PLAN_VERSION,
        "job_id": job_id,
        "created_at": _now_iso(),
        "status": status,
        "beats": beat_entries,
        "summary": {
            "total_beats": len(beat_entries),
            **counts,
            "assets_downloaded": len(manifest),
        },
    }
    _atomic_write_json(os.path.join(directory, "media_plan.json"), plan)
    _atomic_write_json(os.path.join(directory, "assets_manifest.json"), manifest)
    return {"plan": plan, "manifest": manifest}
