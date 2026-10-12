import os
import tempfile
import unittest
from unittest.mock import patch

from shared.modules import video_handler
from shared.services.tiktok_clipssaver import (
    build_candidate,
    channel_username,
    normalize_title,
    profile_url,
    title_dedupe_key,
)


class ClipSaverMetadataTests(unittest.TestCase):
    def test_profile_url_uses_source_username_without_at(self):
        source = "https://www.tiktok.com/@kienthuckinhte28?lang=vi"
        self.assertEqual(channel_username(source), "kienthuckinhte28")
        self.assertEqual(
            profile_url(source),
            "https://clipssaver.com/tiktok-profile-downloader/kienthuckinhte28",
        )

    def test_title_key_is_normalized_and_scoped_to_channel(self):
        first = title_dedupe_key(
            "https://www.tiktok.com/@kenh_a",
            "  Giá VÀNG   tăng\u200b mạnh  ",
        )
        same = title_dedupe_key(
            "@kenh_a",
            "giá vàng tăng mạnh",
        )
        other_channel = title_dedupe_key(
            "@kenh_b",
            "giá vàng tăng mạnh",
        )
        self.assertEqual(first, same)
        self.assertNotEqual(first, other_channel)

    def test_candidate_keeps_full_title_for_caption_and_dedupe(self):
        candidate = build_candidate(
            "https://www.tiktok.com/@kenh_nguon",
            "Tiêu đề đầy đủ #tintuc",
            position=0,
        )
        self.assertEqual(candidate["provider"], "clipssaver")
        self.assertEqual(candidate["title"], "Tiêu đề đầy đủ #tintuc")
        self.assertEqual(candidate["caption"], candidate["title"])
        self.assertEqual(
            candidate["title_key"],
            "kenh_nguon:" + normalize_title(candidate["title"]),
        )


class ClipSaverVideoHandlerTests(unittest.TestCase):
    @patch("shared.modules.video_handler.get_clipssaver_candidates")
    def test_scanner_caps_every_channel_at_three(self, get_candidates):
        get_candidates.return_value = [{"url": "one"}]
        result = video_handler.get_channel_video_candidates("@kenh_nguon", limit=15)
        self.assertEqual(result, [{"url": "one"}])
        get_candidates.assert_called_once_with("@kenh_nguon", 3)

    @patch("shared.modules.video_handler.compress_video_if_needed")
    @patch("shared.modules.video_handler.download_clipssaver_candidate")
    def test_downloader_uses_clipssaver_candidate_only(self, download, compress):
        download.return_value = "/tmp/source.mp4"
        compress.return_value = "/tmp/source_small.mp4"
        candidate = {"provider": "clipssaver", "title": "Tin mới"}
        result = video_handler.download_tiktok_video(
            "https://www.tiktok.com/@kenh#clipssaver-id",
            "/tmp",
            candidate=candidate,
        )
        self.assertEqual(result["original"], "/tmp/source.mp4")
        self.assertEqual(result["ai_studio"], "/tmp/source_small.mp4")
        download.assert_called_once_with(candidate, "/tmp")

    @patch("shared.modules.video_handler._download_tiktok_video_legacy")
    def test_legacy_downloader_is_disabled_by_default(self, legacy_download):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TIKTOK_LEGACY_SOURCE_ENABLED", None)
            result = video_handler.download_tiktok_video(
                "https://www.tiktok.com/@kenh/video/123",
                tempfile.gettempdir(),
            )
        self.assertIsNone(result)
        legacy_download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
