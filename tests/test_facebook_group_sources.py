from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from apps.creator_facebook.facebook_pipeline.group_crawler import (
    GROUP_POST_EXTRACTOR_JS,
    build_group_video_items,
)
from apps.creator_facebook.facebook_pipeline.auth import chromium_launch_options
from apps.creator_facebook.facebook_pipeline.dash_download import (
    normalize_dash_url,
    select_dash_tracks,
)
from apps.creator_facebook.facebook_pipeline.hook_mode import prepare_hook_content
from apps.creator_facebook.facebook_pipeline.source_config import (
    EDIT_MODE_FULL_AI,
    EDIT_MODE_HOOK_THEN_ORIGINAL,
    build_crawl_url,
    normalize_source_record,
    parse_group_post_url,
    sanitize_group_source_payload,
    sanitize_page_source_payload,
    sanitize_source_payload,
)
from apps.creator_facebook.facebook_pipeline.source_repository import (
    GROUP_SOURCES_TABLE,
    PAGE_SOURCES_TABLE,
    load_active_sources,
)


class FacebookSourceConfigTests(unittest.TestCase):
    def test_page_payload_keeps_legacy_schema(self):
        payload = sanitize_page_source_payload(
            {
                "source_name": "Page cũ",
                "source_url": "https://facebook.com/vtv24",
                "source_type": "group",
                "edit_mode": EDIT_MODE_HOOK_THEN_ORIGINAL,
                "max_videos_per_scan": 3,
            }
        )
        self.assertNotIn("source_type", payload)
        self.assertNotIn("edit_mode", payload)
        self.assertNotIn("max_videos_per_scan", payload)

    def test_group_payload_is_group_only(self):
        payload = sanitize_group_source_payload(
            {
                "source_name": "Nhóm xe",
                "source_url": "https://facebook.com/groups/123/videos",
                "max_videos_per_scan": 3,
            }
        )
        self.assertEqual(
            payload["source_url"], "https://www.facebook.com/groups/123"
        )
        self.assertEqual(payload["edit_mode"], EDIT_MODE_HOOK_THEN_ORIGINAL)
        self.assertEqual(payload["max_videos_per_scan"], 3)

    def test_group_defaults_to_feed_and_hook_mode(self):
        source = normalize_source_record(
            {
                "source_url": "https://facebook.com/groups/123456789/videos/",
                "source_type": "group",
            }
        )
        self.assertEqual(source["edit_mode"], EDIT_MODE_HOOK_THEN_ORIGINAL)
        self.assertEqual(
            build_crawl_url(source["source_url"], source["source_type"]),
            "https://www.facebook.com/groups/123456789",
        )

    def test_page_keeps_legacy_full_ai_default(self):
        source = normalize_source_record(
            {"source_url": "https://facebook.com/vtv24"}
        )
        self.assertEqual(source["source_type"], "page")
        self.assertEqual(source["edit_mode"], EDIT_MODE_FULL_AI)

    def test_group_post_must_match_expected_group(self):
        self.assertIsNotNone(
            parse_group_post_url(
                "https://facebook.com/groups/123/posts/999?comment_id=1", "123"
            )
        )
        self.assertIsNone(
            parse_group_post_url(
                "https://facebook.com/groups/456/posts/999", "123"
            )
        )

    def test_group_url_rejected_when_page_type_selected(self):
        with self.assertRaises(ValueError):
            sanitize_source_payload(
                {
                    "source_name": "Sai loại",
                    "source_url": "https://facebook.com/groups/123",
                    "source_type": "page",
                }
            )


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def order(self, *_args):
        return self

    def execute(self):
        return type("Response", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.tables = []

    def table(self, name):
        self.tables.append(name)
        return _FakeQuery(self.rows_by_table.get(name, []))


class FacebookSourceRepositoryTests(unittest.TestCase):
    def test_page_and_group_are_loaded_from_separate_tables(self):
        client = _FakeClient(
            {
                PAGE_SOURCES_TABLE: [
                    {
                        "id": 1,
                        "source_name": "Page cũ",
                        "source_url": "https://facebook.com/vtv24",
                    }
                ],
                GROUP_SOURCES_TABLE: [
                    {
                        "id": 2,
                        "source_name": "Group mới",
                        "source_url": "https://facebook.com/groups/123",
                    }
                ],
            }
        )
        pages = load_active_sources(client, "page")
        self.assertEqual(client.tables, [PAGE_SOURCES_TABLE])
        self.assertEqual(pages[0]["source_type"], "page")

        client.tables.clear()
        groups = load_active_sources(client, "group")
        self.assertEqual(client.tables, [GROUP_SOURCES_TABLE])
        self.assertEqual(groups[0]["source_type"], "group")


class FacebookGroupCrawlerFilterTests(unittest.TestCase):
    def test_dom_extractor_uses_top_level_feed_posts_not_comment_articles(self):
        from playwright.sync_api import sync_playwright

        html = """
        <div role="feed">
          <div aria-posinset="1">
            <a href="https://facebook.com/groups/123/posts/2001">2 phút</a>
            <div data-ad-preview="message">Video nằm trong bài chính</div>
            <video data-video-id="8001"></video>
            <div role="article">
              <a href="https://facebook.com/groups/123/posts/2001?comment_id=9">
                Bình luận
              </a>
            </div>
          </div>
          <div aria-posinset="2">
            <a href="https://facebook.com/groups/123/posts/2002">1 phút</a>
            <div data-ad-preview="message">Bài ảnh không được lấy</div>
          </div>
        </div>
        """
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                **chromium_launch_options(headless=True)
            )
            page = browser.new_page()
            page.set_content(html)
            candidates = page.evaluate(
                GROUP_POST_EXTRACTOR_JS, {"expectedGroupKey": "123"}
            )
            browser.close()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["post_id"], "2001")
        self.assertEqual(candidates[0]["video_id"], "8001")

    def test_dom_extractor_requires_video_inside_same_group_article(self):
        from playwright.sync_api import sync_playwright

        html = """
        <article role="article">
          <a href="https://facebook.com/groups/123/posts/1001">2 giờ</a>
          <div data-ad-preview="message">Bài hợp lệ có video</div>
          <video data-video-id="7001"></video>
        </article>
        <article role="article">
          <a href="https://facebook.com/groups/123/posts/1002">1 giờ</a>
          <div data-ad-preview="message">Bài chỉ có ảnh</div>
        </article>
        <article role="article">
          <a href="https://facebook.com/groups/999/posts/1003">30 phút</a>
          <video data-video-id="7003"></video>
        </article>
        <aside><video data-video-id="9999"></video></aside>
        """
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                **chromium_launch_options(headless=True)
            )
            page = browser.new_page()
            page.set_content(html)
            candidates = page.evaluate(
                GROUP_POST_EXTRACTOR_JS, {"expectedGroupKey": "123"}
            )
            browser.close()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["post_id"], "1001")
        self.assertEqual(candidates[0]["video_id"], "7001")

    def test_only_same_group_posts_with_native_video_are_kept(self):
        candidates = [
            {
                "post_url": "https://facebook.com/groups/123/posts/1001",
                "post_id": "1001",
                "video_id": "7001",
                "caption": "Video hợp lệ trong nhóm",
                "published_at": "2026-08-31T01:00:00+00:00",
                "has_native_video": True,
            },
            {
                "post_url": "https://facebook.com/groups/123/posts/1002",
                "post_id": "1002",
                "caption": "Bài chỉ có ảnh",
                "has_native_video": False,
            },
            {
                "post_url": "https://facebook.com/groups/999/posts/1003",
                "post_id": "1003",
                "video_id": "7003",
                "caption": "Video thuộc nhóm khác",
                "has_native_video": True,
            },
            {
                "post_url": "https://facebook.com/groups/123/posts/1004",
                "post_id": "1004",
                "video_id": "7004",
                "caption": "Video quá cũ",
                "published_at": "2026-08-20T01:00:00+00:00",
                "has_native_video": True,
            },
        ]
        items = build_group_video_items(
            candidates,
            source_url="https://facebook.com/groups/123",
            max_videos=5,
            max_age_hours=48,
            now=datetime(2026, 8, 31, 2, 0, tzinfo=timezone.utc),
        )
        self.assertEqual([item["post_id"] for item in items], ["1001"])
        self.assertEqual(items[0]["url"], "https://www.facebook.com/groups/123/posts/1001")

    def test_post_id_is_stable_fallback_when_video_id_is_hidden(self):
        items = build_group_video_items(
            [
                {
                    "post_url": "https://facebook.com/groups/mygroup/posts/5555",
                    "caption": "Facebook không lộ video id trong DOM",
                    "has_native_video": True,
                }
            ],
            source_url="https://facebook.com/groups/mygroup",
            max_videos=5,
        )
        self.assertEqual(items[0]["video_id"], "5555")


class FacebookDashDownloadTests(unittest.TestCase):
    def test_normalize_dash_url_removes_only_byte_range(self):
        normalized = normalize_dash_url(
            "https://cdn.example/video.mp4?token=abc&bytestart=946&byteend=1596565"
        )
        self.assertEqual(normalized, "https://cdn.example/video.mp4?token=abc")

    def test_selects_target_video_and_matching_audio(self):
        tracks = [
            {"path": "other.mp4", "types": {"video"}, "duration": 82.3, "width": 1280, "height": 720},
            {"path": "other.m4a", "types": {"audio"}, "duration": 82.31, "width": 0, "height": 0},
            {"path": "target.mp4", "types": {"video"}, "duration": 37.83, "width": 1080, "height": 1920},
            {"path": "target.m4a", "types": {"audio"}, "duration": 37.84, "width": 0, "height": 0},
        ]
        video, audio = select_dash_tracks(
            tracks,
            {"duration": 37.83, "width": 1080, "height": 1920},
        )
        self.assertEqual(video["path"], "target.mp4")
        self.assertEqual(audio["path"], "target.m4a")

    @patch("apps.creator_facebook.fb_downloader._download_playwright")
    @patch("apps.creator_facebook.fb_downloader._download_ytdlp")
    def test_group_bypasses_ytdlp_and_requires_exact_player(
        self, ytdlp_download, playwright_download
    ):
        from apps.creator_facebook.fb_downloader import download_video

        playwright_download.return_value = {"path": "target.mp4"}
        result = download_video(
            "https://facebook.com/groups/123/posts/456",
            "789",
            source_type="group",
        )
        self.assertEqual(result, {"path": "target.mp4"})
        ytdlp_download.assert_not_called()
        playwright_download.assert_called_once_with(
            "https://facebook.com/groups/123/posts/456",
            "789",
            require_target=True,
        )


class FacebookHookModeTests(unittest.TestCase):
    def test_hook_mode_never_keeps_full_script_or_beats(self):
        prepared = prepare_hook_content(
            {
                "hook": "Chiếc xe bất ngờ lao qua dòng nước ngay giữa khu dân cư",
                "script_voice": "Đây là phần kịch bản dài không được dùng.",
                "beats": [{"voice_over": "Không dùng"}],
                "should_make_video": True,
            },
            caption="Một chiếc xe đi qua vùng ngập nước",
            channel_id="Adsupnews",
            source_url="https://facebook.com/groups/123/posts/999",
        )
        self.assertTrue(prepared.report.passed)
        self.assertEqual(prepared.content["script_voice"], "")
        self.assertEqual(prepared.content["beats"], [])
        self.assertFalse(prepared.content["have_frame"])


if __name__ == "__main__":
    unittest.main()
