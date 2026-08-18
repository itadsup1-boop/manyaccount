import os
import sys
import requests
import shutil
import json
import ffmpeg
import random
import logging
import textwrap
import uuid
from datetime import datetime

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

def wrap_text_ffmpeg(text, font_size, max_width_px):
    if not text: return []
    avg_char_width = font_size * 0.55
    if avg_char_width <= 0: avg_char_width = 10
    max_chars_per_line = int(max_width_px / avg_char_width)
    if max_chars_per_line < 1: max_chars_per_line = 1
    return textwrap.wrap(text, width=max_chars_per_line)

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
        print(f"⚠️ Cảnh báo: Thời gian bắt đầu ({s_start}s) lớn hơn tổng độ dài video ({total_video_duration}s). Tự động trả về 0s.")
        s_start = 0.0

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

    if audio_filename == video_filename:
        duration_audio = (real_end - s_start) if real_end else (total_video_duration - s_start)
        if duration_audio <= 0: duration_audio = 5.0
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

    video_speed = random.uniform(0.95, 1.05)
    k1_distort = random.uniform(-0.03, 0.03)
    k2_distort = random.uniform(-0.03, 0.03)
    contrast_val = random.uniform(1.0, 1.1)
    brightness_val = random.uniform(-0.02, 0.02)
    saturation_val = random.uniform(0.9, 1.2)

    v_in = ffmpeg.input(video_filename).video
    a_in = ffmpeg.input(audio_filename).audio
    
    if audio_filename == video_filename:
        if real_end:
            a_in = a_in.filter('atrim', start=s_start, end=real_end)
        else:
            a_in = a_in.filter('atrim', start=s_start)
        a_in = a_in.filter('asetpts', 'PTS-STARTPTS')

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

    v = v.filter('setpts', f'PTS/{video_speed}')

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
        v_main = v_main.filter('lenscorrection', k1=k1_distort, k2=k2_distort)
        v_main = v_main.filter('eq', contrast=contrast_val, brightness=brightness_val, saturation=saturation_val)
        
        v = ffmpeg.overlay(bg, v_main, x=x_expr, y=y_expr, shortest=1)
    else:
        v = v.filter('scale', width=scaled_w, height=-2)
        v = v.filter('lenscorrection', k1=k1_distort, k2=k2_distort)
        v = v.filter('eq', contrast=contrast_val, brightness=brightness_val, saturation=saturation_val)
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
        wrapped_lines = wrap_text_ffmpeg(safe_text, f_size, max_text_width)

        start_y_px = 1920 * y_start_pct
        line_spacing_px = f_size * 1.2

        for i, line in enumerate(wrapped_lines):
            current_line_y = start_y_px + (i * line_spacing_px)
            v = v.drawtext(
                text=line, fontfile=font_file_clean, fontsize=f_size,
                fontcolor=t_color, borderw=border_w, bordercolor="black",
                shadowcolor="black", shadowx=2, shadowy=2,
                x='(w-text_w)/2', y=str(current_line_y), fix_bounds=True
            )
    # Map audio
    import glob
    def _get_random_bgm(tone_name):
        bgm_dir = os.path.join(PROJECT_ROOT, "assets", "bgm")
        if not os.path.exists(bgm_dir): return None
        safe_tone = tone_name.lower().replace(" ", "_").replace("à", "a").replace("á", "a").replace("ẹ", "e").replace("ể", "e").replace("ồ", "o").replace("ộ", "o").replace("ị", "i").replace("í", "i").replace("ũ", "u").capitalize()
        files = glob.glob(os.path.join(bgm_dir, f"{safe_tone}_*.mp3")) + glob.glob(os.path.join(bgm_dir, f"{safe_tone}_*.wav"))
        if not files:
            files = glob.glob(os.path.join(bgm_dir, "*.mp3")) + glob.glob(os.path.join(bgm_dir, "*.wav"))
        return random.choice(files) if files else None

    bgm_path = _get_random_bgm(tone)
    if bgm_path:
        bgm_in = ffmpeg.input(bgm_path, stream_loop=-1)
        a_main = a_in.filter('volume', volume=1.0)
        a_bgm = bgm_in.filter('volume', volume=0.06)
        a_out = ffmpeg.filter([a_main, a_bgm], 'amix', inputs=2, duration='first', dropout_transition=2)
        a_out = a_out.filter('loudnorm', I=-14, LRA=11, TP=-1.5)
    else:
        a_out = a_in.filter('volume', volume=1.0).filter('loudnorm', I=-14, LRA=11, TP=-1.5)

    try:
        (
            ffmpeg
            .output(v, a_out, output_filename, t=duration_audio, r=30, vcodec='libx264', acodec='aac', pix_fmt='yuv420p', preset='ultrafast')
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
        cfg = load_render_config(target_channel_url, target_tiktok_id=tiktok_id)

        if override_config and isinstance(override_config, dict):
            sections = ["title_settings", "content_settings", "text_overlay_settings", "text_content_settings", "assets"]
            for section in sections:
                if section in override_config:
                    if section not in cfg: cfg[section] = {}
                    cfg[section].update(override_config[section])
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

        segs = []
        if edit_mode == "Frame Intro + Gốc (Giống FB)":
            if has_intro:
                out = f"seg1_{unique_session_id}.mp4"
                if render_segment_to_file(p_vid_name, p_aud_title_name, out, cfg["title_settings"], cfg["text_overlay_settings"], title_tiktok, local_t_frame_name, local_t_logo_name, title_logo_settings, working_dir, tone):
                    segs.append(out)
            
            # Tính thời gian đoạn gốc
            intro_duration = get_media_duration(os.path.join(working_dir, p_aud_title_name)) if has_intro else 0
            intro_start = float(cfg["title_settings"].get("source_start", 0))
            
            content_settings_goc = cfg["content_settings"].copy()
            content_settings_goc["source_start"] = intro_start + intro_duration
            
            out2 = f"seg2_{unique_session_id}.mp4"
            if render_segment_to_file(p_vid_name, p_vid_name, out2, content_settings_goc, {}, None, None, None, {}, working_dir, tone, blur_background=True):
                segs.append(out2)
            else:
                raise Exception("Render Content Gốc Failed")
        else:
            if has_intro:
                out = f"seg1_{unique_session_id}.mp4"
                if render_segment_to_file(p_vid_name, p_aud_title_name, out, cfg["title_settings"], cfg["text_overlay_settings"], title_tiktok, local_t_frame_name, local_t_logo_name, title_logo_settings, working_dir, tone):
                    segs.append(out)
            out2 = f"seg2_{unique_session_id}.mp4"
            if not os.path.exists(p_aud_main_name): raise Exception("Mất file aud_main.mp3")
            if render_segment_to_file(p_vid_name, p_aud_main_name, out2, cfg["content_settings"], cfg["text_content_settings"], content_text, local_c_frame_name, local_c_logo_name, content_logo_settings, working_dir, tone):
                segs.append(out2)
            else:
                raise Exception("Render Content Failed")

        concat_list_file = f"list_{unique_session_id}.txt"
        concat_out_file = f"concat_{unique_session_id}.mp4"

        with open(concat_list_file, "w", encoding="utf-8") as f:
            for s in segs: f.write(f"file '{s}'\n")

        try:
            (
                ffmpeg
                .input(concat_list_file, format='concat', safe=0)
                .output(concat_out_file, vcodec='libx264', acodec='aac')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
            raise Exception("Concat Failed")

        shutil.move(concat_out_file, final_path)

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