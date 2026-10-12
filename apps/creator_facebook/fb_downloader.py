#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  Facebook News Auto Remix — Video Downloader
  Tải video Facebook: yt-dlp (thử trước) → Playwright (fallback)
═══════════════════════════════════════════════════════
"""

import json
import os
import uuid
import hashlib
import subprocess
from pathlib import Path

import requests

from shared.core.ffmpeg_utils import ffprobe_command
from apps.creator_facebook.facebook_pipeline.auth import (
    NETSCAPE_COOKIE_PATH,
    STORAGE_STATE_PATH,
    chromium_launch_options,
)
from apps.creator_facebook.facebook_pipeline.dash_download import download_dash_video

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "temp", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MIN_SOURCE_DIMENSION = 360  # reject corrupt/HTML-error/extremely low-res downloads.


def _is_tiktok_url(url: str) -> bool:
    """Nhận diện cả link TikTok đầy đủ và link rút gọn vt.tiktok.com."""
    value = str(url or "").lower()
    return "tiktok.com" in value


def _verify_downloaded_video(path: str) -> bool:
    """Reject files that aren't actually decodable video before they enter the
    pipeline (HTML error pages saved as .mp4, truncated downloads, near-zero
    resolution sources). This is a cheap ffprobe check, not a full decode."""
    if not path or not os.path.exists(path) or os.path.getsize(path) < 1024:
        return False
    try:
        probe = subprocess.run(
            ffprobe_command(
                "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of", "json", path,
            ),
            capture_output=True, text=True, timeout=30,
        )
        if probe.returncode != 0:
            return False
        data = json.loads(probe.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False

    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video_stream:
        return False
    try:
        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        return False
    return min(width, height) >= MIN_SOURCE_DIMENSION and duration > 0


def download_video(
    video_url: str,
    video_id: str,
    *,
    source_type: str = "page",
) -> dict | None:
    """
    Tải video Facebook hoặc TikTok gửi từ Telegram.
    Trả về {"path": "/path/to/file.mp4", "hash": "sha256...", "size": bytes} hoặc None.
    """
    # Telegram cho phép gửi link TikTok trực tiếp. Không đưa link này qua
    # Playwright/Facebook: trang TikTok không có data-video-id của Facebook và
    # sẽ luôn kết thúc bằng "Download thất bại" dù mạng vẫn hoạt động.
    if _is_tiktok_url(video_url):
        print("   ↳ Nhận diện nguồn TikTok: dùng TikWM, dự phòng yt-dlp...")
        result = _download_tiktok_via_tikwm(video_url, video_id)
        if result:
            return result
        result = _download_ytdlp(video_url, video_id)
        if result:
            return result
        print("   ❌ Không tải được TikTok qua TikWM hoặc yt-dlp.")
        return None

    # URL bài trong Group chứa nhiều player/gợi ý. yt-dlp có thể báo thành công
    # nhưng lấy nhầm video khác trên trang, nên Group phải bám đúng data-video-id.
    if source_type == "group":
        print("   ↳ Group: dùng Playwright theo đúng video_id...")
        return _download_playwright(video_url, video_id, require_target=True)

    # Page cũ vẫn thử yt-dlp trước.
    result = _download_ytdlp(video_url, video_id)
    if result:
        return result

    print("   ↳ yt-dlp thất bại, thử qua Tecniincas...")
    result = _download_via_tecniincas(video_url, video_id)
    if result:
        return result

    # Fallback: Playwright trực tiếp bằng phiên Facebook đã đăng nhập.
    print("   ↳ Thử Playwright trực tiếp bằng phiên Facebook...")
    return _download_playwright(video_url, video_id)


def _download_tiktok_via_tikwm(video_url: str, video_id: str) -> dict | None:
    """Tải TikTok qua TikWM rồi kiểm tra file bằng ffprobe.

    TikTok thường thay đổi response HTML khiến yt-dlp không trích xuất được
    link. TikWM trả về URL CDN MP4 trực tiếp và xử lý được cả vt.tiktok.com.
    """
    uid = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"tt_{video_id}_{uid}.mp4")
    timeout = float(os.environ.get("TIKWM_TIMEOUT_SECONDS", "30"))
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.post(
            os.environ.get("TIKWM_API_URL", "https://www.tikwm.com/api/"),
            data={"url": video_url, "hd": 1},
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or payload.get("code") != 0:
            print(f"   ❌ TikWM không trả dữ liệu video: {str(payload)[:180]}")
            return None

        media_urls = [data.get("hdplay"), data.get("play")]
        media_urls = [str(url).strip() for url in media_urls if str(url or "").startswith("http")]
        if not media_urls:
            print("   ❌ TikWM không trả URL CDN MP4.")
            return None

        for media_url in media_urls:
            try:
                with requests.get(
                    media_url,
                    stream=True,
                    headers={**headers, "Referer": "https://www.tiktok.com/"},
                    timeout=max(timeout, 60),
                ) as media_response:
                    media_response.raise_for_status()
                    with open(output_path, "wb") as output:
                        for chunk in media_response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                output.write(chunk)
                if _verify_downloaded_video(output_path):
                    size = os.path.getsize(output_path)
                    print(f"   ✅ TikWM downloaded: {size / 1024 / 1024:.1f}MB")
                    return {
                        "path": output_path,
                        "hash": _compute_hash(output_path),
                        "size": size,
                        "title": str(data.get("title") or "").strip(),
                    }
            except (OSError, requests.RequestException) as error:
                print(f"   ⚠️ TikWM CDN lỗi: {str(error)[:160]}")
            if os.path.exists(output_path):
                os.remove(output_path)

    except (OSError, ValueError, requests.RequestException) as error:
        print(f"   ❌ TikWM lỗi: {type(error).__name__}: {str(error)[:180]}")
    finally:
        if os.path.exists(output_path) and not _verify_downloaded_video(output_path):
            os.remove(output_path)
    return None


def _download_ytdlp(video_url: str, video_id: str) -> dict | None:
    uid = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"fb_{video_id}_{uid}.mp4")

    try:
        print(f"   📥 [yt-dlp] {video_url}")

        # Cookie cho yt-dlp (nếu có)
        cookie_file = str(NETSCAPE_COOKIE_PATH)
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

        if not _verify_downloaded_video(output_path):
            print("   ❌ File tải về không phải video hợp lệ (hỏng/độ phân giải quá thấp).")
            if os.path.exists(output_path):
                os.remove(output_path)
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


def _download_playwright(
    video_url: str,
    video_id: str,
    *,
    require_target: bool = False,
) -> dict | None:
    uid = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"fb_{video_id}_{uid}.mp4")

    try:
        from playwright.sync_api import sync_playwright
        import requests

        print(f"   📥 [Playwright] {video_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(**chromium_launch_options(headless=True))

            cookie_path = str(STORAGE_STATE_PATH)
            ctx_opts = {"user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"}
            if os.path.exists(cookie_path):
                ctx_opts["storage_state"] = cookie_path

            context = browser.new_context(**ctx_opts)
            page = context.new_page()

            # Facebook thường trả video/audio DASH thành nhiều byte-range.
            media_urls = []

            def handle_response(response):
                url = response.url
                ct = response.headers.get("content-type", "")
                if ("video/" in ct or ".mp4" in url) and "thumbnail" not in url and "preview" not in url and "tiktok_web_login_static" not in url:
                    media_urls.append(url)

            page.on("response", handle_response)

            page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # Ưu tiên phát đúng player của video đang xử lý.
            target_metrics = {}
            try:
                target_metrics = page.evaluate(
                    """
                    async ({ videoId }) => {
                      const marker = document.querySelector(`[data-video-id="${videoId}"]`);
                      const video = marker && (
                        marker.matches('video')
                          ? marker
                          : marker.querySelector('video') ||
                            marker.closest('[aria-posinset], [role="article"]')?.querySelector('video')
                      );
                      if (!video) return { found: false };
                      video.muted = true;
                      try { await video.play(); } catch (_) {}
                      return {
                        found: true,
                        duration: Number(video.duration || 0),
                        width: Number(video.videoWidth || 0),
                        height: Number(video.videoHeight || 0),
                      };
                    }
                    """,
                    {"videoId": str(video_id)},
                ) or {}
                page.wait_for_timeout(5000)
            except Exception:
                pass

            if require_target and not target_metrics.get("found"):
                browser.close()
                print(f"   ❌ Không tìm thấy đúng player video_id={video_id}")
                return None
            if target_metrics.get("found"):
                print(
                    "   🎯 Player đích: "
                    f"{int(target_metrics.get('width') or 0)}x"
                    f"{int(target_metrics.get('height') or 0)}, "
                    f"{float(target_metrics.get('duration') or 0):.1f}s"
                )

            # Fallback cho video progressive có src HTTP trực tiếp.
            if not media_urls:
                direct_url = page.evaluate("""
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
                if direct_url:
                    media_urls.append(direct_url)

            # Lưu cookie để dùng cho requests
            playwright_cookies = context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in playwright_cookies}
            
            browser.close()

            if not media_urls:
                print("   ❌ Không tìm thấy URL video")
                return None

            print(f"   🔗 Found: {len(media_urls)} luồng media Facebook")
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                "Referer": "https://www.facebook.com/",
                "Accept": "*/*"
            }
            downloaded = download_dash_video(
                media_urls,
                output_path,
                headers=headers,
                cookies=cookie_dict,
                target_metrics=target_metrics,
            )

            if not downloaded or not _verify_downloaded_video(output_path):
                print("   ❌ File tải về không phải video hợp lệ (hỏng/độ phân giải quá thấp).")
                if os.path.exists(output_path):
                    os.remove(output_path)
                return None

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

            if not _verify_downloaded_video(output_path):
                print("   ❌ File tải về không phải video hợp lệ (hỏng/độ phân giải quá thấp).")
                if os.path.exists(output_path):
                    os.remove(output_path)
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
