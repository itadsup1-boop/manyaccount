"""Tải và ghép các luồng DASH do Facebook CDN trả theo byte-range."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from shared.core.ffmpeg_utils import ffmpeg_command, ffprobe_command


RANGE_QUERY_KEYS = {"bytestart", "byteend"}
MAX_MEDIA_BYTES = 200 * 1024 * 1024


def normalize_dash_url(url: str) -> str:
    """Bỏ byte-range để Facebook CDN trả toàn bộ track thay vì một fragment."""

    parsed = urlparse(str(url or ""))
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in RANGE_QUERY_KEYS
    ]
    return urlunparse(parsed._replace(query=urlencode(query)))


def probe_media(path: str) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ffprobe_command(
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height,duration",
                "-of",
                "json",
                path,
            ),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None

    streams = payload.get("streams") or []
    types = {str(stream.get("codec_type") or "") for stream in streams}
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    try:
        duration = float(
            video.get("duration")
            or next(
                (item.get("duration") for item in streams if item.get("duration")),
                0,
            )
            or (payload.get("format") or {}).get("duration")
            or 0
        )
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
    except (TypeError, ValueError):
        return None
    return {
        "path": path,
        "types": types,
        "duration": duration,
        "width": width,
        "height": height,
    }


def select_dash_tracks(
    tracks: Iterable[Mapping[str, Any]],
    target_metrics: Mapping[str, Any] | None = None,
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    tracks = list(tracks)
    videos = [track for track in tracks if "video" in set(track.get("types") or [])]
    if not videos:
        return None, None

    target = target_metrics or {}
    target_duration = float(target.get("duration") or 0)
    target_width = int(target.get("width") or 0)
    target_height = int(target.get("height") or 0)

    def video_key(track: Mapping[str, Any]) -> tuple[float, int]:
        duration = float(track.get("duration") or 0)
        width = int(track.get("width") or 0)
        height = int(track.get("height") or 0)
        duration_delta = abs(duration - target_duration) if target_duration else 0
        dimension_delta = (
            abs(width - target_width) + abs(height - target_height)
            if target_width and target_height
            else 0
        )
        return (duration_delta * 10000 + dimension_delta, -(width * height))

    video = min(videos, key=video_key)
    if "audio" in set(video.get("types") or []):
        return video, None

    audio_tracks = [
        track
        for track in tracks
        if "audio" in set(track.get("types") or [])
        and "video" not in set(track.get("types") or [])
    ]
    if not audio_tracks:
        return video, None
    video_duration = float(video.get("duration") or 0)
    audio = min(
        audio_tracks,
        key=lambda track: abs(float(track.get("duration") or 0) - video_duration),
    )
    return video, audio


def download_dash_video(
    urls: Iterable[str],
    output_path: str,
    *,
    headers: Mapping[str, str],
    cookies: Mapping[str, str],
    target_metrics: Mapping[str, Any] | None = None,
) -> bool:
    import requests

    complete_urls = list(
        dict.fromkeys(normalize_dash_url(url) for url in urls if str(url).strip())
    )
    if not complete_urls:
        return False

    temp_dir = tempfile.mkdtemp(prefix="facebook_dash_")
    tracks: list[dict[str, Any]] = []
    try:
        for index, url in enumerate(complete_urls):
            path = os.path.join(temp_dir, f"track_{index}.mp4")
            try:
                with requests.get(
                    url,
                    timeout=300,
                    stream=True,
                    headers=dict(headers),
                    cookies=dict(cookies),
                ) as response:
                    response.raise_for_status()
                    announced = int(response.headers.get("content-length") or 0)
                    if announced > MAX_MEDIA_BYTES:
                        continue
                    written = 0
                    with open(path, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if not chunk:
                                continue
                            written += len(chunk)
                            if written > MAX_MEDIA_BYTES:
                                raise ValueError("Facebook media vượt quá 200 MB")
                            handle.write(chunk)
            except Exception:
                continue
            media = probe_media(path)
            if media:
                tracks.append(media)

        video, audio = select_dash_tracks(tracks, target_metrics)
        if not video:
            return False
        if audio is None and "audio" not in set(video.get("types") or []):
            return False

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        if audio:
            command = ffmpeg_command(
                "-y",
                "-v",
                "error",
                "-i",
                str(video["path"]),
                "-i",
                str(audio["path"]),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                output_path,
            )
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
            return result.returncode == 0 and os.path.exists(output_path)

        shutil.copyfile(str(video["path"]), output_path)
        return os.path.exists(output_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
