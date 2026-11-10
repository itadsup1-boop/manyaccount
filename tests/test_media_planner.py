"""Unit test media_planner + set_job_status (Giai đoạn 2).

Toàn bộ tìm kiếm/tải asset bị fake qua ``http_get``/``http_download`` nên test
không chạm network. Job store chạy trong thư mục tạm qua tham số ``jobs_dir``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adsup_central_hub.backend import production_jobs
from apps.creator_article.media_planner import (
    classify_visual_query,
    plan_media_for_job,
    score_relevance,
)
from apps.creator_article.stock_provider import (
    search_pexels,
    search_pixabay,
    search_serpapi_google_images,
    search_unsplash,
    search_wikimedia,
)


def _beat(n: int, visual_query: str, **extra: object) -> dict:
    beat = {
        "beat_number": n,
        "role": "fact",
        "duration_hint": 6.5,
        "voice_over": f"voice {n}",
        "visual_query": visual_query,
        "on_screen_text": f"Chữ {n}",
        "motion": "cut",
        "transition": "cut",
        "must_show": [],
    }
    beat.update(extra)
    return beat


def _doc() -> dict:
    return {
        "schema_version": 1,
        "hook": "Hook mở màn",
        "script_voice": "Nội dung voice chính.",
        "beats": [
            _beat(1, "DATA GRAPHIC: 2 tỷ đồng so sánh"),
            _beat(2, "people walking on street"),
            _beat(3, "unrelated quantum physics diagram"),
        ],
        "music_mood": "neutral_news",
    }


def _video_payload(asset_id: int = 77, slug: str = "people-walking-on-street") -> dict:
    return {
        "videos": [
            {
                "id": asset_id,
                "url": f"https://www.pexels.com/video/{slug}-{asset_id}/",
                "duration": 10,
                "user": {"name": "Nhung"},
                "video_files": [
                    {
                        "file_type": "video/mp4",
                        "width": 1080,
                        "height": 1920,
                        "link": f"http://cdn/{asset_id}_1080.mp4",
                        "file_size": 5,
                    }
                ],
            }
        ]
    }


def _photo_payload(asset_id: int = 55) -> dict:
    return {
        "photos": [
            {
                "id": asset_id,
                "url": f"https://www.pexels.com/photo/street-{asset_id}/",
                "width": 3000,
                "height": 4000,
                "alt": "people walking on street",
                "user": {"name": "Phuc"},
                "src": {"original": f"http://cdn/{asset_id}_orig.jpg"},
            }
        ]
    }


def _constant_get(payload: dict):
    def fake_get(url: str, headers: dict) -> dict:
        return payload

    return fake_get


def _recorded_get(payloads: list[dict]):
    """Trả payload theo thứ tự lần gọi (video trước, photo sau)."""

    def fake_get(url: str, headers: dict) -> dict:
        return payloads.pop(0) if payloads else {"videos": [], "photos": []}

    return fake_get


def _fake_download(log: list[str] | None = None):
    def fake_download(url: str, dest_path: str) -> int:
        if log is not None:
            log.append(url)
        with open(dest_path, "wb") as handle:
            handle.write(b"\x00" * 100)
        return 100

    return fake_download


def _clean_scanner(path: str, media_type: str):
    from shared.modules.logo_scanner import WatermarkScanResult

    return WatermarkScanResult(detected=False, score=0.0, region="")


class TestClassifyVisualQuery(unittest.TestCase):
    def test_data_graphic_prefix(self):
        kind, cleaned = classify_visual_query("DATA GRAPHIC: so sánh 2 tỷ đồng")
        self.assertEqual(kind, "data_graphic")
        self.assertEqual(cleaned, "so sánh 2 tỷ đồng")

    def test_map_graphic_prefix_case_insensitive(self):
        kind, cleaned = classify_visual_query("map graphic: Ha Noi map")
        self.assertEqual(kind, "map_graphic")
        self.assertEqual(cleaned, "Ha Noi map")

    def test_plain_query_is_broll(self):
        kind, cleaned = classify_visual_query("city traffic at night")
        self.assertEqual(kind, "broll")
        self.assertEqual(cleaned, "city traffic at night")

    def test_empty_query_is_broll(self):
        self.assertEqual(classify_visual_query(""), ("broll", ""))

    def test_quote_and_fact_card_prefixes(self):
        self.assertEqual(
            classify_visual_query("QUOTE CARD: Giá tăng mạnh - Bộ Công Thương"),
            ("quote_card", "Giá tăng mạnh - Bộ Công Thương"),
        )
        self.assertEqual(
            classify_visual_query("fact card: 3 mốc điều chỉnh mới"),
            ("fact_card", "3 mốc điều chỉnh mới"),
        )


class TestScoreRelevance(unittest.TestCase):
    def test_full_match_ignoring_stopword(self):
        candidate = {"description": "people walking on street", "tags": [], "author": ""}
        self.assertAlmostEqual(score_relevance("people walking street", candidate), 1.0)

    def test_zero_match(self):
        candidate = {"description": "people walking on street", "tags": [], "author": ""}
        self.assertEqual(score_relevance("mortgage document signing", candidate), 0.0)

    def test_tags_and_author_count(self):
        candidate = {"description": "", "tags": ["traffic"], "author": "Hanoi"}
        self.assertAlmostEqual(score_relevance("hanoi traffic", candidate), 1.0)

    def test_empty_query_scores_zero(self):
        self.assertEqual(score_relevance("", {"description": "anything"}), 0.0)

    def test_ignores_nonsemantic_style_words_in_query(self):
        candidate = {"description": "apartment building exterior", "tags": [], "author": ""}
        self.assertAlmostEqual(
            score_relevance(
                "modern apartment building exterior Vietnam daylight no logo", candidate
            ),
            1.0,
        )


class TestPlanMediaForJob(unittest.TestCase):
    def setUp(self):
        os.environ.pop("SERPAPI_API_KEY", None)
        os.environ.pop("PEXELS_API_KEY", None)
        os.environ.pop("UNSPLASH_ACCESS_KEY", None)
        os.environ.pop("PIXABAY_API_KEY", None)
        os.environ.pop("STOCK_PROVIDER", None)
        self.tmp = tempfile.mkdtemp(prefix="media_planner_test_")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _save_job(self, document=None, channel: str = "kenh_a") -> str:
        document = document or _doc()
        job_id, _ = production_jobs.save_job(
            document,
            channel_id=channel,
            validation={"beat_count": len(document["beats"]), "passed": True},
            storyboard={"beats": document["beats"]},
            jobs_dir=self.tmp,
        )
        return job_id

    def test_missing_job_raises_job_not_found(self):
        with self.assertRaises(ValueError) as ctx:
            plan_media_for_job("prod_000000000000", jobs_dir=self.tmp)
        self.assertEqual(str(ctx.exception), "JOB_NOT_FOUND")

    def test_job_without_storyboard_raises(self):
        job_id, _ = production_jobs.save_job(
            _doc(), channel_id="kenh_a", validation={"beat_count": 3, "passed": True},
            jobs_dir=self.tmp,
        )
        with self.assertRaises(ValueError) as ctx:
            plan_media_for_job(job_id, jobs_dir=self.tmp)
        self.assertEqual(str(ctx.exception), "STORYBOARD_MISSING")

    def test_missing_api_key_raises(self):
        job_id = self._save_job()
        with self.assertRaises(RuntimeError) as ctx:
            plan_media_for_job(job_id, jobs_dir=self.tmp)
        self.assertEqual(str(ctx.exception), "PEXELS_API_KEY_MISSING")

    def test_allow_missing_api_key_falls_back_to_graphics(self):
        job_id = self._save_job()
        result = plan_media_for_job(
            job_id, jobs_dir=self.tmp, allow_missing_api_key=True
        )
        plan = result["plan"]
        self.assertEqual(plan["status"], "graphics_only")
        self.assertEqual(
            [b["kind"] for b in plan["beats"]],
            ["data_graphic", "no_asset_found", "no_asset_found"],
        )
        self.assertEqual(plan["beats"][1]["reason"], "pexels_api_key_missing")

    def test_graphic_only_plan_needs_no_api_key(self):
        document = _doc()
        document["beats"] = [_beat(1, "MAP GRAPHIC: ha noi"), _beat(2, "DATA GRAPHIC: 3 căn")]
        job_id = self._save_job(document)
        result = plan_media_for_job(job_id, jobs_dir=self.tmp)
        plan = result["plan"]
        self.assertEqual(plan["status"], "graphics_only")
        self.assertEqual([b["kind"] for b in plan["beats"]], ["map_graphic", "data_graphic"])
        self.assertEqual(result["manifest"], [])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, job_id, "media_plan.json")))

    def test_broll_selected_downloaded_and_manifest_complete(self):
        downloads: list[str] = []
        job_id = self._save_job()
        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=_constant_get(_video_payload()),
            http_download=_fake_download(downloads),
            watermark_scanner=_clean_scanner,
        )
        plan, manifest = result["plan"], result["manifest"]
        self.assertEqual([b["kind"] for b in plan["beats"]], ["data_graphic", "broll", "no_asset_found"])
        self.assertEqual(plan["beats"][1]["selected"]["provider_asset_id"], "pexels_video_77")
        self.assertEqual(plan["beats"][1]["selected"]["relevance_score"], 1.0)
        self.assertEqual(plan["beats"][2]["reason"], "below_threshold")
        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["summary"]["assets_downloaded"], 1)
        self.assertEqual(downloads, ["http://cdn/77_1080.mp4"])

        self.assertEqual(len(manifest), 1)
        record = manifest[0]
        for field in (
            "asset_id", "beat_number", "provider", "provider_asset_id", "asset_url",
            "page_url", "local_path", "license_status", "license_source",
            "downloaded_at", "relevance_score", "logo_scan", "watermark_scan",
            "is_ai_generated", "publisher_asset",
        ):
            self.assertIn(field, record, f"manifest thiếu field {field} (BRIEF §4)")
        self.assertEqual(record["asset_id"], "stock_002")
        self.assertEqual(record["license_status"], "licensed")
        self.assertEqual(record["license_source"], "pexels_license")
        self.assertEqual(record["local_path"], "assets/stock_002.mp4")
        self.assertFalse(record["is_ai_generated"])
        self.assertFalse(record["publisher_asset"])

        # File thật trong job dir + artifacts ghi đĩa
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, job_id, record["local_path"])))
        on_disk = production_jobs.load_job_artifact(job_id, "media_plan", jobs_dir=self.tmp)
        self.assertEqual(on_disk["plan_version"], "media_plan_v1")
        manifest_on_disk = production_jobs.load_job_artifact(job_id, "assets_manifest", jobs_dir=self.tmp)
        self.assertEqual(manifest_on_disk[0]["asset_id"], "stock_002")

    def test_uses_relevant_photo_when_video_results_are_irrelevant(self):
        """Không bỏ qua ảnh chỉ vì endpoint video trả về kết quả yếu."""

        document = _doc()
        document["beats"] = [_beat(1, "people walking street")]
        job_id = self._save_job(document)
        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=_recorded_get([
                _video_payload(77, "traffic-at-night"),
                _photo_payload(55),
            ]),
            http_download=_fake_download(),
            watermark_scanner=_clean_scanner,
        )

        beat = result["plan"]["beats"][0]
        self.assertEqual(result["plan"]["status"], "ready")
        self.assertEqual(beat["kind"], "broll")
        self.assertEqual(beat["media_type"], "photo")
        self.assertEqual(beat["selected"]["provider_asset_id"], "pexels_photo_55")
        self.assertEqual(beat["candidates_evaluated"], 2)
        self.assertEqual(result["manifest"][0]["local_path"], "assets/stock_001.jpg")

    def test_tries_alternative_asset_search_queries(self):
        document = _doc()
        document["beats"] = [
            _beat(
                1,
                "apartment building exterior",
                asset_search_queries=[
                    "apartment building exterior",
                    "people walking street",
                ],
            )
        ]
        job_id = self._save_job(document)

        def query_aware_get(url: str, headers: dict) -> dict:
            if "people+walking+street" in url:
                return _video_payload() if "/videos/search" in url else {"photos": []}
            return {"videos": []} if "/videos/search" in url else {"photos": []}

        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=query_aware_get,
            http_download=_fake_download(),
            watermark_scanner=_clean_scanner,
        )
        beat = result["plan"]["beats"][0]
        self.assertEqual(beat["kind"], "broll")
        self.assertEqual(beat["search_query"], "people walking street")
        self.assertEqual(beat["selected"]["provider_asset_id"], "pexels_video_77")

    def test_strict_country_rejects_asset_without_verified_location(self):
        document = _doc()
        document["beats"] = [
            _beat(
                1,
                "people walking street",
                required_country="Vietnam",
                country_strict=True,
            )
        ]
        job_id = self._save_job(document)
        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=_recorded_get([_video_payload(), {"photos": []}]),
            http_download=_fake_download(),
            watermark_scanner=_clean_scanner,
        )
        beat = result["plan"]["beats"][0]
        self.assertEqual(beat["kind"], "no_asset_found")
        self.assertEqual(beat["reason"], "country_unverified")
        self.assertEqual(beat["required_country"], "Vietnam")
        self.assertTrue(beat["country_strict"])

    def test_photo_fallback_when_video_search_empty(self):
        downloads: list[str] = []
        job_id = self._save_job()
        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=_recorded_get([{"videos": []}, _photo_payload()]),
            http_download=_fake_download(downloads),
            watermark_scanner=_clean_scanner,
        )
        beat = result["plan"]["beats"][1]
        self.assertEqual(beat["kind"], "broll")
        self.assertEqual(beat["media_type"], "photo")
        self.assertEqual(result["manifest"][0]["local_path"], "assets/stock_002.jpg")
        self.assertEqual(downloads, ["http://cdn/55_orig.jpg"])

    def test_usage_cap_two_per_video(self):
        document = _doc()
        document["beats"] = [
            _beat(1, "people walking on street"),
            _beat(2, "people walking on street"),
            _beat(3, "people walking on street"),
        ]
        job_id = self._save_job(document)
        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=_constant_get(_video_payload()),
            http_download=_fake_download(),
            watermark_scanner=_clean_scanner,
        )
        kinds = [b["kind"] for b in result["plan"]["beats"]]
        self.assertEqual(kinds, ["broll", "broll", "no_asset_found"])
        self.assertEqual(result["plan"]["beats"][2]["reason"], "usage_cap_reached")
        self.assertEqual(result["plan"]["summary"]["broll"], 2)

    def test_download_failure_falls_back_to_no_asset(self):
        def broken_download(url: str, dest_path: str) -> int:
            raise OSError("network down")

        job_id = self._save_job()
        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=_constant_get(_video_payload()),
            http_download=broken_download,
        )
        beat = result["plan"]["beats"][1]
        self.assertEqual(beat["kind"], "no_asset_found")
        self.assertEqual(beat["reason"], "download_failed")
        self.assertEqual(result["manifest"], [])

    def test_watermark_detected_excludes_asset_and_deletes_file(self):
        from shared.modules.logo_scanner import WatermarkScanResult

        def wm_scanner(path: str, media_type: str):
            return WatermarkScanResult(detected=True, score=0.0305, region="bottom_right")

        job_id = self._save_job()
        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=_constant_get(_video_payload()),
            http_download=_fake_download(),
            watermark_scanner=wm_scanner,
        )
        beat = result["plan"]["beats"][1]
        self.assertEqual(beat["kind"], "no_asset_found")
        self.assertEqual(beat["reason"], "watermark_detected")
        self.assertEqual(result["manifest"], [])
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, job_id, "assets/stock_002.mp4")))

    def test_watermark_scan_error_treated_as_detected(self):
        def broken_scanner(path: str, media_type: str):
            raise OSError("unreadable file")

        job_id = self._save_job()
        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=_constant_get(_video_payload()),
            http_download=_fake_download(),
            watermark_scanner=broken_scanner,
        )
        beat = result["plan"]["beats"][1]
        self.assertEqual(beat["kind"], "no_asset_found")
        self.assertEqual(beat["reason"], "watermark_scan_error")
        self.assertEqual(result["manifest"], [])

    def test_search_error_recorded_per_beat(self):
        def rate_limited(url: str, headers: dict) -> dict:
            raise RuntimeError("PEXELS_RATE_LIMITED")

        job_id = self._save_job()
        result = plan_media_for_job(
            job_id, jobs_dir=self.tmp, http_get=rate_limited, http_download=_fake_download()
        )
        beat = result["plan"]["beats"][1]
        self.assertEqual(beat["kind"], "no_asset_found")
        self.assertEqual(beat["reason"], "search_error: PEXELS_RATE_LIMITED")

    def test_small_video_file_filtered_by_technical_check(self):
        payload = _video_payload()
        payload["videos"][0]["video_files"] = [
            {"file_type": "video/mp4", "width": 720, "height": 1280,
             "link": "http://cdn/small.mp4", "file_size": 2}
        ]
        job_id = self._save_job()
        result = plan_media_for_job(
            job_id,
            jobs_dir=self.tmp,
            http_get=_recorded_get([payload, {"photos": []}]),
            http_download=_fake_download(),
        )
        # File 720x1280 không đủ crop 1080x1920 -> video bị loại, photo rỗng -> no asset
        beat = result["plan"]["beats"][1]
        self.assertEqual(beat["kind"], "no_asset_found")
        self.assertEqual(beat["reason"], "below_technical_requirement")


class TestSetJobStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="set_status_test_")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_status_round_trip(self):
        job_id, _ = production_jobs.save_job(
            _doc(), channel_id="kenh_a",
            validation={"beat_count": 3, "passed": True},
            storyboard={"beats": _doc()["beats"]},
            jobs_dir=self.tmp,
        )
        meta = production_jobs.set_job_status(job_id, "assets_partial", jobs_dir=self.tmp)
        self.assertEqual(meta["status"], "assets_partial")
        reloaded = production_jobs.load_job(job_id, jobs_dir=self.tmp)
        self.assertEqual(reloaded["status"], "assets_partial")
        self.assertGreaterEqual(reloaded["updated_at"], reloaded["created_at"] or reloaded["updated_at"])

    def test_unknown_job_returns_none(self):
        self.assertIsNone(
            production_jobs.set_job_status("prod_000000000000", "assets_ready", jobs_dir=self.tmp)
        )


class TestPexelsProviderInjection(unittest.TestCase):
    def test_search_without_key_and_without_http_raises(self):
        os.environ.pop("PEXELS_API_KEY", None)
        with self.assertRaises(RuntimeError) as ctx:
            search_pexels("people walking")
        self.assertEqual(str(ctx.exception), "PEXELS_API_KEY_MISSING")

    def test_search_empty_query_returns_empty(self):
        self.assertEqual(search_pexels("", http_get=_constant_get({"videos": []})), [])

    def test_search_normalizes_video_payload(self):
        results = search_pexels(
            "people walking on street",
            http_get=_constant_get(_video_payload()),
        )
        self.assertEqual(len(results), 1)
        entry = results[0]
        self.assertEqual(entry["provider"], "pexels")
        self.assertEqual(entry["provider_asset_id"], "pexels_video_77")
        self.assertEqual(entry["media_type"], "video")
        self.assertEqual(entry["description"], "people walking on street")
        self.assertEqual(entry["asset_url"], "http://cdn/77_1080.mp4")

    def test_search_json_payload_written_by_provider_is_plain_dict(self):
        payload = _video_payload()
        # đảm bảo normalize đọc được JSON deserialize chuẩn (không tuple/list lạ)
        round_trip = json.loads(json.dumps(payload))
        results = search_pexels("street", http_get=_constant_get(round_trip))
        self.assertEqual(results[0]["provider_asset_id"], "pexels_video_77")

    def test_search_pixabay_normalizes_video_and_photo(self):
        video_hits = {
            "hits": [
                {
                    "id": 901,
                    "pageURL": "https://pixabay.com/videos/apartment-building-901/",
                    "duration": 12,
                    "tags": "apartment, building, city",
                    "user": "StudioA",
                    "videos": {
                        "large": {
                            "url": "https://cdn.pixabay.com/v/901.mp4",
                            "width": 1920,
                            "height": 1080,
                            "size": 1024,
                        }
                    },
                }
            ]
        }
        v_res = search_pixabay("apartment", media_type="video", http_get=_constant_get(video_hits))
        self.assertEqual(len(v_res), 1)
        self.assertEqual(v_res[0]["provider"], "pixabay")
        self.assertEqual(v_res[0]["provider_asset_id"], "pixabay_video_901")
        self.assertEqual(v_res[0]["license_source"], "pixabay_license")

    def test_search_wikimedia_normalizes_photo_without_api_key(self):
        wm_payload = {
            "query": {
                "pages": {
                    "1001": {
                        "pageid": 1001,
                        "title": "File:Apartment_building_exterior_HCMC.jpg",
                        "imageinfo": [
                            {
                                "url": "https://upload.wikimedia.org/apt.jpg",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Apartment_building_exterior_HCMC.jpg",
                                "width": 3000,
                                "height": 2000,
                                "mime": "image/jpeg",
                                "extmetadata": {
                                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    "Artist": {"value": "AuthorB"},
                                    "ImageDescription": {"value": "High rise apartment building exterior"},
                                    "Categories": {"value": "Buildings in Vietnam|Apartments"},
                                },
                            }
                        ],
                    }
                }
            }
        }
        w_res = search_wikimedia("apartment building", media_type="photo", http_get=_constant_get(wm_payload))
        self.assertEqual(len(w_res), 1)
        self.assertEqual(w_res[0]["provider"], "wikimedia")
        self.assertEqual(w_res[0]["provider_asset_id"], "wikimedia_photo_1001")
        self.assertIn("wikimedia_commons", w_res[0]["license_source"])

    def test_search_unsplash_normalizes_real_photo(self):
        unsplash_payload = {
            "results": [
                {
                    "id": "vn_apt_01",
                    "width": 4000,
                    "height": 6000,
                    "alt_description": "high rise apartment building exterior in Ho Chi Minh City",
                    "description": "Saigon residential tower",
                    "slug": "saigon-apartment-tower-vn_apt_01",
                    "urls": {
                        "full": "https://images.unsplash.com/photo-vn_apt_01?fm=jpg&q=85",
                    },
                    "links": {
                        "html": "https://unsplash.com/photos/vn_apt_01",
                    },
                    "user": {"name": "Minh Tran", "username": "minhtran"},
                    "tags": [{"title": "apartment"}, {"title": "vietnam"}],
                }
            ]
        }
        u_res = search_unsplash("apartment building", http_get=_constant_get(unsplash_payload))
        self.assertEqual(len(u_res), 1)
        self.assertEqual(u_res[0]["provider"], "unsplash")
        self.assertEqual(u_res[0]["provider_asset_id"], "unsplash_photo_vn_apt_01")
        self.assertEqual(u_res[0]["license_source"], "unsplash_license")

    def test_search_serpapi_google_images_normalizes_results(self):
        serp_payload = {
            "images_results": [
                {
                    "position": 1,
                    "thumbnail": "https://encrypted-tbn0.gstatic.com/images?q=tbn:xyz",
                    "original": "https://media.vnexpress.net/chung-cu-tphcm-1080.jpg",
                    "title": "Chung cư TP HCM điều chỉnh khung giá mới",
                    "source": "VnExpress",
                    "link": "https://vnexpress.net/tin-tuc-chung-cu-5142712.html",
                    "original_width": 1920,
                    "original_height": 1080,
                }
            ]
        }
        res = search_serpapi_google_images("chung cư", http_get=_constant_get(serp_payload), api_key="fake")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["provider"], "serpapi_google")
        self.assertEqual(res[0]["asset_url"], "https://media.vnexpress.net/chung-cu-tphcm-1080.jpg")
        self.assertEqual(res[0]["thumbnail_url"], "https://encrypted-tbn0.gstatic.com/images?q=tbn:xyz")
        self.assertEqual(res[0]["page_url"], "https://vnexpress.net/tin-tuc-chung-cu-5142712.html")
        self.assertEqual(res[0]["license_source"], "serpapi_google_images")
        self.assertEqual(res[0]["width"], 1920)
        self.assertEqual(res[0]["height"], 1080)


if __name__ == "__main__":
    unittest.main()
