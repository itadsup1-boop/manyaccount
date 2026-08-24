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
from shared.core.beat_timeline import plan_beat_timeline
from shared.services.audio_director import plan_audio_cues
from shared.core.video_encoding import (
    final_output_args,
    resolve_color_grade,
)
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
        probe = ffmpeg.probe(file_path)
        return float(probe['format']['duration'])
    except: return 0.0

def normalize_url(url):
    if not url: return ""
    return str(url).lower().replace("https://", "").replace("http://", "").replace("www.", "").strip().rstrip('/')

# ==============================================================================
# LOGIC TÌM CONFIG MẶC ĐỊNH (BASE CONFIG)
# ==============================================================================
def load_render_config(target_channel_url=None, target_tiktok_id=None):
    default_config = {
        "channel_url": "Default",
        "title_settings": {"source_start": 0, "zoom_factor": 1.4, "manual_x_offset": "center", "manual_y_offset": "center"},
        "content_settings": {"source_start": 5.0, "zoom_factor": 1.1, "manual_x_offset": 0, "manual_y_offset": 0},
        "text_overlay_settings": {"font_filename": "arialbd.ttf", "font_size": 60, "text_color": "#FFFFFF", "stroke_width": 2, "box_width_percentage": 0.85, "box_y_start": 0.70},
        "text_content_settings": {"font_filename": "arialbd.ttf", "font_size": 35, "text_color": "#FFFFFF", "stroke_width": 2, "box_width_percentage": 0.85, "box_y_start": 0.15},
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
                for key in ["title_settings", "content_settings", "assets", "text_overlay_settings", "text_content_settings"]:
                    if key in selected_config: default_config[key].update(selected_config[key])

        except Exception as e: print(f"⚠️ Lỗi đọc config: {e}")

    return default_config

def render_segment_to_file(video_filename, audio_filename, output_filename, settings, text_settings, text_content, frame_filename, logo_filename, logo_settings, temp_dir, tone="Trung tính", blur_background=False):
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

    # ═══ LÀM MỜ LOGO BẰNG TỌA ĐỘ CHUẨN (CHỈ GÓC TRÊN BÊN PHẢI) ═══
    try:
        # Lấy kích thước video gốc để map toạ độ chính xác
        try:
            probe = ffmpeg.probe(video_filename)
            vs = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            w_orig = int(vs['width'])
            h_orig = int(vs['height'])
        except:
            w_orig, h_orig = 1080, 1920
        
        # Cấu hình kích thước và vị trí (cho Top-Right)
        w_pct = 0.35  # Rộng 35% màn hình
        h_pct = 0.06  # Cao 6% màn hình
        margin_x = 0.02

        # Góc trên bên phải (Top-Right) - Chuyên che logo 24h.com.vn
        # Yêu cầu: dịch trái tổng cộng 30px, dịch xuống tổng cộng 130px
        tr_x = int(w_orig * (1 - w_pct - margin_x)) - 30
        tr_y = int(h_orig * 0.04) + 130
        tr_w = int(w_orig * w_pct)
        tr_h = int(h_orig * h_pct)

        regions = [(tr_x, tr_y, tr_w, tr_h)]
        
        for (bx, by, bw, bh) in regions:
            if bx + bw > w_orig: bw = w_orig - bx
            if by + bh > h_orig: bh = h_orig - by
            
            if bw > 0 and bh > 0:
                # Sử dụng thuật toán DELOGO nội suy mượt mà (giống y hệt tool Facebook) thay vì blur
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
        max_text_width = int(1080 * box_w_pct)
        safe_text = str(text_content).replace("'", "").replace(":", "").replace("%", "").strip().upper()
        layout = plan_text_layout(
            safe_text,
            font_size=f_size,
            preferred_y=int(1920 * y_start_pct),
            max_width=max_text_width,
        )

        for i, line in enumerate(layout.lines):
            current_line_y = layout.y + (i * layout.line_spacing)
            v = v.drawtext(
                text=line, fontfile=font_file_clean, fontsize=f_size,
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

    try:
        (
            ffmpeg
            .output(
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
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return True
    except ffmpeg.Error as e:
        print(f"❌ FFmpeg Log:\n{e.stderr.decode('utf8')}")
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
        )
        title_tiktok = timeline.first_frame_text or title_tiktok
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
            sections = ["title_settings", "content_settings", "text_overlay_settings", "text_content_settings", "assets"]
            for section in sections:
                if section in override_config:
                    if section not in cfg: cfg[section] = {}
                    cfg[section].update(override_config[section])
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

        segs = []
        if uses_original_audio:
            if has_intro:
                out = f"seg1_{unique_session_id}.mkv"
                if render_segment_to_file(p_vid_name, p_aud_title_name, out, cfg["title_settings"], cfg["text_overlay_settings"], title_tiktok, local_t_frame_name, local_t_logo_name, title_logo_settings, working_dir, tone):
                    segs.append(out)
            
            # Tính thời gian đoạn gốc
            intro_start = float(cfg["title_settings"].get("source_start", 0))
            
            content_settings_goc = cfg["content_settings"].copy()
            content_settings_goc["source_start"] = intro_start + intro_duration
            
            out2 = f"seg2_{unique_session_id}.mkv"
            if render_segment_to_file(p_vid_name, p_vid_name, out2, content_settings_goc, {}, None, None, None, {}, working_dir, tone, blur_background=True):
                segs.append(out2)
            else:
                raise Exception("Render Content Gốc Failed")
        else:
            if has_intro:
                out = f"seg1_{unique_session_id}.mkv"
                if render_segment_to_file(p_vid_name, p_aud_title_name, out, cfg["title_settings"], cfg["text_overlay_settings"], title_tiktok, local_t_frame_name, local_t_logo_name, title_logo_settings, working_dir, tone):
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
                beat_text = segment.on_screen_text or (
                    content_text if timeline.used_fallback and beat_index == 0 else ""
                )
                out2 = f"seg_body_{beat_index}_{unique_session_id}.mkv"
                if render_segment_to_file(
                    p_vid_name,
                    p_aud_main_name,
                    out2,
                    beat_settings,
                    cfg["text_content_settings"],
                    beat_text,
                    local_c_frame_name,
                    local_c_logo_name,
                    content_logo_settings,
                    working_dir,
                    tone,
                ):
                    segs.append(out2)
                else:
                    raise Exception(f"Render Content Beat #{beat_index + 1} Failed")

        concat_list_file = f"list_{unique_session_id}.txt"
        concat_out_file = f"concat_{unique_session_id}.mkv"

        if not segs:
            raise Exception("Không có segment hợp lệ để concat")
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for s in segs: f.write(f"file '{s}'\n")

        concat_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_file, "-c", "copy", concat_out_file,
        ]
        concat_result = subprocess.run(concat_cmd, capture_output=True, text=True)
        if concat_result.returncode != 0:
            raise Exception(f"Concat lossless thất bại: {concat_result.stderr[-500:]}")

        subtitle_path = None
        if not uses_original_audio and script_text and body_duration > 0:
            subtitle_preset = get_subtitle_preset(tiktok_id)
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
                )
        audio_cues = [] if uses_original_audio else plan_audio_cues(
            timeline,
            is_sensitive=is_sensitive,
            sfx_dir=os.path.join(ASSETS_DIR, "sfx"),
        )
        duration = get_media_duration(concat_out_file)
        final_inputs = ["ffmpeg", "-y", "-i", concat_out_file]
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
            raise Exception(f"Final encode thất bại: {final_result.stderr[-700:]}")

        if os.path.exists(final_path):
            print(f"✅ DONE: {final_path}")
            return final_path

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        os.chdir(original_cwd)
        if 'working_dir' in locals() and os.path.exists(working_dir):
            try: shutil.rmtree(working_dir, ignore_errors=True)
            except: pass

if __name__ == "__main__":
    pass
