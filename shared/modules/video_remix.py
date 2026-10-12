import os
import sys
import requests
import shutil
import json
import ffmpeg
import logging
import uuid
import subprocess
from datetime import datetime

from shared.services.music_selector import build_ducked_mix_filter, select_music
from shared.core.beat_timeline import plan_beat_timeline, resolve_intro_overlay_text
from shared.services.audio_director import plan_audio_cues
from shared.core.video_encoding import (
    final_output_args,
    resolve_color_grade,
)
from shared.core.ffmpeg_utils import resolve_ffmpeg_binary, resolve_ffprobe_binary
from shared.core.safe_zone import plan_text_layout
from shared.modules.subtitle_renderer import (
    generate_text_ass,
    generate_word_ass,
    get_subtitle_preset,
)

# ==============================================================================
# 0. SETUP MÔI TRƯỜNG
# ==============================================================================
if "FONTCONFIG_FILE" in os.environ: del os.environ["FONTCONFIG_FILE"]
if "FONTCONFIG_PATH" in os.environ: del os.environ["FONTCONFIG_PATH"]

try:
    import streamlit as st
except ImportError:
    class MockSt:
        def info(self, msg): print(f"[INFO] {msg}")
        def error(self, msg): print(f"[ERROR] {msg}")
        def success(self, msg): print(f"[SUCCESS] {msg}")
    st = MockSt()

logging.getLogger('streamlit').setLevel(logging.ERROR)

# ==============================================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN
# ==============================================================================
CURRENT_FILE_PATH = os.path.abspath(__file__)
MODULES_DIR = os.path.dirname(CURRENT_FILE_PATH)
SHARED_DIR = os.path.dirname(MODULES_DIR)
PROJECT_ROOT = os.path.dirname(SHARED_DIR)

ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
TEMP_REMIX_DIR = os.path.join(ASSETS_DIR, "temp_remix")
FRAME_DIR = os.path.join(ASSETS_DIR, "frame")
LOGO_DIR = os.path.join(ASSETS_DIR, "logo")
FONT_DIR = os.path.join(ASSETS_DIR, "font")
TARGET_VIDEO_FOLDER = os.path.join(os.path.expanduser("~"), "Videos")
RENDER_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "render_config.json")
FFMPEG_BINARY = resolve_ffmpeg_binary()
FFPROBE_BINARY = resolve_ffprobe_binary()
TIKTOK_KARAOKE_SUBTITLES_ENABLED = False

for d in [TARGET_VIDEO_FOLDER, TEMP_REMIX_DIR, FRAME_DIR, LOGO_DIR, FONT_DIR]:
    os.makedirs(d, exist_ok=True)

# ==============================================================================
# 2. CÁC HÀM HỖ TRỢ (UTILS)
# ==============================================================================
def download_or_copy_file(source, save_path):
    try:
        if not source: return False
        source = str(source).strip()
        if os.path.exists(source):
            shutil.copy2(source, save_path)
            return True
        if source.startswith("http"):
            res = requests.get(source, stream=True, timeout=30)
            if res.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in res.iter_content(chunk_size=8192): f.write(chunk)
                return True
        return False
    except Exception as e:
        print(f"⚠️ Load Error ({source}): {e}")
    return False

def get_media_duration(file_path):
    """Lấy thời lượng chính xác của file media (video/audio)"""
    try:
        if not os.path.exists(file_path): return 0.0
        probe = ffmpeg.probe(file_path, cmd=FFPROBE_BINARY)
        return float(probe['format']['duration'])
    except: return 0.0


def _record_render_failure(output_filename, command, stderr, temp_dir, error_type="FFmpegError"):
    """Persist the real FFmpeg failure before the worker cleans its temp dir."""
    try:
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stderr = str(stderr or "").strip()
        command_text = json.dumps(
            [str(item) for item in (command or [])],
            ensure_ascii=False,
        )
        report = (
            f"error_type={error_type}\n"
            f"output={output_filename}\n"
            f"temp_dir={temp_dir}\n"
            f"command={command_text}\n"
            f"stderr={stderr}\n"
        )
        local_report = os.path.join(temp_dir or os.getcwd(), "render_errors.log")
        with open(local_report, "a", encoding="utf-8") as file:
            file.write(report + "\n")

        persistent_dir = os.path.join(PROJECT_ROOT, "data", "render_failures")
        os.makedirs(persistent_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_name = os.path.splitext(os.path.basename(str(output_filename)))[0]
        persistent_report = os.path.join(
            persistent_dir, f"{stamp}_{safe_name}.log"
        )
        with open(persistent_report, "w", encoding="utf-8") as file:
            file.write(report)
        return persistent_report
    except Exception as record_error:
        print(f"   ⚠️ Không lưu được render diagnostic: {record_error}")
        return ""

def normalize_url(url):
    if not url: return ""
    return str(url).lower().replace("https://", "").replace("http://", "").replace("www.", "").strip().rstrip('/')

def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "y", "có", "co"}:
        return True
    if normalized in {"0", "false", "no", "off", "n", "không", "khong"}:
        return False
    return default

def _tiktok_karaoke_enabled(_settings=None):
    """Hard policy: source TikTok never receives generated karaoke captions."""
    return TIKTOK_KARAOKE_SUBTITLES_ENABLED

# ==============================================================================
# LOGIC TÌM CONFIG MẶC ĐỊNH (BASE CONFIG)
# ==============================================================================
def load_render_config(target_channel_url=None, target_tiktok_id=None):
    default_config = {
        "channel_url": "Default",
        # TikTok sources in this project are operator-approved.  The old
        # temporal detector mistakes static people/backgrounds and the
        # channel's own frame for source watermarks, then delogo creates
        # visible rectangular smears.  Keep removal opt-in per channel.
        "remove_source_watermark": False,
        "title_settings": {"source_start": 0, "zoom_factor": 1.4, "manual_x_offset": "center", "manual_y_offset": "center", "fill_mode": "auto"},
        "content_settings": {"source_start": 5.0, "zoom_factor": 1.1, "manual_x_offset": 0, "manual_y_offset": 0, "fill_mode": "auto"},
        "text_overlay_settings": {"font_filename": "arialbd.ttf", "font_size": 50, "text_color": "#FFFFFF", "stroke_width": 2, "box_width_percentage": 0.85, "box_y_start": 0.70, "box_x_offset": 0, "position_mode": "manual"},
        "text_content_settings": {"font_filename": "arialbd.ttf", "font_size": 45, "text_color": "#FFFFFF", "stroke_width": 2, "box_width_percentage": 0.85, "box_y_start": 0.78, "box_x_offset": 0, "position_mode": "manual"},
        # ASS MarginV is measured upward from the bottom edge.  320px is the
        # lowest position that still clears TikTok's bottom caption area.
        "subtitle_settings": {
            # Source TikTok already contains the visual context. Karaoke is
            # hard-disabled; article rendering uses a separate pipeline.
            "enabled": False,
            "margin_v": 320,
            "font_size": 52,
            "adaptive_long_caption": False,
            "position_mode": "manual",
        },
        "assets": {
            "title_logo_width_percentage": 0.14, "title_logo_x": "main_w-overlay_w-30", "title_logo_y": "30",
            "content_logo_width_percentage": 0.14, "content_logo_x": "main_w-overlay_w-30", "content_logo_y": "30"
        }
    }

    if os.path.exists(RENDER_CONFIG_PATH):
        try:
            with open(RENDER_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            selected_config = None
            if isinstance(data, list):
                if target_channel_url:
                    clean_target_url = normalize_url(target_channel_url)
                    if target_tiktok_id:
                        for cfg in data:
                            cfg_url = normalize_url(cfg.get("channel_url", ""))
                            cfg_id = cfg.get("tiktok_id")
                            if (clean_target_url in cfg_url or cfg_url in clean_target_url) and cfg_id == target_tiktok_id:
                                selected_config = cfg; break

                    if not selected_config:
                        for cfg in data:
                            cfg_url = normalize_url(cfg.get("channel_url", ""))
                            if (clean_target_url in cfg_url or cfg_url in clean_target_url) and not cfg.get("tiktok_id"):
                                selected_config = cfg; break

                    if not selected_config:
                        for cfg in data:
                            cfg_url = normalize_url(cfg.get("channel_url", ""))
                            if clean_target_url in cfg_url or cfg_url in clean_target_url:
                                selected_config = cfg; break

                if not selected_config and len(data) > 0: selected_config = data[0]

            elif isinstance(data, dict): selected_config = data

            if selected_config:
                for key in ["title_settings", "content_settings", "assets", "text_overlay_settings", "text_content_settings", "subtitle_settings"]:
                    if key in selected_config: default_config[key].update(selected_config[key])

        except Exception as e: print(f"⚠️ Lỗi đọc config: {e}")

    return default_config

def render_segment_to_file(video_filename, audio_filename, output_filename, settings, text_settings, text_content, frame_filename, logo_filename, logo_settings, temp_dir, tone="Trung tính", blur_background=False, logo_regions=None, _allow_fallback=True):
    if not os.path.exists(video_filename): return False
    if not os.path.exists(audio_filename): return False

    print(f"   ⚙️ Rendering segment: {output_filename}")

    # 1. Lấy thông số thời gian
    total_video_duration = get_media_duration(video_filename)

    s_start = float(settings.get("source_start", 0))
    if s_start < 0 and total_video_duration > 0:
        s_start = total_video_duration + s_start
        if s_start < 0: s_start = 0.0
        
    if total_video_duration > 0 and s_start >= total_video_duration:
        s_start = s_start % total_video_duration

    raw_end = settings.get("source_end", "auto")
    real_end = None
    if raw_end != "auto" and raw_end is not None:
        val = float(raw_end)
        if val < 0:
            real_end = total_video_duration + val
        else:
            real_end = val
        if real_end <= s_start: 
            real_end = None

    audio_start = max(0.0, float(settings.get("audio_start", 0) or 0))
    audio_end_raw = settings.get("audio_end")
    audio_end = float(audio_end_raw) if audio_end_raw is not None else None
    duration_override = float(settings.get("duration_override", 0) or 0)

    if duration_override > 0:
        duration_audio = duration_override
        real_end = s_start + duration_override
    elif audio_filename == video_filename:
        duration_audio = (real_end - s_start) if real_end else (total_video_duration - s_start)
        if duration_audio <= 0: duration_audio = 5.0
    elif audio_end is not None and audio_end > audio_start:
        duration_audio = audio_end - audio_start
    else:
        duration_audio = get_media_duration(audio_filename)

    font_file_clean = "font.ttf"
    if not os.path.exists(font_file_clean):
        if sys.platform == "win32": font_file_clean = "C\\:/Windows/Fonts/arial.ttf"
        else:
            linux_fonts = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
            for f in linux_fonts:
                if os.path.exists(f): font_file_clean = f; break

    zoom = float(settings.get("zoom_factor", 1.0))
    raw_grade = dict(settings.get("_color_grade") or {})
    if raw_grade.get("name") and not raw_grade.get("grading_preset"):
        raw_grade["grading_preset"] = raw_grade["name"]
    color_grade = resolve_color_grade(video_style=raw_grade)

    v_in = ffmpeg.input(video_filename).video
    a_in = ffmpeg.input(audio_filename).audio
    
    if audio_filename == video_filename:
        if real_end:
            a_in = a_in.filter('atrim', start=s_start, end=real_end)
        else:
            a_in = a_in.filter('atrim', start=s_start)
        a_in = a_in.filter('asetpts', 'PTS-STARTPTS')
    elif audio_start > 0 or audio_end is not None:
        trim_kwargs = {"start": audio_start}
        if audio_end is not None and audio_end > audio_start:
            trim_kwargs["end"] = audio_end
        a_in = a_in.filter("atrim", **trim_kwargs).filter("asetpts", "PTS-STARTPTS")

    if real_end:
        v = v_in.filter('trim', start=s_start, end=real_end)
    else:
        v = v_in.filter('trim', start=s_start)

    v = v.filter('setpts', 'PTS-STARTPTS')
    v = v.filter('loop', loop=-1, size=32767, start=0)

    # ═══ LÀM MỜ LOGO THEO VÙNG PHÁT HIỆN THẬT (không dùng tọa độ cố định) ═══
    # Keep dimensions available even when no watermark is detected.  The
    # fill-mode decision below still needs the source aspect ratio in that
    # normal case.
    w_orig, h_orig = 1080, 1920
    if logo_regions:
        try:
            # Lấy kích thước video gốc để quy đổi tọa độ (logo_regions ở hệ 1080x1920)
            try:
                probe = ffmpeg.probe(video_filename, cmd=FFPROBE_BINARY)
                vs = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
                w_orig = int(vs['width'])
                h_orig = int(vs['height'])
            except Exception:
                w_orig, h_orig = 1080, 1920

            scale_x = w_orig / 1080
            scale_y = h_orig / 1920

            for (rx, ry, rw, rh) in logo_regions:
                # Detector coordinates are normalized to 1080x1920, while
                # downloaded TikTok sources can be 576x1024 (or any other
                # size).  Clamp both origin and extent with a two-pixel
                # safety margin; FFmpeg rejects even a one-pixel overflow at
                # filter-graph configuration time.
                bx = int(float(rx) * scale_x)
                by = int(float(ry) * scale_y)
                bw = int(float(rw) * scale_x)
                bh = int(float(rh) * scale_y)
                if w_orig < 2 or h_orig < 2:
                    continue
                # FFmpeg's delogo also requires a small border around the
                # rectangle; x=0/y=0 or a rectangle ending exactly at iw/ih
                # is rejected as "outside of the frame".
                edge_margin = 2
                bx = max(edge_margin, min(bx, w_orig - edge_margin - 2))
                by = max(edge_margin, min(by, h_orig - edge_margin - 2))
                bw = max(2, min(bw, w_orig - bx - edge_margin))
                bh = max(2, min(bh, h_orig - by - edge_margin))
                if bx + bw + edge_margin > w_orig:
                    bw = w_orig - bx - edge_margin
                if by + bh + edge_margin > h_orig:
                    bh = h_orig - by - edge_margin
                if bw >= 2 and bh >= 2:
                    v = v.filter('delogo', x=bx, y=by, w=bw, h=bh)
        except Exception as _le:
            print(f"   ⚠️ Lỗi auto-blur logo: {_le}")

    target_w = 1080
    scaled_w = int(target_w * zoom)
    if scaled_w % 2 != 0: scaled_w += 1

    raw_x = settings.get("manual_x_offset", "center")
    if str(raw_x).lower() == "center":
        x_expr = '(W-w)/2'
    else:
        try:
            val_x = float(raw_x)
            x_expr = f'(W-w)/2 + ({val_x})'
        except: x_expr = '(W-w)/2'

    raw_y = settings.get("manual_y_offset", "center")
    if str(raw_y).lower() == "center":
        y_expr = '(H-h)/2'
    else:
        try:
            val_y = float(raw_y)
            y_expr = f'(H-h)/2 + ({val_y})'
        except: y_expr = '(H-h)/2'

    fill_mode = str(settings.get("fill_mode", "auto") or "auto").strip().lower()
    if fill_mode == "blur" or (
        fill_mode == "auto" and w_orig > 0 and h_orig > 0 and w_orig / h_orig > 1.20
    ):
        blur_background = True

    if blur_background:
        v_split = v.split()
        v_main = v_split[0]
        v_bg = v_split[1]
        
        bg = v_bg.filter('scale', 1080, 1920, force_original_aspect_ratio='increase').filter('crop', 1080, 1920).filter('boxblur', luma_radius=40, luma_power=2)
        
        v_main = v_main.filter('scale', width=scaled_w, height=-2)
        v_main = v_main.filter(
            'eq',
            contrast=color_grade.contrast,
            brightness=color_grade.brightness,
            saturation=color_grade.saturation,
        )
        if color_grade.sharpen > 0:
            v_main = v_main.filter(
                'unsharp',
                luma_msize_x=5,
                luma_msize_y=5,
                luma_amount=color_grade.sharpen,
            )
        
        v = ffmpeg.overlay(bg, v_main, x=x_expr, y=y_expr, shortest=1)
    else:
        v = v.filter('scale', width=scaled_w, height=-2)
        v = v.filter(
            'eq',
            contrast=color_grade.contrast,
            brightness=color_grade.brightness,
            saturation=color_grade.saturation,
        )
        if color_grade.sharpen > 0:
            v = v.filter(
                'unsharp',
                luma_msize_x=5,
                luma_msize_y=5,
                luma_amount=color_grade.sharpen,
            )
        bg = ffmpeg.input(f'color=c=black:s=1080x1920:d={duration_audio}', f='lavfi')
        v = ffmpeg.overlay(bg, v, x=x_expr, y=y_expr, shortest=1)

    if frame_filename and os.path.exists(frame_filename):
        fr = ffmpeg.input(frame_filename).filter('scale', 1080, 1920)
        v = ffmpeg.overlay(v, fr)

    if logo_filename and os.path.exists(logo_filename):
        pct = float(logo_settings.get("width_percentage", 0.14))
        lx = str(logo_settings.get("x", "main_w-overlay_w-30"))
        ly = str(logo_settings.get("y", "30"))
        logo = ffmpeg.input(logo_filename)
        if pct > 0:
            lw = int(1080 * pct)
            logo = logo.filter('scale', lw, -1)
        v = ffmpeg.overlay(v, logo, x=lx, y=ly)

    # Thêm Text
    if text_content:
        t_color = text_settings.get("text_color", "#FFFFFF").replace("#", "0x")
        f_size = int(text_settings.get("font_size", 60))
        border_w = int(text_settings.get("stroke_width", 2))
        box_w_pct = float(text_settings.get("box_width_percentage", 0.85))
        y_start_pct = float(text_settings.get("box_y_start", 0.7))
        x_offset = int(float(text_settings.get("box_x_offset", 0) or 0))
        manual_text_position = (
            str(text_settings.get("position_mode", "manual")).strip().lower()
            == "manual"
        )
        max_text_width = int(1080 * box_w_pct)
        preferred_x = int((1080 - max_text_width) / 2) + x_offset
        safe_text = str(text_content).replace("'", "").replace(":", "").replace("%", "").strip().upper()
        layout = plan_text_layout(
            safe_text,
            font_size=f_size,
            preferred_x=preferred_x,
            preferred_y=int(1920 * y_start_pct),
            max_width=max_text_width,
            clamp_to_safe_zone=not manual_text_position,
            allow_extra_lines=True,
        )
        print(
            "   📍 Title layout: "
            f"mode={'manual' if manual_text_position else 'safe-zone'} "
            f"x={layout.x}px y={layout.y}px font={layout.font_size}px"
        )
        if layout.font_size != f_size:
            print(
                "   🧩 Auto-fit text: "
                f"{f_size}px → {layout.font_size}px trước khi tự xuống dòng."
            )

        for i, line in enumerate(layout.lines):
            current_line_y = layout.y + (i * layout.line_spacing)
            v = v.drawtext(
                text=line, fontfile=font_file_clean, fontsize=layout.font_size,
                fontcolor=t_color, borderw=border_w, bordercolor="black",
                shadowcolor="black", shadowx=2, shadowy=2,
                x=str(layout.x), y=str(current_line_y), fix_bounds=True
            )
    # Intermediate giữ audio lossless. Loudness, BGM và SFX chỉ xử lý một lần
    # trong lần encode final sau khi concat.
    a_out = (
        a_in
        .filter('aresample', 48000)
        .filter('aformat', sample_rates=48000, channel_layouts='stereo')
    )

    render_command = []
    try:
        render_graph = ffmpeg.output(
            v,
            a_out,
            output_filename,
            t=duration_audio,
            r=30,
            fps_mode='cfr',
            vcodec='libx264',
            preset='fast',
            crf=0,
            pix_fmt='yuv420p',
            g=60,
            keyint_min=60,
            acodec='flac',
            ar=48000,
            ac=2,
            format='matroska',
            map_metadata=-1,
        ).overwrite_output()
        render_command = ffmpeg.compile(
            render_graph, cmd=FFMPEG_BINARY, overwrite_output=True
        )
        render_graph.run(
            cmd=FFMPEG_BINARY,
            capture_stdout=True,
            capture_stderr=True,
        )
        return True
    except Exception as e:
        raw_stderr = getattr(e, "stderr", "") or ""
        stderr = (
            raw_stderr.decode("utf-8", errors="replace")
            if isinstance(raw_stderr, bytes)
            else str(raw_stderr)
        )
        if not stderr:
            stderr = str(e)
        report_path = _record_render_failure(
            output_filename,
            render_command,
            stderr,
            temp_dir,
            error_type=type(e).__name__,
        )
        print(f"❌ FFmpeg Log ({os.path.basename(str(output_filename))}):\n{stderr[-2000:]}")
        if report_path:
            print(f"   🧾 Render diagnostic: {report_path}")
        if _allow_fallback:
            # A bad watermark rectangle, frame asset or drawtext filter should
            # not discard an otherwise usable source video. Retry with the
            # source video + generated voice only, preserving the same timing.
            print("   🔁 Retry render an toàn: bỏ logo/frame/text lỗi...")
            try:
                if os.path.exists(output_filename):
                    os.remove(output_filename)
            except OSError:
                pass
            fallback_settings = dict(settings or {})
            fallback_settings["fill_mode"] = "black"
            fallback_settings["zoom_factor"] = 1.0
            fallback_settings["manual_x_offset"] = "center"
            fallback_settings["manual_y_offset"] = "center"
            return render_segment_to_file(
                video_filename,
                audio_filename,
                output_filename,
                fallback_settings,
                {},
                None,
                None,
                None,
                {},
                temp_dir,
                tone=tone,
                blur_background=False,
                logo_regions=None,
                _allow_fallback=False,
            )
        return False

def create_video_from_source_video(
        audio_url, source_video_url, resolution_tuple=(1080, 1920),
        output_filename=None,
        title_frame_path=None, content_frame_path=None,
        title_tiktok=None, content_text=None,
        title_logo_path=None, content_logo_path=None, title_audio_url=None, script_url=None,
        row_index=None,
        target_channel_url=None,
        tiktok_id=None,
        override_config=None,
        temp_dir=None,
        tone="Trung tính",
        music_mood=None,
        music_energy=2,
        is_sensitive=False,
        beats=None,
        script_text="",
        subtitle_style="keyword_highlight",
        have_frame=False,
        frame_end_sec=None,
        **kwargs
):
    unique_session_id = str(uuid.uuid4())[:8]
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not output_filename: output_filename = f"remix_{timestamp_str}_{unique_session_id}.mp4"

    if temp_dir:
        working_dir = os.path.join(temp_dir, f"remix_{unique_session_id}")
    else:
        working_dir = os.path.join(TEMP_REMIX_DIR, f"task_{timestamp_str}_{unique_session_id}")

    os.makedirs(working_dir, exist_ok=True)
    original_cwd = os.getcwd()
    final_path = os.path.join(TARGET_VIDEO_FOLDER, output_filename)
    try:
        p_vid_name = f"vid_{unique_session_id}.mp4"
        p_aud_main_name = f"aud_main_{unique_session_id}.mp3"
        p_aud_title_name = f"aud_title_{unique_session_id}.mp3"

        if not download_or_copy_file(source_video_url, os.path.join(working_dir, p_vid_name)):
            raise Exception("Không thể tải Video gốc.")
        if not audio_url: raise Exception("Link Audio Content bị rỗng.")
        if not download_or_copy_file(audio_url, os.path.join(working_dir, p_aud_main_name)):
            raise Exception("Không thể tải Audio Content.")
        has_intro = False
        if title_audio_url:
            if download_or_copy_file(title_audio_url, os.path.join(working_dir, p_aud_title_name)):
                has_intro = True
        intro_duration = get_media_duration(
            os.path.join(working_dir, p_aud_title_name)
        ) if has_intro else 0.0
        body_duration = get_media_duration(os.path.join(working_dir, p_aud_main_name))
        timeline = plan_beat_timeline(
            beats,
            total_duration=max(0.1, intro_duration + body_duration),
            hook_duration=intro_duration,
            media_count=1,
            hook_text=title_tiktok or content_text or "",
            script_text=script_text or content_text or "",
        )
        # Intro text must match the title audio exactly.  Beat #1's compact
        # ``on_screen_text`` is reserved for content overlays.
        title_tiktok = resolve_intro_overlay_text(title_tiktok, timeline)
        print(
            f"🧭 Beat timeline: {len(timeline.segments)} beats / "
            f"{timeline.total_duration:.2f}s | first frame: {title_tiktok}"
        )
        cfg = load_render_config(target_channel_url, target_tiktok_id=tiktok_id)
        music = select_music(
            music_mood,
            tone=tone,
            energy=music_energy,
            is_sensitive=is_sensitive,
            channel_id=tiktok_id,
        )
        if music:
            print(
                f"🎵 BGM đã chọn: {os.path.basename(music.path)} | "
                f"mood={music.mood} | energy={music.energy} | bed={music.bed_lufs:.1f} LUFS"
            )
            if music.license_status != "approved":
                print("⚠️ BGM hiện tại chưa có metadata giấy phép approved trong catalog.json")
        else:
            print(f"⚠️ Không có BGM phù hợp cho mood={music_mood or tone}; giữ voice-only an toàn")

        if override_config and isinstance(override_config, dict):
            sections = ["title_settings", "content_settings", "text_overlay_settings", "text_content_settings", "subtitle_settings", "assets"]
            for section in sections:
                if section in override_config:
                    if section not in cfg: cfg[section] = {}
                    cfg[section].update(override_config[section])
            if "remove_source_watermark" in override_config:
                remove_value = override_config.get("remove_source_watermark")
                cfg["remove_source_watermark"] = _as_bool(remove_value)
        color_grade = resolve_color_grade(
            tiktok_id or "",
            tone=tone,
            is_sensitive=is_sensitive,
        )
        cfg["title_settings"]["_color_grade"] = color_grade.to_dict()
        cfg["content_settings"]["_color_grade"] = color_grade.to_dict()
        print(f"🎨 Color grade: {color_grade.name}")
        assets = cfg.get("assets", {})

        def find_asset_src(arg, key, default_folder):
            if arg:
                if os.path.exists(arg): return arg
                filename = os.path.basename(arg)
                p = os.path.join(default_folder, filename)
                if os.path.exists(p): return p
            val = assets.get(key)
            if val:
                if os.path.exists(val): return val
                p = os.path.join(default_folder, val)
                if os.path.exists(p): return p
            return None

        src_t_frame = find_asset_src(title_frame_path, "title_frame_filename", FRAME_DIR)
        src_c_frame = find_asset_src(content_frame_path, "content_frame_filename", FRAME_DIR)
        src_t_logo = find_asset_src(title_logo_path, "title_logo_filename", LOGO_DIR)
        src_c_logo = find_asset_src(content_logo_path, "content_logo_filename", LOGO_DIR)
        src_font_name = cfg["text_content_settings"].get("font_filename", "arialbd.ttf")

        # B3. Copy Assets
        local_t_frame_name = f"frame_intro_{unique_session_id}.png" if src_t_frame else None
        if src_t_frame: shutil.copy2(src_t_frame, os.path.join(working_dir, local_t_frame_name))

        local_c_frame_name = f"frame_content_{unique_session_id}.png" if src_c_frame else None
        if src_c_frame: shutil.copy2(src_c_frame, os.path.join(working_dir, local_c_frame_name))

        local_t_logo_name = f"logo_intro_{unique_session_id}.png" if src_t_logo else None
        if src_t_logo: shutil.copy2(src_t_logo, os.path.join(working_dir, local_t_logo_name))

        local_c_logo_name = f"logo_content_{unique_session_id}.png" if src_c_logo else None
        if src_c_logo: shutil.copy2(src_c_logo, os.path.join(working_dir, local_c_logo_name))

        font_src_path = None
        possible_fonts = [
            os.path.join(FONT_DIR, src_font_name),
            os.path.join(PROJECT_ROOT, "config", src_font_name),
            os.path.join(working_dir, "font.ttf")
        ]
        if sys.platform == "win32":
            possible_fonts.extend([
                os.path.join("C:\\Windows\\Fonts", src_font_name),
                os.path.join("C:\\Windows\\Fonts", "arial.ttf")
            ])
        else:
            possible_fonts.extend([
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
            ])

        for p in possible_fonts:
            if os.path.exists(p): font_src_path = p; break
        if font_src_path: shutil.copy2(font_src_path, os.path.join(working_dir, "font.ttf"))

        os.chdir(working_dir)

        logo_regions = []
        if cfg.get("remove_source_watermark", False):
            try:
                from shared.modules.logo_detector import detect_logo_regions
                logo_regions = detect_logo_regions(p_vid_name)
                if logo_regions:
                    print(
                        f"🔍 Phát hiện {len(logo_regions)} vùng logo trong "
                        "video nguồn → tự động delogo"
                    )
            except Exception as _le:
                print(f"⚠️ Logo detection lỗi: {_le}")
        else:
            print(
                "ℹ️ Không auto-delogo nguồn TikTok: tránh nhận nhầm vùng ảnh "
                "tĩnh/frame thành watermark."
            )

        title_logo_settings = {
            "width_percentage": assets.get("title_logo_width_percentage", assets.get("logo_width_percentage", 0.14)),
            "x": assets.get("title_logo_x", "main_w-overlay_w-30"),
            "y": assets.get("title_logo_y", "30")
        }
        content_logo_settings = {
            "width_percentage": assets.get("content_logo_width_percentage", assets.get("logo_width_percentage", 0.14)),
            "x": assets.get("content_logo_x", "main_w-overlay_w-30"),
            "y": assets.get("content_logo_y", "30")
        }

        edit_mode = cfg.get("edit_mode", "Có Frame Full (Tiktok)")
        if override_config and "edit_mode" in override_config:
            edit_mode = override_config["edit_mode"]
        uses_original_audio = edit_mode == "Frame Intro + Gốc (Giống FB)"
        persistent_title = str(title_tiktok or content_text or "").strip()

        # Facebook-style dynamic frame handling for TikTok. A logo/watermark
        # alone is not a frame; this branch is entered only when the AI says
        # that an actual competitor frame/template exists.
        frame_transition_mode = False
        frame_only_mode = False
        cut_time = None
        source_duration = get_media_duration(p_vid_name)
        if have_frame and source_duration > 0 and local_t_frame_name:
            raw_end = None
            if frame_end_sec not in (None, ""):
                try:
                    raw_end = float(frame_end_sec)
                except (TypeError, ValueError):
                    raw_end = None
                if raw_end is not None and (raw_end < 0 or raw_end != raw_end):
                    raw_end = None

            # null/invalid means we cannot safely locate the end of the
            # competitor frame, so keep the brand frame for the whole output.
            if raw_end is None:
                frame_only_mode = True
                print(
                    "🖼️ TikTok have_frame=true nhưng không có mốc hợp lệ "
                    "→ frame thương hiệu xuyên suốt"
                )
            else:
                cut_time = min(source_duration, raw_end + 1.0)
                print(
                    f"🧭 TikTok mốc frame AI={raw_end:.3f}s, "
                    f"cắt sau +1s={cut_time:.3f}s/{source_duration:.3f}s"
                )
                if cut_time >= source_duration * (2 / 3):
                    frame_only_mode = True
                    print(
                        "🖼️ TikTok mốc cắt từ 2/3 trở đi "
                        "→ frame thương hiệu xuyên suốt"
                    )
                elif has_intro and cut_time < source_duration:
                    frame_transition_mode = True
                    print(
                        "✂️ TikTok mốc cắt trước 2/3 "
                        "→ intro frame + body video gốc sau mốc"
                    )
                else:
                    print(
                        "⚠️ TikTok không có Hook audio hoặc mốc nằm ngoài video "
                        "→ giữ renderer hiện tại"
                    )

        special_frame_mode = frame_transition_mode or frame_only_mode
        if special_frame_mode:
            # These two branches deliberately use Hook + Script or original
            # source audio only; no TikTok BGM/SFX/karaoke is added.
            music = None

        segs = []
        if frame_only_mode:
            # Merge Hook + Script once, then render one static brand-frame
            # segment for the complete voice duration.
            frame_audio_name = f"frame_audio_{unique_session_id}.wav"
            frame_audio_path = os.path.join(working_dir, frame_audio_name)
            if has_intro and os.path.exists(p_aud_main_name):
                merge_cmd = [
                    FFMPEG_BINARY, "-y",
                    "-i", p_aud_title_name,
                    "-i", p_aud_main_name,
                    "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[aout]",
                    "-map", "[aout]", frame_audio_path,
                ]
                merge_result = subprocess.run(
                    merge_cmd, capture_output=True, text=True
                )
                if merge_result.returncode != 0:
                    raise Exception(
                        "Không thể nối Hook + Script cho nhánh frame xuyên suốt: "
                        f"{merge_result.stderr[-800:]}"
                    )
            elif os.path.exists(p_aud_main_name):
                shutil.copy2(p_aud_main_name, frame_audio_path)
            else:
                raise Exception("Thiếu audio cho nhánh frame xuyên suốt TikTok.")

            out = f"seg_frame_only_{unique_session_id}.mkv"
            frame_settings = cfg["title_settings"].copy()
            frame_settings["source_start"] = 0
            frame_settings["source_end"] = "auto"
            frame_settings.pop("duration_override", None)
            if render_segment_to_file(
                p_vid_name,
                frame_audio_path,
                out,
                frame_settings,
                cfg["text_overlay_settings"],
                title_tiktok,
                local_t_frame_name,
                local_t_logo_name,
                title_logo_settings,
                working_dir,
                tone,
                logo_regions=logo_regions,
            ):
                segs.append(out)
            else:
                raise Exception("Render frame thương hiệu xuyên suốt thất bại")

        elif frame_transition_mode:
            # Intro: brand frame + Hook. Body: source video/audio from the
            # dynamic cut point to the real end, without frame or text.
            out = f"seg_frame_intro_{unique_session_id}.mkv"
            if render_segment_to_file(
                p_vid_name,
                p_aud_title_name,
                out,
                cfg["title_settings"],
                cfg["text_overlay_settings"],
                title_tiktok,
                local_t_frame_name,
                local_t_logo_name,
                title_logo_settings,
                working_dir,
                tone,
                logo_regions=logo_regions,
            ):
                segs.append(out)
            else:
                raise Exception("Render TikTok Hook + frame thất bại")

            body_settings = cfg["content_settings"].copy()
            body_settings.update({
                "source_start": cut_time,
                "source_end": source_duration,
                "audio_start": 0,
                "audio_end": None,
                "duration_override": max(0.1, source_duration - cut_time),
            })
            body_out = f"seg_original_tail_{unique_session_id}.mkv"
            if render_segment_to_file(
                p_vid_name,
                p_vid_name,
                body_out,
                body_settings,
                {},
                None,
                None,
                None,
                {},
                working_dir,
                tone,
                blur_background=True,
                logo_regions=logo_regions,
            ):
                segs.append(body_out)
            else:
                raise Exception("Render TikTok video gốc sau mốc cắt thất bại")

        elif uses_original_audio:
            if has_intro:
                out = f"seg1_{unique_session_id}.mkv"
                if render_segment_to_file(p_vid_name, p_aud_title_name, out, cfg["title_settings"], cfg["text_overlay_settings"], title_tiktok, local_t_frame_name, local_t_logo_name, title_logo_settings, working_dir, tone, logo_regions=logo_regions):
                    segs.append(out)

            # Tính thời gian đoạn gốc
            intro_start = float(cfg["title_settings"].get("source_start", 0))

            content_settings_goc = cfg["content_settings"].copy()
            content_settings_goc["source_start"] = intro_start + intro_duration

            out2 = f"seg2_{unique_session_id}.mkv"
            if render_segment_to_file(
                p_vid_name,
                p_vid_name,
                out2,
                content_settings_goc,
                cfg["text_content_settings"],
                persistent_title,
                None,
                None,
                {},
                working_dir,
                tone,
                blur_background=True,
                logo_regions=logo_regions,
            ):
                segs.append(out2)
            else:
                raise Exception("Render Content Gốc Failed")
        else:
            if has_intro:
                out = f"seg1_{unique_session_id}.mkv"
                if render_segment_to_file(p_vid_name, p_aud_title_name, out, cfg["title_settings"], cfg["text_overlay_settings"], title_tiktok, local_t_frame_name, local_t_logo_name, title_logo_settings, working_dir, tone, logo_regions=logo_regions):
                    segs.append(out)
            if not os.path.exists(p_aud_main_name): raise Exception("Mất file aud_main.mp3")
            base_source_start = float(cfg["content_settings"].get("source_start", 0) or 0)
            body_segments = []
            for segment in timeline.segments:
                body_start = max(intro_duration, segment.start)
                body_end = min(timeline.total_duration, segment.end)
                if body_end - body_start <= 0.05:
                    continue
                body_segments.append((segment, body_start, body_end))

            for beat_index, (segment, body_start, body_end) in enumerate(body_segments):
                relative_start = max(0.0, body_start - intro_duration)
                relative_end = max(relative_start, body_end - intro_duration)
                beat_settings = cfg["content_settings"].copy()
                beat_settings.update({
                    "source_start": base_source_start + relative_start,
                    "source_end": base_source_start + relative_end,
                    "audio_start": relative_start,
                    "audio_end": relative_end,
                    "duration_override": relative_end - relative_start,
                    "motion": segment.motion,
                    "transition": segment.transition,
                })
                out2 = f"seg_body_{beat_index}_{unique_session_id}.mkv"
                if render_segment_to_file(
                    p_vid_name,
                    p_aud_main_name,
                    out2,
                    beat_settings,
                    cfg["text_content_settings"],
                    persistent_title,
                    local_c_frame_name,
                    local_c_logo_name,
                    content_logo_settings,
                    working_dir,
                    tone,
                    logo_regions=logo_regions,
                ):
                    segs.append(out2)
                else:
                    diagnostic = ""
                    diagnostic_path = os.path.join(working_dir, "render_errors.log")
                    try:
                        if os.path.exists(diagnostic_path):
                            with open(diagnostic_path, "r", encoding="utf-8") as file:
                                diagnostic = file.read()[-1600:]
                    except OSError:
                        pass
                    raise Exception(
                        f"Render Content Beat #{beat_index + 1} Failed"
                        + (f" | {diagnostic}" if diagnostic else "")
                    )

        concat_list_file = f"list_{unique_session_id}.txt"
        concat_out_file = f"concat_{unique_session_id}.mkv"

        if not segs:
            raise Exception("Không có segment hợp lệ để concat")
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for s in segs: f.write(f"file '{s}'\n")

        concat_cmd = [
            FFMPEG_BINARY, "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_file, "-c", "copy", concat_out_file,
        ]
        concat_result = subprocess.run(concat_cmd, capture_output=True, text=True)
        if concat_result.returncode != 0:
            first_concat_report = _record_render_failure(
                concat_out_file,
                concat_cmd,
                concat_result.stderr,
                working_dir,
                error_type="ConcatCopyError",
            )
            print(
                "   🔁 Concat copy thất bại; retry bằng encode tương thích..."
                + (f" Diagnostic: {first_concat_report}" if first_concat_report else "")
            )
            concat_retry_cmd = [
                FFMPEG_BINARY, "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list_file,
                "-c:v", "libx264", "-preset", "fast", "-crf", "0",
                "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "flac", "-ar", "48000", "-ac", "2",
                concat_out_file,
            ]
            concat_result = subprocess.run(
                concat_retry_cmd, capture_output=True, text=True
            )
            if concat_result.returncode != 0:
                retry_report = _record_render_failure(
                    concat_out_file,
                    concat_retry_cmd,
                    concat_result.stderr,
                    working_dir,
                    error_type="ConcatRetryError",
                )
                raise Exception(
                    "Concat thất bại sau retry: "
                    f"{concat_result.stderr[-700:]}"
                    + (f" | diagnostic={retry_report}" if retry_report else "")
                )

        subtitle_path = None
        requested_subtitle_enabled = _as_bool(
            cfg.get("subtitle_settings", {}).get("enabled"),
            default=False,
        )
        # Karaoke của nguồn TikTok bị khóa tắt ở renderer. Cấu hình cũ trên
        # Supabase có enabled=true cũng không được phép ghi đè chính sách này.
        subtitle_enabled = _tiktok_karaoke_enabled(
            cfg.get("subtitle_settings", {})
        )
        if requested_subtitle_enabled and not subtitle_enabled:
            print(
                "⚠️ Bỏ qua subtitle_settings.enabled=true cũ: "
                "karaoke nguồn TikTok đang bị khóa tắt."
            )
        if not subtitle_enabled:
            print("🔇 Subtitle karaoke đã tắt cho video nguồn TikTok.")
        if (
            subtitle_enabled
            and not uses_original_audio
            and not special_frame_mode
            and script_text
            and body_duration > 0
        ):
            subtitle_preset = get_subtitle_preset(
                tiktok_id,
                cfg.get("subtitle_settings", {}),
            )
            manual_subtitle_position = (
                str(subtitle_preset.get("position_mode", "manual"))
                .strip()
                .lower()
                == "manual"
            )
            print(
                "📝 Subtitle: "
                f"margin đáy={subtitle_preset['margin_v']}px "
                f"mode={'manual' if manual_subtitle_position else 'safe-zone'} "
                "(số nhỏ hơn = vị trí thấp hơn)"
            )
            keywords = [
                value
                for segment in timeline.segments
                for value in segment.must_show
                if value
            ]
            if subtitle_style == "normal":
                keywords = []
            subtitle_path = f"subtitle_{unique_session_id}.ass"
            subtitle_path = generate_word_ass(
                p_aud_main_name,
                subtitle_path,
                time_offset=intro_duration,
                words_per_line=subtitle_preset["max_words"],
                font_size=subtitle_preset["font_size"],
                margin_v=subtitle_preset["margin_v"],
                hex_color=subtitle_preset["hex_color"],
                highlight_color=subtitle_preset["highlight_color"],
                keywords=keywords,
                font_name=subtitle_preset["font_name"],
                margin_l=subtitle_preset["margin_l"],
                margin_r=subtitle_preset["margin_r"],
                clamp_to_safe_zone=not manual_subtitle_position,
                adaptive_long_caption=bool(
                    subtitle_preset.get("adaptive_long_caption", False)
                ),
            )
            if not subtitle_path:
                subtitle_path = generate_text_ass(
                    script_text,
                    f"subtitle_{unique_session_id}.ass",
                    duration=body_duration,
                    time_offset=intro_duration,
                    words_per_line=subtitle_preset["max_words"],
                    font_size=subtitle_preset["font_size"],
                    margin_v=subtitle_preset["margin_v"],
                    hex_color=subtitle_preset["hex_color"],
                    highlight_color=subtitle_preset["highlight_color"],
                    keywords=keywords,
                    font_name=subtitle_preset["font_name"],
                    margin_l=subtitle_preset["margin_l"],
                    margin_r=subtitle_preset["margin_r"],
                    clamp_to_safe_zone=not manual_subtitle_position,
                    adaptive_long_caption=bool(
                        subtitle_preset.get("adaptive_long_caption", False)
                    ),
                )
        audio_cues = [] if (uses_original_audio or special_frame_mode) else plan_audio_cues(
            timeline,
            is_sensitive=is_sensitive,
            sfx_dir=os.path.join(ASSETS_DIR, "sfx"),
        )
        duration = get_media_duration(concat_out_file)
        final_inputs = [FFMPEG_BINARY, "-y", "-i", concat_out_file]
        final_filters = []
        video_map = "0:v:0"

        if subtitle_path and os.path.exists(subtitle_path):
            safe_ass_path = os.path.abspath(subtitle_path).replace("\\", "/").replace(":", "\\:")
            safe_fonts_dir = working_dir.replace("\\", "/").replace(":", "\\:")
            final_filters.append(
                f"[0:v]subtitles='{safe_ass_path}':fontsdir='{safe_fonts_dir}'[v_final]"
            )
            video_map = "[v_final]"

        input_index = 1
        if music:
            final_inputs += ["-stream_loop", "-1", "-i", music.path]
            final_filters.append(build_ducked_mix_filter(
                "0:a",
                f"{input_index}:a",
                duration,
                music,
                output_label="a_base",
                label_prefix="remix_music",
            ))
            input_index += 1
        else:
            final_filters.append("[0:a]loudnorm=I=-14:LRA=9:TP=-1.5[a_base]")

        sfx_labels = []
        for cue_index, cue in enumerate(audio_cues):
            final_inputs += ["-i", cue.asset_path]
            label = f"remix_sfx{cue_index}"
            delay_ms = int(cue.timestamp * 1000)
            final_filters.append(
                f"[{input_index}:a]adelay={delay_ms}|{delay_ms},"
                f"volume={cue.gain:.2f}[{label}]"
            )
            sfx_labels.append(label)
            input_index += 1

        audio_map = "[a_base]"
        if sfx_labels:
            final_filters.append(
                f"[a_base]{''.join(f'[{label}]' for label in sfx_labels)}"
                f"amix=inputs={1 + len(sfx_labels)}:duration=first:"
                f"normalize=0,alimiter=limit=0.84[a_mixed]"
            )
            audio_map = "[a_mixed]"
            print(f"🔊 AudioDirector: {len(sfx_labels)} SFX có chủ đích")

        final_filters.append(
            f"{audio_map}aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:"
            "channel_layouts=stereo[a_final]"
        )
        final_cmd = final_inputs + [
            "-filter_complex", ";".join(final_filters),
            "-map", video_map,
            "-map", "[a_final]",
            *final_output_args(),
            "-t", f"{duration:.3f}",
            final_path,
        ]
        final_result = subprocess.run(final_cmd, capture_output=True, text=True)
        if final_result.returncode != 0:
            first_final_report = _record_render_failure(
                final_path,
                final_cmd,
                final_result.stderr,
                working_dir,
                error_type="FinalEncodeError",
            )
            print(
                "   🔁 Final encode thất bại; retry an toàn không "
                "subtitle/BGM/SFX..."
                + (f" Diagnostic: {first_final_report}" if first_final_report else "")
            )
            # The segments already contain the channel frame/text.  If an
            # optional subtitle, BGM or SFX filter is malformed, preserve a
            # usable video with the generated voice instead of discarding it.
            safe_final_cmd = [
                FFMPEG_BINARY, "-y", "-i", concat_out_file,
                "-map", "0:v:0", "-map", "0:a:0",
                *final_output_args(),
                "-t", f"{duration:.3f}",
                final_path,
            ]
            final_result = subprocess.run(
                safe_final_cmd, capture_output=True, text=True
            )
            if final_result.returncode != 0:
                retry_report = _record_render_failure(
                    final_path,
                    safe_final_cmd,
                    final_result.stderr,
                    working_dir,
                    error_type="FinalEncodeRetryError",
                )
                raise Exception(
                    "Final encode thất bại sau retry: "
                    f"{final_result.stderr[-900:]}"
                    + (f" | diagnostic={retry_report}" if retry_report else "")
                )

        if os.path.exists(final_path):
            print(f"✅ DONE: {final_path}")

            watermark_still_present = False
            if logo_regions:
                from shared.modules.logo_detector import verify_watermark_removed
                watermark_still_present = not verify_watermark_removed(final_path, logo_regions)
                if watermark_still_present:
                    print("⚠️ Vẫn phát hiện vùng watermark sau khi blur.")

            persisted_subtitle_path = ""
            if subtitle_path and os.path.exists(subtitle_path):
                persisted_subtitle_path = final_path + ".ass"
                try:
                    shutil.copy2(subtitle_path, persisted_subtitle_path)
                except Exception:
                    persisted_subtitle_path = ""

            return {
                "final_path": final_path,
                "watermark_detected": watermark_still_present,
                "subtitle_ass_path": persisted_subtitle_path,
            }

    except Exception as e:
        print(f"❌ ERROR: {e}")
        print(f"RENDER ERROR: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        return {
            "final_path": "",
            "watermark_detected": False,
            "subtitle_ass_path": "",
            "error": f"{type(e).__name__}: {e}",
        }
    finally:
        os.chdir(original_cwd)
        if 'working_dir' in locals() and os.path.exists(working_dir):
            try: shutil.rmtree(working_dir, ignore_errors=True)
            except: pass

if __name__ == "__main__":
    pass
