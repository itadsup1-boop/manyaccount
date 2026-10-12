"""Quét và tải video TikTok qua trang ClipSaver bằng Playwright chạy ngầm."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import unicodedata
import uuid
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

import requests
from filelock import FileLock, Timeout


CLIPSSAVER_BASE_URL = "https://clipssaver.com/tiktok-profile-downloader"
MAX_VIDEOS_PER_CHANNEL = 3
CARD_SELECTOR = "div[role='button'].tiktok-video-card"
TITLE_SELECTOR = "p.video-desc"
DOWNLOAD_SELECTOR = "button[aria-label='Save video']"
LOAD_MORE_SELECTOR = "button.load-more-btn"
_DEFAULT_LOCK_PATH = Path(os.environ.get("TIKTOK_CLIPSSAVER_LOCK", "/tmp/tiktok_clipssaver.lock"))


def _get_lock_path(channel_url: str = "") -> Path:
    if channel_url:
        try:
            user = channel_username(channel_url).lower()
            if user:
                clean_user = re.sub(r"[^a-zA-Z0-9_.-]+", "_", user)
                return Path(f"/tmp/tiktok_clipssaver_{clean_user}.lock")
        except Exception:
            pass
    return _DEFAULT_LOCK_PATH


@contextmanager
def _clipssaver_lock(channel_url: str = "", timeout: float = 120):
    lock_path = _get_lock_path(channel_url)
    if lock_path.exists():
        try:
            mtime = lock_path.stat().st_mtime
            if time.time() - mtime > 180:
                print(f"      🧹 Phát hiện stale lock ({lock_path.name}), đang tự động dọn dẹp...")
                lock_path.unlink(missing_ok=True)
        except Exception:
            pass

    lock = FileLock(str(lock_path), timeout=timeout)
    try:
        lock.acquire(timeout=timeout)
    except Timeout:
        print(f"      ⚠️ Timeout file lock ({lock_path.name}), dọn dẹp và thử lại lần cuối...")
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            lock.acquire(timeout=15)
        except Timeout as err:
            raise ClipSaverError(
                f"Không thể lấy file lock ({lock_path.name}) cho kênh {channel_url or 'chung'} sau nhiều lần thử."
            ) from err

    try:
        yield lock
    finally:
        try:
            lock.release()
        except Exception:
            pass


class ClipSaverError(RuntimeError):
    """Lỗi có thể đọc được khi ClipSaver không trả dữ liệu hoặc không tải được."""


def channel_username(channel_url: str) -> str:
    """Lấy username kênh nguồn, luôn bỏ ký tự @."""
    raw = str(channel_url or "").strip()
    match = re.search(r"(?:tiktok\.com/)?@([^/?#]+)", raw, re.I)
    if match:
        return unquote(match.group(1)).strip().lstrip("@")
    try:
        path = urlsplit(raw).path
        if path:
            return unquote(path.rstrip("/").rsplit("/", 1)[-1]).strip().lstrip("@")
    except ValueError:
        pass
    return raw.rstrip("/").rsplit("/", 1)[-1].lstrip("@").strip()


def profile_url(channel_url: str) -> str:
    username = channel_username(channel_url)
    if not username:
        raise ClipSaverError("Không xác định được tên kênh nguồn TikTok.")
    return f"{CLIPSSAVER_BASE_URL}/{quote(username, safe='._-')}"


def normalize_title(title: str) -> str:
    """Chuẩn hóa tiêu đề để so sánh trùng ổn định."""
    value = unicodedata.normalize("NFKC", str(title or ""))
    value = value.replace("\u200b", "").replace("\ufeff", "")
    return " ".join(value.casefold().split())


def title_dedupe_key(channel_url: str, title: str) -> str:
    username = channel_username(channel_url).casefold()
    normalized = normalize_title(title)
    return f"{username}:{normalized}" if username and normalized else ""


def _candidate_reference(username: str, title_key: str) -> str:
    digest = hashlib.sha256(title_key.encode("utf-8")).hexdigest()[:20]
    return f"https://www.tiktok.com/@{quote(username, safe='._-')}#clipssaver-{digest}"


def build_candidate(
    channel_url: str,
    title: str,
    *,
    position: int,
    thumbnail: str = "",
    published_text: str = "",
    original_url: str = "",
) -> dict[str, Any]:
    username = channel_username(channel_url)
    dedupe_key = title_dedupe_key(channel_url, title)
    source_ref = original_url or _candidate_reference(username, dedupe_key)
    return {
        "url": source_ref,
        "source_profile_url": f"https://www.tiktok.com/@{username}",
        "provider": "clipssaver",
        "provider_url": profile_url(channel_url),
        "provider_position": int(position),
        "video_id": hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:20],
        "title": str(title or "").strip(),
        "caption": str(title or "").strip(),
        "description": str(title or "").strip(),
        "title_key": dedupe_key,
        "thumbnail": thumbnail or None,
        "published_text": published_text,
        "position": int(position),
    }


def _apply_stealth(page: Any) -> None:
    try:
        from playwright_stealth import Stealth

        Stealth().apply_stealth_sync(page)
    except (ImportError, AttributeError, TypeError):
        return


def _launch_context(playwright: Any) -> tuple[Any, Any]:
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    )
    context = browser.new_context(
        accept_downloads=True,
        viewport={"width": 1365, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        locale="vi-VN",
    )
    return browser, context


def _open_video_grid(page: Any, target_url: str, timeout_ms: int) -> Any:
    page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(1500)
    page.mouse.wheel(0, 900)
    cards = page.locator(CARD_SELECTOR)
    try:
        cards.first.wait_for(state="visible", timeout=timeout_ms)
    except Exception as error:
        page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
        page.mouse.wheel(0, 1000)
        try:
            cards.first.wait_for(state="visible", timeout=timeout_ms)
        except Exception as retry_error:
            raise ClipSaverError(
                "ClipSaver không hiển thị danh sách video. Có thể trang đang chặn, "
                "đổi giao diện hoặc kênh không tồn tại."
            ) from retry_error
    # Chờ React gắn xong sự kiện click cho các nút Save.
    page.wait_for_timeout(2000)
    return cards


def _select_newest_sort(page: Any) -> None:
    """ClipSaver mặc định xếp theo lượt xem; pipeline cần video mới nhất."""
    try:
        sort_button = page.get_by_text(re.compile(r"^Sort:"), exact=False).first
        if not sort_button.count():
            return
        current_label = str(sort_button.inner_text() or "")
        if "Newest" in current_label:
            return
        sort_button.click()
        newest_option = page.get_by_text("Newest", exact=True).first
        newest_option.wait_for(state="visible", timeout=5000)
        newest_option.click()
        page.wait_for_timeout(1200)
    except Exception:
        # Nếu ClipSaver đổi nhãn, vẫn lấy được tối đa ba thẻ thay vì làm sập worker.
        return


def _full_title(card: Any) -> str:
    title_element = card.locator(TITLE_SELECTOR).first
    title = title_element.get_attribute("title") or title_element.inner_text()
    return str(title or "").strip()


def _original_video_url(card: Any) -> str:
    selectors = (
        "a[href*='tiktok.com'][href*='/video/']",
        "a[href*='/video/']",
    )
    for selector in selectors:
        link = card.locator(selector).first
        if link.count():
            href = str(link.get_attribute("href") or "").strip()
            if href.startswith("http"):
                return href
    return ""


def get_channel_video_candidates(channel_url: str, limit: int = 3) -> list[dict[str, Any]]:
    """Lấy tối đa ba video mới nhất của một kênh nguồn từ ClipSaver."""
    from playwright.sync_api import sync_playwright

    requested_limit = max(1, min(int(limit or MAX_VIDEOS_PER_CHANNEL), MAX_VIDEOS_PER_CHANNEL))
    target_url = profile_url(channel_url)
    timeout_ms = int(os.environ.get("TIKTOK_CLIPSSAVER_TIMEOUT_MS", "90000"))
    candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    lock_timeout = max(120, timeout_ms // 1000 + 30)
    with _clipssaver_lock(channel_url, timeout=lock_timeout):
        with sync_playwright() as playwright:
            browser, context = _launch_context(playwright)
            try:
                page = context.new_page()
                _apply_stealth(page)
                cards = _open_video_grid(page, target_url, timeout_ms)
                _select_newest_sort(page)
                count = min(cards.count(), requested_limit)
                for index in range(count):
                    card = cards.nth(index)
                    title = _full_title(card)
                    title_key = title_dedupe_key(channel_url, title)
                    if not title_key or title_key in seen_titles:
                        continue
                    seen_titles.add(title_key)
                    thumbnail = str(
                        card.locator("img.thumbnail-img").first.get_attribute("src") or ""
                    )
                    published = ""
                    date_element = card.locator("span.meta-date").first
                    if date_element.count():
                        published = str(date_element.inner_text() or "").strip()
                    candidates.append(
                        build_candidate(
                            channel_url,
                            title,
                            position=index,
                            thumbnail=thumbnail,
                            published_text=published,
                            original_url=_original_video_url(card),
                        )
                    )
            finally:
                context.close()
                browser.close()
    return candidates[:requested_limit]


def _valid_video(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 100_000:
        return False
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0 and "video" in result.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def _download_response_url(context: Any, media_url: str, destination: Path) -> bool:
    cookies = {item["name"]: item["value"] for item in context.cookies()}
    try:
        with requests.get(
            media_url,
            stream=True,
            timeout=90,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0", "Referer": CLIPSSAVER_BASE_URL},
            cookies=cookies,
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        return _valid_video(destination)
    except requests.RequestException:
        destination.unlink(missing_ok=True)
        return False


def download_candidate(candidate: dict[str, Any], temp_dir: str) -> str:
    """Bấm đúng nút Save của video có tiêu đề tương ứng và trả đường dẫn MP4."""
    from playwright.sync_api import sync_playwright

    title = str(candidate.get("title") or candidate.get("caption") or "").strip()
    expected_key = str(candidate.get("title_key") or "").strip()
    channel_url = str(candidate.get("source_profile_url") or "").strip()
    if not expected_key and channel_url and title:
        expected_key = title_dedupe_key(channel_url, title)
    target_url = str(candidate.get("provider_url") or profile_url(channel_url)).strip()
    if not expected_key or not target_url:
        raise ClipSaverError("Thiếu tiêu đề hoặc địa chỉ ClipSaver của video cần tải.")

    output_dir = Path(temp_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"src_clipssaver_{candidate.get('video_id') or uuid.uuid4().hex[:12]}_{uuid.uuid4().hex[:8]}.mp4"
    timeout_ms = int(os.environ.get("TIKTOK_CLIPSSAVER_DOWNLOAD_TIMEOUT_MS", "120000"))

    lock_timeout = max(150, timeout_ms // 1000 + 30)
    with _clipssaver_lock(channel_url, timeout=lock_timeout):
        with sync_playwright() as playwright:
            browser, context = _launch_context(playwright)
            try:
                page = context.new_page()
                _apply_stealth(page)
                cards = _open_video_grid(page, target_url, timeout_ms)
                _select_newest_sort(page)
                matched_card = None
                for index in range(cards.count()):
                    card = cards.nth(index)
                    if normalize_title(_full_title(card)) == expected_key.split(":", 1)[-1]:
                        matched_card = card
                        break
                if matched_card is None:
                    raise ClipSaverError(
                        "Không còn tìm thấy video theo tiêu đề trên ClipSaver."
                    )

                matched_card.scroll_into_view_if_needed()
                button = matched_card.locator(DOWNLOAD_SELECTOR).first
                button.wait_for(state="visible", timeout=timeout_ms)

                media_urls: list[str] = []

                def capture_download_request(route: Any, request: Any) -> None:
                    request_url = str(request.url or "")
                    if request_url and request_url not in media_urls:
                        media_urls.append(request_url)
                    # Không để Chromium tải thêm một bản blob rất lớn. Sau khi
                    # lấy được URL, requests sẽ tải thẳng vào file đích.
                    route.abort()

                page.route(
                    re.compile(r"https://clipssaver\.com/api/download/cdn\?.+"),
                    capture_download_request,
                )

                click_actions = (
                    lambda: button.click(force=True, timeout=15000),
                    lambda: button.evaluate("element => element.click()"),
                    lambda: button.dispatch_event("click"),
                )
                for click_action in click_actions:
                    try:
                        click_action()
                    except Exception:
                        pass
                    for _ in range(30):
                        if media_urls:
                            break
                        page.wait_for_timeout(500)
                    if media_urls:
                        break

                download_urls = list(reversed(media_urls))
                for media_url in list(download_urls):
                    query = parse_qs(urlsplit(media_url).query)
                    direct_url = str((query.get("url") or [""])[0]).strip()
                    if direct_url:
                        download_urls.append(direct_url)

                for media_url in download_urls:
                    if _download_response_url(context, media_url, output_path):
                        break

                if not _valid_video(output_path):
                    output_path.unlink(missing_ok=True)
                    raise ClipSaverError(
                        "ClipSaver không trả về file video hợp lệ sau khi bấm Save."
                    )
                return str(output_path)
            finally:
                context.close()
                browser.close()
