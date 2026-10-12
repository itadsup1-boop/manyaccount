"""Điều phối Playwright crawler cho Page và Group."""

from __future__ import annotations

from typing import Any

from filelock import FileLock, Timeout

from .auth import (
    SESSION_LOCK_PATH,
    STORAGE_STATE_PATH,
    browser_context_options,
    chromium_launch_options,
    save_browser_storage,
)
from .group_crawler import crawl_group_video_posts
from .page_crawler import crawl_page_videos
from .source_config import (
    SOURCE_TYPE_GROUP,
    build_crawl_url,
    normalize_source_type,
)


def _login_blocked(page: Any) -> bool:
    url = str(page.url or "").lower()
    if "/login" in url or "/checkpoint" in url:
        return True
    return page.locator('form[action*="login"], input[name="email"]').count() > 0


def crawl_facebook_videos(
    source_url: str,
    max_videos: int = 10,
    *,
    source_type: str | None = None,
    max_age_hours: int = 0,
) -> list[dict]:
    from playwright.sync_api import sync_playwright

    resolved_type = normalize_source_type(source_type, source_url)
    crawl_url = build_crawl_url(source_url, resolved_type)
    print(f"🕷️ Cào {resolved_type}: {crawl_url}")
    if resolved_type == SOURCE_TYPE_GROUP and not STORAGE_STATE_PATH.exists():
        print("   ❌ Chưa có phiên Facebook. Hãy bấm 'Đăng nhập Facebook'.")
        return []

    lock = FileLock(str(SESSION_LOCK_PATH))
    try:
        with lock.acquire(timeout=30):
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    **chromium_launch_options(headless=True)
                )
                context = browser.new_context(**browser_context_options())
                page = context.new_page()
                page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,woff,woff2}",
                    lambda route: route.abort(),
                )
                try:
                    page.goto(crawl_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(3500)
                    if _login_blocked(page):
                        print("   ❌ Phiên Facebook hết hạn hoặc đang bị checkpoint.")
                        return []
                    if resolved_type == SOURCE_TYPE_GROUP:
                        videos = crawl_group_video_posts(
                            page,
                            source_url=crawl_url,
                            max_videos=max_videos,
                            max_age_hours=max_age_hours,
                        )
                    else:
                        videos = crawl_page_videos(page, max_videos)
                    save_browser_storage(context)
                finally:
                    browser.close()
    except Timeout:
        print("   ❌ Phiên Facebook đang được tiến trình khác sử dụng.")
        return []

    print(f"   ✅ Cào được {len(videos)} bài có video")
    for index, video in enumerate(videos, start=1):
        print(
            f"      {index}. [{video['video_id']}] "
            f"{str(video.get('caption') or '')[:60]}..."
        )
    return videos
