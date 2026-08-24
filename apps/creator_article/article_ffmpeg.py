import os
import sys
import json
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.services.music_selector import build_ducked_mix_filter, select_music
from shared.core.beat_timeline import plan_beat_timeline
from shared.core.video_encoding import (
    CLEAN_METADATA_ARGS,
    build_color_filter,
    final_output_args,
    resolve_color_grade,
)
from shared.core.safe_zone import plan_text_layout
from shared.services.audio_director import plan_audio_cues

CHANNELS_DIR = os.path.join(PROJECT_ROOT, "assets", "channels")
SFX_DIR = os.path.join(PROJECT_ROOT, "assets", "sfx")

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

def create_article_video(
    id_tiktok: str,
    image_paths: list,
    hook_voice_path: str,
    script_voice_path: str,
    output_path: str,
    hook_text: str = "",
    appended_video_path: str = None,
    tone: str = "Trung tính",
    script_text: str = "",
    music_mood: str | None = None,
    music_energy: int = 2,
    is_sensitive: bool = False,
    beats: list | None = None,
    subtitle_style: str = "keyword_highlight",
):
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
        
    source_images = valid_images
    num_imgs = len(source_images)
    
    if num_imgs == 0:
        print("   ❌ Không còn ảnh nào hợp lệ sau khi chuẩn hoá, huỷ dựng video.")
        return

    timeline = plan_beat_timeline(
        beats,
        total_duration=audio_dur,
        hook_duration=hook_dur,
        media_count=num_imgs,
        hook_text=hook_text,
    )
    segments = list(timeline.segments)
    image_paths = [source_images[item.media_index] for item in segments]
    num_imgs = len(image_paths)
    transition_durations = [
        0.35 if segments[index + 1].transition == "fade" else 0.08
        for index in range(max(0, num_imgs - 1))
    ]
    input_durations = [
        segment.duration + (
            transition_durations[index] if index < len(transition_durations) else 0.0
        )
        for index, segment in enumerate(segments)
    ]
    hook_text = timeline.first_frame_text or hook_text
    color_grade = resolve_color_grade(
        id_tiktok,
        tone=tone,
        is_sensitive=is_sensitive,
    )
    color_filter = build_color_filter(color_grade)
    print(
        f"   🧭 Beat timeline: {len(segments)} beats / {audio_dur:.2f}s | "
        f"first frame: {hook_text}"
    )
    print(f"   🎨 Color grade: {color_grade.name}")

    # ═══ TẠO SUBTITLE TỪ SCRIPT VOICE BẰNG FASTER-WHISPER (ASS KARAOKE) ═══
    ass_path = None
    try:
        if not script_voice_path or not os.path.exists(script_voice_path) or script_dur <= 0:
            raise Exception("Không có file âm thanh script_voice để tạo phụ đề.")
        print(f"   🤖 Đang nhận diện giọng nói (Whisper) tạo Subtitle ASS...")
        import sys
        sys.path.insert(0, PROJECT_ROOT)
        from shared.modules.subtitle_renderer import (
            generate_text_ass,
            generate_word_ass,
            get_subtitle_preset,
        )
        subtitle_preset = get_subtitle_preset(id_tiktok, {
            "font_size": cfg.get("sub_font_size"),
            "margin_v": cfg.get("sub_margin_v"),
            "hex_color": cfg.get("sub_color"),
        })
        keywords = [
            value
            for segment in segments
            for value in segment.must_show
            if value
        ]
        if subtitle_style == "normal":
            keywords = []
        ass_out = output_path.replace(".mp4", "_body.ass")
        ass_path = generate_word_ass(
            script_voice_path, 
            ass_out, 
            time_offset=hook_dur, 
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
        if not ass_path and script_text:
            print("   ⚠️ Whisper không tạo được subtitle, dùng script_voice text để tạo karaoke gần đúng...")
            ass_path = generate_text_ass(
                script_text,
                ass_out,
                duration=script_dur,
                time_offset=hook_dur,
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
        if ass_path:
            print(f"   ✅ Đã tạo phụ đề ASS: {os.path.basename(ass_path)}")
    except Exception as e:
        print(f"   ⚠️ Lỗi tạo phụ đề: {e}")
        ass_path = None

    print("   📸 Thời lượng cảnh lấy từ duration_hint/role của từng beat.")
    
    # 2. Xây dựng inputs và filter_complex cho từng ảnh
    inputs = []
    filter_complex_parts = []
    
    for idx, img in enumerate(image_paths):
        segment = segments[idx]
        input_duration = input_durations[idx]
        inputs.extend(["-loop", "1", "-t", f"{input_duration:.3f}", "-i", os.path.abspath(img)])
        
        bg_raw = f"[bg_raw{idx}]"
        fg_raw = f"[fg_raw{idx}]"
        bg = f"[bg{idx}]"
        fg = f"[fg{idx}]"
        overlay_pad = f"[overlayed{idx}]"
        v_seg = f"[v_seg{idx}]"
        
        filter_complex_parts.append(
            f"[{idx}:v]crop='iw*(1-0.3*gt(iw/ih,1.2))':'ih':'(iw-ow)/2':'0'[cropped{idx}];"
            f"[cropped{idx}]split=2{bg_raw}{fg_raw};"
            f"{bg_raw}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:2{bg};"
            f"{fg_raw}scale=1080:1920:force_original_aspect_ratio=decrease,{color_filter}{fg};"
            f"{bg}{fg}overlay=(W-w)/2:(H-h)/2-50,setsar=1{overlay_pad}"
        )
        
        effect = segment.motion
        num_frames = max(1, int(input_duration * 30))
        
        # Pan: scale lên lớn hơn rồi crop di chuyển
        expr_x = "'(iw-1080)/2'"
        expr_y = "'(ih-1920)/2'"
        
        if effect == "pan_left":
            expr_x = f"'(iw-1080)*(1-n/{num_frames})'"
        elif effect == "pan_right":
            expr_x = f"'(iw-1080)*(n/{num_frames})'"

        scale_filter = "scale=1242:2208"
        if effect == "slow_push_in":
            scale_filter = (
                f"scale=w='1134+108*n/{num_frames}':"
                f"h='2016+192*n/{num_frames}':eval=frame"
            )
        elif effect == "slow_pull_out":
            scale_filter = (
                f"scale=w='1242-108*n/{num_frames}':"
                f"h='2208-192*n/{num_frames}':eval=frame"
            )
        elif effect == "static":
            scale_filter = "scale=1134:2016"
            
        filter_complex_parts.append(
            f"{overlay_pad}{scale_filter},"
            f"crop=1080:1920:x={expr_x}:y={expr_y}{v_seg}"
        )

    # ═══ CROSSFADE TRANSITIONS giữa các ảnh ═══
    if num_imgs == 1:
        filter_complex_parts.append(f"[v_seg0]null[v_scaled]")
    else:
        prev = "[v_seg0]"
        for i in range(1, num_imgs):
            transition = "fade"
            transition_duration = transition_durations[i - 1]
            cur_offset = segments[i].start
            out_label = f"[v_scaled]" if i == num_imgs - 1 else f"[xf{i}]"
            filter_complex_parts.append(
                f"{prev}[v_seg{i}]xfade=transition={transition}:"
                f"duration={transition_duration:.3f}:offset={cur_offset:.3f}{out_label}"
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
    
    # Chọn đúng một BGM cho toàn video, theo mood biên tập và lịch sử của kênh.
    music = select_music(
        music_mood,
        tone=tone,
        energy=music_energy,
        is_sensitive=is_sensitive,
        channel_id=id_tiktok,
    )
    if music:
        inputs.extend(["-stream_loop", "-1", "-i", music.path])
        bgm_idx = curr_idx
        filter_complex_parts.append(
            build_ducked_mix_filter(
                "a_voice",
                f"{bgm_idx}:a",
                audio_dur,
                music,
                output_label="a_merged",
                label_prefix="article_music",
            )
        )
        audio_map = "[a_merged]"
        curr_idx += 1
        print(
            f"   🎵 Nhạc nền: {os.path.basename(music.path)} | "
            f"mood={music.mood} | energy={music.energy} | bed={music.bed_lufs:.1f} LUFS"
        )
        if music.license_status != "approved":
            print("   ⚠️ BGM hiện tại chưa có metadata giấy phép approved trong catalog.json")
    else:
        filter_complex_parts.append("[a_voice]loudnorm=I=-14:LRA=9:TP=-1.5[a_merged]")
        audio_map = "[a_merged]"
        print(f"   ⚠️ Không có BGM phù hợp cho mood={music_mood or tone}; giữ voice-only an toàn")

    # ═══ SFX: Chỉ ở beat reveal/con số/bước ngoặt được AudioDirector chọn ═══
    sfx_labels = []
    audio_cues = plan_audio_cues(timeline, is_sensitive=is_sensitive, sfx_dir=SFX_DIR)
    for cue_index, cue in enumerate(audio_cues):
        delay_ms = int(cue.timestamp * 1000)
        inputs.extend(["-i", cue.asset_path])
        label = f"sfx{cue_index}"
        filter_complex_parts.append(
            f"[{curr_idx}:a]adelay={delay_ms}|{delay_ms},"
            f"volume={cue.gain:.2f}[{label}]"
        )
        sfx_labels.append(label)
        curr_idx += 1
    if sfx_labels:
        amix_in = "[a_merged]" + "".join(f"[{l}]" for l in sfx_labels)
        filter_complex_parts.append(
            f"{amix_in}amix=inputs={1 + len(sfx_labels)}:duration=first:"
            f"dropout_transition=0:normalize=0,alimiter=limit=0.84[a_final]"
        )
        audio_map = "[a_final]"
        print(f"   🔊 AudioDirector: {len(sfx_labels)} SFX có chủ đích")

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
        
    # ═══ Hook Text: chỉ hiện đúng thời lượng hook thật (không xuyên suốt) ═══
    font_name = cfg.get("text_font", "RobotoCondensed-Bold.ttf")
    font_path = os.path.join(PROJECT_ROOT, "assets", "font", font_name)
    has_font = os.path.exists(font_path)
    
    if has_font and hook_text:
        # Giữ nguyên chính tả gốc, không viết hoa toàn bộ
        safe_text = str(hook_text).replace("'", "").replace(":", "\\:").replace("%", "\\%").strip()
        font_size = int(cfg.get("text_size", 65))
        max_width_px = int(1080 * float(cfg.get("text_w", 0.75)))
        preferred_y = int(1920 * float(cfg.get("text_y1", 0.73)))
        text_color = cfg.get("text_color", "#ffffff")
        stroke = int(cfg.get("text_stroke", 3))
        
        # Chỉ hiển thị text trong khoảng hook (0 → hook_dur giây)
        hook_show_dur = hook_dur if hook_dur > 0 else 5.0
        
        # Calculate left margin to align left based on the max_width_px + text_x offset
        text_x_offset = int(cfg.get("text_x", 0))
        preferred_x = int((1080 - max_width_px) / 2) + text_x_offset
        layout = plan_text_layout(
            safe_text,
            font_size=font_size,
            preferred_x=preferred_x,
            preferred_y=preferred_y,
            max_width=max_width_px,
        )
        
        for i, line in enumerate(layout.lines):
            y_pos = layout.y + (i * layout.line_spacing)
            draw_filter = (
                f"drawtext=fontfile='{font_path}':text='{line}':"
                f"fontsize={font_size}:fontcolor={text_color}:bordercolor=black:borderw={stroke}:"
                f"shadowcolor=black:shadowx=3:shadowy=3:"
                f"x={layout.x}:y={y_pos}:"
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

    # ═══ ENCODE CHUẨN DÙNG CHUNG: H.264 High + AAC 48 kHz stereo ═══
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", f"{out_pad}",
        "-map", f"{audio_map}",
        *final_output_args(),
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
            filter_v = (
                "[0:v]setpts=PTS-STARTPTS,scale=1080:1920:"
                "force_original_aspect_ratio=increase,crop=1080:1920,"
                "boxblur=10:2[bg_blur];"
                "[0:v]setpts=PTS-STARTPTS,scale=1080:1920:"
                f"force_original_aspect_ratio=decrease,{color_filter}[fg];"
                "[bg_blur][fg]overlay=(W-w)/2:(H-h)/2[vout]"
            )
            
            if has_audio:
                filter_v += ";[0:a]asetpts=PTS-STARTPTS[aout]"
            else:
                filter_v += ";[1:a]asetpts=PTS-STARTPTS[aout]"
                
            cmd_app = ["ffmpeg", "-y", "-i", appended_video_path]
            if not has_audio:
                cmd_app += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
                
            cmd_app += [
                "-filter_complex", filter_v,
                "-map", "[vout]",
                "-map", "[aout]",
                *final_output_args(),
                "-t", "15",  # Giới hạn video chèn thêm tối đa 15 giây để tránh quá dài
                "-shortest", temp_appended
            ]
            subprocess.run(cmd_app, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            print(f"   🎬 Đang ghép nối phần Ảnh và phần Video...")
            concat_txt = output_path.replace(".mp4", "_concat.txt")
            with open(concat_txt, "w") as f:
                f.write(f"file '{os.path.basename(temp_main_path)}'\n")
                f.write(f"file '{os.path.basename(temp_appended)}'\n")
                
            cmd_concat = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
                "-c", "copy", "-movflags", "+faststart", *CLEAN_METADATA_ARGS,
                output_path,
            ]
            subprocess.run(cmd_concat, check=True, cwd=os.path.dirname(output_path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            try:
                os.remove(temp_main_path)
                os.remove(temp_appended)
                os.remove(concat_txt)
            except: pass

        print(f"   ✅ Đã xong video: {output_path}")
    except Exception as e:
        print(f"   ❌ Lỗi FFmpeg: {e}")
