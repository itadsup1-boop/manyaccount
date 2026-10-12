import os
import json
import requests
import yt_dlp
import shutil
import time
import subprocess
import uuid  # <--- [MỚI] Thêm thư viện này để tạo tên file duy nhất

from shared.services.tiktok_rapidapi import (
    get_user_posts as rapidapi_get_user_posts,
    get_video_info as rapidapi_get_video_info,
    has_cached_download_url as rapidapi_has_cached_download_url,
    load_config as load_tiktok_rapidapi_config,
)
from shared.services.tiktok_clipssaver import (
    MAX_VIDEOS_PER_CHANNEL as CLIPSSAVER_MAX_VIDEOS,
    ClipSaverError,
    download_candidate as download_clipssaver_candidate,
    get_channel_video_candidates as get_clipssaver_candidates,
)

# Xác định đường dẫn gốc dự án
MODULE_DIR = os.path.dirname(os.path.abspath(__file__)) # shared/modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(MODULE_DIR)) # mannyAccount
RAPID_CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "rapid_api.json")

def load_rapid_config():
    """Hàm đọc cấu hình RapidAPI từ file JSON"""
    return load_tiktok_rapidapi_config()

# --- [MỚI] HÀM NÉN VIDEO ---
def compress_video_if_needed(input_path, limit_mb=20):
    """
    Kiểm tra dung lượng file. Nếu > limit_mb thì nén lại.
    Trả về đường dẫn file nén (hoặc file gốc nếu không cần nén).
    """
    try:
        if not os.path.exists(input_path): return None

        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)

        # Nếu file nhỏ hơn giới hạn thì dùng luôn file gốc
        if file_size_mb < limit_mb:
            print(f"   ✅ File nhẹ ({file_size_mb:.2f} MB). Không cần nén.")
            return input_path

        print(f"   ⚠️ File nặng ({file_size_mb:.2f} MB). Đang nén xuống < {limit_mb}MB cho AI Studio...")

        # Tạo tên file nén
        dir_name = os.path.dirname(input_path)
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        # File nén cũng sẽ mang tính duy nhất vì base_name đã duy nhất (nhờ hàm download bên dưới)
        output_path = os.path.join(dir_name, f"{base_name}_small.mp4")

        # Lệnh FFmpeg nén
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-vf', 'scale=-2:720',
            '-c:v', 'libx264', '-crf', '28', '-preset', 'veryfast',
            '-c:a', 'aac', '-b:a', '64k',
            '-fs', f'{int(limit_mb * 1024 * 1024)}',
            output_path
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"   🎉 Nén xong: {new_size:.2f} MB. Saved: {os.path.basename(output_path)}")
            return output_path
        else:
            print("   ❌ Lỗi nén file. Dùng tạm file gốc.")
            return input_path

    except Exception as e:
        print(f"   ❌ Lỗi Compression: {e}")
        return input_path

# --- PHẦN 1: CRAWLER (LẤY LINK VIDEO) ---

def get_video_candidates_via_rapidapi(channel_url, limit=5):
    """Sử dụng RapidAPI lấy URL và metadata nhẹ nếu yt-dlp thất bại."""
    return rapidapi_get_user_posts(channel_url, limit)

def get_videos_via_rapidapi(channel_url, limit=5):
    """Backward-compatible URL-only RapidAPI API."""
    return [
        item["url"]
        for item in get_video_candidates_via_rapidapi(channel_url, limit)
    ]


def _get_channel_video_candidates_legacy(channel_url, limit=5):
    """Luồng quét TikTok cũ; giữ lại để có thể khôi phục khi cần."""
    print(f"🔍 Đang quét kênh: {channel_url}")

    ydl_opts = {
        'quiet': True, 'extract_flat': True, 'playlistend': limit,
        'ignoreerrors': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    candidates = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            if info and 'entries' in info:
                for e in info['entries']:
                    if e:
                        v_url = e.get('url') or e.get('webpage_url')
                        if v_url:
                            candidates.append({
                                "url": v_url,
                                "video_id": str(e.get("id") or ""),
                                "title": e.get("title") or "",
                                "caption": e.get("description") or e.get("title") or "",
                                "description": e.get("description") or "",
                                "thumbnail": e.get("thumbnail"),
                                "duration": e.get("duration"),
                                "timestamp": e.get("timestamp"),
                                "view_count": e.get("view_count"),
                                "like_count": e.get("like_count"),
                                "comment_count": e.get("comment_count"),
                                "position": len(candidates),
                            })
    except Exception as e:
        print(f"⚠️ yt-dlp Error: {e}")

    if not candidates:
        print("   ↳ yt-dlp thất bại, chuyển sang RapidAPI...")
        candidates = get_video_candidates_via_rapidapi(channel_url, limit)

    return [item for item in candidates if item.get("url")]


def get_channel_video_candidates(channel_url, limit=3):
    """Quét kênh nguồn qua ClipSaver; luồng yt-dlp/RapidAPI cũ đã tắt."""
    safe_limit = max(1, min(int(limit or CLIPSSAVER_MAX_VIDEOS), CLIPSSAVER_MAX_VIDEOS))
    print(f"🔍 ClipSaver đang quét kênh nguồn: {channel_url}")
    try:
        candidates = get_clipssaver_candidates(channel_url, safe_limit)
    except ClipSaverError as error:
        print(f"   ❌ ClipSaver: {error}")
        return []
    except Exception as error:
        print(f"   ❌ ClipSaver lỗi ngoài dự kiến: {type(error).__name__}: {error}")
        return []
    print(f"   ✅ ClipSaver tìm thấy {len(candidates)}/{safe_limit} video.")
    return candidates


def get_channel_videos(channel_url, limit=5):
    """Backward-compatible URL-only API."""
    return [
        item["url"]
        for item in get_channel_video_candidates(channel_url, limit)
    ]

# --- PHẦN 2: DOWNLOADER (TẢI FILE) ---

def download_via_tikwm(url, save_path):
    try:
        api_url = "https://www.tikwm.com/api/"
        print("      -> Đang thử kéo video gốc không logo từ TikWM...")
        res = requests.post(api_url, data={'url': url, 'hd': 1}, timeout=15).json()
        if res.get('code') == 0:
            play_url = res['data']['play']
            if not play_url.startswith("http"):
                v_url = "https://www.tikwm.com" + play_url
            else:
                v_url = play_url

            with requests.get(v_url, stream=True, headers={"User-Agent": "Mozilla/5.0"}, timeout=30) as r:
                if r.status_code == 200:
                    with open(save_path, 'wb') as f:
                        shutil.copyfileobj(r.raw, f)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 1000:
                return True
    except:
        pass
    if os.path.exists(save_path):
        try: os.remove(save_path)
        except: pass
    return False

def download_via_rapidapi(tiktok_url, save_path):
    print("      -> [Dự phòng] Đang thử kéo qua RapidAPI...")
    result = rapidapi_get_video_info(tiktok_url)
    download_url = (result or {}).get("hdplay") or (result or {}).get("play")
    if isinstance(download_url, list):
        download_url = download_url[0] if download_url else None
    if download_url:
        try:
            with requests.get(
                download_url,
                stream=True,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=60,
            ) as response:
                response.raise_for_status()
                with open(save_path, "wb") as handle:
                    shutil.copyfileobj(response.raw, handle)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 1000:
                return True
        except requests.RequestException:
            pass
    if os.path.exists(save_path):
        try: os.remove(save_path)
        except: pass
    return False

def _download_tiktok_video_legacy(url, temp_dir):
    """
    Hàm tải video.
    temp_dir: Bắt buộc truyền vào thư mục tạm riêng của Account.
    Trả về Dict: {'original': path_goc, 'ai_studio': path_nho}
    """
    if not os.path.exists(temp_dir): os.makedirs(temp_dir)

    try:
        video_id = url.split("video/")[1].split("?")[0]
    except:
        video_id = str(int(time.time()))

    timestamp = int(time.time())

    # [QUAN TRỌNG] Tạo suffix ngẫu nhiên để đảm bảo tên file không bao giờ trùng
    # ngay cả khi chạy đa luồng cùng giây
    unique_suffix = str(uuid.uuid4())[:8]

    # Tên file sẽ có dạng: src_73823123_17154234_a1b2c3d4.mp4
    final_path = os.path.join(temp_dir, f"src_{video_id}_{timestamp}_{unique_suffix}.mp4")

    print(f"   ⬇️ Downloading: {url}")
    downloaded = False

    # Video vừa quét bằng RapidAPI đã có sẵn link CDN. Dùng ngay để tránh chờ
    # TikWM rồi lại gọi thêm endpoint video-info không cần thiết.
    if rapidapi_has_cached_download_url(url):
        if download_via_rapidapi(url, final_path):
            downloaded = True
        elif download_via_tikwm(url, final_path):
            downloaded = True
    # URL lẻ hoặc video do yt-dlp quét được vẫn giữ chuỗi fallback cũ.
    elif download_via_tikwm(url, final_path):
        downloaded = True
    elif download_via_rapidapi(url, final_path):
        downloaded = True
    # 3. Fallback yt-dlp
    else:
        try:
            ydl_opts = {'outtmpl': final_path, 'format': 'best', 'quiet': True, 'overwrites': True, 'socket_timeout': 30}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
            if os.path.exists(final_path) and os.path.getsize(final_path) > 1000:
                downloaded = True
            else:
                if os.path.exists(final_path):
                    try: os.remove(final_path)
                    except: pass
        except Exception as e:
            print(f"   ❌ Lỗi yt-dlp: {e}")

    if downloaded and os.path.exists(final_path) and os.path.getsize(final_path) > 1000:
        # [NEW LOGIC] Xử lý nén file cho AI Studio
        compressed_path = compress_video_if_needed(final_path, limit_mb=20)

        # Trả về cả 2 đường dẫn để Scheduler tự chọn dùng cái nào
        return {
            "original": final_path,        # Dùng để Edit/Remix (Full chất lượng)
            "ai_studio": compressed_path   # Dùng để upload AI Studio (<20MB)
        }

    return None


def download_tiktok_video(url, temp_dir, candidate=None):
    """Tải video nguồn; mặc định chỉ dùng ClipSaver.

    Luồng TikWM/RapidAPI/yt-dlp cũ vẫn còn trong
    ``_download_tiktok_video_legacy`` nhưng bị tắt. Chỉ bật lại khi chủ động đặt
    ``TIKTOK_LEGACY_SOURCE_ENABLED=true``.
    """
    candidate = candidate if isinstance(candidate, dict) else {}
    if candidate.get("provider") == "clipssaver":
        title = candidate.get("title") or candidate.get("caption") or ""
        print(f"   ⬇️ ClipSaver tải theo tiêu đề: {title}")
        try:
            original_path = download_clipssaver_candidate(candidate, temp_dir)
        except ClipSaverError as error:
            print(f"   ❌ ClipSaver: {error}")
            return None
        except Exception as error:
            print(
                f"   ❌ ClipSaver tải lỗi ngoài dự kiến: "
                f"{type(error).__name__}: {error}"
            )
            return None
        compressed_path = compress_video_if_needed(original_path, limit_mb=20)
        return {
            "original": original_path,
            "ai_studio": compressed_path,
        }

    legacy_enabled = str(
        os.environ.get("TIKTOK_LEGACY_SOURCE_ENABLED", "false")
    ).strip().lower() in {"1", "true", "yes", "on"}
    if not legacy_enabled:
        print(
            "   ❌ Luồng tải TikTok cũ đang tắt. "
            "Video phải được chọn từ ClipSaver."
        )
        return None
    return _download_tiktok_video_legacy(url, temp_dir)
