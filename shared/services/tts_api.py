import os
import re
import subprocess
import time
import uuid
import requests

from shared.core.ffmpeg_utils import ffprobe_command

# ─── CẤU HÌNH ──────────────────────────────────────────────────────────────────
DEFAULT_PROFILE_ID = "3fb3db24-b0af-4db4-b75f-b897f0431843"
DEFAULT_SPEED       = 1.03
# TTS tự nhiên có thể nhanh/chậm hơn ước lượng theo số từ một chút. Chỉ coi
# audio là bị cụt khi thấp hơn 92% sàn ước lượng; tránh retry vô ích do lệch
# vài phần trăm hoặc do làm tròn duration của ffprobe.
MIN_DURATION_RATIO = 0.92

# Alias cũ → UUID mới trong DB
_ALIAS_MAP = {
    "theanh28": DEFAULT_PROFILE_ID,
    "tiktok":   DEFAULT_PROFILE_ID,
    "847040":   DEFAULT_PROFILE_ID,
    "viterbox": DEFAULT_PROFILE_ID,
}


def _voicebox_api_key(explicit_key=None):
    """Resolve the TTS credential without ever logging it."""
    environment_key = str(os.environ.get("VOICEBOX_API_KEY") or "").strip()
    if environment_key:
        return environment_key

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    env_path = os.path.join(project_root, ".env")
    try:
        with open(env_path, "r", encoding="utf-8", errors="replace") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "VOICEBOX_API_KEY":
                    file_key = value.strip().strip("\"'")
                    if file_key:
                        return file_key
    except OSError:
        pass

    return str(explicit_key or "").strip()


def probe_audio_duration(audio_path):
    """Return the decoded duration in seconds, or 0 when the file is invalid."""
    if not audio_path or not os.path.isfile(audio_path):
        return 0.0
    try:
        result = subprocess.run(
            ffprobe_command(
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return max(0.0, float((result.stdout or "").strip()))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def _minimum_expected_duration(text, speed):
    """Conservative floor used to detect a severely truncated TTS response.

    This deliberately only catches responses that stop after a few words.  TTS
    providers vary in their pauses and speaking rate, so it is not intended to
    predict the exact final duration.
    """
    words = len(re.findall(r"\S+", str(text or "")))
    if words <= 0:
        return 0.0
    try:
        rate = max(0.5, float(speed))
    except (TypeError, ValueError):
        rate = DEFAULT_SPEED
    estimated = (words * 0.20) / rate
    return max(0.75, estimated * MIN_DURATION_RATIO)


def create_voice_full_pipeline(
    text,
    save_dir,
    filename,
    profile_id=DEFAULT_PROFILE_ID,
    rvc_pitch=0,
    emotion="binh_thuong",
    speed=DEFAULT_SPEED,
    rvc_model=None,
    api_key=None,
    idempotency_key=None,
):
    """
    Gọi API Voicebox Full Pipeline với cơ chế tự động thử lại 3 lần.
    """
    save_path = os.path.join(save_dir, filename)
    # Never replace a previously good file until the new response has been
    # completely downloaded and decoded successfully.
    part_path = f"{save_path}.part-{os.getpid()}"

    # Chuẩn hóa alias → UUID
    if rvc_model and str(rvc_model).strip():
        profile_id = _ALIAS_MAP.get(str(rvc_model).strip(), str(rvc_model).strip())
    profile_id = _ALIAS_MAP.get(profile_id, profile_id)

    # Nếu người dùng điền sai hoặc trống thì dùng mặc định
    if not profile_id or "VD:" in str(profile_id) or len(str(profile_id).strip()) < 5:
        profile_id = DEFAULT_PROFILE_ID

    url = "https://voice.adsup.vn/api/external/tts"
    payload = {
        "text": text,
        "voice_id": profile_id,
        "language": "vi",
        "speed": float(speed)
    }
    resolved_api_key = _voicebox_api_key(api_key)
    if not resolved_api_key:
        print("❌ Thiếu VOICEBOX_API_KEY; không thể gọi API TTS.", flush=True)
        return None
    request_idempotency_key = str(idempotency_key or uuid.uuid4().hex).strip()
    headers = {
        "X-API-Key": resolved_api_key,
        "Idempotency-Key": request_idempotency_key,
    }

    print(f"🚀 Đang gửi yêu cầu sinh giọng từ xa tới {url} với voice_id={profile_id}...", flush=True)
    for attempt in range(1, 4):
        try:
            # Reuse the same key for every retry so the server does not render
            # or charge for the same audio request more than once.
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=180,
            )
            if response.status_code != 200:
                print(f"⚠️ Thử lần {attempt}/3 thất bại ({response.status_code}): {response.text[:200]}", flush=True)
                response.close()
                if response.status_code in {401, 402, 409, 422}:
                    break
            else:
                os.makedirs(save_dir, exist_ok=True)
                try:
                    with open(part_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    response.close()

                    file_size = os.path.getsize(part_path) if os.path.exists(part_path) else 0
                    duration = probe_audio_duration(part_path)
                    minimum_duration = _minimum_expected_duration(text, speed)
                    word_count = len(re.findall(r"\S+", str(text or "")))
                    print(
                        f"🔎 TTS kiểm tra: {word_count} từ, "
                        f"{file_size} bytes, {duration:.2f}s (tối thiểu {minimum_duration:.2f}s)",
                        flush=True,
                    )
                    if file_size < 1024 or duration <= 0 or duration < minimum_duration:
                        print(
                            f"⚠️ TTS trả audio có vẻ bị cụt ở lần {attempt}/3 "
                            f"(duration={duration:.2f}s); sẽ gọi lại.",
                            flush=True,
                        )
                        try:
                            os.remove(part_path)
                        except OSError:
                            pass
                    else:
                        os.replace(part_path, save_path)
                        print(
                            f"✅ Đã tải và lưu file âm thanh thành công tại: {save_path} "
                            f"({duration:.2f}s)",
                            flush=True,
                        )
                        return save_path
                finally:
                    response.close()
        except Exception as e:
            print(f"⚠️ Thử lần {attempt}/3 lỗi kết nối: {e}", flush=True)
            try:
                if os.path.exists(part_path):
                    os.remove(part_path)
            except OSError:
                pass
        if attempt < 3:
            time.sleep(2 * attempt)

    print(f"❌ Cả 3 lần gọi API TTS tới {url} đều thất bại.", flush=True)
    return None


def create_voice_default(text, save_dir, filename):
    return create_voice_full_pipeline(text, save_dir, filename)


def create_voice_clone(text, ref_audio_path, ref_text, save_dir, filename):
    return create_voice_full_pipeline(
        text, save_dir, filename,
        profile_id=DEFAULT_PROFILE_ID,
    )


if __name__ == "__main__":
    BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    OUTPUT_DIR = os.path.join(BASE_DIR, "assets", "temp_voice")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    text = "Xin chào! Đây là bài kiểm tra kết nối API với tiếng Việt có dấu."
    print(f"Test: {text}\n")

    result = create_voice_full_pipeline(
        text=text,
        save_dir=OUTPUT_DIR,
        filename="test_voice_api.wav",
        profile_id=DEFAULT_PROFILE_ID
    )

    if result:
        print(f"\nTHANH CONG: {result}")
    else:
        print("\nTHAT BAI!")
