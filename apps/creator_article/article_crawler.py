import os
import hashlib
import re
import requests
import shutil
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def _resolve_ffmpeg_binary():
    """Return a usable FFmpeg executable on Windows and Unix.

    The Web Hub may be started from a GUI process whose PATH does not contain
    the system FFmpeg installation.  ``imageio-ffmpeg`` is already a project
    dependency and provides a bundled executable as a reliable fallback.
    """
    configured = os.getenv("FFMPEG_BINARY", "").strip()
    candidates = [configured, shutil.which("ffmpeg")]
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isabs(candidate):
            if os.path.isfile(candidate):
                return candidate
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.exists(bundled):
            return bundled
    except Exception as exc:
        print(f"   ⚠️ Không tìm thấy FFmpeg hệ thống/bundled: {exc}")
    return "ffmpeg"

class ArticleCrawler:
    MAX_CLEAN_CONTENT_CHARS = 8000
    _ARTICLE_SELECTORS = (
        "#article_body",
        ".singular-content",
        "article",
        ".detail-content",
        ".article-body",
        ".article-content",
    )
    _NOISE_HINTS = (
        "nav", "menu", "sidebar", "related", "recommend", "quang cao",
        "advertisement", "ads", "banner", "footer", "header", "breadcrumb",
        "comment", "social", "share", "newsletter", "subscribe", "cookie",
        "popup", "modal", "login", "pagination", "tag-list",
    )

    def __init__(self):
        # Tránh bị web báo chặn chặn Bot
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    @staticmethod
    def _normalize_text(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @classmethod
    def _is_noise_element(cls, element):
        values = [str(element.get("id") or "")]
        classes = element.get("class") or []
        values.extend(str(item) for item in classes)
        marker = " ".join(values).lower().replace("-", " ").replace("_", " ")
        return any(hint in marker for hint in cls._NOISE_HINTS)

    @classmethod
    def _article_container(cls, soup):
        for selector in cls._ARTICLE_SELECTORS:
            container = soup.select_one(selector)
            if container:
                return container
        return soup

    @staticmethod
    def _fetch_rendered_html(url, timeout_ms=20000):
        """Render the page with a real browser for sites that inject the
        article body via JavaScript (requests+BeautifulSoup only sees the
        pre-hydration shell, which yields 0 characters for those sites)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                try:
                    page = browser.new_page(user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ))
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_timeout(2500)
                    return page.content()
                finally:
                    browser.close()
        except Exception as e:
            print(f"   ⚠️ Không render được trang bằng trình duyệt: {e}")
            return None

    @classmethod
    def _extract_lines(cls, root, minimum_length=20):
        lines = []
        seen = set()
        for node in root.find_all(["h2", "h3", "p"]):
            text = cls._normalize_text(node.get_text(" ", strip=True))
            if len(text) < minimum_length:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            lines.append(text)
        return lines

    @staticmethod
    def _split_sections(lines):
        if not lines:
            return {"intro": "", "body": "", "conclusion": ""}
        if len(lines) == 1:
            return {"intro": lines[0], "body": "", "conclusion": ""}
        if len(lines) == 2:
            return {"intro": lines[0], "body": lines[1], "conclusion": ""}
        return {
            "intro": lines[0],
            "body": "\n".join(lines[1:-1]),
            "conclusion": lines[-1],
        }

    @staticmethod
    def _truncate_content(value, maximum):
        value = str(value or "")
        if len(value) <= maximum:
            return value
        # Giữ cả phần mở đầu và kết luận; chỉ lấy đầu bài sẽ dễ mất payoff.
        head_size = int(maximum * 0.72)
        tail_size = maximum - head_size
        return (
            value[:head_size]
            + "\n\n[...NỘI DUNG GIỮA ĐÃ ĐƯỢC RÚT GỌN...]\n\n"
            + value[-tail_size:]
        )

    @classmethod
    def _clean_article_lines(cls, container):
        # Làm sạch trên bản sao để không ảnh hưởng tới việc lấy ảnh/video bên dưới.
        cloned = BeautifulSoup(str(container), "html.parser")
        for tag in cloned.find_all(["script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "button", "iframe"]):
            tag.decompose()
        for element in list(cloned.find_all(True)):
            if element.parent and cls._is_noise_element(element):
                element.decompose()
        return cls._extract_lines(cloned)

    def crawl(self, url, save_dir):
        print(f"🕷️ Đang cào bài báo từ: {url}")
        try:
            res = requests.get(url, headers=self.headers, timeout=15)
            res.raise_for_status()
            html_text = res.text
            soup = BeautifulSoup(html_text, "html.parser")

            # Một số trang (vd: dantri.com.vn) render nội dung bài bằng JS, nên
            # HTML tĩnh chỉ là khung rỗng. Thử render bằng trình duyệt thật khi
            # nội dung tĩnh quá mỏng, trước khi trích xuất tiêu đề/nội dung/ảnh.
            probe_text = " ".join(self._extract_lines(soup, minimum_length=20))
            if len(probe_text) < 200:
                print("   ℹ️ Nội dung tĩnh quá mỏng, thử render bằng trình duyệt (trang có thể dùng JavaScript)...")
                rendered_html = self._fetch_rendered_html(url)
                if rendered_html:
                    rendered_soup = BeautifulSoup(rendered_html, "html.parser")
                    rendered_text = " ".join(self._extract_lines(rendered_soup, minimum_length=20))
                    if len(rendered_text) > len(probe_text):
                        html_text = rendered_html
                        soup = rendered_soup
                        print(f"   ✅ Render bằng trình duyệt lấy được nội dung ({len(rendered_text)} ký tự thô).")

            # Giữ lại metadata nguồn để bước viết kịch bản dùng đúng bài đã crawl,
            # thay vì yêu cầu AI tự mở lại URL và có nguy cơ đọc nhầm phiên bản.
            canonical_url = url
            canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
            if canonical_tag and canonical_tag.get("href"):
                canonical_url = urljoin(url, canonical_tag["href"].strip())

            def _meta_content(*names):
                for name in names:
                    tag = soup.find("meta", attrs={"property": name}) or soup.find(
                        "meta", attrs={"name": name}
                    )
                    if tag and tag.get("content"):
                        return tag["content"].strip()
                return ""

            source_name = _meta_content("og:site_name", "application-name")
            author = _meta_content("author", "article:author", "byl")
            category = _meta_content("article:section", "section", "category")
            description = _meta_content("description", "og:description")
            published_at = _meta_content(
                "article:published_time",
                "datePublished",
                "publishdate",
                "pubdate",
            )
            
            # 1. Trích xuất Tiêu đề
            title = _meta_content("og:title")
            if not title and soup.h1:
                title = soup.h1.get_text(" ", strip=True)
            elif not title and soup.title:
                title = soup.title.get_text(" ", strip=True)
                
            # 2. Trích xuất Text Content (bỏ qua các đoạn quá ngắn)
            raw_lines = self._extract_lines(soup, minimum_length=20)
            raw_content = "\n".join(raw_lines)
            article_container = self._article_container(soup)
            clean_lines = self._clean_article_lines(article_container)
            if len(" ".join(clean_lines)) < 200 and raw_lines:
                clean_lines = raw_lines
            clean_full_content = "\n".join(clean_lines)
            sections = self._split_sections(clean_lines)
            
            # 3. Trích xuất Hình ảnh
            img_urls = []
            
            # Xử lý đặc thù cho Báo Mới (baomoi.com) vì họ giấu ảnh trong script __NEXT_DATA__
            next_data = soup.find('script', id='__NEXT_DATA__')
            if next_data:
                try:
                    import json
                    data = json.loads(next_data.text)
                    images = data.get('props', {}).get('pageProps', {}).get('resp', {}).get('data', {}).get('content', {}).get('images', [])
                    for img_url in images:
                        if img_url and img_url.startswith("http"):
                            img_urls.append(img_url)
                except Exception as e:
                    print(f"   ⚠️ Lỗi phân tích JSON của Báo Mới: {e}")
            
            # Nếu chưa có ảnh (không phải Báo Mới), thì bắt thẻ <img> thường
            if not img_urls:
                # Tìm khu vực chứa nội dung chính của bài viết để tránh lấy nhầm ảnh sidebar, quảng cáo
                article_container = self._article_container(soup)
                                    
                # Bắt cả src, data-src và data-original (vì nhiều trang báo dùng lazy load, đặc biệt 24h dùng data-original)
                for img in article_container.find_all("img"):
                    src = img.get("data-original") or img.get("data-src") or img.get("src")
                    if src and src.startswith("http"):
                        # Loại bỏ các ảnh logo, icon, avatar (dựa vào từ khóa thường thấy)
                        if any(x in src.lower() for x in ['logo', 'icon', 'avatar', '/thumb/']):
                            continue
                        img_urls.append(src)
            
            # Xóa trùng lặp và chỉ lấy tối đa 5-7 ảnh đầu tiên của bài báo
            img_urls = list(dict.fromkeys(img_urls))[:7]
            
            # --- EXTRACT VIDEOS ---
            video_urls = []
            for v in soup.find_all("video"):
                # Lấy src trực tiếp từ thẻ <video>
                src = v.get("src") or v.get("data-src")
                if src and src.startswith("http"):
                    video_urls.append(src)
                # Lấy từ các thẻ <source> con bên trong
                for s in v.find_all("source"):
                    src = s.get("src") or s.get("data-src")
                    if src and src.startswith("http"):
                        video_urls.append(src)
                        
            # Tìm thêm trong regex (phòng trường hợp video nằm trong script JS)
            import re
            m3u8_matches = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html_text)
            mp4_matches = re.findall(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', html_text)
            for m in m3u8_matches + mp4_matches:
                if m not in video_urls:
                    video_urls.append(m)
                             
            video_urls = list(dict.fromkeys(video_urls))[:1] # Lấy tối đa 1 video thôi
            
            # 4. Tải ảnh và video về thư mục
            downloaded_images = []
            image_assets = []
            downloaded_videos = []
            os.makedirs(save_dir, exist_ok=True)
            
            for idx, img_url in enumerate(img_urls):
                try:
                    img_res = requests.get(img_url, headers=self.headers, timeout=10)
                    if img_res.status_code == 200:
                        img_path = os.path.join(save_dir, f"img_{idx + 1}.jpg")
                        with open(img_path, "wb") as f:
                            f.write(img_res.content)
                        downloaded_images.append(img_path)
                        image_assets.append({
                            "path": img_path,
                            "asset_url": img_url,
                            "source_url": canonical_url,
                            "source_name": source_name,
                            "alt": "",
                            "grounding_text": "",
                            "rights_status": "unknown",
                        })
                except Exception as e:
                    print(f"   ⚠️ Lỗi tải ảnh {idx}: {e}")
                    
            if video_urls:
                import subprocess
                from urllib.parse import urlparse
                ffmpeg_binary = _resolve_ffmpeg_binary()
                if ffmpeg_binary != "ffmpeg":
                    print(f"   ℹ️ Sử dụng FFmpeg: {ffmpeg_binary}")
                for idx, v_url in enumerate(video_urls):
                    v_path = os.path.join(save_dir, f"video_{idx + 1}.mp4")
                    print(f"   🎥 Phát hiện video trong bài báo, đang tải: {v_url[:80]}...")
                    downloaded = False
                    
                    # Lấy domain gốc để làm referer
                    parsed = urlparse(url)
                    referer = f"{parsed.scheme}://{parsed.netloc}/"
                    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    
                    # Ưu tiên 1: Dùng ffmpeg với user-agent + referer (xử lý HLS/m3u8 của báo VN rất tốt)
                    try:
                        cmd = [ffmpeg_binary, "-y", "-user_agent", ua, "-referer", referer, "-i", v_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", v_path]
                        res_ff = subprocess.run(cmd, capture_output=True, timeout=120)
                        if res_ff.returncode == 0 and os.path.exists(v_path) and os.path.getsize(v_path) > 10000:
                            downloaded_videos.append(v_path)
                            print("   ✅ Tải video bài báo thành công!")
                            downloaded = True
                    except Exception as e:
                        print(f"   ⚠️ ffmpeg copy thất bại: {e}")
                    
                    # Fallback 2: Dùng yt-dlp
                    if not downloaded:
                        try:
                            cmd_yt = ["yt-dlp", "-f", "best[height<=720]", "--no-warnings", "-o", v_path, v_url]
                            res_yt = subprocess.run(cmd_yt, capture_output=True, text=True, timeout=120)
                            if res_yt.returncode == 0 and os.path.exists(v_path) and os.path.getsize(v_path) > 10000:
                                downloaded_videos.append(v_path)
                                print("   ✅ Tải video bài báo thành công (yt-dlp)!")
                                downloaded = True
                        except Exception as e:
                            print(f"   ⚠️ yt-dlp thất bại: {e}")
                    
                    # Fallback 3: Re-encode
                    if not downloaded:
                        try:
                            cmd2 = [ffmpeg_binary, "-y", "-user_agent", ua, "-referer", referer, "-i", v_url, "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", v_path]
                            res_ff2 = subprocess.run(cmd2, capture_output=True, timeout=180)
                            if res_ff2.returncode == 0 and os.path.exists(v_path) and os.path.getsize(v_path) > 10000:
                                downloaded_videos.append(v_path)
                                print("   ✅ Tải video bài báo thành công (re-encode)!")
                        except Exception as e:
                            print(f"   ⚠️ ffmpeg re-encode thất bại: {e}")
                    
            # Nội dung này được truyền trực tiếp cho AI. Giới hạn để prompt ổn định,
            # đồng thời giữ cả phần mở đầu và kết luận/payoff của bài.
            source_content = self._truncate_content(
                clean_full_content,
                self.MAX_CLEAN_CONTENT_CHARS,
            )
            content_hash = hashlib.sha256(
                clean_full_content.encode("utf-8")
            ).hexdigest() if clean_full_content else ""
            print(f"✅ Đã cào xong: Tiêu đề + {len(source_content)} ký tự sạch / {len(raw_content)} ký tự thô + {len(downloaded_images)} ảnh + {len(downloaded_videos)} video.")
            return {
                "title": title,
                "description": description,
                "author": author,
                "category": category,
                "content": source_content,
                "raw_content": raw_content,
                "clean_content": source_content,
                "clean_content_full": clean_full_content,
                "content_sections": sections,
                "content_hash": content_hash,
                "content_truncated": len(clean_full_content) > len(source_content),
                "source_url": canonical_url,
                "source_name": source_name,
                "published_at": published_at,
                "images": downloaded_images,
                "image_assets": image_assets,
                "videos": downloaded_videos
            }
            
        except Exception as e:
            print(f"❌ Lỗi khi cào bài báo: {e}")
            return None

# Test thử nếu chạy file này trực tiếp
if __name__ == "__main__":
    crawler = ArticleCrawler()
    test_dir = os.path.join(os.path.dirname(__file__), "test_article_images")
    res = crawler.crawl("https://kenh14.vn/can-canh-hien-truong-vu-chay-lon-tai-xuong-go-o-ha-noi-cot-khoi-den-boc-cao-hang-chuc-met-20240312080512345.chn", test_dir)
    if res:
        print("Tiêu đề:", res["title"])
        print("Số lượng ảnh:", len(res["images"]))
