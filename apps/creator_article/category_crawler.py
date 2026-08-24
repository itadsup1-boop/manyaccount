import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

class CategoryCrawler:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_latest_article_candidates(self, category_url: str, max_links=5) -> list:
        """Return article URLs with free listing metadata for pre-AI ranking."""
        print(f"📡 Đang quét danh mục: {category_url}")
        try:
            res = requests.get(category_url, headers=self.headers, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            
            candidates_by_url = {}
            
            # Ưu tiên tìm trong thẻ <article> (chuẩn báo chí)
            containers = soup.find_all("article")
            if not containers:
                # Fallback: tìm các <div> có class phổ biến chứa tin tức
                containers = soup.find_all("div", class_=re.compile(r"article|story|item-news|post|news-item", re.I))
            
            # Nếu vẫn không có, quét toàn trang
            elements_to_scan = containers if containers else [soup]
            
            # Quét tất cả thẻ <a> trong các vùng nội dung đã lọc
            for element in elements_to_scan:
                for a_tag in element.find_all("a", href=True):
                    href = a_tag["href"]
                    # Chuẩn hóa link tương đối thành tuyệt đối
                    full_url = urljoin(category_url, href)
                    
                    # Cắt bỏ các đoạn đuôi #box_comment hoặc ?tracking
                    if "#" in full_url:
                        full_url = full_url.split("#")[0]
                    if "?" in full_url:
                        full_url = full_url.split("?")[0]
                    
                    # Loại bỏ link không hợp lệ hoặc link ảnh
                    if full_url.endswith((".jpg", ".png", ".webp", ".gif")):
                        continue
                        
                    is_article = False
                    filename = full_url.split("/")[-1]
                    
                    if (".html" in full_url or ".chn" in full_url or ".htm" in full_url) and len(filename) > 15:
                        is_article = True
                        # Loại trừ các link danh mục của 24h, hoặc event/video của Dân trí
                        if re.search(r'-c\d+\.html?$', filename):
                            is_article = False
                        if "/event/" in full_url or "/video/" in full_url or "/tac-gia/" in full_url:
                            is_article = False
                    
                    # BaoMoi format: bài báo kết thúc bằng -c + số + .epi
                    if ".epi" in full_url and re.search(r'-c\d+\.epi$', full_url):
                        is_article = True
                        
                    if is_article:
                        title = " ".join(a_tag.get_text(" ", strip=True).split())
                        if not title:
                            title = str(a_tag.get("title") or "").strip()
                        if not title and a_tag.find("img"):
                            title = str(a_tag.find("img").get("alt") or "").strip()
                        context_node = a_tag.find_parent(["article", "li", "div"])
                        context_node = context_node or element
                        container_text = " ".join(
                            context_node.get_text(" ", strip=True).split()
                        )
                        description = container_text[:500] if container_text != title else ""
                        has_image = bool(a_tag.find("img") or element.find("img"))
                        existing = candidates_by_url.get(full_url)
                        if existing:
                            if len(title) > len(existing.get("title", "")):
                                existing["title"] = title
                            if len(description) > len(existing.get("description", "")):
                                existing["description"] = description
                            existing["has_image"] = existing.get("has_image") or has_image
                            continue
                        candidates_by_url[full_url] = {
                            "url": full_url,
                            "title": title,
                            "description": description,
                            "has_image": has_image,
                            "position": len(candidates_by_url),
                        }
                        
            # Lấy số bài báo mới nhất theo yêu cầu
            return list(candidates_by_url.values())[:max_links]
            
        except Exception as e:
            print(f"❌ Lỗi quét danh mục {category_url}: {e}")
            return []

    def get_latest_articles(self, category_url: str, max_links=5) -> list:
        """Backward-compatible URL-only API."""
        return [
            item["url"]
            for item in self.get_latest_article_candidates(category_url, max_links)
        ]

if __name__ == "__main__":
    crawler = CategoryCrawler()
    links = crawler.get_latest_articles("https://vnexpress.net/giai-tri")
    for link in links:
        print("Bắt được link:", link)
