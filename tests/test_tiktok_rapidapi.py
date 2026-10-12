from __future__ import annotations

import unittest

from shared.services import tiktok_rapidapi
from shared.services.tiktok_rapidapi import (
    channel_username,
    extract_user_id,
    parse_user_posts,
)


class TikTokRapidApiTests(unittest.TestCase):
    def test_extracts_username_and_public_user_id(self):
        self.assertEqual(
            channel_username("https://www.tiktok.com/@theanh28entertainment?lang=vi"),
            "theanh28entertainment",
        )
        self.assertEqual(
            extract_user_id('<img src="/api/img/?userId=6713788996806706178&location=2">'),
            "6713788996806706178",
        )

    def test_parses_documented_user_posts_response(self):
        payload = {
            "code": 0,
            "msg": "success",
            "data": {
                "videos": [
                    {
                        "video_id": "7680996287877008670",
                        "title": "Bản tin mới",
                        "duration": 59,
                        "play_count": 37922,
                        "digg_count": 1698,
                        "comment_count": 294,
                        "create_time": 1788371338,
                        "play": "https://cdn.example/video.mp4",
                        "author": {"id": "107955", "unique_id": "tiktok"},
                    }
                ]
            },
        }
        rows = parse_user_posts(payload, username="fallback", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["video_id"], "7680996287877008670")
        self.assertEqual(
            rows[0]["url"],
            "https://www.tiktok.com/@tiktok/video/7680996287877008670",
        )
        self.assertEqual(rows[0]["view_count"], 37922)

    def test_reuses_play_url_from_channel_scan(self):
        tiktok_rapidapi._DOWNLOAD_URL_CACHE.clear()
        tiktok_rapidapi._remember_download_urls(
            [
                {
                    "video_id": "7680996287877008670",
                    "rapid_play_url": "https://cdn.example/video.mp4",
                }
            ]
        )

        result = tiktok_rapidapi.get_video_info(
            "https://www.tiktok.com/@tiktok/video/7680996287877008670"
        )

        self.assertTrue(
            tiktok_rapidapi.has_cached_download_url(
                "https://www.tiktok.com/@tiktok/video/7680996287877008670"
            )
        )
        self.assertEqual(result["play"], "https://cdn.example/video.mp4")
        self.assertEqual(result["source"], "user_posts_cache")


if __name__ == "__main__":
    unittest.main()
