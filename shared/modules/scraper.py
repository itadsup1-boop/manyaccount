import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

SCRAPER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def scrape_article_content(url):
    try:
        res = requests.get(url, headers=SCRAPER_HEADERS, timeout=15)
        if res.status_code != 200: return None, None, [], f"HTTP {res.status_code}"

        soup = BeautifulSoup(res.text, "html.parser")
        article = soup.find("article") or soup.find("div", class_="content") or soup.find("body")
        if not article: return None, None, [], "Không tìm thấy nội dung"

        title_node = soup.find("h1")
        title = title_node.get_text(strip=True) if title_node else "No Title"

        lines = [title] if title else []
        for p in article.find_all(["p", "h2", "h3"]):
            txt = p.get_text(strip=True)
            if txt: lines.append(txt)
        full_text = "\n\n".join(lines)

        img_urls = []
        for img in article.find_all("img"):
            raw = img.get("data-src") or img.get("src")
            if raw and len(raw) > 5:
                abs_url = urljoin(url, raw)
                bad = ["icon", ".svg", "avatar", "logo"]
                if not any(b in abs_url.lower() for b in bad):
                    img_urls.append(abs_url)

        seen = set()
        ordered = []
        for u in img_urls:
            if u not in seen:
                ordered.append(u)
                seen.add(u)

        final_urls = ordered[1:31]
        return title, full_text, final_urls, "Thành công"
    except Exception as e: return None, None, [], str(e)