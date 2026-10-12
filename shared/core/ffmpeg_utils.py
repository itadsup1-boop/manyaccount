"""Resolve FFmpeg binaries consistently on Windows and other platforms."""

from __future__ import annotations

import os
import shutil
from functools import lru_cache


def _configured(name: str) -> str | None:
    value = str(os.environ.get(name, "") or "").strip().strip('"')
    return value if value and os.path.isfile(value) else None


@lru_cache(maxsize=1)
def resolve_ffmpeg_binary() -> str:
    """Return an executable path usable by subprocess and ffmpeg-python."""
    for env_name in ("FFMPEG_BINARY", "IMAGEIO_FFMPEG_EXE"):
        configured = _configured(env_name)
        if configured:
            return configured

    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path

    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.isfile(bundled):
            return bundled
    except Exception:
        pass
    return "ffmpeg"


@lru_cache(maxsize=1)
def resolve_ffprobe_binary() -> str:
    """Return the matching FFprobe executable when available."""
    configured = _configured("FFPROBE_BINARY")
    if configured:
        return configured

    on_path = shutil.which("ffprobe")
    if on_path:
        return on_path

    ffmpeg_path = resolve_ffmpeg_binary()
    if os.path.isfile(ffmpeg_path):
        sibling = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe.exe")
        if os.path.isfile(sibling):
            return sibling
    return "ffprobe"


def ffmpeg_command(*args: str) -> list[str]:
    return [resolve_ffmpeg_binary(), *[str(arg) for arg in args]]


def ffprobe_command(*args: str) -> list[str]:
    return [resolve_ffprobe_binary(), *[str(arg) for arg in args]]
