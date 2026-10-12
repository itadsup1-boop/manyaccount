"""Client cho RapidAPI TikTok Video No Watermark.

Tách khỏi ``video_handler`` để phần quét kênh và tải video dùng cùng host,
endpoint và quy tắc đọc phản hồi.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "rapid_api.json"
API_HOST = "tiktok-video-no-watermark2.p.rapidapi.com"
API_BASE_URL = f"https://{API_HOST}"
_DOWNLOAD_URL_CACHE: dict[str, str] = {}


def _video_id(video_url: str) -> str:
    match = re.search(r"/video/(\d+)", str(video_url or ""))
    return match.group(1) if match else ""


def _remember_download_urls(candidates: list[dict[str, Any]]) -> None:
    """Giữ link CDN ngắn hạn để không phải gọi API video-info lần nữa."""
    for candidate in candidates:
        video_id = str(candidate.get("video_id") or "")
        download_url = candidate.get("rapid_play_url")
        if video_id and isinstance(download_url, str) and download_url.startswith("http"):
            _DOWNLOAD_URL_CACHE[video_id] = download_url

    # Một worker chỉ cần các video vừa quét; tránh cache tăng mãi khi chạy lâu.
    while len(_DOWNLOAD_URL_CACHE) > 100:
        _DOWNLOAD_URL_CACHE.pop(next(iter(_DOWNLOAD_URL_CACHE)))


def has_cached_download_url(video_url: str) -> bool:
    """Cho downloader biết có thể bỏ qua các nhà cung cấp chậm hơn hay không."""
    return bool(_DOWNLOAD_URL_CACHE.get(_video_id(video_url)))


def load_config() -> dict[str, Any]:
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_keys() -> list[str]:
    env_keys = [
        item.strip()
        for item in os.environ.get("RAPIDAPI_TIKTOK_KEYS", "").split(",")
        if item.strip()
    ]
    config_keys = [
        str(item).strip()
        for item in load_config().get("keys", [])
        if str(item).strip()
    ]
    return list(dict.fromkeys([*env_keys, *config_keys]))


def _headers(key: str) -> dict[str, str]:
    return {
        "x-rapidapi-key": key,
        "x-rapidapi-host": API_HOST,
        "Content-Type": "application/json",
    }


def channel_username(channel_url: str) -> str:
    match = re.search(r"(?:tiktok\.com/)?@([^/?#]+)", str(channel_url or ""), re.I)
    if match:
        return unquote(match.group(1)).strip()
    return str(channel_url or "").rstrip("/").rsplit("/", 1)[-1].lstrip("@").strip()


def extract_user_id(profile_html: str) -> str:
    patterns = (
        r"userId=(\d+)",
        r'"userInfo"\s*:\s*\{.*?"user"\s*:\s*\{.*?"id"\s*:\s*"(\d+)"',
        r'"author"\s*:\s*\{.*?"id"\s*:\s*"(\d+)"',
    )
    for pattern in patterns:
        match = re.search(pattern, profile_html or "", re.S)
        if match:
            return match.group(1)
    return ""


def resolve_user_id(channel_url: str, *, timeout: int = 25) -> str:
    username = channel_username(channel_url)
    if not username:
        return ""
    try:
        response = requests.get(
            f"https://www.tiktok.com/@{username}",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                )
            },
            timeout=timeout,
        )
        if response.status_code == 200:
            return extract_user_id(response.text)
    except requests.RequestException:
        pass
    return ""


def parse_user_posts(
    payload: Mapping[str, Any], *, username: str, limit: int
) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, Mapping) else None
    videos = data.get("videos", []) if isinstance(data, Mapping) else []
    candidates: list[dict[str, Any]] = []
    for item in videos:
        if not isinstance(item, Mapping):
            continue
        video_id = str(item.get("video_id") or item.get("id") or "").strip()
        if not video_id:
            continue
        author = item.get("author") if isinstance(item.get("author"), Mapping) else {}
        actual_username = str(author.get("unique_id") or username).lstrip("@")
        title = str(item.get("title") or item.get("desc") or "")
        candidates.append(
            {
                "url": f"https://www.tiktok.com/@{actual_username}/video/{video_id}",
                "video_id": video_id,
                "title": title,
                "caption": title,
                "description": title,
                "thumbnail": item.get("cover") or item.get("origin_cover"),
                "duration": item.get("duration"),
                "timestamp": item.get("create_time"),
                "view_count": item.get("play_count"),
                "like_count": item.get("digg_count"),
                "comment_count": item.get("comment_count"),
                "position": len(candidates),
                "rapid_play_url": item.get("play"),
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def get_user_posts(channel_url: str, limit: int = 5) -> list[dict[str, Any]]:
    username = channel_username(channel_url)
    if not username:
        return []
    user_id = resolve_user_id(channel_url)
    params = {
        "unique_id": f"@{username}",
        "count": max(1, min(int(limit), 50)),
        "cursor": 0,
        "sort_type": 0,
    }
    if user_id:
        params["user_id"] = user_id

    for key in load_keys():
        try:
            response = requests.get(
                f"{API_BASE_URL}/user/posts",
                headers=_headers(key),
                params=params,
                timeout=25,
            )
            if response.status_code != 200:
                print(
                    f"   ⚠️ RapidAPI key '{key[:8]}...' trả về "
                    f"HTTP {response.status_code} khi quét."
                )
                continue
            payload = response.json()
            candidates = parse_user_posts(payload, username=username, limit=limit)
            if candidates:
                _remember_download_urls(candidates)
                return candidates
            print(
                f"   ⚠️ RapidAPI key '{key[:8]}...' không trả về video "
                f"({payload.get('msg') or payload.get('message') or 'response rỗng'})."
            )
        except (requests.RequestException, ValueError) as error:
            print(f"   ⚠️ RapidAPI quét lỗi với key '{key[:8]}...': {error}")
    return []


def get_video_info(video_url: str) -> dict[str, Any] | None:
    cached_url = _DOWNLOAD_URL_CACHE.get(_video_id(video_url))
    if cached_url:
        return {"play": cached_url, "source": "user_posts_cache"}

    for key in load_keys():
        try:
            response = requests.get(
                f"{API_BASE_URL}/",
                headers=_headers(key),
                params={"url": video_url, "hd": 1},
                timeout=25,
            )
            if response.status_code != 200:
                print(
                    f"   ⚠️ RapidAPI video-info trả về HTTP {response.status_code}."
                )
                continue
            payload = response.json()
            data = payload.get("data") if isinstance(payload, Mapping) else None
            if isinstance(data, dict) and (data.get("hdplay") or data.get("play")):
                return data
        except requests.RequestException as error:
            print(f"   ⚠️ RapidAPI video-info lỗi kết nối: {error}")
            continue
        except ValueError:
            print("   ⚠️ RapidAPI video-info trả về JSON không hợp lệ.")
            continue
    return None
