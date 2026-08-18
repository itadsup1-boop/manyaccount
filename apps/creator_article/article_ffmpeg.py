import os
import json
import subprocess
import random
import glob

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHANNELS_DIR = os.path.join(PROJECT_ROOT, "assets", "channels")
BGM_DIR = os.path.join(PROJECT_ROOT, "assets", "bgm")
SFX_DIR = os.path.join(PROJECT_ROOT, "assets", "sfx")


def _get_random_sfx():
    if not os.path.exists(SFX_DIR):
        return None
    files = glob.glob(os.path.join(SFX_DIR, "*.mp3")) + glob.glob(os.path.join(SFX_DIR, "*.wav"))
    return random.choice(files) if files else None

def _get_supabase_client():
    env_file = os.path.join(PROJECT_ROOT, ".env")
    env = {}
    if os.path.exists(env_file):
        try:
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        env[key.strip()] = val.strip()
        except:
            pass
    url = env.get("SUPABASE_URL", "")
    key = env.get("SUPABASE_KEY", "")
    if url and key:
        try:
            from supabase import create_client
            return create_client(url, key)
        except Exception as e:
            print(f"⚠️ Không thể tạo client Supabase: {e}")
    return None

def sync_channel_assets(id_tiktok: str):
    """Đồng bộ assets (frame, logo, config.json) của kênh từ Supabase Storage về local."""
    client = _get_supabase_client()
    if not client:
        return

    channel_dir = os.path.join(CHANNELS_DIR, id_tiktok)
    os.makedirs(channel_dir, exist_ok=True)
    
    storage_folder = f"channels/{id_tiktok}"
    try:
        res = client.storage.from_("assets").list(storage_folder)
        if not isinstance(res, list):
            return
            
        files = [f.get("name") for f in res if isinstance(f, dict) and f.get("name")]
        
        for file_name in files:
            if file_name in ["frame_intro.png", "frame_content.png", "frame.png", "logo.png", "config.json"]:
                local_path = os.path.join(channel_dir, file_name)
                storage_path = f"{storage_folder}/{file_name}"
                try:
                    data = client.storage.from_("assets").download(storage_path)
                    with open(local_path, "wb") as f:
                        f.write(data)
                    print(f"   📥 Đã tải thành công {file_name} của kênh {id_tiktok} từ Supabase Storage.")
                except Exception as e:
                    print(f"   ⚠️ Lỗi tải file {file_name} từ Supabase Storage: {e}")
    except Exception as e:
        print(f"   ⚠️ Lỗi kết nối Supabase Storage để đồng bộ assets: {e}")

def get_channel_config(id_tiktok: str) -> dict:
    """Đọc cấu hình frame và logo của một kênh cụ thể, có fallback về mặc định."""
    # Đồng bộ từ Supabase Storage trước
    sync_channel_assets(id_tiktok)
    
    channel_dir = os.path.join(CHANNELS_DIR, id_tiktok)
    config_path = os.path.join(channel_dir, "config.json")
    
    frame_intro_path = os.path.join(channel_dir, "frame_intro.png")
    frame_content_path = os.path.join(channel_dir, "frame_content.png")
    logo_path = os.path.join(channel_dir, "logo.png")
    
    # Đọc custom config trước
    custom_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                custom_config = json.load(f)
        except Exception as e:
            print(f"⚠️ Lỗi đọc {config_path}: {e}")

    # Fallback về default ở assets/ nếu kênh riêng chưa có VÀ không bị disable
    if not os.path.exists(frame_intro_path) and not custom_config.get("frame_intro_disabled"):
        default_frame_intro = os.path.join(PROJECT_ROOT, "assets", "frame_intro.png")
        if os.path.exists(default_frame_intro):
            frame_intro_path = default_frame_intro
    elif custom_config.get("frame_intro_disabled"):
        frame_intro_path = ""
            
    if not os.path.exists(frame_content_path) and not custom_config.get("frame_content_disabled"):
        default_frame_content = os.path.join(PROJECT_ROOT, "assets", "frame_content.png")
        if os.path.exists(default_frame_content):
            frame_content_path = default_frame_content
    elif custom_config.get("frame_content_disabled"):
        frame_content_path = ""
            
    # Bỏ fallback logo_path theo yêu cầu: nếu không set logo thì không chèn gì cả
    if custom_config.get("logo_disabled"):
        logo_path = ""

    config = {
        "frame_intro_path": frame_intro_path,
        "frame_content_path": frame_content_path,
        "logo_path": logo_path,
        "logo_x": 50,
        "logo_y": 50,
        "logo_scale": 250, # Chiều rộng của logo (px)
        "text_y1": 0.73,
        "text_y2": 0.83,
        "text_w": 0.65,
        "text_size": 65,
        "text_color": "#ffffff",
        "text_stroke": 3,
        "text_font": "RobotoCondensed-Bold.ttf",
        "text_x": 0
    }
    
    config.update(custom_config)
    return config

def _get_random_bgm(tone_name):
    if not os.path.exists(BGM_DIR): return None
    safe_tone = tone_name.lower().replace(" ", "_").replace("à", "a").replace("á", "a").replace("ẹ", "e").replace("ể", "e").replace("ồ", "o").replace("ộ", "o").replace("ị", "i").replace("í", "i").replace("ũ", "u").capitalize()
    files = glob.glob(os.path.join(BGM_DIR, f"{safe_tone}_*.mp3")) + glob.glob(os.path.join(BGM_DIR, f"{safe_tone}_*.wav"))
    if not files: files = glob.glob(os.path.join(BGM_DIR, "*.mp3")) + glob.glob(os.path.join(BGM_DIR, "*.wav"))
    return random.choice(files) if files else None

def create_article_video(id_tiktok: str, image_paths: list, hook_voice_path: str, script_voice_path: str, output_path: str, hook_text: str = "", appended_video_path: str = None, tone: str = "Trung tính", script_text: str = ""):
    """
    Dựng video từ mảng ảnh tĩnh và file âm thanh (hook + script).
    ✅ V2: Crossfade transition, nhạc nền, encode chất lượng cao, hiệu ứng đa dạng.
    """
    print(f"\n🎬 Đang dựng video cho kênh: {id_tiktok}")
    
    # 1. Lấy thông số cấu hình của kênh này
    cfg = get_channel_config(id_tiktok)
    
    has_frame_intro = os.path.exists(cfg["frame_intro_path"])
    has_frame_content = os.path.exists(cfg["frame_content_path"])
    has_logo = os.path.exists(cfg["logo_path"])
    
    if has_frame_intro:
        print(f"   🖼️ Đã tìm thấy Khung Intro riêng của kênh {id_tiktok}")
    if has_frame_content:
        print(f"   🖼️ Đã tìm thấy Khung Content riêng của kênh {id_tiktok}")
    if has_logo:
        print(f"   💠 Đã tìm thấy Logo riêng của kênh {id_tiktok}")
        
    # Lấy độ dài audio
    def get_duration(p):
        if not p or not os.path.exists(p): return 0.0
        duration_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", p
        ]
        return float(subprocess.check_output(duration_cmd).decode("utf-8").strip())

    try:
        hook_dur = get_duration(hook_voice_path)
        script_dur = get_duration(script_voice_path)
        audio_dur = hook_dur + script_dur
        print(f"   🎙️ Độ dài audio: Hook ({hook_dur:.2f}s) + Script ({script_dur:.2f}s) = {audio_dur:.2f} giây")
    except Exception as e:
        print(f"   ❌ Lỗi lấy độ dài audio: {e}")
        return
        
    num_imgs = len(image_paths)
    if num_imgs == 0 or audio_dur == 0:
        return

    # ═══ CHUẨN HOÁ ẢNH VỚI PILLOW TRÁNH LỖI FFMPEG (SVG, GIF, v.v) ═══
    valid_images = []
    try:
        from PIL import Image
        for img in image_paths:
            if not os.path.exists(img): continue
            try:
                with Image.open(img) as im:
                    if im.mode != "RGB":
                        im = im.convert("RGB")
                    # Ghi đè lại để đảm bảo là JPEG thực thụ
                    im.save(img, "JPEG", quality=95)
                    valid_images.append(img)
            except Exception as e:
                print(f"   ⚠️ Bỏ qua ảnh không hợp lệ {os.path.basename(img)}: {e}")
    except ImportError:
        valid_images = image_paths
        
    image_paths = valid_images
    num_imgs = len(image_paths)
    
    if num_imgs == 0:
        print("   ❌ Không còn ảnh nào hợp lệ sau khi chuẩn hoá, huỷ dựng video.")
        return

    # ═══ CROSSFADE: Tính thời lượng mỗi ảnh có tính overlap ═══
    CROSSFADE_DUR = 0.5  # Thời gian fade giữa 2 ảnh (giây)
    # Tổng thời gian = N*img_dur - (N-1)*crossfade → img_dur = (audio_dur + (N-1)*crossfade) / N
    img_dur = (audio_dur + (num_imgs - 1) * CROSSFADE_DUR) / num_imgs
    img_dur = max(img_dur, 1.5)  # Tối thiểu 1.5 giây/ảnh

    # ═══ TẠO SUBTITLE TỪ SCRIPT VOICE BẰNG FASTER-WHISPER (ASS KARAOKE) ═══
    ass_path = None
    try:
        if not script_voice_path or not os.path.exists(script_voice_path) or script_dur <= 0:
            raise Exception("Không có file âm thanh script_voice để tạo phụ đề.")
        print(f"   🤖 Đang nhận diện giọng nói (Whisper) tạo Subtitle ASS...")
        import sys
        sys.path.insert(0, PROJECT_ROOT)
        from shared.modules.subtitle_renderer import generate_text_ass, generate_word_ass
        ass_out = output_path.replace(".mp4", "_body.ass")
        ass_path = generate_word_ass(
            script_voice_path, 
            ass_out, 
            time_offset=hook_dur, 
            words_per_line=4,
            font_size=cfg.get("sub_font_size", 70),
            margin_v=cfg.get("sub_margin_v", 150),
            hex_color=cfg.get("sub_color", "#00ffff")
        )
        if not ass_path and script_text:
            print("   ⚠️ Whisper không tạo được subtitle, dùng script_voice text để tạo karaoke gần đúng...")
            ass_path = generate_text_ass(
                script_text,
                ass_out,
                duration=script_dur,
                time_offset=hook_dur,
                words_per_line=4,
                font_size=cfg.get("sub_font_size", 70),
                margin_v=cfg.get("sub_margin_v", 150),
                hex_color=cfg.get("sub_color", "#00ffff")
            )
        if ass_path:
            print(f"   ✅ Đã tạo phụ đề ASS: {os.path.basename(ass_path)}")
    except Exception as e:
        print(f"   ⚠️ Lỗi tạo phụ đề: {e}")
        ass_path = None

    print(f"   📸 Mỗi ảnh hiển thị: {img_dur:.2f} giây (crossfade {CROSSFADE_DUR}s)")
    
    # 2. Xây dựng inputs và filter_complex cho từng ảnh
    inputs = []
    filter_complex_parts = []
    
    # Danh sách hiệu ứng đa dạng: pan
    EFFECTS = ["pan_left", "pan_right", "pan_up", "pan_down", "pan_up_left", "pan_down_right"]
    
    for idx, img in enumerate(image_paths):
        inputs.extend(["-loop", "1", "-t", f"{img_dur:.3f}", "-i", os.path.abspath(img)])
        
        bg_raw = f"[bg_raw{idx}]"
        fg_raw = f"[fg_raw{idx}]"
        bg = f"[bg{idx}]"
        fg = f"[fg{idx}]"
        overlay_pad = f"[overlayed{idx}]"
        v_seg = f"[v_seg{idx}]"
        
        # Color Grading ngẫu nhiên nhẹ
        contrast = round(random.uniform(0.98, 1.02), 3)
        saturation = round(random.uniform(0.98, 1.02), 3)
        brightness = round(random.uniform(-0.02, 0.02), 3)
        
        filter_complex_parts.append(
            f"[{idx}:v]crop='iw*(1-0.3*gt(iw/ih,1.2))':'ih':'(iw-ow)/2':'0'[cropped{idx}];"
            f"[cropped{idx}]split=2{bg_raw}{fg_raw};"
            f"{bg_raw}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:2{bg};"
            f"{fg_raw}scale=1080:1920:force_original_aspect_ratio=decrease,eq=contrast={contrast}:saturation={saturation}:brightness={brightness}{fg};"
            f"{bg}{fg}overlay=(W-w)/2:(H-h)/2-50,setsar=1{overlay_pad}"
        )
        
        # Ảnh đầu tiên dùng pan_up_left để tạo visual hook mạnh thay vì zoom_in (FFmpeg crop không cho w/h động)
        effect = "pan_up_left" if idx == 0 else random.choice(EFFECTS)
        num_frames = max(1, int(img_dur * 25))
        
        # Pan: scale lên lớn hơn rồi crop di chuyển
        expr_x = "'(iw-1080)/2'"
        expr_y = "'(ih-1920)/2'"
        
        if "left" in effect:
            expr_x = f"'(iw-1080)*(1-n/{num_frames})'"
        elif "right" in effect:
            expr_x = f"'(iw-1080)*(n/{num_frames})'"
            
        if "up" in effect:
            expr_y = f"'(ih-1920)*(1-n/{num_frames})'"
        elif "down" in effect:
            expr_y = f"'(ih-1920)*(n/{num_frames})'"
            
        filter_complex_parts.append(
            f"{overlay_pad}scale=1242:2208,crop=1080:1920:x={expr_x}:y={expr_y}{v_seg}"
        )

    # ═══ CROSSFADE TRANSITIONS giữa các ảnh ═══
    if num_imgs == 1:
        filter_complex_parts.append(f"[v_seg0]null[v_scaled]")
    else:
        # Ghép xfade liên tiếp: seg0 xfade seg1 → tmp0, tmp0 xfade seg2 → tmp1, ...
        offset = img_dur - CROSSFADE_DUR
        xfade_transitions = ["fade", "fadeblack", "slideleft", "slideright", "slideup", "slidedown"]
        
        prev = "[v_seg0]"
        for i in range(1, num_imgs):
            transition = random.choice(xfade_transitions)
            cur_offset = offset * i  # Thời điểm bắt đầu crossfade
            out_label = f"[v_scaled]" if i == num_imgs - 1 else f"[xf{i}]"
            filter_complex_parts.append(
                f"{prev}[v_seg{i}]xfade=transition={transition}:duration={CROSSFADE_DUR}:offset={cur_offset:.3f}{out_label}"
            )
            prev = out_label
    
    # ═══ AUDIO: Voice + Nhạc nền ═══
    audio_idx = num_imgs
    
    if hook_dur > 0 and script_dur > 0:
        inputs.extend(["-i", hook_voice_path, "-i", script_voice_path])
        filter_complex_parts.append(f"[{audio_idx}:a][{audio_idx+1}:a]concat=n=2:v=0:a=1[a_voice]")
        curr_idx = num_imgs + 2
    elif hook_dur > 0:
        inputs.extend(["-i", hook_voice_path])
        filter_complex_parts.append(f"[{audio_idx}:a]acopy[a_voice]")
        curr_idx = num_imgs + 1
    else:
        inputs.extend(["-i", script_voice_path])
        filter_complex_parts.append(f"[{audio_idx}:a]acopy[a_voice]")
        curr_idx = num_imgs + 1
    
    # Nhạc nền (BGM) mix dưới voice
    bgm_path = _get_random_bgm(tone)
    if bgm_path:
        inputs.extend(["-stream_loop", "-1", "-i", bgm_path])
        bgm_idx = curr_idx
        # Trim BGM theo độ dài audio, giảm volume xuống 0.06 (amix sẽ giảm tiếp), fade out 3 giây cuối
        filter_complex_parts.append(
            f"[{bgm_idx}:a]atrim=0:{audio_dur:.3f},afade=t=in:st=0:d=2,afade=t=out:st={max(0, audio_dur-3):.3f}:d=3,volume=0.06[a_bgm];"
            f"[a_voice][a_bgm]amix=inputs=2:duration=first:dropout_transition=2[a_mix];"
            f"[a_mix]loudnorm=I=-14:LRA=11:TP=-1.5[a_merged]"
        )
        audio_map = "[a_merged]"
        curr_idx += 1
        print(f"   🎵 Nhạc nền: {os.path.basename(bgm_path)}")
    else:
        filter_complex_parts.append(f"[a_voice]loudnorm=I=-14:LRA=11:TP=-1.5[a_merged]"); audio_map = "[a_merged]"

    # ═══ SFX: Tiếng whoosh tại ~50% điểm chuyển cảnh ═══
    sfx_labels = []
    for i in range(1, num_imgs):
        if random.random() < 0.5:
            sfx_file = _get_random_sfx()
            if sfx_file:
                delay_ms = int((i * (img_dur - CROSSFADE_DUR) + hook_dur) * 1000)
                inputs.extend(["-i", sfx_file])
                label = f"sfx{i}"
                filter_complex_parts.append(
                    f"[{curr_idx}:a]adelay={delay_ms}|{delay_ms},volume=0.15[{label}]"
                )
                sfx_labels.append(label)
                curr_idx += 1
    if sfx_labels:
        amix_in = "[a_merged]" + "".join(f"[{l}]" for l in sfx_labels)
        filter_complex_parts.append(
            f"{amix_in}amix=inputs={1 + len(sfx_labels)}:duration=first:dropout_transition=2[a_final]"
        )
        audio_map = "[a_final]"
        print(f"   🔊 SFX: {len(sfx_labels)} tiếng chuyển cảnh")

    out_pad = "[v_scaled]"
    
    # ═══ THÊM KHUNG (FRAME): Intro cho phần Hook, Content cho phần Thân bài ═══
    has_tf = has_frame_intro and os.path.exists(cfg["frame_intro_path"])
    has_cf = has_frame_content and os.path.exists(cfg["frame_content_path"])
    
    if has_tf and has_cf:
        inputs.extend(["-loop", "1", "-i", cfg["frame_intro_path"]])
        tf_idx = curr_idx
        curr_idx += 1
        inputs.extend(["-loop", "1", "-i", cfg["frame_content_path"]])
        cf_idx = curr_idx
        curr_idx += 1
        
        filter_complex_parts.append(f"{out_pad}[{tf_idx}:v]overlay=0:0:shortest=1:enable='between(t,0,{hook_dur})'[with_tf]")
        filter_complex_parts.append(f"[with_tf][{cf_idx}:v]overlay=0:0:shortest=1:enable='gt(t,{hook_dur})'[v_frame]")
        out_pad = "[v_frame]"
    elif has_tf:
        inputs.extend(["-loop", "1", "-i", cfg["frame_intro_path"]])
        filter_complex_parts.append(f"{out_pad}[{curr_idx}:v]overlay=0:0:shortest=1:enable='between(t,0,{hook_dur})'[v_frame]")
        out_pad = "[v_frame]"
        curr_idx += 1
    elif has_cf:
        inputs.extend(["-loop", "1", "-i", cfg["frame_content_path"]])
        filter_complex_parts.append(f"{out_pad}[{curr_idx}:v]overlay=0:0:shortest=1[v_frame]")
        out_pad = "[v_frame]"
        curr_idx += 1
        
    # Thêm Logo nếu có
    if has_logo:
        inputs.extend(["-loop", "1", "-i", cfg["logo_path"]])
        lx, ly = cfg.get("logo_x", 50), cfg.get("logo_y", 50)
        filter_complex_parts.append(f"{out_pad}[{curr_idx}:v]overlay={lx}:{ly}:shortest=1[v_final]")
        out_pad = "[v_final]"
        curr_idx += 1
        
    # ═══ Hook Text: CHỈ HIỆN 5 GIÂY ĐẦU (không xuyên suốt) ═══
    import textwrap
    font_name = cfg.get("text_font", "RobotoCondensed-Bold.ttf")
    font_path = os.path.join(PROJECT_ROOT, "assets", "font", font_name)
    has_font = os.path.exists(font_path)
    
    if has_font and hook_text:
        # Giữ nguyên chính tả gốc, không viết hoa toàn bộ
        safe_text = str(hook_text).replace("'", "").replace(":", "\\:").replace("%", "\\%").strip()
        font_size = int(cfg.get("text_size", 65))
        max_width_px = int(1080 * float(cfg.get("text_w", 0.75)))
        avg_char_width = font_size * 0.55
        max_chars = int(max_width_px / avg_char_width)
        wrapped_lines = textwrap.wrap(safe_text, width=max_chars)

        start_y = int(1920 * float(cfg.get("text_y1", 0.73)))
        text_color = cfg.get("text_color", "#ffffff")
        stroke = int(cfg.get("text_stroke", 3))
        line_spacing = int(font_size * 1.2)
        
        # Chỉ hiển thị text trong khoảng hook (0 → hook_dur giây)
        hook_show_dur = hook_dur if hook_dur > 0 else 5.0
        
        # Calculate left margin to align left based on the max_width_px + text_x offset
        text_x_offset = int(cfg.get("text_x", 0))
        margin_x = int((1080 - max_width_px) / 2) + text_x_offset
        
        for i, line in enumerate(wrapped_lines):
            y_pos = start_y + (i * line_spacing)
            draw_filter = (
                f"drawtext=fontfile='{font_path}':text='{line}':"
                f"fontsize={font_size}:fontcolor={text_color}:bordercolor=black:borderw={stroke}:"
                f"shadowcolor=black:shadowx=3:shadowy=3:"
                f"x={margin_x}:y={y_pos}:"
                f"enable='between(t,0,{hook_show_dur:.2f})'"
            )
            filter_complex_parts.append(f"{out_pad}{draw_filter}[v_text{i}]")
            out_pad = f"[v_text{i}]"

    # Nối tất cả các filter
    filter_complex = ";".join(filter_complex_parts)

    if ass_path and os.path.exists(ass_path):
        safe_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")
        fonts_dir = os.path.join(PROJECT_ROOT, "assets", "font").replace("\\", "/")
        sub_filter = f"subtitles='{safe_ass_path}':fontsdir='{fonts_dir}'"
        filter_complex += f";{out_pad}{sub_filter}[v_with_sub]"
        out_pad = "[v_with_sub]"

    
    temp_main_path = output_path
    if appended_video_path and os.path.exists(appended_video_path):
        temp_main_path = output_path.replace(".mp4", "_main.mp4")

    # ═══ ENCODE CHẤT LƯỢNG CAO: preset medium, crf 18 ═══
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", f"{out_pad}",
        "-map", f"{audio_map}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-video_track_timescale", "90000", "-preset", "medium", "-crf", "18", "-threads", "0",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-t", str(audio_dur + 0.2),
        "-shortest",
        temp_main_path
    ]
    
    print(f"   🚀 Đang render FFmpeg (Quá trình này mất khoảng 1-3 phút, vui lòng chờ và KHÔNG tắt ngang)...")
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            err_lines = result.stderr.strip().split('\n')[-10:]
            for l in err_lines:
                print(f"      {l}")
            raise Exception(f"FFmpeg exit code {result.returncode}")
        
        # Nếu có video đính kèm, render video đó và ghép vào cuối
        if appended_video_path and os.path.exists(appended_video_path):
            print(f"   🎬 Đang xử lý video chèn thêm từ bài báo...")
            temp_appended = output_path.replace(".mp4", "_appended.mp4")
            
            has_audio = False
            try:
                probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", appended_video_path], capture_output=True, text=True)
                has_audio = bool(probe.stdout.strip())
            except: pass
            
            # Sửa lỗi PTS (thời gian) không bắt đầu từ 0 của video livestream/m3u8
            filter_v = "[0:v]setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:2[bg_blur];[0:v]setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg_blur][fg]overlay=(W-w)/2:(H-h)/2[vout]"
            
            if has_audio:
                filter_v += ";[0:a]asetpts=PTS-STARTPTS[aout]"
            else:
                filter_v += ";[1:a]asetpts=PTS-STARTPTS[aout]"
                
            cmd_app = ["ffmpeg", "-y", "-i", appended_video_path]
            if not has_audio:
                cmd_app += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
                
            cmd_app += [
                "-filter_complex", filter_v,
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-video_track_timescale", "90000", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-t", "15",  # Giới hạn video chèn thêm tối đa 15 giây để tránh quá dài
                "-shortest", temp_appended
            ]
            subprocess.run(cmd_app, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            print(f"   🎬 Đang ghép nối phần Ảnh và phần Video...")
            concat_txt = output_path.replace(".mp4", "_concat.txt")
            with open(concat_txt, "w") as f:
                f.write(f"file '{os.path.basename(temp_main_path)}'\n")
                f.write(f"file '{os.path.basename(temp_appended)}'\n")
                
            cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", output_path]
            subprocess.run(cmd_concat, check=True, cwd=os.path.dirname(output_path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            try:
                os.remove(temp_main_path)
                os.remove(temp_appended)
                os.remove(concat_txt)
            except: pass

        print(f"   ✅ Đã xong video: {output_path}")
    except Exception as e:
        print(f"   ❌ Lỗi FFmpeg: {e}")
