import os
import json
import requests
import yt_dlp
import shutil
import time
import subprocess
import uuid  # <--- [MỚI] Thêm thư viện này để tạo tên file duy nhất

# Xác định đường dẫn gốc dự án
MODULE_DIR = os.path.dirname(os.path.abspath(__file__)) # shared/modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(MODULE_DIR)) # mannyAccount
RAPID_CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "rapid_api.json")

def load_rapid_config():
    """Hàm đọc cấu hình RapidAPI từ file JSON"""
    if not os.path.exists(RAPID_CONFIG_FILE):
        return {}
    try:
        with open(RAPID_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

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
    config = load_rapid_config()
    try:
        if "@" in channel_url:
            username = channel_url.split('@')[-1].split('?')[0].strip('/')
        else:
            username = channel_url.split('/')[-1].split('?')[0]
    except: return []

    keys = config.get("keys", [])
    for key in keys:
        if not key: continue
        headers = {
            "x-rapidapi-key": key,
            "x-rapidapi-host": "tiktok-video-no-watermark2.p.rapidapi.com"
        }

        candidates = []
        try:
             url = "https://tiktok-video-no-watermark2.p.rapidapi.com/user/posts"
             response = requests.get(url, headers=headers, params={"unique_id": username, "count": limit}, timeout=20)
             if response.status_code == 200:
                 data = response.json()

                 if isinstance(data, dict):
                     items = data.get("data", {}).get("videos", []) if "data" in data else data.get("videos", [])
                     for item in items[:limit]:
                         vid_id = item.get("video_id")
                         if vid_id:
                             stats = item.get("stats") or {}
                             candidates.append({
                                 "url": f"https://www.tiktok.com/@{username}/video/{vid_id}",
                                 "video_id": str(vid_id),
                                 "title": item.get("title") or item.get("desc") or "",
                                 "caption": item.get("title") or item.get("desc") or "",
                                 "thumbnail": item.get("cover") or item.get("origin_cover"),
                                 "duration": item.get("duration"),
                                 "timestamp": item.get("create_time"),
                                 "view_count": item.get("play_count") or stats.get("play_count"),
                                 "like_count": item.get("digg_count") or stats.get("digg_count"),
                                 "comment_count": item.get("comment_count") or stats.get("comment_count"),
                                 "position": len(candidates),
                             })
                 if candidates:
                     return candidates
             else:
                 print(f"   ⚠️ Key '{key[:8]}...' trả về status code {response.status_code} khi quét.")
        except Exception as e:
             print(f"⚠️ Lỗi quét video qua RapidAPI với key '{key[:8]}...': {e}")
    return []

def get_videos_via_rapidapi(channel_url, limit=5):
    """Backward-compatible URL-only RapidAPI API."""
    return [
        item["url"]
        for item in get_video_candidates_via_rapidapi(channel_url, limit)
    ]


def get_channel_video_candidates(channel_url, limit=5):
    """Hàm tổng hợp lấy video kèm metadata cho SourceRanker."""
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

            with requests.get(v_url, stream=True, headers={"User-Agent": "Mozilla/5.0"}) as r:
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
    config = load_rapid_config()
    keys = config.get("keys", [])
    host = config.get("host", "")
    api_url = config.get("endpoint", "")
    print("      -> [Dự phòng] Đang thử kéo qua RapidAPI...")

    for key in keys:
        if not key: continue
        try:
            resp = requests.get(api_url, headers={"x-rapidapi-key": key, "x-rapidapi-host": host}, params={"url": tiktok_url}, timeout=20)
            if resp.status_code != 200: continue

            result = resp.json()
            download_url = None
            if isinstance(result, dict):
                if "data" in result and isinstance(result["data"], dict):
                    result = result["data"]
                download_url = result.get("hdplay") or result.get("video_hd") or result.get("play") or result.get("video")
                if isinstance(download_url, list): download_url = download_url[0]

            if download_url:
                with requests.get(download_url, stream=True, headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status_code == 200:
                        with open(save_path, 'wb') as f: shutil.copyfileobj(r.raw, f)
                if os.path.exists(save_path) and os.path.getsize(save_path) > 1000:
                    return True
        except:
            pass
        if os.path.exists(save_path):
            try: os.remove(save_path)
            except: pass
    return False

def download_tiktok_video(url, temp_dir):
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

    # 1. Thử TikWM
    if download_via_tikwm(url, final_path): downloaded = True
    # 2. Thử RapidAPI
    elif download_via_rapidapi(url, final_path): downloaded = True
    # 3. Fallback yt-dlp
    else:
        try:
            ydl_opts = {'outtmpl': final_path, 'format': 'best', 'quiet': True, 'overwrites': True}
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
