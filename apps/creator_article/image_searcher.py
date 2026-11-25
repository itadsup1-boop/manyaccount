import os
import sys
import json
import time
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import requests
from duckduckgo_search import DDGS

try:
    from apps.creator_article.stock_provider import (
        get_serpapi_api_key,
        search_serpapi_google_images,
        search_bing_highres_images,
        _is_junk_image_url,
    )
except ImportError:
    try:
        from stock_provider import (
            get_serpapi_api_key,
            search_serpapi_google_images,
            search_bing_highres_images,
            _is_junk_image_url,
        )
    except ImportError:
        def get_serpapi_api_key() -> str:
            return str(os.getenv("SERPAPI_API_KEY") or "").strip()

        def search_serpapi_google_images(*args, **kwargs):
            return []

        def search_bing_highres_images(*args, **kwargs):
            return []

        def _is_junk_image_url(url: str) -> bool:
            return False

try:
    from PIL import Image
except ImportError:  # Pillow is a project dependency; keep a soft fallback anyway.
    Image = None

DEFAULT_HISTORY_PATH = PROJECT_ROOT / "data" / "image_history.json"

MIN_DIMENSION = 500          # Bỏ qua ảnh có cạnh bé hơn 500px để không bao giờ bị vỡ nét
MIN_WIDTH = 700              # Chiều rộng tối thiểu 700px
MIN_HEIGHT = 450             # Chiều cao tối thiểu 450px
MAX_ASPECT_RATIO = 2.2       # Chống ảnh banner dài dẹt
FLAT_STDDEV_THRESHOLD = 9.0  # Chống ảnh placeholder, ảnh đơn sắc
DUPLICATE_HAMMING_DISTANCE = 6  # ahash bits that may differ and still count as "same image".
HISTORY_RECENT_LIMIT = 60


def _metadata_ok(result: dict) -> bool:
    img_url = result.get("image") or ""
    if _is_junk_image_url(img_url):
        return False
    width = result.get("width") or 0
    height = result.get("height") or 0
    try:
        width, height = int(width), int(height)
    except (TypeError, ValueError):
        return True

    if not width or not height:
        return True
    if min(width, height) < MIN_DIMENSION or width < MIN_WIDTH or height < MIN_HEIGHT:
        return False
    ratio = max(width, height) / max(1, min(width, height))
    return ratio <= MAX_ASPECT_RATIO


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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        self.last_download_metadata = []
        self._serpapi_exhausted = False

    def _verify_image(self, file_path: str, recent_hashes: list) -> dict | None:
        """Kiểm định chất lượng ảnh nghiêm ngặt: loại bỏ ảnh mờ, thumbnail bé tí, ảnh logo/đơn sắc và ảnh trùng."""
        if Image is None:
            return {}

        try:
            with Image.open(file_path) as probe:
                probe.verify()
            with Image.open(file_path) as img:
                width, height = img.size
                # Chặn hoàn toàn ảnh thumbnail nhỏ, ảnh vỡ hạt
                if min(width, height) < MIN_DIMENSION or width < MIN_WIDTH or height < MIN_HEIGHT:
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
                ext = os.path.splitext(file_path)[1].lower()
                if ext in {".jpg", ".jpeg", ".png", ".webp"}:
                    expected_fmt = "PNG" if ext == ".png" else "JPEG"
                    actual_fmt = (img.format or "").upper()
                    if actual_fmt != expected_fmt or img.mode != "RGB":
                        rgb = img.convert("RGB")
                        tmp_path = file_path + ".norm.tmp"
                        save_kwargs = {"quality": 92} if expected_fmt == "JPEG" else {}
                        rgb.save(tmp_path, format=expected_fmt, **save_kwargs)
                        os.replace(tmp_path, file_path)
                return {"width": width, "height": height, "phash": f"{image_hash:016x}"}
        except Exception:
            return None

    def filter_quality_images(
        self,
        paths: list,
        channel_id: str | None = None,
        history_path: str | os.PathLike | None = None,
    ) -> list:
        """
        Lọc ảnh đã tải sẵn (ảnh gốc bài báo): bỏ ảnh quá nhỏ, méo, placeholder
        hoặc trùng ảnh đã dùng gần đây cho kênh. Ảnh đạt chuẩn được ghi vào
        lịch sử chống trùng để ảnh search sau không chọn lại chúng.
        """
        if not paths:
            return []

        history_file = Path(history_path) if history_path else DEFAULT_HISTORY_PATH
        history = _read_history(history_file)
        history_key = str(channel_id or "default").strip() or "default"
        recent_hashes = [
            int(value, 16) for value in history.get(history_key, [])
            if isinstance(value, str)
        ]

        kept = []
        removed = 0
        for path in paths:
            if _is_junk_image_url(str(path)):
                removed += 1
                continue
            verified = self._verify_image(path, recent_hashes) if os.path.exists(path) else None
            if verified is None:
                removed += 1
                continue
            image_hash = verified.get("phash")
            if image_hash:
                recent_hashes.append(int(image_hash, 16))
                history.setdefault(history_key, [])
                history[history_key] = (
                    history[history_key] + [image_hash]
                )[-HISTORY_RECENT_LIMIT:]
            kept.append(path)

        if removed:
            print(
                f"   🧹 Lọc ảnh gốc bài báo: bỏ {removed} ảnh mờ/placeholder/trùng, "
                f"giữ {len(kept)} ảnh đạt chuẩn."
            )
        if kept:
            _write_history(history_file, history)
        return kept

    def download_missing_images(
        self,
        prompts: list,
        save_dir: str,
        channel_id: str | None = None,
        history_path: str | os.PathLike | None = None,
    ) -> list:
        """
        Duyệt qua mảng mô tả ảnh (của ChatGPT):
        1. Ưu tiên số 1: Tìm kiếm qua SerpApi (Google Images) để lấy ảnh báo chí,
           sự kiện thực tế đúng ngữ cảnh bài báo tại Việt Nam.
        2. Fallback: Nếu không có API key hoặc không tìm được, chuyển sang DuckDuckGo.
        Ảnh được kiểm định chất lượng nghiêm ngặt (đủ nét, không placeholder, không trùng lặp).
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

        serpapi_key = get_serpapi_api_key()
        if serpapi_key:
            print("   🔑 [SerpApi] Phát hiện API key, ưu tiên tìm ảnh Google Images chân thật theo sự kiện...")

        for idx, prompt in enumerate(prompts):
            print(f"   🔎 Đang săn ảnh sắc nét cho: '{prompt}'...")
            downloaded_this = False

            # ƯU TIÊN 1: Bing HighRes Images (100% MIỄN PHÍ, KHÔNG CẦN KEY, KHÔNG GIỚI HẠN, ẢNH GỐC FULL HD)
            try:
                bing_results = search_bing_highres_images(prompt, per_page=15)
                for cand in bing_results:
                    img_url = cand.get("asset_url")
                    if not img_url or _is_junk_image_url(img_url):
                        continue
                    try:
                        r = requests.get(
                            img_url,
                            headers={
                                **self.headers,
                                "Referer": cand.get("page_url") or "https://www.bing.com/",
                            },
                            timeout=10,
                        )
                        # Chặn ảnh thumbnail nhỏ < 25KB
                        if r.status_code != 200 or len(r.content) < 25000:
                            continue

                        file_path = os.path.join(save_dir, f"search_img_{idx + 1}.jpg")
                        with open(file_path, "wb") as f:
                            f.write(r.content)

                        verified = self._verify_image(file_path, recent_hashes)
                        if verified is None:
                            try:
                                os.remove(file_path)
                            except OSError:
                                pass
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
                            "source_url": cand.get("page_url") or "",
                            "source_name": "Bing HighRes Images (FREE)",
                            "search_query": prompt,
                            "grounding_text": prompt,
                            "rights_status": "editorial_photo",
                            "width": verified.get("width"),
                            "height": verified.get("height"),
                        })
                        print(f"     ✅ [Bing HighRes - FREE] Tải thành công ảnh gốc FULL HD: {verified.get('width')}x{verified.get('height')} ({len(r.content)//1024} KB)!")
                        downloaded_this = True
                        break
                    except Exception:
                        continue
            except Exception as e:
                print(f"   ⚠️ Lỗi Bing HighRes: {e}")

            if downloaded_this:
                continue

            # ƯU TIÊN 2: SerpApi Google Images (Nếu còn quota trong gói)
            if serpapi_key and not self._serpapi_exhausted:
                try:
                    serp_results = search_serpapi_google_images(
                        prompt, per_page=10, api_key=serpapi_key
                    )
                    for cand in serp_results:
                        target_urls = [cand.get("asset_url"), cand.get("thumbnail_url")]
                        for img_url in target_urls:
                            if not img_url or _is_junk_image_url(img_url):
                                continue
                            try:
                                r = requests.get(
                                    img_url,
                                    headers={
                                        **self.headers,
                                        "Referer": "https://www.google.com/",
                                    },
                                    timeout=10,
                                )
                                if r.status_code != 200 or len(r.content) < 25000:
                                    continue

                                file_path = os.path.join(save_dir, f"search_img_{idx + 1}.jpg")
                                with open(file_path, "wb") as f:
                                    f.write(r.content)

                                verified = self._verify_image(file_path, recent_hashes)
                                if verified is None:
                                    try:
                                        os.remove(file_path)
                                    except OSError:
                                        pass
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
                                    "source_url": cand.get("page_url") or "",
                                    "source_name": "Google Images (SerpApi)",
                                    "search_query": prompt,
                                    "grounding_text": prompt,
                                    "rights_status": "serpapi_google_images",
                                    "width": verified.get("width"),
                                    "height": verified.get("height"),
                                })
                                print(f"     ✅ [SerpApi] Bắt được 1 ảnh Google Images đạt chuẩn: {verified.get('width')}x{verified.get('height')}!")
                                downloaded_this = True
                                break
                            except Exception:
                                continue
                        if downloaded_this:
                            break
                except Exception as e:
                    err_msg = str(e).lower()
                    if "run out of searches" in err_msg or "429" in err_msg:
                        print("   ⚠️ SerpApi đã hết 250 lượt miễn phí. Tự động chuyển 100% sang nguồn FREE!")
                        self._serpapi_exhausted = True
                    else:
                        print(f"   ⚠️ Lỗi tìm SerpApi ({e}), chuyển sang fallback...")

            if downloaded_this:
                continue

            max_retries = 2
            success = False

            for attempt in range(max_retries):
                try:
                    time.sleep(random.uniform(1.0, 2.5))
                    results = list(ddgs.images(
                        keywords=prompt,
                        region="vn-vi",
                        safesearch="moderate",
                        size="Large",
                        max_results=15
                    ))
                    results = [res for res in results if _metadata_ok(res)]

                    for res in results:
                        img_url = res.get("image")
                        if not img_url or _is_junk_image_url(img_url):
                            continue
                        try:
                            r = requests.get(img_url, headers=self.headers, timeout=10)
                            if r.status_code != 200 or len(r.content) < 25000:
                                continue

                            ext = img_url.split(".")[-1][:4]
                            if ext.lower() not in ["jpg", "jpeg", "png", "webp"]:
                                ext = "jpg"
                            file_path = os.path.join(save_dir, f"search_img_{idx + 1}.{ext}")
                            with open(file_path, "wb") as f:
                                f.write(r.content)

                            verified = self._verify_image(file_path, recent_hashes)
                            if verified is None:
                                try:
                                    os.remove(file_path)
                                except OSError:
                                    pass
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
                            print(f"     ✅ [DuckDuckGo] Bắt được 1 ảnh lớn đạt chuẩn: {verified.get('width')}x{verified.get('height')}!")
                            success = True
                            break
                        except Exception:
                            continue

                    if not success:
                        print(f"     ❌ Thất bại: Không có ảnh nào đạt chuẩn chất lượng (đủ nét, không logo).")

                    break
                except Exception as e:
                    print(f"   ⚠️ DuckDuckGo lỗi ({e})...")
                    time.sleep(3)

            if not success and not downloaded_this:
                print(f"   ❌ Đã từ bỏ ảnh '{prompt}' sau khi quét tất cả các nguồn.")

        _write_history(history_file, history)
        return downloaded_paths


# Test thử nếu chạy trực tiếp
if __name__ == "__main__":
    searcher = ImageSearcher()
    test_prompts = ["xe cứu hỏa đang phun nước dập lửa", "cảnh sát giao thông phân luồng"]
    test_dir = os.path.join(os.path.dirname(__file__), "test_search_images")
    res = searcher.download_missing_images(test_prompts, test_dir, channel_id="test_channel")
    print("Các ảnh tải về:", res)
