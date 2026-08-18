import os
import requests
from bs4 import BeautifulSoup

class ArticleCrawler:
    def __init__(self):
        # Tránh bị web báo chặn chặn Bot
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def crawl(self, url, save_dir):
        print(f"🕷️ Đang cào bài báo từ: {url}")
        try:
            res = requests.get(url, headers=self.headers, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 1. Trích xuất Tiêu đề
            title = ""
            if soup.h1:
                title = soup.h1.get_text(strip=True)
            elif soup.title:
                title = soup.title.get_text(strip=True)
                
            # 2. Trích xuất Text Content (bỏ qua các đoạn quá ngắn)
            paragraphs = soup.find_all("p")
            text_lines = []
            for p in paragraphs:
                txt = p.get_text(strip=True)
                if len(txt) > 40: # Lọc bỏ các text rác, caption ngắn
                    text_lines.append(txt)
            
            full_text = "\n".join(text_lines)
            
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
                article_container = soup.find(id="article_body") or \
                                    soup.find(class_="singular-content") or \
                                    soup.find("article") or \
                                    soup.find(class_="detail-content") or \
                                    soup.find(class_="article-body") or \
                                    soup.find(class_="content") or \
                                    soup # Fallback: tìm toàn trang
                                    
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
            m3u8_matches = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', res.text)
            mp4_matches = re.findall(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', res.text)
            for m in m3u8_matches + mp4_matches:
                if m not in video_urls:
                    video_urls.append(m)
                             
            video_urls = list(dict.fromkeys(video_urls))[:1] # Lấy tối đa 1 video thôi
            
            # 4. Tải ảnh và video về thư mục
            downloaded_images = []
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
                except Exception as e:
                    print(f"   ⚠️ Lỗi tải ảnh {idx}: {e}")
                    
            if video_urls:
                import subprocess
                from urllib.parse import urlparse
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
                        cmd = ["ffmpeg", "-y", "-user_agent", ua, "-referer", referer, "-i", v_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", v_path]
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
                            cmd2 = ["ffmpeg", "-y", "-user_agent", ua, "-referer", referer, "-i", v_url, "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", v_path]
                            res_ff2 = subprocess.run(cmd2, capture_output=True, timeout=180)
                            if res_ff2.returncode == 0 and os.path.exists(v_path) and os.path.getsize(v_path) > 10000:
                                downloaded_videos.append(v_path)
                                print("   ✅ Tải video bài báo thành công (re-encode)!")
                        except Exception as e:
                            print(f"   ⚠️ ffmpeg re-encode thất bại: {e}")
                    
            print(f"✅ Đã cào xong: Tiêu đề + {len(full_text)} ký tự + {len(downloaded_images)} ảnh + {len(downloaded_videos)} video.")
            return {
                "title": title,
                "content": full_text[:4000],
                "images": downloaded_images,
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
