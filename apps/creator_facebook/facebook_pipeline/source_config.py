"""Chuẩn hóa cấu hình nguồn Facebook dùng chung cho UI, API và pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit, urlunsplit


SOURCE_TYPE_PAGE = "page"
SOURCE_TYPE_GROUP = "group"
EDIT_MODE_FULL_AI = "full_ai_voiceover"
EDIT_MODE_HOOK_THEN_ORIGINAL = "hook_then_original"

DEFAULT_PAGE_MAX_VIDEOS_PER_SCAN = 10
DEFAULT_GROUP_MAX_VIDEOS_PER_SCAN = 5
DEFAULT_MAX_VIDEOS_PER_SCAN = DEFAULT_GROUP_MAX_VIDEOS_PER_SCAN
MAX_VIDEOS_PER_SCAN_LIMIT = 10

SOURCE_TYPE_LABELS = {
    SOURCE_TYPE_PAGE: "Trang (Page)",
    SOURCE_TYPE_GROUP: "Nhóm (Group)",
}
EDIT_MODE_LABELS = {
    EDIT_MODE_FULL_AI: "Full AI Script",
    EDIT_MODE_HOOK_THEN_ORIGINAL: "Đọc Hook + Giữ tiếng gốc",
}

_EDIT_MODE_ALIASES = {
    "full_ai": EDIT_MODE_FULL_AI,
    "full_ai_voiceover": EDIT_MODE_FULL_AI,
    "title_only": EDIT_MODE_HOOK_THEN_ORIGINAL,
    "hook_then_original": EDIT_MODE_HOOK_THEN_ORIGINAL,
}
_ALLOWED_WRITE_FIELDS = {
    "id_tiktok",
    "source_name",
    "source_url",
    "source_type",
    "edit_mode",
    "max_video_age_hours",
    "max_videos_per_scan",
    "scan_interval_min",
    "delogo",
    "platform",
    "is_active",
    "extra_content",
}

_PAGE_WRITE_FIELDS = {
    "id_tiktok",
    "source_name",
    "source_url",
    "max_video_age_hours",
    "scan_interval_min",
    "delogo",
    "platform",
    "is_active",
    "extra_content",
}

_GROUP_WRITE_FIELDS = {
    "id_tiktok",
    "source_name",
    "source_url",
    "edit_mode",
    "max_video_age_hours",
    "max_videos_per_scan",
    "scan_interval_min",
    "delogo",
    "platform",
    "is_active",
    "extra_content",
}


@dataclass(frozen=True)
class GroupPostReference:
    group_key: str
    post_id: str
    canonical_url: str


def _facebook_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Thiếu URL nguồn Facebook.")
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    parsed = urlsplit(raw)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    if host not in {"facebook.com", "m.facebook.com", "web.facebook.com", "fb.com"}:
        raise ValueError("URL phải thuộc facebook.com hoặc fb.com.")
    path = re.sub(r"/{2,}", "/", parsed.path or "/").rstrip("/") or "/"
    return urlunsplit(("https", "www.facebook.com", path, parsed.query, ""))


def extract_group_key(source_url: Any) -> str:
    try:
        parsed = urlsplit(_facebook_url(source_url))
    except ValueError:
        return ""
    match = re.search(r"(?:^|/)groups/([^/?#]+)", parsed.path, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def is_group_url(source_url: Any) -> bool:
    return bool(extract_group_key(source_url))


def normalize_source_type(value: Any, source_url: Any = "") -> str:
    raw = str(value or "").strip().lower()
    inferred = SOURCE_TYPE_GROUP if is_group_url(source_url) else SOURCE_TYPE_PAGE
    if not raw:
        return inferred
    if raw not in {SOURCE_TYPE_PAGE, SOURCE_TYPE_GROUP}:
        raise ValueError("source_type chỉ nhận 'page' hoặc 'group'.")
    if raw == SOURCE_TYPE_GROUP and not is_group_url(source_url):
        raise ValueError("Nguồn Group phải có URL dạng facebook.com/groups/...")
    if raw == SOURCE_TYPE_PAGE and is_group_url(source_url):
        raise ValueError("URL nhóm Facebook phải chọn loại nguồn Group.")
    return raw


def normalize_edit_mode(value: Any, source_type: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return (
            EDIT_MODE_HOOK_THEN_ORIGINAL
            if source_type == SOURCE_TYPE_GROUP
            else EDIT_MODE_FULL_AI
        )
    normalized = _EDIT_MODE_ALIASES.get(raw)
    if not normalized:
        raise ValueError(
            "edit_mode chỉ nhận 'full_ai_voiceover' hoặc 'hook_then_original'."
        )
    return normalized


def normalize_max_videos(value: Any) -> int:
    if value in (None, ""):
        return DEFAULT_MAX_VIDEOS_PER_SCAN
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Số video mỗi lượt phải là số nguyên.") from exc
    if not 1 <= parsed <= MAX_VIDEOS_PER_SCAN_LIMIT:
        raise ValueError(
            f"Số video mỗi lượt phải từ 1 đến {MAX_VIDEOS_PER_SCAN_LIMIT}."
        )
    return parsed


def canonicalize_source_url(source_url: Any, source_type: str | None = None) -> str:
    normalized = _facebook_url(source_url)
    resolved_type = normalize_source_type(source_type, normalized)
    if resolved_type != SOURCE_TYPE_GROUP:
        return normalized.rstrip("/")
    group_key = extract_group_key(normalized)
    return f"https://www.facebook.com/groups/{group_key}"


def build_crawl_url(source_url: Any, source_type: str | None = None) -> str:
    normalized = canonicalize_source_url(source_url, source_type)
    resolved_type = normalize_source_type(source_type, normalized)
    if resolved_type == SOURCE_TYPE_GROUP:
        # Bắt buộc quét feed bài viết của nhóm, không quét tab reels/videos.
        return normalized
    if normalized.endswith(("/reels", "/videos")):
        return normalized
    if "profile.php" in normalized:
        separator = "&" if "?" in normalized else "?"
        return normalized + separator + "sk=reels"
    return normalized + "/reels"


def parse_group_post_url(url: Any, expected_group_key: str = "") -> GroupPostReference | None:
    try:
        normalized = _facebook_url(url)
    except ValueError:
        return None
    parsed = urlsplit(normalized)
    path_match = re.search(
        r"(?:^|/)groups/([^/?#]+)/(?:posts|permalink)/(\d+)",
        parsed.path,
        re.IGNORECASE,
    )
    group_key = ""
    post_id = ""
    if path_match:
        group_key, post_id = path_match.group(1), path_match.group(2)
    else:
        group_match = re.search(
            r"(?:^|/)groups/([^/?#]+)", parsed.path, re.IGNORECASE
        )
        query = parse_qs(parsed.query)
        multi_ids = query.get("multi_permalinks", [])
        if group_match and multi_ids and str(multi_ids[0]).isdigit():
            group_key, post_id = group_match.group(1), str(multi_ids[0])
    if not group_key or not post_id:
        return None
    if expected_group_key and group_key.casefold() != expected_group_key.casefold():
        return None
    return GroupPostReference(
        group_key=group_key,
        post_id=post_id,
        canonical_url=f"https://www.facebook.com/groups/{group_key}/posts/{post_id}",
    )


def extract_video_id(url: Any) -> str:
    raw = str(url or "")
    patterns = (
        r"/videos/(\d+)",
        r"/reel/(\d+)",
        r"story_fbid=(\d+)",
        r"[?&]v=(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def normalize_source_record(source: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(source)
    url = str(result.get("source_url") or "").strip()
    source_type = normalize_source_type(result.get("source_type"), url)
    result["source_type"] = source_type
    result["edit_mode"] = normalize_edit_mode(result.get("edit_mode"), source_type)
    result["max_videos_per_scan"] = normalize_max_videos(
        result.get("max_videos_per_scan")
    )
    return result


def normalize_page_source_record(source: Mapping[str, Any]) -> dict[str, Any]:
    """Thêm cấu hình runtime cho Page mà không đòi cột mới trong bảng cũ."""
    result = dict(source)
    url = str(result.get("source_url") or "").strip()
    if is_group_url(url):
        raise ValueError("Bảng nguồn Page không nhận URL Facebook Group.")
    result["source_type"] = SOURCE_TYPE_PAGE
    result["edit_mode"] = EDIT_MODE_FULL_AI
    result["max_videos_per_scan"] = DEFAULT_PAGE_MAX_VIDEOS_PER_SCAN
    return result


def normalize_group_source_record(source: Mapping[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa một bản ghi lấy từ bảng Group riêng."""
    result = dict(source)
    url = str(result.get("source_url") or "").strip()
    if not is_group_url(url):
        raise ValueError("Bảng nguồn Group chỉ nhận URL facebook.com/groups/...")
    result["source_url"] = canonicalize_source_url(url, SOURCE_TYPE_GROUP)
    result["source_type"] = SOURCE_TYPE_GROUP
    result["edit_mode"] = normalize_edit_mode(
        result.get("edit_mode"), SOURCE_TYPE_GROUP
    )
    result["max_videos_per_scan"] = normalize_max_videos(
        result.get("max_videos_per_scan")
    )
    return result


def _sanitize_common_fields(
    payload: Mapping[str, Any],
    *,
    allowed_fields: set[str],
    partial: bool,
) -> dict[str, Any]:
    data = {
        key: value
        for key, value in dict(payload).items()
        if key in allowed_fields
    }
    if not partial:
        for required in ("source_name", "source_url"):
            if not str(data.get(required) or "").strip():
                raise ValueError(f"Thiếu trường bắt buộc: {required}.")
    if "source_name" in data:
        data["source_name"] = str(data["source_name"] or "").strip()
    if "max_video_age_hours" in data:
        try:
            max_age = int(data["max_video_age_hours"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Max giờ phải là số nguyên.") from exc
        if not 0 <= max_age <= 24 * 30:
            raise ValueError("Max giờ phải từ 0 đến 720; 0 nghĩa là không giới hạn.")
        data["max_video_age_hours"] = max_age
    return data


def sanitize_page_source_payload(
    payload: Mapping[str, Any], *, partial: bool = False
) -> dict[str, Any]:
    """Payload đúng schema Page cũ; tuyệt đối không ghi các cột Group."""
    data = _sanitize_common_fields(
        payload,
        allowed_fields=_PAGE_WRITE_FIELDS,
        partial=partial,
    )
    if "source_url" in data:
        if is_group_url(data["source_url"]):
            raise ValueError("URL nhóm phải thêm tại mục Nguồn Group.")
        data["source_url"] = canonicalize_source_url(
            data["source_url"], SOURCE_TYPE_PAGE
        )
    if not partial:
        data.setdefault("platform", "facebook")
        data.setdefault("is_active", True)
        data.setdefault("scan_interval_min", 30)
        data.setdefault("max_video_age_hours", 48)
    return data


def sanitize_group_source_payload(
    payload: Mapping[str, Any], *, partial: bool = False
) -> dict[str, Any]:
    """Payload dành riêng cho bảng ``facebook_group_sources``."""
    data = _sanitize_common_fields(
        payload,
        allowed_fields=_GROUP_WRITE_FIELDS,
        partial=partial,
    )
    if "source_url" in data:
        if not is_group_url(data["source_url"]):
            raise ValueError("Nguồn Group phải có URL facebook.com/groups/...")
        data["source_url"] = canonicalize_source_url(
            data["source_url"], SOURCE_TYPE_GROUP
        )
    if "edit_mode" in data or not partial:
        data["edit_mode"] = normalize_edit_mode(
            data.get("edit_mode"), SOURCE_TYPE_GROUP
        )
    if "max_videos_per_scan" in data or not partial:
        data["max_videos_per_scan"] = normalize_max_videos(
            data.get("max_videos_per_scan")
        )
    if not partial:
        data.setdefault("platform", "facebook_group")
        data.setdefault("is_active", True)
        data.setdefault("scan_interval_min", 30)
        data.setdefault("max_video_age_hours", 48)
    return data


def sanitize_source_payload(
    payload: Mapping[str, Any], *, partial: bool = False
) -> dict[str, Any]:
    data = {key: value for key, value in dict(payload).items() if key in _ALLOWED_WRITE_FIELDS}
    if not partial:
        for required in ("source_name", "source_url"):
            if not str(data.get(required) or "").strip():
                raise ValueError(f"Thiếu trường bắt buộc: {required}.")

    if "source_name" in data:
        data["source_name"] = str(data["source_name"] or "").strip()
    if "source_url" in data:
        requested_type = data.get("source_type")
        source_type = normalize_source_type(requested_type, data["source_url"])
        data["source_url"] = canonicalize_source_url(data["source_url"], source_type)
        data["source_type"] = source_type
    elif "source_type" in data:
        source_type = str(data["source_type"] or "").strip().lower()
        if source_type not in {SOURCE_TYPE_PAGE, SOURCE_TYPE_GROUP}:
            raise ValueError("source_type chỉ nhận 'page' hoặc 'group'.")
        data["source_type"] = source_type
    else:
        source_type = SOURCE_TYPE_PAGE

    if "edit_mode" in data or not partial:
        data["edit_mode"] = normalize_edit_mode(data.get("edit_mode"), source_type)
    if "max_videos_per_scan" in data or not partial:
        data["max_videos_per_scan"] = normalize_max_videos(
            data.get("max_videos_per_scan")
        )
    if "max_video_age_hours" in data:
        try:
            max_age = int(data["max_video_age_hours"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Max giờ phải là số nguyên.") from exc
        if not 0 <= max_age <= 24 * 30:
            raise ValueError("Max giờ phải từ 0 đến 720; 0 nghĩa là không giới hạn.")
        data["max_video_age_hours"] = max_age

    if not partial:
        data.setdefault("platform", "facebook")
        data.setdefault("is_active", True)
        data.setdefault("scan_interval_min", 30)
        data.setdefault("max_video_age_hours", 48)
    return data
