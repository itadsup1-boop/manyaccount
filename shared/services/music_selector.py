"""Select licensed background music consistently for short-form news videos.

The selector keeps editorial tone (voice) separate from music mood.  It supports
the legacy flat ``assets/bgm`` filenames as well as the preferred catalog/folder
layout documented in ``assets/bgm/README.md``.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import random
import subprocess
import threading
from typing import Any, Iterator

from shared.core.ffmpeg_utils import ffmpeg_command
from shared.core.rights_guard import guard_music_rights


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BGM_DIR = PROJECT_ROOT / "assets" / "bgm"
DEFAULT_HISTORY_PATH = PROJECT_ROOT / "data" / "music_history.json"

VALID_MUSIC_MOODS = (
    "breaking_tension",
    "serious_warning",
    "neutral_news",
    "positive_upbeat",
    "sensitive_empathy",
    "sports_energy",
    "entertainment_drama",
)

TONE_TO_MOOD = {
    "tích cực": "positive_upbeat",
    "tich cuc": "positive_upbeat",
    "trung tính": "neutral_news",
    "trung tinh": "neutral_news",
    "cảnh báo": "serious_warning",
    "canh bao": "serious_warning",
    "đồng cảm": "sensitive_empathy",
    "dong cam": "sensitive_empathy",
}

# Existing local files use these prefixes.  A prefix can safely serve more than
# one related mood, but sensitive stories never fall back to a non-sensitive one.
LEGACY_PREFIX_MOODS = {
    "vui_ve_": ("positive_upbeat",),
    "hoi_hop_": ("serious_warning", "breaking_tension", "entertainment_drama"),
    "cam_dong_": ("sensitive_empathy",),
    "kich_tinh_": ("breaking_tension", "sports_energy", "entertainment_drama"),
    "nhe_nhang_": ("neutral_news", "sensitive_empathy"),
    "trung_tinh_": ("neutral_news",),
}

MOOD_FALLBACKS = {
    "breaking_tension": ("serious_warning", "neutral_news"),
    "serious_warning": ("breaking_tension", "neutral_news"),
    "neutral_news": (),
    "positive_upbeat": ("neutral_news",),
    "sensitive_empathy": (),
    "sports_energy": ("breaking_tension", "neutral_news"),
    "entertainment_drama": ("breaking_tension", "positive_upbeat", "neutral_news"),
}

# Target loudness before speech-triggered ducking.  Normalizing each track first
# prevents a quiet master and a loud master from producing very different mixes.
MOOD_BED_LUFS = {
    "breaking_tension": -19.0,
    "serious_warning": -21.0,
    "neutral_news": -22.0,
    "positive_upbeat": -20.0,
    "sensitive_empathy": -25.0,
    "sports_energy": -19.0,
    "entertainment_drama": -20.0,
}

_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac"}
_THREAD_LOCK = threading.Lock()


@dataclass(frozen=True)
class MusicTrack:
    track_id: str
    path: str
    moods: tuple[str, ...]
    energy: int = 2
    cue_start_sec: float = 8.0
    license_status: str = "unverified"
    license_source: str = ""


@dataclass(frozen=True)
class MusicSelection:
    track_id: str
    path: str
    mood: str
    energy: int
    cue_start_sec: float
    bed_lufs: float
    license_status: str
    license_source: str = ""
    # Gain tĩnh (dB) đưa track về mức bed_lufs. None = chưa đo được, filter
    # sẽ dùng mức dự phòng.
    bed_gain_db: float | None = None


def clamp_energy(value: Any) -> int:
    try:
        return max(1, min(3, int(value)))
    except (TypeError, ValueError):
        return 2


_MEASURED_BED_GAIN_CACHE: dict[str, float] = {}
_MEASURE_LOCK = threading.Lock()


def measure_bed_gain_db(path: str | os.PathLike[str], target_lufs: float) -> float | None:
    """Đo integrated loudness của track và quy thành gain dB tĩnh.

    Phải đo ngoài filtergraph vì sidechaincompress mất khoảng 3 giây cuối
    stream (giọng hook bị đứt) nếu một trong hai đầu vào từng đi qua bộ
    chuẩn hoá động như loudnorm/dynaudnorm. Gain tĩnh giữ nguyên mục tiêu
    bed_lufs mà không đưa loudnorm vào cạnh sidechaincompress.
    """
    try:
        key = f"{os.path.realpath(str(path))}::{float(target_lufs):.2f}"
    except (OSError, ValueError):
        return None
    with _MEASURE_LOCK:
        cached = _MEASURED_BED_GAIN_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        result = subprocess.run(
            ffmpeg_command(
                "-hide_banner", "-nostats", "-i", str(path),
                "-af", "loudnorm=print_format=json", "-f", "null", "-",
            ),
            capture_output=True,
            text=True,
            timeout=60,
        )
        stderr_tail = (result.stderr or "")[-6000:]
        start = stderr_tail.rfind("{")
        end = stderr_tail.rfind("}")
        measured_i = float(json.loads(stderr_tail[start : end + 1])["input_i"])
    except Exception:
        return None
    gain = max(-24.0, min(-3.0, float(target_lufs) - measured_i))
    with _MEASURE_LOCK:
        _MEASURED_BED_GAIN_CACHE[key] = gain
    return gain


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "có", "co"}


def normalize_music_mood(
    music_mood: str | None,
    tone: str | None = None,
    is_sensitive: Any = False,
) -> str:
    """Return a safe mood enum, forcing empathy for sensitive stories."""
    if _as_bool(is_sensitive):
        return "sensitive_empathy"

    requested = str(music_mood or "").strip().lower().replace("-", "_").replace(" ", "_")
    if requested in VALID_MUSIC_MOODS:
        return requested

    normalized_tone = str(tone or "").strip().lower()
    return TONE_TO_MOOD.get(normalized_tone, "neutral_news")


def _safe_asset_path(bgm_dir: Path, relative_path: str) -> Path | None:
    candidate = (bgm_dir / relative_path).resolve()
    try:
        candidate.relative_to(bgm_dir.resolve())
    except ValueError:
        return None
    if not candidate.is_file() or candidate.suffix.lower() not in _AUDIO_EXTENSIONS:
        return None
    return candidate


def _catalog_tracks(bgm_dir: Path, catalog_path: Path) -> list[MusicTrack]:
    if not catalog_path.is_file():
        return []
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, dict):
        return []

    tracks: list[MusicTrack] = []
    for raw in payload.get("tracks", []):
        if not isinstance(raw, dict) or raw.get("enabled", True) is False:
            continue
        path = _safe_asset_path(bgm_dir, str(raw.get("file", "")))
        if not path:
            continue
        raw_moods = raw.get("moods") or [raw.get("mood")]
        moods = tuple(m for m in raw_moods if m in VALID_MUSIC_MOODS)
        if not moods:
            continue
        try:
            cue_start_sec = max(0.0, float(raw.get("cue_start_sec", 8.0)))
        except (TypeError, ValueError):
            cue_start_sec = 8.0
        tracks.append(
            MusicTrack(
                track_id=str(raw.get("id") or path.stem),
                path=str(path),
                moods=moods,
                energy=clamp_energy(raw.get("energy", 2)),
                cue_start_sec=cue_start_sec,
                license_status=str(raw.get("license_status", "unverified")),
                license_source=str(raw.get("license_source", "")),
            )
        )
    return tracks


def _folder_tracks(bgm_dir: Path) -> list[MusicTrack]:
    tracks: list[MusicTrack] = []
    for mood in VALID_MUSIC_MOODS:
        mood_dir = bgm_dir / mood
        if not mood_dir.is_dir():
            continue
        for path in sorted(mood_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS:
                tracks.append(
                    MusicTrack(
                        track_id=path.stem,
                        path=str(path.resolve()),
                        moods=(mood,),
                    )
                )
    return tracks


def _legacy_tracks(bgm_dir: Path) -> list[MusicTrack]:
    tracks: list[MusicTrack] = []
    if not bgm_dir.is_dir():
        return tracks
    for path in sorted(bgm_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _AUDIO_EXTENSIONS:
            continue
        lowered = path.name.lower()
        if lowered.startswith("test"):
            continue
        for prefix, moods in LEGACY_PREFIX_MOODS.items():
            if lowered.startswith(prefix):
                energy = 3 if prefix == "kich_tinh_" else 1 if prefix in {"cam_dong_", "nhe_nhang_"} else 2
                tracks.append(
                    MusicTrack(
                        track_id=path.stem,
                        path=str(path.resolve()),
                        moods=moods,
                        energy=energy,
                    )
                )
                break
    return tracks


def discover_music_tracks(
    bgm_dir: str | os.PathLike[str] = DEFAULT_BGM_DIR,
    catalog_path: str | os.PathLike[str] | None = None,
) -> list[MusicTrack]:
    """Discover cataloged, mood-folder, and legacy tracks without duplicates."""
    root = Path(bgm_dir)
    catalog = Path(catalog_path) if catalog_path else root / "catalog.json"
    found = _catalog_tracks(root, catalog) + _folder_tracks(root) + _legacy_tracks(root)
    unique: dict[str, MusicTrack] = {}
    for track in found:
        # Catalog metadata wins because it is discovered first.
        unique.setdefault(os.path.realpath(track.path), track)
    return list(unique.values())


@contextmanager
def _history_guard(history_path: Path) -> Iterator[None]:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = history_path.with_suffix(history_path.suffix + ".lock")
    with _THREAD_LOCK:
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass
            try:
                yield
            finally:
                try:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except (ImportError, OSError):
                    pass


def _read_history(path: Path) -> dict[str, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_history(path: Path, data: dict[str, list[str]]) -> None:
    temp_path = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def _eligible_tracks(tracks: list[MusicTrack], mood: str, energy: int) -> list[MusicTrack]:
    exact = [track for track in tracks if mood in track.moods]
    if exact:
        nearest_gap = min(abs(track.energy - energy) for track in exact)
        nearest = [track for track in exact if abs(track.energy - energy) == nearest_gap]
        return nearest or exact

    for fallback in MOOD_FALLBACKS[mood]:
        candidates = [track for track in tracks if fallback in track.moods]
        if candidates:
            return candidates
    return []


def select_music(
    music_mood: str | None = None,
    *,
    tone: str | None = None,
    energy: Any = 2,
    is_sensitive: Any = False,
    channel_id: str | None = None,
    bgm_dir: str | os.PathLike[str] = DEFAULT_BGM_DIR,
    catalog_path: str | os.PathLike[str] | None = None,
    history_path: str | os.PathLike[str] = DEFAULT_HISTORY_PATH,
    recent_limit: int = 5,
) -> MusicSelection | None:
    """Choose one appropriate track and avoid recent repeats per channel."""
    mood = normalize_music_mood(music_mood, tone=tone, is_sensitive=is_sensitive)
    normalized_energy = clamp_energy(energy)
    tracks = discover_music_tracks(bgm_dir, catalog_path)
    tracks = [track for track in tracks if guard_music_rights(track).passed]
    candidates = _eligible_tracks(tracks, mood, normalized_energy)
    if not candidates:
        return None

    history_file = Path(history_path)
    history_key = str(channel_id or "default").strip() or "default"
    with _history_guard(history_file):
        history = _read_history(history_file)
        saved_recent = history.get(history_key, [])
        if not isinstance(saved_recent, list):
            saved_recent = []
        recent = saved_recent[-max(1, recent_limit) :]
        fresh = [track for track in candidates if track.track_id not in recent]
        pool = fresh or candidates
        track = random.choice(pool)
        history[history_key] = (recent + [track.track_id])[-max(1, recent_limit) :]
        _write_history(history_file, history)

    # Energy nudges the target bed loudness without changing the selected mood.
    bed_lufs = max(-27.0, min(-18.0, MOOD_BED_LUFS[mood] + (normalized_energy - 2) * 1.5))
    bed_gain_db = measure_bed_gain_db(track.path, bed_lufs)
    return MusicSelection(
        track_id=track.track_id,
        path=track.path,
        mood=mood,
        energy=normalized_energy,
        cue_start_sec=track.cue_start_sec,
        bed_lufs=bed_lufs,
        license_status=track.license_status,
        license_source=track.license_source,
        bed_gain_db=bed_gain_db,
    )


def build_ducked_mix_filter(
    voice_label: str,
    bgm_label: str,
    duration_sec: float,
    selection: MusicSelection,
    *,
    output_label: str = "aout",
    label_prefix: str = "music",
    music_offset_sec: float = 0.0,
) -> str:
    """Build an FFmpeg filter graph that ducks music under normalized speech."""
    duration = max(0.1, float(duration_sec))
    cue = max(0.0, selection.cue_start_sec + float(music_offset_sec))
    fade_out_start = max(0.0, duration - min(0.8, duration / 3))
    voice = voice_label.strip("[]")
    bgm = bgm_label.strip("[]")
    out = output_label.strip("[]")
    prefix = "".join(char for char in label_prefix if char.isalnum() or char == "_") or "music"
    # sidechaincompress dừng sớm (~mất 3 giây cuối, voice ngắn còn ~0.1s) nếu
    # một trong hai đầu vào của nó từng đi qua loudnorm/dynaudnorm: bộ chuẩn
    # hoá động phát frame không đều khiến cặp main/sidechain mất đồng bộ.
    # Vì vậy tách bản voice THÔ cho sidechain, loudnorm chỉ đứng sau khi đã
    # tách; bed chỉnh mức bằng gain tĩnh đo trước (bed_gain_db) thay vì
    # loudnorm trong graph.
    bed_gain = (
        f"{selection.bed_gain_db:.2f}"
        if selection.bed_gain_db is not None
        else "-12.00"
    )
    return (
        f"[{voice}]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"asplit=2[{prefix}_voicemix][{prefix}_side];"
        f"[{prefix}_voicemix]loudnorm=I=-16:LRA=7:TP=-2[{prefix}_voice];"
        f"[{bgm}]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"atrim=start={cue:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={min(0.2, duration / 4):.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={duration - fade_out_start:.3f},"
        f"volume={bed_gain}dB[{prefix}_bed];"
        f"[{prefix}_bed][{prefix}_side]sidechaincompress="
        f"threshold=0.08:ratio=4:attack=15:release=300[{prefix}_ducked];"
        f"[{prefix}_voice][{prefix}_ducked]amix="
        f"inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"loudnorm=I=-14:LRA=9:TP=-1.5[{out}]"
    )
