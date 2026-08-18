#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  Facebook News Auto Remix — Crawler
  Dùng Playwright mở Facebook page, cào 10 video đầu.
═══════════════════════════════════════════════════════
"""

import os
import re
import json
import time
import random
from datetime import datetime

# Playwright
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

COOKIE_DIR = os.path.join(os.path.dirname(__file__), "data", "fb_cookies")
COOKIE_PATH = os.path.join(COOKIE_DIR, "fb_state.json")


def crawl_facebook_videos(source_url: str, max_videos: int = 10) -> list[dict]:
    """
    Mở Facebook page/videos bằng Playwright, cào danh sách video.

    Trả về list dict:
    [
      {"video_id": "123...", "url": "https://...", "caption": "..."},
      ...
    ]
    Thứ tự: MỚI NHẤT → CŨ NHẤT (theo thứ tự trên trang)
    """
    print(f"🕷️ Cào video từ: {source_url}")

    videos = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )

        # Context + cookies
        ctx_opts = {
            "user_agent": _random_ua(),
            "viewport": {"width": 1920, "height": 1080},
            "locale": "vi-VN",
            "timezone_id": "Asia/Ho_Chi_Minh",
        }
        if os.path.exists(COOKIE_PATH):
            ctx_opts["storage_state"] = COOKIE_PATH
            print("   🍪 Dùng cookies đã lưu")
        else:
            print("   ⚠️ Chưa có cookies — chạy: python3 login_facebook.py")

        context = browser.new_context(**ctx_opts)
        page = context.new_page()

        # Chặn ảnh/font cho nhanh
        page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())

        # Xây URL đúng (hỗ trợ /videos, /reels, profile)
        videos_url = _build_page_url(source_url)
        print(f"   🌐 Mở: {videos_url}")

        try:
            page.goto(videos_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"   ❌ Không mở được trang: {e}")
            browser.close()
            return []

        time.sleep(3 + random.random() * 2)

        # Check login wall
        if "/login" in page.url or "checkpoint" in page.url:
            print("   ❌ Facebook yêu cầu đăng nhập!")
            print("   💡 Chạy: python3 login_facebook.py")
            browser.close()
            return []

        # Scroll
        scroll_count = random.randint(3, 5)
        print(f"   📜 Scroll {scroll_count} lần...")
        for _ in range(scroll_count):
            page.evaluate("window.scrollBy(0, 800 + Math.random() * 700)")
            time.sleep(1.5 + random.random() * 2)

        # Lấy link video từ DOM
        raw_links = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.href;
                    if (href.includes('/videos/') || href.includes('/watch/?v=') || href.includes('/reel/')) {
                        results.push({
                            href: href,
                            text: (a.innerText || '').trim().substring(0, 500)
                        });
                    }
                });
                return results;
            }
        """)

        print(f"   🔗 Tìm thấy {len(raw_links)} link thô")

        # Lọc trùng, giữ thứ tự
        seen = set()
        for link in raw_links:
            if len(videos) >= max_videos:
                break

            video_id = _extract_video_id(link["href"])
            if not video_id or video_id in seen or len(video_id) < 6:
                continue
            seen.add(video_id)

            videos.append({
                "video_id": video_id,
                "url": f"https://www.facebook.com/watch/?v={video_id}",
                "caption": link.get("text", ""),
            })

        # Lưu cookies
        try:
            os.makedirs(COOKIE_DIR, exist_ok=True)
            context.storage_state(path=COOKIE_PATH)
        except:
            pass

        browser.close()

    print(f"   ✅ Cào được {len(videos)} video (mới → cũ)")
    for i, v in enumerate(videos, 1):
        print(f"      {i}. [{v['video_id']}] {v['caption'][:60]}...")

    return videos


def login_facebook_interactive():
    """
    Mở browser CÓ giao diện để user login Facebook thủ công.
    Sau khi login xong, lưu cookies cho crawler dùng.
    """
    print("╔═══════════════════════════════════════════════════╗")
    print("║  🔑 Login Facebook — Lưu cookie cho crawler      ║")
    print("╚═══════════════════════════════════════════════════╝")
    print()
    print("📋 Hướng dẫn:")
    print("   1. Trình duyệt sẽ mở Facebook")
    print("   2. Bạn đăng nhập tài khoản")
    print("   3. Sau khi thấy News Feed → nhấn ENTER ở terminal")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="vi-VN",
        )
        page = context.new_page()

        print("🌐 Đang mở Facebook...")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")

        print()
        input("👉 Đăng nhập xong rồi nhấn ENTER... ")

        # Lưu cookies
        os.makedirs(COOKIE_DIR, exist_ok=True)
        context.storage_state(path=COOKIE_PATH)

        print(f"\n✅ Cookies đã lưu: {COOKIE_PATH}")
        print("🎉 Crawler sẽ dùng cookies này để quét Facebook!")

        browser.close()


# ─── HELPERS ───

def _build_page_url(source_url: str) -> str:
    """
    Xây URL đúng để cào video.
    - facebook.com/page/reels   → giữ nguyên
    - facebook.com/page/videos  → giữ nguyên
    - facebook.com/page         → thêm /reels (nhiều content hơn /videos)
    - facebook.com/profile.php  → thêm &sk=reels
    """
    url = source_url.rstrip("/")

    # Đã có /reels hoặc /videos → giữ nguyên
    if url.endswith("/reels") or url.endswith("/videos"):
        return url

    # Profile URL
    if "profile.php" in url:
        return url + "&sk=reels"

    # Page bình thường → mặc định /reels
    return url + "/reels"

def _extract_video_id(url: str) -> str | None:
    patterns = [
        r'/videos/(\d+)',
        r'/watch/\?v=(\d+)',
        r'/reel/(\d+)',
        r'story_fbid=(\d+)',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def _random_ua() -> str:
    uas = [
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    ]
    return random.choice(uas)


# ─── CLI ───
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        login_facebook_interactive()
    elif len(sys.argv) > 1:
        results = crawl_facebook_videos(sys.argv[1])
        print(f"\n📊 Tổng: {len(results)} video")
    else:
        print("Cách dùng:")
        print("  python3 fb_crawler.py login                       → Login Facebook")
        print("  python3 fb_crawler.py https://facebook.com/page   → Test cào")
