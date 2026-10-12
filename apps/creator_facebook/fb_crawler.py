#!/usr/bin/env python3
"""CLI/lớp tương thích cho Facebook crawler.

Phần triển khai được chia nhỏ trong ``facebook_pipeline`` để file entry point
không tiếp tục phình to.
"""

from __future__ import annotations

from facebook_pipeline.auth import login_facebook_interactive
from facebook_pipeline.crawler import crawl_facebook_videos
from facebook_pipeline.source_config import build_crawl_url, extract_video_id


def _build_page_url(source_url: str) -> str:
    """Giữ API helper cũ cho các script bên ngoài."""

    return build_crawl_url(source_url)


def _extract_video_id(url: str) -> str | None:
    """Giữ API helper cũ cho các test/script bên ngoài."""

    return extract_video_id(url) or None


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "login":
        print(json.dumps(login_facebook_interactive(), ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1:
        results = crawl_facebook_videos(sys.argv[1])
        print(f"\n📊 Tổng: {len(results)} video")
    else:
        print("Dùng: python3 fb_crawler.py login | <URL Facebook>")
