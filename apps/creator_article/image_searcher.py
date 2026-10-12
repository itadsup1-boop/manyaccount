import os
import json
import time
import random
from pathlib import Path

import requests
from duckduckgo_search import DDGS

try:
    from PIL import Image
except ImportError:  # Pillow is a project dependency; keep a soft fallback anyway.
    Image = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HISTORY_PATH = PROJECT_ROOT / "data" / "image_history.json"

MIN_DIMENSION = 480          # reject thumbnails too small for a 1080x1920 render.
MAX_ASPECT_RATIO = 2.4       # reject banner/divider-shaped images (likely ads/decoration).
FLAT_STDDEV_THRESHOLD = 8.0  # near-solid color / placeholder ("image not found") images.
DUPLICATE_HAMMING_DISTANCE = 6  # ahash bits that may differ and still count as "same image".
HISTORY_RECENT_LIMIT = 60


def _rank_score(result: dict) -> float:
    """Score a DuckDuckGo image result before downloading anything.

    Higher is better. Known-good resolution/aspect ratio beats unknown
    metadata, which in turn beats known-bad (tiny or banner-shaped) results.
    """
    width = result.get("width") or 0
    height = result.get("height") or 0
    try:
        width, height = int(width), int(height)
    except (TypeError, ValueError):
        width, height = 0, 0

    if not width or not height:
        return 1_500_000.0  # neutral: metadata missing, still worth trying.

    area = min(width * height, 4_000_000)
    long_side, short_side = max(width, height), max(1, min(width, height))
    ratio = long_side / short_side
    ratio_penalty = 0.0 if ratio <= MAX_ASPECT_RATIO else (ratio - MAX_ASPECT_RATIO) * 200_000
    size_penalty = 0.0 if min(width, height) >= MIN_DIMENSION else 2_000_000.0
    return area - ratio_penalty - size_penalty


def _average_hash(image: "Image.Image") -> int:
    """Cheap 8x8 average-hash for near-duplicate detection (no extra deps)."""
    small = image.convert("L").resize((8, 8), Image.LANCZOS)
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for pixel in pixels:
        bits = (bits << 1) | (1 if pixel >= avg else 0)
    return bits


def _grayscale_stddev(image: "Image.Image") -> float:
    small = image.convert("L").resize((32, 32), Image.LANCZOS)
    pixels = list(small.getdata())
    mean = sum(pixels) / len(pixels)
    variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
    return variance ** 0.5


def _hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _read_history(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_history(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


class ImageSearcher:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.last_download_metadata = []

    def _verify_image(self, file_path: str, recent_hashes: list) -> dict | None:
        """Validate a downloaded file and return its metadata, or None to reject it."""
        if Image is None:
            return {}  # Pillow unavailable: skip quality checks rather than block the pipeline.

        try:
            with Image.open(file_path) as probe:
                probe.verify()
            with Image.open(file_path) as img:
                width, height = img.size
                if min(width, height) < MIN_DIMENSION:
                    return None
                ratio = max(width, height) / max(1, min(width, height))
                if ratio > MAX_ASPECT_RATIO:
                    return None
                stddev = _grayscale_stddev(img)
                if stddev < FLAT_STDDEV_THRESHOLD:
                    return None
                image_hash = _average_hash(img)
                if any(_hamming_distance(image_hash, prior) <= DUPLICATE_HAMMING_DISTANCE for prior in recent_hashes):
                    return None
                return {"width": width, "height": height, "phash": f"{image_hash:016x}"}
        except Exception:
            return None

    def download_missing_images(
        self,
        prompts: list,
        save_dir: str,
        channel_id: str | None = None,
        history_path: str | os.PathLike | None = None,
    ) -> list:
        """
        Duyệt qua mảng mô tả ảnh (của ChatGPT), tìm trên DuckDuckGo, xếp hạng theo
        độ phân giải/tỷ lệ khung hình, rồi tải ảnh đầu tiên vừa tải được vừa qua
        kiểm tra chất lượng (đủ nét, không phải ảnh đơn sắc/placeholder, không
        trùng ảnh vừa dùng gần đây cho kênh này).
        """
        if not prompts:
            self.last_download_metadata = []
            return []

        print(f"🛠️ Tool săn ảnh kích hoạt: Cần tìm {len(prompts)} ảnh còn thiếu...")
        os.makedirs(save_dir, exist_ok=True)
        downloaded_paths = []
        self.last_download_metadata = []
        ddgs = DDGS()

        history_file = Path(history_path) if history_path else DEFAULT_HISTORY_PATH
        history = _read_history(history_file)
        history_key = str(channel_id or "default").strip() or "default"
        recent_hashes = [
            int(value, 16) for value in history.get(history_key, [])
            if isinstance(value, str)
        ]

        for idx, prompt in enumerate(prompts):
            print(f"   🔎 Đang search: '{prompt}'...")

            max_retries = 3
            success = False

            for attempt in range(max_retries):
                try:
                    # Ngủ ngẫu nhiên một chút trước khi search để tránh bị chém IP
                    time.sleep(random.uniform(1.5, 3.5))

                    # Tìm ảnh với từ khóa, ưu tiên ảnh to (Large) để làm video cho nét
                    results = list(ddgs.images(
                        keywords=prompt,
                        region="wt-wt",
                        safesearch="moderate",
                        size="Large",
                        max_results=8  # lấy dư để có đủ ứng viên sau khi xếp hạng/loại
                    ))
                    results.sort(key=_rank_score, reverse=True)

                    for res in results:
                        img_url = res.get("image")
                        if not img_url:
                            continue
                        try:
                            r = requests.get(img_url, headers=self.headers, timeout=10)
                            if r.status_code != 200 or not r.content:
                                continue

                            ext = img_url.split(".")[-1][:4]
                            if ext.lower() not in ["jpg", "jpeg", "png", "webp"]:
                                ext = "jpg"
                            file_path = os.path.join(save_dir, f"search_img_{idx + 1}.{ext}")
                            with open(file_path, "wb") as f:
                                f.write(r.content)

                            verified = self._verify_image(file_path, recent_hashes)
                            if verified is None:
                                os.remove(file_path)
                                continue

                            downloaded_paths.append(file_path)
                            image_hash = verified.get("phash")
                            if image_hash:
                                recent_hashes.append(int(image_hash, 16))
                                history.setdefault(history_key, [])
                                history[history_key] = (
                                    history[history_key] + [image_hash]
                                )[-HISTORY_RECENT_LIMIT:]
                            self.last_download_metadata.append({
                                "path": file_path,
                                "asset_url": img_url,
                                "source_url": res.get("url") or "",
                                "source_name": "DuckDuckGo Images",
                                "search_query": prompt,
                                "grounding_text": prompt,
                                "rights_status": "unknown",
                                "width": verified.get("width"),
                                "height": verified.get("height"),
                            })
                            print(f"     ✅ Bắt được 1 ảnh nét căng, đúng khung hình!")
                            success = True
                            break  # Bắt được ảnh rồi thì thoát vòng lặp, sang câu prompt khác
                        except Exception:
                            continue  # Nếu link này lỗi (403, timeout) thì thử link ảnh kế tiếp

                    if not success:
                        print(f"     ❌ Thất bại: Không có ảnh nào trong top kết quả đạt chuẩn (đủ nét, không trùng, không placeholder).")

                    break  # Nếu đã thành công HOẶC không có exception thì thoát vòng lặp retry

                except Exception as e:
                    print(f"   ⚠️ Lần thử {attempt + 1}: DuckDuckGo lỗi ({e}). Đang đợi vài giây để thử lại...")
                    time.sleep(5)  # Đợi 5 giây rồi thử lại nếu bị Ratelimit

            if not success:
                print(f"   ❌ Đã từ bỏ ảnh '{prompt}' sau 3 lần thử thất bại.")

        _write_history(history_file, history)
        return downloaded_paths


# Test thử nếu chạy trực tiếp
if __name__ == "__main__":
    searcher = ImageSearcher()
    test_prompts = ["xe cứu hỏa đang phun nước dập lửa", "cảnh sát giao thông phân luồng"]
    test_dir = os.path.join(os.path.dirname(__file__), "test_search_images")
    res = searcher.download_missing_images(test_prompts, test_dir, channel_id="test_channel")
    print("Các ảnh tải về:", res)
