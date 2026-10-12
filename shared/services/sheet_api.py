import hashlib
import os
import tempfile
import threading
import time
import random
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

import requests


_SAVE_LOCKS = {}
_SAVE_LOCKS_GUARD = threading.Lock()
_IDEMPOTENT_SAVE_ACTIONS = {"save", "save_facebook"}


def _normalise_dedup_value(value):
    """Chuẩn hóa giá trị dùng làm khóa chống ghi trùng."""
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        try:
            parts = urlsplit(text)
            # Fragment không xác định một bài/video khác; query vẫn giữ lại
            # vì một số nguồn dùng query để phân biệt video.
            text = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))
        except ValueError:
            pass
    return text.casefold()


def _save_dedup_key(script_url, payload, source_url=None, channel_id=None, sheet_name=None):
    source = source_url
    channel = channel_id
    if source is None:
        source = payload.get("link") or payload.get("url") or payload.get("original_video")
    if channel is None:
        channel = payload.get("tiktok_id") or payload.get("id_tiktok")
    sheet = sheet_name or payload.get("sheet_name") or "__default__"
    return "|".join(
        (
            _normalise_dedup_value(script_url),
            _normalise_dedup_value(sheet),
            _normalise_dedup_value(source),
            _normalise_dedup_value(channel),
        )
    )


@contextmanager
def _cross_process_save_lock(key):
    """Khóa cùng một khóa save giữa các thread/process trên máy hiện tại.

    fcntl được dùng trên Linux/macOS (môi trường chạy hiện tại). Trên môi
    trường không có fcntl, khóa thread vẫn bảo vệ các worker trong một process.
    """
    with _SAVE_LOCKS_GUARD:
        lock = _SAVE_LOCKS.setdefault(key, threading.Lock())
    lock.acquire()
    handle = None
    try:
        try:
            import fcntl

            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
            lock_path = os.path.join(tempfile.gettempdir(), f"tiktoknews_sheet_save_{digest}.lock")
            handle = open(lock_path, "a+")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            handle = None
        yield
    finally:
        if handle is not None:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
            try:
                handle.close()
            except OSError:
                pass
        lock.release()


def save_idempotent_to_sheet(
    script_url,
    payload,
    *,
    source_url=None,
    channel_id=None,
    sheet_name=None,
):
    """Ghi một dòng duy nhất cho cùng nguồn + kênh.

    Các action ghi (`save`, `save_facebook`, ...) có thể đã append thành công
    dù HTTP response bị timeout/rỗng. Vì vậy tuyệt đối không dùng retry mù:
    đọc lại Sheet trước khi ghi và sau mọi response mơ hồ.
    """
    if not script_url or not isinstance(payload, dict):
        return None

    source = source_url
    if source is None:
        source = payload.get("link") or payload.get("url") or payload.get("original_video")
    channel = channel_id
    if channel is None:
        channel = payload.get("tiktok_id") or payload.get("id_tiktok")
    target_sheet = sheet_name or payload.get("sheet_name")
    key = _save_dedup_key(script_url, payload, source, channel, target_sheet)

    with _cross_process_save_lock(key):
        existing = find_saved_script_row(script_url, source, channel, sheet_name=target_sheet)
        if existing:
            return {"status": "success", "row": existing, "deduplicated": True}
        if existing is None:
            return {
                "status": "error",
                "message": "Không xác minh được Sheet trước khi save; dừng để tránh ghi trùng.",
            }

        try:
            response = requests.post(script_url, json=payload, timeout=30)
        except (requests.RequestException, OSError) as exc:
            response = None
            error_message = str(exc)
        else:
            error_message = ""

        # Dù request lỗi, server có thể đã append. Luôn read-back trước khi
        # kết luận thất bại hoặc thử lại.
        if response is not None and response.status_code == 200 and response.text.strip():
            try:
                result = response.json()
            except ValueError:
                result = None
            if isinstance(result, dict) and result.get("status") == "success":
                if result.get("row"):
                    return result
                recovered = find_saved_script_row(script_url, source, channel, sheet_name=target_sheet)
                if recovered:
                    return {"status": "success", "row": recovered, "recovered": True}
                return result
            if isinstance(result, dict) and "lock" in str(result.get("message", "")).casefold():
                # Lock của Apps Script không phải append thành công; đọc lại,
                # rồi chỉ retry khi chắc chắn chưa có dòng.
                existing = find_saved_script_row(script_url, source, channel, sheet_name=target_sheet)
                if existing:
                    return {"status": "success", "row": existing, "deduplicated": True}
                if existing is None:
                    return {"status": "error", "message": "Không xác minh được kết quả save sau lỗi lock."}
                time.sleep(2)
                try:
                    retry_response = requests.post(script_url, json=payload, timeout=30)
                    if retry_response.status_code == 200 and retry_response.text.strip():
                        retry_result = retry_response.json()
                        if isinstance(retry_result, dict) and retry_result.get("status") == "success":
                            return retry_result
                    error_message = "Google Sheet từ chối save do lock."
                except (requests.RequestException, ValueError, OSError) as exc:
                    error_message = str(exc)
            elif isinstance(result, dict):
                return result
        else:
            error_message = error_message or (
                f"HTTP {response.status_code}" if response is not None else "Không nhận được phản hồi"
            )

        existing = find_saved_script_row(script_url, source, channel, sheet_name=target_sheet)
        if existing:
            return {"status": "success", "row": existing, "recovered": True}
        if existing is None:
            return {
                "status": "error",
                "message": f"{error_message}; không xác minh được kết quả save, không retry để tránh trùng.",
            }
        return {"status": "error", "message": error_message or "Không ghi được dữ liệu vào Sheet."}


def save_to_sheet(script_url, link, title, script, combined_hints, original_video, title_tiktok, tiktok_id, file_path=""):

    if not script_url: return None

    payload = {
        "action": "save",
        "link": link,
        "title": title,
        "script": script,
        "combined_hints": combined_hints,
        "original_video": original_video,
        "title_tiktok": title_tiktok,
        "tiktok_id": tiktok_id, # Cột N
        "file_path": file_path,
        "pipeline_status": "scripted",
        "pipeline_stage": "scripted",
    }

    return save_idempotent_to_sheet(
        script_url,
        payload,
        source_url=link,
        channel_id=tiktok_id,
    )


def find_saved_script_row(script_url, source_url, tiktok_id, sheet_name=None):
    """Trả về số dòng, 0 nếu chắc chắn chưa có, None nếu không xác minh được."""
    payload = {"action": "read_bulk_optimized"}
    if sheet_name:
        payload["sheet_name"] = sheet_name
    result = safe_post_json(
        script_url,
        payload,
        timeout=30,
        max_retries=2,
    )
    if not isinstance(result, dict) or result.get("status") != "success":
        return None
    rows = result.get("data")
    if not isinstance(rows, list):
        return None
    source_url = _normalise_dedup_value(source_url)
    channel_id = _normalise_dedup_value(str(tiktok_id or "").replace("@", ""))
    for item in reversed(rows):
        if not isinstance(item, dict):
            continue
        row_source = _normalise_dedup_value(
            item.get("url") or item.get("link") or item.get("original_video_url") or ""
        )
        row_channel = _normalise_dedup_value(str(item.get("tiktok_id") or "").replace("@", ""))
        if row_source == source_url and row_channel == channel_id and item.get("row"):
            return item["row"]
    return 0

def update_tiktok_info(script_url, row, file_path=None, link_tiktok=None, title_tiktok=None):
    """
    [CŨ/MỚI] Cập nhật thông tin cơ bản (Action: update_tiktok_info)
    """
    try:
        payload = {"action": "update_tiktok_info", "row": int(row)}
        if file_path: payload["file_path"] = str(file_path)
        if link_tiktok: payload["link_tiktok"] = str(link_tiktok)
        if title_tiktok: payload["title_tiktok"] = str(title_tiktok)

        requests.post(script_url, json=payload, timeout=20)
        return True
    except: return False

def update_final_result(
    script_url,
    row_idx,
    drive_link,
    *,
    pipeline_status="uploaded",
    pipeline_stage="uploaded",
):
    payload = {
        "action": "update_file_path",
        "row": int(row_idx),
        "file_path": str(drive_link),
        "pipeline_status": str(pipeline_status),
        "pipeline_stage": str(pipeline_stage),
    }
    result = safe_post_json(script_url, payload)
    return result.get("status") == "success" if result else False

def update_source_link(script_url, row_idx, link):
    """
    Cập nhật link gốc Tiktok vào Cột A của dòng đã có.
    """
    payload = {
        "action": "update_link", 
        "row": int(row_idx),
        "link": str(link)
    }
    result = safe_post_json(script_url, payload)
    return result.get("status") == "success" if result else False

def update_voice_links(sheet_url, row, title_voice_link, content_voice_link):

    try:
        payload = {
            "action": "update_voice",
            "row": int(row),
            "title_voice": str(title_voice_link) if title_voice_link else "",
            "content_voice": str(content_voice_link) if content_voice_link else ""
        }
        requests.post(sheet_url, json=payload, timeout=20)
        return True
    except Exception as e:
        print(f"❌ Lỗi update voice: {e}")
        return False

def update_status_finish(script_url, row, link_tiktok):

    try:
        payload = {
            "action": "finish_upload",
            "row": int(row),
            "link_tiktok": str(link_tiktok),
            "pipeline_status": "published",
            "pipeline_stage": "published",
        }
        res = requests.post(script_url, json=payload, timeout=20)
        return res.json().get("status") == "success"
    except: return False

# ==============================================================================
# 2. CÁC HÀM ĐỌC DỮ LIỆU (READ)
# ==============================================================================

def get_data_from_sheet(script_url, row_number=None):

    if not script_url: return None

    payload = {"action": "read"}
    if row_number: payload["row"] = int(row_number)

    try:
        res = requests.post(script_url, json=payload, timeout=30)
        if res.status_code != 200: return None

        data = res.json()
        if data.get("status") == "success":
            # Xử lý text
            raw_title = data.get("title_text", "")
            clean_title = raw_title.replace("\n", " ").strip() if raw_title else ""
            raw_content = data.get("content_text", "")
            clean_content = raw_content.replace("\n", " ").strip() if raw_content else ""

            return (
                data.get("url", "").strip(),            # 0
                clean_title,                            # 1
                clean_content,                          # 2
                data.get("row"),                        # 3
                data.get("existing_content_audio", ""), # 4
                data.get("existing_title_audio", ""),   # 5
                data.get("image_prompts", []),          # 6
                data.get("original_video_url", ""),     # 7
                data.get("tiktok_id", ""),              # 8 [QUAN TRỌNG: ID TikTok]
                data.get("title_tiktok", ""),           # 9
                data.get("status", "")                  # 10
            )
        else: return None
    except: return None

def get_pending_tasks(script_url):

    if not script_url: return []
    try:
        payload = {"action": "read_pending"}
        res = requests.post(script_url, json=payload, timeout=30)
        data = res.json()
        if data.get("status") == "success":
            return data.get("tasks", [])
        return []
    except: return []

def get_last_row_index(sheet_url, sheet_name=None):
    try:
        payload = {"action": "read", "row": ""}
        if sheet_name:
            payload["sheet_name"] = sheet_name
        # Gửi request
        response = requests.post(sheet_url, json=payload, timeout=10)

        if response.status_code != 200:
            print(f"❌ HTTP Error {response.status_code}: {response.text}")
            return 0

        try:
            data = response.json()
        except Exception as json_err:
            print(f"❌ Lỗi đọc JSON (Có thể Script bị Crash): {response.text[:200]}...") # In 200 ký tự đầu
            return 0

        if data.get("status") == "success":
            return int(data.get("row", 0))
        return 0

    except Exception as e:
        print(f"🔥 Lỗi Exception: {e}")
        return 0

def get_latest_row_by_id(sheet_url, tiktok_id):
    if not sheet_url: return None
    payload = {"action": "read_bulk_optimized"}
    try:
        res = requests.post(sheet_url, json=payload, timeout=30)
        if res.status_code != 200 or not res.text.strip():
            print("⚠️ Google Sheet không phản hồi hoặc trả về nội dung rỗng.")
            return None

        try:
            data_json = res.json()
        except Exception as e:
            print(f"🔥 Lỗi đọc JSON (API Script có thể bị lỗi cú pháp hoặc sai quyền): {res.text[:500]}")
            return None

        if data_json.get("status") != "success":
            return None

        all_rows = data_json.get("data", []) # Mảng 200 dòng cuối
    except Exception as e:
        print(f"🔥 Lỗi lấy dữ liệu từ Sheet: {e}")
        return None

    # Chuẩn hóa ID để so sánh chính xác
    def norm(x): return str(x).replace("@","").strip().lower()
    target = norm(tiktok_id)

    # Duyệt NGƯỢC danh sách trên RAM (Micro-giây)
    for item in reversed(all_rows):
        sheet_id = norm(item.get("tiktok_id", ""))
        content = item.get("content_text", "")

        if target == sheet_id:
            if content and len(str(content)) > 5:
                return {
                    "row": item.get("row"),
                    "title_text": item.get("title_text", ""),
                    "content_text": content,
                    "tone": item.get("tone", "Trung tính"),
                    "music_mood": item.get("music_mood"),
                    "music_energy": item.get("music_energy", 2),
                    "is_sensitive": item.get("is_sensitive", False),
                    "tiktok_id_sheet": sheet_id
                }
            else:
                print(f"📍 Dòng {item.get('row')} khớp ID {tiktok_id} nhưng Text chưa sẵn sàng.")
                return None
    return None

def safe_post_json(
    url,
    payload,
    timeout=30,
    max_retries=3,
    retry_empty=True,
):
    """
    Hàm gửi request an toàn: Tự động thử lại nếu Google trả về rỗng hoặc lỗi Lock.
    """
    # Bắt cả caller cũ chưa chuyển sang save_idempotent_to_sheet, để không
    # còn đường nào retry mù các action append dòng.
    if str(payload.get("action", "")).strip().casefold() in _IDEMPOTENT_SAVE_ACTIONS:
        return save_idempotent_to_sheet(url, payload)

    for attempt in range(max_retries):
        try:
            res = requests.post(url, json=payload, timeout=timeout)

            # 1. Kiểm tra mã lỗi HTTP
            if res.status_code != 200:
                print(f"⚠️ Lần {attempt+1}: HTTP {res.status_code}. Đang thử lại...")
                time.sleep(random.uniform(2, 5))
                continue

            # 2. Kiểm tra nội dung rỗng (Lỗi char 0)
            raw_text = res.text.strip()
            if not raw_text:
                print(f"⚠️ Lần {attempt+1}: Server trả về rỗng (char 0). Đang thử lại...")
                if not retry_empty:
                    return {"status": "error", "message": "Server trả về rỗng."}
                time.sleep(random.uniform(2, 5))
                continue

            # 3. Thử đọc JSON
            data = res.json()

            # 4. Kiểm tra nếu Google báo lỗi "Could not acquire lock"
            if data.get("status") == "error" and "lock" in data.get("message", "").lower():
                print(f"⚠️ Lần {attempt+1}: Google đang bận (Lock). Đang đợi...")
                time.sleep(random.uniform(3, 7))
                continue

            return data

        except (requests.RequestException, ValueError, OSError) as e:
            print(f"🔥 Lần {attempt+1}: Lỗi kết nối: {e}")
            time.sleep(2)

    return {"status": "error", "message": "Exceeded max retries"}
