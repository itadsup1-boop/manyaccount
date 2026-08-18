#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  Facebook News Auto Remix — Video Downloader
  Tải video Facebook: yt-dlp (thử trước) → Playwright (fallback)
═══════════════════════════════════════════════════════
"""

import os
import uuid
import hashlib
import subprocess
from pathlib import Path

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "temp", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_video(video_url: str, video_id: str) -> dict | None:
    """
    Tải video Facebook.
    Trả về {"path": "/path/to/file.mp4", "hash": "sha256...", "size": bytes} hoặc None.
    """
    # Thử yt-dlp trước
    result = _download_ytdlp(video_url, video_id)
    if result:
        return result

    # Fallback 1: Trang thứ 3 (tecniincas) qua Playwright
    print("   ↳ yt-dlp thất bại, thử qua Tecniincas...")
    result = _download_via_tecniincas(video_url, video_id)
    if result:
        return result

    # Fallback 2: Playwright trực tiếp
    print("   ↳ Tecniincas thất bại, thử Playwright trực tiếp...")
    return _download_playwright(video_url, video_id)


def _download_ytdlp(video_url: str, video_id: str) -> dict | None:
    uid = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"fb_{video_id}_{uid}.mp4")

    try:
        print(f"   📥 [yt-dlp] {video_url}")

        # Cookie cho yt-dlp (nếu có)
        cookie_file = os.path.join(os.path.dirname(__file__), "data", "fb_cookies", "fb_cookies.txt")
        cookie_arg = ["--cookies", cookie_file] if os.path.exists(cookie_file) else []

        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--no-check-certificates",
            "--no-simulate",
            *cookie_arg,
            "--print", "%(title)s",
            "-f", "best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--socket-timeout", "30",
            "--max-filesize", "200M",
            "-o", output_path,
            video_url,
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        title_extracted = ""
        if res.stdout:
            lines = [l for l in res.stdout.strip().split('\n') if l.strip()]
            if lines:
                title_extracted = lines[0].strip()

        if not os.path.exists(output_path):
            return None

        size = os.path.getsize(output_path)
        file_hash = _compute_hash(output_path)

        print(f"   ✅ Downloaded: {size / 1024 / 1024:.1f}MB")
        return {"path": output_path, "hash": file_hash, "size": size, "title": title_extracted}

    except Exception as e:
        print(f"   yt-dlp lỗi: {str(e)[:200]}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None


def _download_playwright(video_url: str, video_id: str) -> dict | None:
    uid = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"fb_{video_id}_{uid}.mp4")

    try:
        from playwright.sync_api import sync_playwright
        import requests

        print(f"   📥 [Playwright] {video_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])

            cookie_path = os.path.join(os.path.dirname(__file__), "data", "fb_cookies", "fb_state.json")
            ctx_opts = {"user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"}
            if os.path.exists(cookie_path):
                ctx_opts["storage_state"] = cookie_path

            context = browser.new_context(**ctx_opts)
            page = context.new_page()

            # Bắt video URL từ network
            video_direct_url = {"url": ""}

            def handle_response(response):
                url = response.url
                ct = response.headers.get("content-type", "")
                if ("video/" in ct or ".mp4" in url) and "thumbnail" not in url and "preview" not in url and "tiktok_web_login_static" not in url:
                    if len(url) > len(video_direct_url["url"]):
                        video_direct_url["url"] = url

            page.on("response", handle_response)

            page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # Thử click play
            try:
                play_btn = page.locator('[aria-label="Play"], [data-testid="play"]')
                if play_btn.count() > 0:
                    play_btn.first.click()
                    page.wait_for_timeout(3000)
            except:
                pass

            # Fallback: lấy src từ <video>
            if not video_direct_url["url"]:
                video_direct_url["url"] = page.evaluate("""
                    () => {
                        const videos = document.querySelectorAll('video');
                        for (const v of videos) {
                            if (v.src && v.src.startsWith('http') && !v.src.includes('blob:'))
                                return v.src;
                            const source = v.querySelector('source');
                            if (source && source.src && source.src.startsWith('http'))
                                return source.src;
                        }
                        return '';
                    }
                """) or ""

            # Lưu cookie để dùng cho requests
            playwright_cookies = context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in playwright_cookies}
            
            browser.close()

            if not video_direct_url["url"]:
                print("   ❌ Không tìm thấy URL video")
                return None

            # Download từ direct URL
            print(f"   🔗 Found: {video_direct_url['url'][:80]}...")
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                "Referer": "https://www.tiktok.com/",
                "Accept": "*/*"
            }
            resp = requests.get(video_direct_url["url"], timeout=300, stream=True, headers=headers, cookies=cookie_dict)
            resp.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)

            size = os.path.getsize(output_path)
            file_hash = _compute_hash(output_path)

            print(f"   ✅ Downloaded: {size / 1024 / 1024:.1f}MB")
            return {"path": output_path, "hash": file_hash, "size": size}

    except Exception as e:
        print(f"   ❌ Playwright download lỗi: {str(e)[:200]}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None


def _compute_hash(filepath: str) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()

def _download_via_tecniincas(video_url: str, video_id: str) -> dict | None:
    uid = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"fb_{video_id}_{uid}.mp4")

    try:
        from playwright.sync_api import sync_playwright

        print(f"   📥 [Tecniincas] {video_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page = context.new_page()

            page.goto("https://tecniincas.com.co/vi-vn/", wait_until="domcontentloaded", timeout=30000)
            page.fill('input#url', video_url)
            page.click('button.btn.btn-primary:has-text("TẢI XUỐNG")')

            # Wait for processing...
            try:
                page.wait_for_selector('button.download-btn-result.mp4', timeout=60000)
            except:
                print("   ❌ Tecniincas timeout (quá thời gian xử lý)")
                browser.close()
                return None

            # Get video title
            title_text = ""
            title_el = page.locator('p.video-title')
            if title_el.count() > 0:
                title_text = title_el.first.inner_text().strip()

            print("   ⏳ Đang tải video từ Tecniincas...")
            with page.expect_download(timeout=60000) as download_info:
                page.click('button.download-btn-result.mp4')
            
            download = download_info.value
            download.save_as(output_path)
            
            browser.close()

            if not os.path.exists(output_path):
                return None

            size = os.path.getsize(output_path)
            file_hash = _compute_hash(output_path)

            print(f"   ✅ Downloaded via Tecniincas: {size / 1024 / 1024:.1f}MB")
            return {"path": output_path, "hash": file_hash, "size": size, "title": title_text}

    except Exception as e:
        print(f"   ❌ Tecniincas lỗi: {str(e)[:200]}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None
