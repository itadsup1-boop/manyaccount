import os
import requests

# ─── CẤU HÌNH ──────────────────────────────────────────────────────────────────
# Voice mặc định: "voice the anh 28" - lưu trong PostgreSQL DB
# DB đã có: rvc_model_path = voices/847040/model.pth
#           rvc_index_path = voices/847040/model.index
#           default_engine = viterbox
DEFAULT_PROFILE_ID = "d4dbf9de-2f6a-42e7-8f8d-0e5586824a21"
DEFAULT_SPEED       = 1.05

# URL kết nối API
LOCAL_URL  = "http://127.0.0.1:8080/generate/full-pipeline"
PUBLIC_URL = "https://voice.adsup.vn/generate/full-pipeline"


def _get_server_url() -> str:
    """Tự động chọn URL: thử local trước, nếu không được dùng public."""
    override = os.environ.get("VOICEBOX_API_URL", "").strip()
    if override:
        return override
    try:
        r = requests.get("http://127.0.0.1:8080/health", timeout=2)
        if r.status_code == 200:
            return LOCAL_URL
    except Exception:
        pass
    return PUBLIC_URL


# Alias cũ → UUID mới trong DB
_ALIAS_MAP = {
    "theanh28": DEFAULT_PROFILE_ID,
    "tiktok":   DEFAULT_PROFILE_ID,
    "847040":   DEFAULT_PROFILE_ID,
    "viterbox": DEFAULT_PROFILE_ID,
}


def create_voice_full_pipeline(
    text,
    save_dir,
    filename,
    profile_id=DEFAULT_PROFILE_ID,
    rvc_pitch=0,
    emotion="binh_thuong",
    speed=DEFAULT_SPEED,
    rvc_model=None,   # tương thích ngược — bị bỏ qua, DB lo
):
    """
    Gọi API Voicebox Full Pipeline.

    - profile_id : UUID của voice trong PostgreSQL hoặc short_id (mặc định: voice the anh 28)
    - Tự động gọi API remote tới voice.adsup.vn
    """
    save_path = os.path.join(save_dir, filename)

    # Chuẩn hóa alias → UUID
    if rvc_model and str(rvc_model).strip():
        profile_id = _ALIAS_MAP.get(str(rvc_model).strip(), str(rvc_model).strip())
    profile_id = _ALIAS_MAP.get(profile_id, profile_id)

    # Nếu người dùng điền "VD: uuid hoặc omnivoice", chưa điền, hoặc điền sai, thì dùng mặc định là voice mới
    if not profile_id or "VD:" in str(profile_id) or len(str(profile_id).strip()) < 5:
        profile_id = "3fb3db24-b0af-4db4-b75f-b897f0431843"
    url = "https://voice.adsup.vn/api/external/tts"
    
    payload = {
        "text": text,
        "voice_id": profile_id,
        "language": "vi",
        "speed": float(speed)
    }

    print(f"🚀 Đang gửi yêu cầu sinh giọng từ xa tới {url} với voice_id={profile_id}...", flush=True)
    try:
        response = requests.post(url, json=payload, stream=True, timeout=120)

        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"✅ Đã tải và lưu file âm thanh thành công tại: {save_path}", flush=True)
            return save_path
        else:
            print(f"❌ Lỗi gọi API: {response.status_code} - {response.text}", flush=True)
            return None
    except Exception as e:
        print(f"❌ Lỗi kết nối tới API TTS: {e}", flush=True)
        return None


# ─── Helper functions ───────────────────────────────────────────────────────────
def create_voice_default(text, save_dir, filename):
    """Dung voice mac dinh (voice the anh 28)."""
    return create_voice_full_pipeline(text, save_dir, filename)


def create_voice_clone(text, ref_audio_path, ref_text, save_dir, filename):
    """Tuong thich nguoc."""
    return create_voice_full_pipeline(
        text, save_dir, filename,
        profile_id="75b59968-5d03-4f45-ad03-45dc7d01e95e"
    )


# ─── Test truc tiep ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    OUTPUT_DIR = os.path.join(BASE_DIR, "assets", "temp_voice")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    text = "Xin chào! Đây là bài kiểm tra kết nối API với tiếng Việt có dấu để đảm bảo hệ thống đọc chuẩn xác."
    print(f"Test: {text}\n")

    result = create_voice_full_pipeline(
        text=text,
        save_dir=OUTPUT_DIR,
        filename="test_voice_api.wav",
        profile_id="3fb3db24-b0af-4db4-b75f-b897f0431843"
    )

    if result:
        print(f"\nTHANH CONG: {result}")
    else:
        print("\nTHAT BAI! Kiem tra server tai http://127.0.0.1:8080 hoac https://voice.adsup.vn")