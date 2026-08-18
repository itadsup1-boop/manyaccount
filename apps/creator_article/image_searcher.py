import os
import requests
import time
import random
from duckduckgo_search import DDGS

class ImageSearcher:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
    def download_missing_images(self, prompts: list, save_dir: str) -> list:
        """
        Duyệt qua mảng mô tả ảnh (của ChatGPT), lên DuckDuckGo tìm và tải về ảnh đầu tiên tải được.
        """
        if not prompts:
            return []
            
        print(f"🛠️ Tool săn ảnh kích hoạt: Cần tìm {len(prompts)} ảnh còn thiếu...")
        os.makedirs(save_dir, exist_ok=True)
        downloaded_paths = []
        ddgs = DDGS()
        
        for idx, prompt in enumerate(prompts):
            print(f"   🔎 Đang search: '{prompt}'...")
            
            # Thử tối đa 3 lần cho mỗi ảnh nếu bị lỗi Ratelimit
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
                        max_results=5 # Thử tối đa 5 link để tránh link chết
                    ))
                    
                    for res in results:
                        img_url = res.get("image")
                        if img_url:
                            try:
                                # Tải thử ảnh
                                r = requests.get(img_url, headers=self.headers, timeout=10)
                                if r.status_code == 200:
                                    ext = img_url.split(".")[-1][:4]
                                    if ext.lower() not in ["jpg", "jpeg", "png", "webp"]:
                                        ext = "jpg"
                                    file_path = os.path.join(save_dir, f"search_img_{idx + 1}.{ext}")
                                    with open(file_path, "wb") as f:
                                        f.write(r.content)
                                    downloaded_paths.append(file_path)
                                    print(f"     ✅ Bắt được 1 ảnh nét căng!")
                                    success = True
                                    break # Bắt được ảnh rồi thì thoát vòng lặp, sang câu prompt khác
                            except Exception as e:
                                continue # Nếu link này lỗi (403, timeout) thì thử link ảnh kế tiếp
                                
                    if not success:
                        print(f"     ❌ Thất bại: Đã thử 5 link nhưng đều chết.")
                    
                    break # Nếu đã thành công HOẶC không có exception thì thoát vòng lặp retry
                        
                except Exception as e:
                    print(f"   ⚠️ Lần thử {attempt + 1}: DuckDuckGo lỗi ({e}). Đang đợi vài giây để thử lại...")
                    time.sleep(5) # Đợi 5 giây rồi thử lại nếu bị Ratelimit
                    
            if not success:
                print(f"   ❌ Đã từ bỏ ảnh '{prompt}' sau 3 lần thử thất bại.")
                
        return downloaded_paths

# Test thử nếu chạy trực tiếp
if __name__ == "__main__":
    searcher = ImageSearcher()
    test_prompts = ["xe cứu hỏa đang phun nước dập lửa", "cảnh sát giao thông phân luồng"]
    test_dir = os.path.join(os.path.dirname(__file__), "test_search_images")
    res = searcher.download_missing_images(test_prompts, test_dir)
    print("Các ảnh tải về:", res)
