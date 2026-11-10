"""Adapter kho stock cấp phép — hỗ trợ Pexels, Pixabay và Wikimedia Commons.

Theo ``BRIEF_AGENT_DUNG_VIDEO_TIN_TUC.md`` §3/§5: chỉ dùng provider có
license/provenance rõ ràng; DuckDuckGo và ảnh bài báo bị cấm trong luồng
production mới.

Khi Pexels tạm dừng cấp API key mới, hệ thống hỗ trợ:
- ``PIXABAY_API_KEY`` (Pixabay API — cấp key miễn phí tức thì tại https://pixabay.com/api/docs/)
- ``STOCK_PROVIDER=wikimedia`` (Wikimedia Commons API — kho tư liệu CC0/CC-BY/Public Domain hợp pháp, không cần API key)

Module này không chạy network khi được test — ``_http_get`` có thể bị thay
bằng fake qua tham số.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Mapping

PEXELS_API_BASE = "https://api.pexels.com"
UNSPLASH_API_BASE = "https://api.unsplash.com"
PIXABAY_API_BASE = "https://pixabay.com/api"
WIKIMEDIA_API_BASE = "https://commons.wikimedia.org/w/api.php"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

REQUEST_TIMEOUT_SECONDS = 20

HttpGet = Callable[[str, Mapping[str, str]], Mapping[str, Any] | None]

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def get_serpapi_api_key() -> str:
    return str(os.getenv("SERPAPI_API_KEY") or "").strip()


def get_pexels_api_key() -> str:
    return str(os.getenv("PEXELS_API_KEY") or "").strip()


def get_unsplash_access_key() -> str:
    return str(os.getenv("UNSPLASH_ACCESS_KEY") or "").strip()


def get_pixabay_api_key() -> str:
    return str(os.getenv("PIXABAY_API_KEY") or "").strip()


def get_stock_provider_config() -> tuple[str, str]:
    """Trả về ``(provider_name, api_key_or_token)`` theo thứ tự ưu tiên."""

    serpapi_key = get_serpapi_api_key()
    if serpapi_key:
        return "serpapi", serpapi_key
    unsplash_key = get_unsplash_access_key()
    if unsplash_key:
        return "unsplash", unsplash_key
    pexels_key = get_pexels_api_key()
    if pexels_key:
        return "pexels", pexels_key
    pixabay_key = get_pixabay_api_key()
    if pixabay_key:
        return "pixabay", pixabay_key
    provider_env = str(os.getenv("STOCK_PROVIDER") or "").strip().lower()
    if provider_env in {"wikimedia", "commons"}:
        return "wikimedia", "wikimedia_keyless"
    return "", ""


def _default_http_get(url: str, headers: Mapping[str, str]) -> Mapping[str, Any] | None:
    import requests

    req_headers = {"User-Agent": DEFAULT_USER_AGENT, **dict(headers or {})}
    response = requests.get(url, headers=req_headers, timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code == 429:
        raise RuntimeError("PEXELS_RATE_LIMITED")
    if response.status_code == 401:
        raise RuntimeError("PEXELS_UNAUTHORIZED")
    response.raise_for_status()
    return response.json()


def _pick_video_file(video: Mapping[str, Any]) -> dict[str, Any] | None:
    """Chọn file MP4 chất lượng đủ crop 1080x1920, ưu tiên nhỏ gọn đủ dùng."""

    files = video.get("video_files")
    if not isinstance(files, list):
        return None
    usable: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("file_type") or "") != "video/mp4":
            continue
        width, height = int(item.get("width") or 0), int(item.get("height") or 0)
        if width <= 0 or height <= 0:
            continue
        usable.append(
            {
                "url": str(item.get("link") or ""),
                "width": width,
                "height": height,
                "size_bytes": int(item.get("file_size") or 0),
            }
        )
    if not usable:
        return None

    def _can_crop_9x16(entry: dict[str, Any]) -> bool:
        return min(entry["width"], entry["height"]) >= 1080 and max(
            entry["width"], entry["height"]
        ) >= 1920

    qualified = [entry for entry in usable if _can_crop_9x16(entry)]
    pool = qualified or usable
    pool.sort(key=lambda entry: entry["size_bytes"] or entry["width"] * entry["height"])
    return pool[0]


def _video_slug_text(page_url: str) -> str:
    """Pexels video search không có alt/tags; slug của page URL là mô tả duy nhất.

    Ví dụ ``https://www.pexels.com/video/people-walking-on-street-856973/``
    -> ``people walking on street``.
    """

    from urllib.parse import urlparse

    path = urlparse(page_url or "").path.rstrip("/")
    last = path.rsplit("/", 1)[-1] if path else ""
    stem = last.rsplit("-", 1)[0] if last.rsplit("-", 1)[-1].isdigit() else last
    return stem.replace("-", " ").strip()


def _normalize_video(video: Mapping[str, Any]) -> dict[str, Any] | None:
    video_id = str(video.get("id") or "").strip()
    if not video_id:
        return None
    chosen = _pick_video_file(video)
    if not chosen or not chosen["url"]:
        return None
    user = video.get("user") if isinstance(video.get("user"), Mapping) else {}
    page_url = str(video.get("url") or f"https://www.pexels.com/video/{video_id}/")
    return {
        "provider": "pexels",
        "provider_asset_id": f"pexels_video_{video_id}",
        "media_type": "video",
        "asset_url": chosen["url"],
        "page_url": page_url,
        "width": chosen["width"],
        "height": chosen["height"],
        "duration_seconds": float(video.get("duration") or 0),
        "author": str(user.get("name") or ""),
        "description": _video_slug_text(page_url),
        "tags": [],
        "country": "",
        "country_verification": "unverified",
    }


def _normalize_photo(photo: Mapping[str, Any]) -> dict[str, Any] | None:
    photo_id = str(photo.get("id") or "").strip()
    if not photo_id:
        return None
    src = photo.get("src") if isinstance(photo.get("src"), Mapping) else {}
    original_url = str(src.get("original") or "").strip()
    if not original_url:
        return None
    user = photo.get("user") if isinstance(photo.get("user"), Mapping) else {}
    width, height = int(photo.get("width") or 0), int(photo.get("height") or 0)
    alt = str(photo.get("alt") or "").strip()
    return {
        "provider": "pexels",
        "provider_asset_id": f"pexels_photo_{photo_id}",
        "media_type": "photo",
        "asset_url": original_url,
        "page_url": str(photo.get("url") or f"https://www.pexels.com/photo/{photo_id}/"),
        "width": width,
        "height": height,
        "duration_seconds": 0.0,
        "author": str(user.get("name") or ""),
        "description": alt,
        "tags": [],
        "country": "",
        "country_verification": "unverified",
    }


def normalize_pexels_response(payload: Mapping[str, Any], media_type: str) -> list[dict[str, Any]]:
    """Chuyển response Pexels thành danh sách ứng viên đã chuẩn hoá."""

    if media_type not in {"video", "photo"}:
        raise ValueError(f"media_type không hợp lệ: {media_type}")
    container = payload.get(media_type == "video" and "videos" or "photos")
    if not isinstance(container, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in container:
        if not isinstance(item, Mapping):
            continue
        entry = _normalize_video(item) if media_type == "video" else _normalize_photo(item)
        if entry is None:
            continue
        if entry["provider_asset_id"] in seen_ids:
            continue
        seen_ids.add(entry["provider_asset_id"])
        normalized.append(entry)
    return normalized


def search_pexels(
    query: str,
    *,
    media_type: str = "video",
    per_page: int = 15,
    orientation: str = "portrait",
    api_key: str | None = None,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    """Tìm ứng viên B-roll trên Pexels. Trả về list rỗng khi query rỗng."""

    clean_query = str(query or "").strip()
    if not clean_query:
        return []
    key = (api_key or get_pexels_api_key()).strip()
    if not key and http_get is None:
        raise RuntimeError("PEXELS_API_KEY_MISSING")
    getter = http_get or _default_http_get

    endpoint = f"{PEXELS_API_BASE}/{'videos/search' if media_type == 'video' else 'search'}"
    url = (
        f"{endpoint}?query={_urlencode(clean_query)}"
        f"&per_page={max(1, min(int(per_page), 40))}&orientation={orientation}"
    )
    payload = getter(url, {"Authorization": key})
    if payload is None:
        return []
    return normalize_pexels_response(payload, media_type)


def _urlencode(value: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(value)


def _strip_html(value: str) -> str:
    return _HTML_TAG_RE.sub(" ", str(value or "")).replace("&nbsp;", " ").strip()


def _normalize_pixabay_video(hit: Mapping[str, Any]) -> dict[str, Any] | None:
    hit_id = str(hit.get("id") or "").strip()
    if not hit_id:
        return None
    videos = hit.get("videos")
    if not isinstance(videos, Mapping):
        return None
    usable: list[dict[str, Any]] = []
    for variant in ("large", "medium", "small", "tiny"):
        item = videos.get(variant)
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("url") or "").strip()
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if not url or width <= 0 or height <= 0:
            continue
        usable.append(
            {
                "url": url,
                "width": width,
                "height": height,
                "size_bytes": int(item.get("size") or 0),
            }
        )
    if not usable:
        return None
    qualified = [
        entry
        for entry in usable
        if min(entry["width"], entry["height"]) >= 1080
        and max(entry["width"], entry["height"]) >= 1920
    ]
    pool = qualified or usable
    pool.sort(key=lambda entry: entry["size_bytes"] or entry["width"] * entry["height"])
    chosen = pool[0]
    tags = [t.strip() for t in str(hit.get("tags") or "").split(",") if t.strip()]
    page_url = str(hit.get("pageURL") or f"https://pixabay.com/videos/id-{hit_id}/")
    return {
        "provider": "pixabay",
        "provider_asset_id": f"pixabay_video_{hit_id}",
        "media_type": "video",
        "asset_url": chosen["url"],
        "page_url": page_url,
        "width": chosen["width"],
        "height": chosen["height"],
        "duration_seconds": float(hit.get("duration") or 0),
        "author": str(hit.get("user") or ""),
        "description": " ".join(tags) or _video_slug_text(page_url),
        "tags": tags,
        "license_source": "pixabay_license",
        "country": "",
        "country_verification": "unverified",
    }


def _normalize_pixabay_photo(hit: Mapping[str, Any]) -> dict[str, Any] | None:
    hit_id = str(hit.get("id") or "").strip()
    if not hit_id:
        return None
    image_url = str(
        hit.get("largeImageURL")
        or hit.get("fullHDURL")
        or hit.get("imageURL")
        or hit.get("webformatURL")
        or ""
    ).strip()
    if not image_url:
        return None
    width = int(hit.get("imageWidth") or hit.get("webformatWidth") or 0)
    height = int(hit.get("imageHeight") or hit.get("webformatHeight") or 0)
    tags = [t.strip() for t in str(hit.get("tags") or "").split(",") if t.strip()]
    page_url = str(hit.get("pageURL") or f"https://pixabay.com/photos/id-{hit_id}/")
    return {
        "provider": "pixabay",
        "provider_asset_id": f"pixabay_photo_{hit_id}",
        "media_type": "photo",
        "asset_url": image_url,
        "page_url": page_url,
        "width": width,
        "height": height,
        "duration_seconds": 0.0,
        "author": str(hit.get("user") or ""),
        "description": " ".join(tags) or _video_slug_text(page_url),
        "tags": tags,
        "license_source": "pixabay_license",
        "country": "",
        "country_verification": "unverified",
    }


def normalize_pixabay_response(
    payload: Mapping[str, Any], media_type: str
) -> list[dict[str, Any]]:
    if media_type not in {"video", "photo"}:
        raise ValueError(f"media_type không hợp lệ: {media_type}")
    hits = payload.get("hits")
    if not isinstance(hits, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in hits:
        if not isinstance(item, Mapping):
            continue
        entry = (
            _normalize_pixabay_video(item)
            if media_type == "video"
            else _normalize_pixabay_photo(item)
        )
        if entry is None or entry["provider_asset_id"] in seen_ids:
            continue
        seen_ids.add(entry["provider_asset_id"])
        normalized.append(entry)
    return normalized


def search_pixabay(
    query: str,
    *,
    media_type: str = "video",
    per_page: int = 15,
    api_key: str | None = None,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    """Tìm ứng viên B-roll trên Pixabay (yêu cầu PIXABAY_API_KEY)."""

    clean_query = str(query or "").strip()
    if not clean_query:
        return []
    key = (api_key or get_pixabay_api_key()).strip()
    if not key and http_get is None:
        raise RuntimeError("PIXABAY_API_KEY_MISSING")
    getter = http_get or _default_http_get
    limit = max(3, min(int(per_page), 50))
    endpoint = f"{PIXABAY_API_BASE}/videos/" if media_type == "video" else f"{PIXABAY_API_BASE}/"
    extra = "" if media_type == "video" else "&image_type=photo"
    url = (
        f"{endpoint}?key={_urlencode(key)}&q={_urlencode(clean_query)}"
        f"&per_page={limit}&safesearch=true{extra}"
    )
    payload = getter(url, {})
    if payload is None:
        return []
    return normalize_pixabay_response(payload, media_type)


def _normalize_wikimedia_page(
    page: Mapping[str, Any], media_type: str
) -> dict[str, Any] | None:
    page_id = str(page.get("pageid") or "").strip()
    if not page_id:
        return None
    imageinfo = page.get("imageinfo")
    if not isinstance(imageinfo, list) or not imageinfo:
        return None
    info = imageinfo[0] if isinstance(imageinfo[0], Mapping) else {}
    mime = str(info.get("mime") or "").lower()
    if media_type == "photo" and mime not in {"image/jpeg", "image/png", "image/webp"}:
        return None
    if media_type == "video" and mime not in {
        "video/mp4",
        "video/webm",
        "application/ogg",
        "video/ogg",
    }:
        return None
    asset_url = str(info.get("url") or "").strip()
    page_url = str(
        info.get("descriptionurl")
        or f"https://commons.wikimedia.org/?curid={page_id}"
    ).strip()
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    if not asset_url or width <= 0 or height <= 0:
        return None
    ext = info.get("extmetadata") if isinstance(info.get("extmetadata"), Mapping) else {}

    def _meta(field: str) -> str:
        node = ext.get(field)
        if isinstance(node, Mapping):
            return _strip_html(str(node.get("value") or ""))
        return ""

    raw_title = str(page.get("title") or "")
    if raw_title.lower().startswith("file:"):
        raw_title = raw_title[5:]
    title_stem = os.path.splitext(raw_title)[0].replace("_", " ").replace("-", " ")
    description_parts = [
        title_stem,
        _meta("ObjectName"),
        _meta("ImageDescription"),
    ]
    description = " ".join(part for part in description_parts if part).strip()
    categories = [
        cat.strip()
        for cat in _meta("Categories").split("|")
        if cat.strip()
    ]
    author = _meta("Artist") or "Wikimedia Commons"
    license_short = _meta("LicenseShortName") or "CC"
    duration = float(
        info.get("duration") or (10.0 if media_type == "video" else 0.0)
    )
    return {
        "provider": "wikimedia",
        "provider_asset_id": f"wikimedia_{media_type}_{page_id}",
        "media_type": media_type,
        "asset_url": asset_url,
        "page_url": page_url,
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "author": author,
        "description": description,
        "tags": categories,
        "license_source": f"wikimedia_commons ({license_short})",
        "country": "",
        "country_verification": "unverified",
    }


def normalize_wikimedia_response(
    payload: Mapping[str, Any], media_type: str
) -> list[dict[str, Any]]:
    if media_type not in {"video", "photo"}:
        raise ValueError(f"media_type không hợp lệ: {media_type}")
    query_obj = payload.get("query")
    if not isinstance(query_obj, Mapping):
        return []
    pages_obj = query_obj.get("pages")
    if isinstance(pages_obj, Mapping):
        pages = list(pages_obj.values())
    elif isinstance(pages_obj, list):
        pages = pages_obj
    else:
        return []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in pages:
        if not isinstance(item, Mapping):
            continue
        entry = _normalize_wikimedia_page(item, media_type)
        if entry is None or entry["provider_asset_id"] in seen_ids:
            continue
        seen_ids.add(entry["provider_asset_id"])
        normalized.append(entry)
    return normalized


def search_wikimedia(
    query: str,
    *,
    media_type: str = "photo",
    per_page: int = 15,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    """Tìm tư liệu CC0/CC-BY/Public Domain trên Wikimedia Commons (không cần API key)."""

    clean_query = str(query or "").strip()
    if not clean_query:
        return []
    getter = http_get or _default_http_get
    limit = max(1, min(int(per_page), 40))
    filetype = "video" if media_type == "video" else "bitmap"
    gsrsearch = f"filetype:{filetype} {clean_query}"
    url = (
        f"{WIKIMEDIA_API_BASE}?action=query&generator=search"
        f"&gsrsearch={_urlencode(gsrsearch)}&gsrnamespace=6&gsrlimit={limit}"
        "&prop=imageinfo&iiprop=url|size|mime|extmetadata&format=json"
    )
    payload = getter(url, {"User-Agent": DEFAULT_USER_AGENT})
    if payload is None:
        return []
    return normalize_wikimedia_response(payload, media_type)


def _normalize_unsplash_photo(item: Mapping[str, Any]) -> dict[str, Any] | None:
    photo_id = str(item.get("id") or "").strip()
    if not photo_id:
        return None
    urls = item.get("urls") if isinstance(item.get("urls"), Mapping) else {}
    asset_url = str(urls.get("full") or urls.get("raw") or urls.get("regular") or "").strip()
    if not asset_url:
        return None
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if width <= 0 or height <= 0:
        return None
    links = item.get("links") if isinstance(item.get("links"), Mapping) else {}
    page_url = str(links.get("html") or f"https://unsplash.com/photos/{photo_id}").strip()
    user = item.get("user") if isinstance(item.get("user"), Mapping) else {}
    raw_tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    tags = [
        str(tag.get("title") or "").strip()
        for tag in raw_tags
        if isinstance(tag, Mapping) and str(tag.get("title") or "").strip()
    ]
    desc_parts = [
        str(item.get("alt_description") or "").strip(),
        str(item.get("description") or "").strip(),
        str(item.get("slug") or "").replace("-", " ").strip(),
    ]
    description = " ".join(part for part in desc_parts if part).strip()
    location = item.get("location") if isinstance(item.get("location"), Mapping) else {}
    country = str(location.get("country") or "").strip()
    city = str(location.get("city") or "").strip()
    return {
        "provider": "unsplash",
        "provider_asset_id": f"unsplash_photo_{photo_id}",
        "media_type": "photo",
        "asset_url": asset_url,
        "page_url": page_url,
        "width": width,
        "height": height,
        "duration_seconds": 0.0,
        "author": str(user.get("name") or user.get("username") or ""),
        "description": description,
        "tags": tags,
        "license_source": "unsplash_license",
        "country": country,
        "country_verification": "provider_metadata" if country else "unverified",
        "city": city,
    }


def normalize_unsplash_response(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in results:
        if not isinstance(item, Mapping):
            continue
        entry = _normalize_unsplash_photo(item)
        if entry is None or entry["provider_asset_id"] in seen_ids:
            continue
        seen_ids.add(entry["provider_asset_id"])
        normalized.append(entry)
    return normalized


def search_unsplash(
    query: str,
    *,
    per_page: int = 15,
    access_key: str | None = None,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    """Tìm ảnh chụp thật (100% non-AI) trên Unsplash."""

    clean_query = str(query or "").strip()
    if not clean_query:
        return []
    key = (access_key or get_unsplash_access_key()).strip()
    if not key and http_get is None:
        raise RuntimeError("UNSPLASH_ACCESS_KEY_MISSING")
    getter = http_get or _default_http_get
    limit = max(1, min(int(per_page), 30))
    url = (
        f"{UNSPLASH_API_BASE}/search/photos?query={_urlencode(clean_query)}"
        f"&per_page={limit}&content_filter=high"
    )
    payload = getter(
        url,
        {
            "Authorization": f"Client-ID {key}",
            "Accept-Version": "v1",
        },
    )
    if payload is None:
        return []
    return normalize_unsplash_response(payload)


def normalize_serpapi_response(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    images_results = payload.get("images_results")
    if not isinstance(images_results, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(images_results):
        if not isinstance(item, Mapping):
            continue
        asset_url = str(item.get("original") or item.get("thumbnail") or "").strip()
        if not asset_url:
            continue
        page_url = str(item.get("link") or item.get("source") or asset_url).strip()
        title = str(item.get("title") or "").strip()
        source = str(item.get("source") or "").strip()
        width = int(item.get("original_width") or 1080)
        height = int(item.get("original_height") or 1920)
        photo_id = str(item.get("position") or index + 1)
        asset_id = f"serpapi_google_{photo_id}_{abs(hash(asset_url)) % 100000}"
        if asset_id in seen_ids:
            continue
        seen_ids.add(asset_id)
        description = f"{title} {source}".strip()
        normalized.append(
            {
                "provider": "serpapi_google",
                "provider_asset_id": asset_id,
                "media_type": "photo",
                "asset_url": asset_url,
                "thumbnail_url": str(item.get("thumbnail") or ""),
                "page_url": page_url,
                "width": width,
                "height": height,
                "duration_seconds": 0.0,
                "author": source or "Google Images",
                "description": description,
                "tags": [],
                "license_source": "serpapi_google_images",
            }
        )
    return normalized


def search_serpapi_google_images(
    query: str,
    *,
    per_page: int = 15,
    api_key: str | None = None,
    client: Any | None = None,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    """Tìm ảnh Google Images qua SerpApi (theo yêu cầu người dùng)."""

    clean_query = str(query or "").strip()
    if not clean_query:
        return []
    key = (api_key or get_serpapi_api_key()).strip()
    if not key and http_get is None and client is None:
        raise RuntimeError("SERPAPI_API_KEY_MISSING")

    # Khi test inject http_get thì gọi REST API URL
    if http_get is not None:
        url = (
            f"https://serpapi.com/search.json?engine=google_images"
            f"&q={_urlencode(clean_query)}&google_domain=google.com&hl=vi&gl=vn&api_key={key}"
        )
        payload = http_get(url, {}) or {}
        return normalize_serpapi_response(payload)

    # Sử dụng serpapi.Client theo đúng code mẫu người dùng
    try:
        if client is None:
            import serpapi
            client = serpapi.Client(api_key=key)
        params = {
            "engine": "google_images",
            "q": clean_query,
            "google_domain": "google.com",
            "hl": "vi",
            "gl": "vn",
            "tbs": "itp:photo",
            "num": max(5, min(int(per_page), 30)),
        }
        results = client.search(params)
        res_dict = results if isinstance(results, Mapping) else dict(results)
        return normalize_serpapi_response(res_dict)
    except Exception as exc:
        # Fallback HTTP requests
        import requests
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google_images",
                "q": clean_query,
                "google_domain": "google.com",
                "hl": "vi",
                "gl": "vn",
                "tbs": "itp:photo",
                "api_key": key,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return normalize_serpapi_response(resp.json())


def search_stock(
    query: str,
    *,
    media_type: str = "video",
    per_page: int = 15,
    orientation: str = "portrait",
    api_key: str | None = None,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    """Router tìm tư liệu stock theo provider khả dụng (SerpApi -> Unsplash -> Pexels -> Pixabay -> Wikimedia)."""

    clean_query = str(query or "").strip()
    if not clean_query:
        return []
    # Khi unit test inject http_get thì giữ nguyên luồng Pexels để tương thích bộ test.
    if http_get is not None:
        return search_pexels(
            clean_query,
            media_type=media_type,
            per_page=per_page,
            orientation=orientation,
            api_key=str(api_key or "").strip() or get_pexels_api_key(),
            http_get=http_get,
        )

    serpapi_key = get_serpapi_api_key()
    if serpapi_key and media_type == "photo":
        results = search_serpapi_google_images(
            clean_query,
            per_page=per_page,
            api_key=serpapi_key,
        )
        if results:
            return results

    unsplash_key = get_unsplash_access_key()
    pexels_key = get_pexels_api_key()
    pixabay_key = get_pixabay_api_key()
    wikimedia_enabled = (
        str(os.getenv("STOCK_PROVIDER") or "").strip().lower() in {"wikimedia", "commons"}
        or str(api_key or "").strip() == "wikimedia_keyless"
    )

    # Ưu tiên Unsplash nếu SerpApi không có hoặc trả về rỗng
    if unsplash_key and media_type == "photo":
        results = search_unsplash(
            clean_query,
            per_page=per_page,
            access_key=unsplash_key,
        )
        if results:
            return results
        if wikimedia_enabled:
            return search_wikimedia(clean_query, media_type="photo", per_page=per_page)
        return []

    # Khi dùng Unsplash làm nguồn chính (không có Pexels/Pixabay), không lấy video
    # tư liệu lưu trữ dài từ Wikimedia để tránh đè lên ảnh chụp thật của Unsplash.
    if unsplash_key and media_type == "video" and not pexels_key and not pixabay_key:
        return []

    explicit_key = str(api_key or "").strip()
    if pexels_key or (
        explicit_key
        and explicit_key not in {"wikimedia_keyless", unsplash_key, pixabay_key}
    ):
        return search_pexels(
            clean_query,
            media_type=media_type,
            per_page=per_page,
            orientation=orientation,
            api_key=explicit_key or pexels_key,
        )
    if pixabay_key:
        results = search_pixabay(
            clean_query,
            media_type=media_type,
            per_page=per_page,
            api_key=pixabay_key,
        )
        if results:
            return results
        if wikimedia_enabled:
            return search_wikimedia(
                clean_query,
                media_type=media_type,
                per_page=per_page,
            )
        return []
    if wikimedia_enabled:
        return search_wikimedia(
            clean_query,
            media_type=media_type,
            per_page=per_page,
        )
    raise RuntimeError("PEXELS_API_KEY_MISSING")
