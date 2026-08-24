"""Generate ASS subtitle files from audio using Faster-Whisper and burn them into video."""

import os
import subprocess
import re
from typing import Any, Iterable, Sequence

from shared.core.safe_zone import get_subtitle_constraints
from shared.core.video_encoding import final_output_args


PHRASE_ENDINGS = (".", "!", "?", ";", ":", ",")


def _format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_color: str, default: str = "&H0000FFFF") -> str:
    # Convert hex #RRGGBB to ASS color &H00BBGGRR
    clean_hex = str(hex_color or "").replace("#", "")
    if len(clean_hex) == 6:
        r, g, b = clean_hex[0:2], clean_hex[2:4], clean_hex[4:6]
        return f"&H00{b}{g}{r}"
    return default


def _get_ass_header(
    font_size=70,
    margin_v=420,
    hex_color="#00ffff",
    font_name="UTM Helve",
    margin_l=90,
    margin_r=150,
):
    ass_color = _ass_color(hex_color)
    constraints = get_subtitle_constraints()
    font_size = max(
        int(constraints.get("min_font_size", 46)),
        min(int(constraints.get("max_font_size", 76)), int(font_size)),
    )
    # Keep subtitles clear of TikTok's bottom caption and right-side controls.
    margin_v = max(
        int(constraints.get("min_margin_bottom", 320)),
        min(int(constraints.get("max_margin_bottom", 760)), int(margin_v)),
    )
    margin_l = max(int(constraints.get("min_margin_left", 40)), int(margin_l))
    margin_r = max(int(constraints.get("min_margin_right", 100)), int(margin_r))

    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{ass_color},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,{margin_l},{margin_r},{margin_v},0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _word_text(word: Any) -> str:
    return str(getattr(word, "word", word) or "").strip()


def chunk_phrase_words(words: Sequence[Any], max_words: int = 7) -> list[list[Any]]:
    """Split on spoken punctuation while keeping every subtitle compact."""
    max_words = max(3, min(9, int(max_words)))
    chunks: list[list[Any]] = []
    current: list[Any] = []
    for word in words:
        if not _word_text(word):
            continue
        current.append(word)
        text = _word_text(word)
        if len(current) >= max_words or (
            text.endswith(PHRASE_ENDINGS) and len(current) >= 3
        ):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _escape_ass(value: str) -> str:
    return str(value or "").replace("{", "(").replace("}", ")")


def _is_highlight_word(word: str, keywords: Iterable[str]) -> bool:
    clean = re.sub(r"[^0-9A-Za-zÀ-ỹđĐ%.,]", "", word)
    keyword_set = {
        token.lower().strip(".,:;!?")
        for item in keywords
        for token in str(item).split()
        if token.strip(".,:;!?")
    }
    return bool(re.search(r"\d", clean)) or clean.lower().strip(".,:;!?") in keyword_set


def _two_line_break(words: list[str]) -> list[str]:
    if len(words) <= 4:
        return words
    split_at = (len(words) + 1) // 2
    return words[:split_at] + [r"\N" + words[split_at]] + words[split_at + 1:]


def format_ass_phrase(
    words: Sequence[Any],
    *,
    word_duration_cs: int | None = None,
    primary_color: str = "#FFFFFF",
    highlight_color: str = "#FFD54A",
    keywords: Iterable[str] = (),
) -> str:
    """Format one karaoke phrase with at most one line break."""
    primary = _ass_color(primary_color, "&H00FFFFFF")
    accent = _ass_color(highlight_color, "&H004AD5FF")
    rendered: list[str] = []
    for word in words:
        value = _escape_ass(_word_text(word).upper())
        if not value:
            continue
        if word_duration_cs is None:
            start = float(getattr(word, "start", 0.0) or 0.0)
            end = float(getattr(word, "end", start + 0.12) or start + 0.12)
            duration_cs = max(8, int((end - start) * 100))
        else:
            duration_cs = max(8, int(word_duration_cs))
        color = f"\\c{accent}" if _is_highlight_word(value, keywords) else f"\\c{primary}"
        rendered.append(f"{{\\k{duration_cs}{color}}}{value}")
    return " ".join(_two_line_break(rendered))


def get_subtitle_preset(channel_id: str = "", overrides: dict | None = None) -> dict:
    """Resolve subtitle font/colors from the central channel video style."""
    constraints = get_subtitle_constraints()
    preset = {
        "font_name": "Roboto Condensed",
        "font_size": 64,
        "margin_v": 420,
        "margin_l": 90,
        "margin_r": 150,
        "hex_color": "#FFFFFF",
        "highlight_color": "#FFD54A",
        "max_words": int(constraints.get("max_words", 7)),
    }
    try:
        from shared.core.prompt_builder import get_video_style

        style = get_video_style(channel_id)
        text_style = style.get("text_preset", {}) if isinstance(style, dict) else {}
        color_style = style.get("color_preset", {}) if isinstance(style, dict) else {}
        if isinstance(text_style, dict) and text_style.get("font"):
            preset["font_name"] = os.path.splitext(str(text_style["font"]))[0]
        if isinstance(color_style, dict):
            preset["hex_color"] = color_style.get("text", preset["hex_color"])
            preset["highlight_color"] = color_style.get("accent", preset["highlight_color"])
    except Exception:
        pass
    if overrides:
        preset.update({key: value for key, value in overrides.items() if value is not None})
    return preset


def _apply_long_caption_preset(
    word_count: int,
    *,
    words_per_line: int,
    font_size: int,
    margin_v: int,
    margin_l: int,
    margin_r: int,
) -> tuple[int, int, int, int, int]:
    fallback = get_subtitle_constraints(long_caption=True)
    threshold = int(fallback.get("word_threshold", 95))
    if word_count < threshold:
        return words_per_line, font_size, margin_v, margin_l, margin_r
    return (
        min(words_per_line, int(fallback.get("max_words", 6))),
        min(font_size, int(fallback.get("font_size", 58))),
        max(margin_v, int(fallback.get("margin_bottom", 460))),
        max(margin_l, int(fallback.get("margin_left", 110))),
        max(margin_r, int(fallback.get("margin_right", 180))),
    )


def generate_word_ass(
    audio_path: str,
    output_ass: str,
    time_offset: float = 0.0,
    words_per_line: int = 7,
    font_size: int = 64,
    margin_v: int = 420,
    hex_color: str = "#FFFFFF",
    highlight_color: str = "#FFD54A",
    keywords: Iterable[str] = (),
    font_name: str = "Roboto Condensed",
    margin_l: int = 90,
    margin_r: int = 150,
):
    """
    Transcribe audio with Faster-Whisper and generate an ASS subtitle file.

    Args:
        audio_path: Path to audio file (WAV/MP3).
        output_ass: Output path for the .ass file.
        time_offset: Seconds to add to all timestamps (e.g. hook_dur for article/FB pipelines).
        words_per_line: Words per subtitle chunk (default 7).

    Returns:
        output_ass path on success, None on failure.
    """
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="float32")
        segments, _ = model.transcribe(audio_path, language="vi", word_timestamps=True)

        all_words = []
        for segment in segments:
            if segment.words:
                all_words.extend(segment.words)

        if not all_words:
            return None

        words_per_line, font_size, margin_v, margin_l, margin_r = _apply_long_caption_preset(
            len(all_words),
            words_per_line=words_per_line,
            font_size=font_size,
            margin_v=margin_v,
            margin_l=margin_l,
            margin_r=margin_r,
        )

        lines = []
        for chunk in chunk_phrase_words(all_words, max_words=words_per_line):
            start = chunk[0].start + time_offset
            end = min(chunk[-1].end + time_offset + 0.15, start + 5.0)
            karaoke_text = format_ass_phrase(
                chunk,
                primary_color=hex_color,
                highlight_color=highlight_color,
                keywords=keywords,
            )
            if not karaoke_text.strip():
                continue
            lines.append(
                f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,,0,0,0,,{karaoke_text.strip()}"
            )

        if not lines:
            return None

        with open(output_ass, "w", encoding="utf-8") as f:
            f.write(_get_ass_header(
                font_size=font_size,
                margin_v=margin_v,
                hex_color=hex_color,
                font_name=font_name,
                margin_l=margin_l,
                margin_r=margin_r,
            ))
            f.write("\n".join(lines))
            f.write("\n")

        return output_ass

    except Exception as e:
        print(f"   ⚠️ Lỗi tạo ASS subtitle: {e}")
        return None


def generate_text_ass(
    text: str,
    output_ass: str,
    duration: float,
    time_offset: float = 0.0,
    words_per_line: int = 7,
    font_size: int = 64,
    margin_v: int = 420,
    hex_color: str = "#FFFFFF",
    highlight_color: str = "#FFD54A",
    keywords: Iterable[str] = (),
    font_name: str = "Roboto Condensed",
    margin_l: int = 90,
    margin_r: int = 150,
):
    """
    Generate an approximate karaoke ASS file directly from the known script text.
    This is a fallback for environments without Faster-Whisper.
    """
    try:
        clean_text = re.sub(r"\s+", " ", str(text or "")).strip()
        words = [w.strip("{}\\") for w in clean_text.split() if w.strip("{}\\")]
        duration = float(duration or 0)

        if not words or duration <= 0:
            return None

        words_per_line, font_size, margin_v, margin_l, margin_r = _apply_long_caption_preset(
            len(words),
            words_per_line=words_per_line,
            font_size=font_size,
            margin_v=margin_v,
            margin_l=margin_l,
            margin_r=margin_r,
        )

        word_duration = duration / len(words)
        elapsed = 0.0
        lines = []

        for chunk in chunk_phrase_words(words, max_words=words_per_line):
            start = time_offset + elapsed
            line_duration = word_duration * len(chunk)
            end = start + line_duration + 0.08
            karaoke_text = format_ass_phrase(
                chunk,
                word_duration_cs=max(8, int(word_duration * 100)),
                primary_color=hex_color,
                highlight_color=highlight_color,
                keywords=keywords,
            )

            lines.append(
                f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,,0,0,0,,{karaoke_text.strip()}"
            )
            elapsed += line_duration

        with open(output_ass, "w", encoding="utf-8") as f:
            f.write(_get_ass_header(
                font_size=font_size,
                margin_v=margin_v,
                hex_color=hex_color,
                font_name=font_name,
                margin_l=margin_l,
                margin_r=margin_r,
            ))
            f.write("\n".join(lines))
            f.write("\n")

        return output_ass

    except Exception as e:
        print(f"   ⚠️ Lỗi tạo ASS từ script text: {e}")
        return None


def apply_subtitles_to_video(input_video: str, ass_path: str, output_video: str, fonts_dir: str = "") -> bool:
    """
    Burn ASS subtitles into video using FFmpeg.
    input_video and output_video must be different paths.

    Returns True on success, False on failure.
    """
    try:
        safe_ass = ass_path.replace("\\", "/").replace(":", "\\:")
        sub_filter = f"subtitles='{safe_ass}'"
        if fonts_dir:
            safe_fonts = fonts_dir.replace("\\", "/")
            sub_filter += f":fontsdir='{safe_fonts}'"

        cmd = [
            "ffmpeg", "-y", "-i", input_video,
            "-vf", sub_filter,
            *final_output_args(),
            output_video
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"   ⚠️ FFmpeg subtitle burn lỗi: {result.stderr[-400:]}")
            return False
        return True

    except Exception as e:
        print(f"   ⚠️ Lỗi burn subtitle: {e}")
        return False
