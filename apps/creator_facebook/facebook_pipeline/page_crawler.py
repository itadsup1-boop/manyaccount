"""Crawler nguồn Facebook Page/Reels cũ, tách khỏi bộ quét Group."""

from __future__ import annotations

from typing import Any

from .source_config import extract_video_id


def crawl_page_videos(page: Any, max_videos: int) -> list[dict]:
    for _ in range(4):
        page.evaluate("window.scrollBy(0, 1100)")
        page.wait_for_timeout(1400)

    raw_links = page.evaluate(
        r"""
        () => Array.from(document.querySelectorAll('a[href]'))
          .filter(a => /\/videos\/|\/watch\/\?v=|\/reel\//.test(a.href))
          .map(a => ({href: a.href, text: (a.innerText || '').trim().slice(0, 500)}))
        """
    )
    videos = []
    seen = set()
    for link in raw_links or []:
        video_id = extract_video_id(link.get("href"))
        if not video_id or video_id in seen or len(video_id) < 6:
            continue
        seen.add(video_id)
        videos.append(
            {
                "video_id": video_id,
                "url": f"https://www.facebook.com/watch/?v={video_id}",
                "caption": str(link.get("text") or ""),
                "published_at": "",
                "source_type": "page",
            }
        )
        if len(videos) >= max_videos:
            break
    return videos
