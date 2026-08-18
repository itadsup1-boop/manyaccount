"""Generate ASS subtitle files from audio using Faster-Whisper and burn them into video."""

import os
import subprocess
import re


def _format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _get_ass_header(font_size=70, margin_v=150, hex_color="#00ffff"):
    # Convert hex #RRGGBB to ASS color &H00BBGGRR
    clean_hex = hex_color.replace("#", "")
    if len(clean_hex) == 6:
        r, g, b = clean_hex[0:2], clean_hex[2:4], clean_hex[4:6]
        ass_color = f"&H00{b}{g}{r}"
    else:
        ass_color = "&H0000FFFF" # Default yellow

    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,UTM Helve,{font_size},{ass_color},&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,1,2,20,20,{margin_v},0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def generate_word_ass(audio_path: str, output_ass: str, time_offset: float = 0.0, words_per_line: int = 4, font_size: int = 70, margin_v: int = 150, hex_color: str = "#00ffff"):
    """
    Transcribe audio with Faster-Whisper and generate an ASS subtitle file.

    Args:
        audio_path: Path to audio file (WAV/MP3).
        output_ass: Output path for the .ass file.
        time_offset: Seconds to add to all timestamps (e.g. hook_dur for article/FB pipelines).
        words_per_line: Words per subtitle chunk (default 4).

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

        lines = []
        for i in range(0, len(all_words), words_per_line):
            chunk = all_words[i:i + words_per_line]
            start = chunk[0].start + time_offset
            end = min(chunk[-1].end + time_offset + 0.15, start + 5.0)
            
            # Khởi tạo chuỗi chữ Karaoke
            karaoke_text = ""
            for w in chunk:
                # Tính thời lượng từng chữ theo centisecond (1/100 giây)
                dur_cs = int((w.end - w.start) * 100)
                word_clean = w.word.strip().upper()
                karaoke_text += f"{{\\k{dur_cs}}}{word_clean} "

            if not karaoke_text.strip():
                continue
            lines.append(
                f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,,0,0,0,,{karaoke_text.strip()}"
            )

        if not lines:
            return None

        with open(output_ass, "w", encoding="utf-8") as f:
            f.write(_get_ass_header(font_size=font_size, margin_v=margin_v, hex_color=hex_color))
            f.write("\n".join(lines))
            f.write("\n")

        return output_ass

    except Exception as e:
        print(f"   ⚠️ Lỗi tạo ASS subtitle: {e}")
        return None


def generate_text_ass(text: str, output_ass: str, duration: float, time_offset: float = 0.0, words_per_line: int = 4, font_size: int = 70, margin_v: int = 150, hex_color: str = "#00ffff"):
    """
    Generate an approximate karaoke ASS file directly from the known script text.
    This is a fallback for environments without Faster-Whisper.
    """
    try:
        clean_text = re.sub(r"\s+", " ", str(text or "")).strip()
        words = [w.strip("{}\\").upper() for w in clean_text.split() if w.strip("{}\\")]
        duration = float(duration or 0)

        if not words or duration <= 0:
            return None

        word_duration = duration / len(words)
        elapsed = 0.0
        lines = []

        for i in range(0, len(words), words_per_line):
            chunk = words[i:i + words_per_line]
            start = time_offset + elapsed
            line_duration = word_duration * len(chunk)
            end = start + line_duration + 0.08

            karaoke_text = ""
            for word in chunk:
                dur_cs = max(8, int(word_duration * 100))
                karaoke_text += f"{{\\k{dur_cs}}}{word} "

            lines.append(
                f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,,0,0,0,,{karaoke_text.strip()}"
            )
            elapsed += line_duration

        with open(output_ass, "w", encoding="utf-8") as f:
            f.write(_get_ass_header(font_size=font_size, margin_v=margin_v, hex_color=hex_color))
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
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
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
