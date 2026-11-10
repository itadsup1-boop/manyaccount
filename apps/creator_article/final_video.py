"""Dựng final.mp4 hoàn chỉnh: TTS thật + phụ đề + BGM/SFX — Giai đoạn 4.

Theo ``KE_HOACH_NANG_CAP_TOOL_VIDEO_TIN_TUC.md`` §7:

- Sinh TTS hook + script qua voice.adsup.vn và ĐO thời lượng thật; thời điểm
  beat lấy từ ``plan_beat_timeline`` (audio thật), không tin ``start_sec`` AI.
- Phụ đề word-timecode (Whisper, fallback text) nhấn từ khoá ``must_show``,
  nằm trong safe area qua preset chung.
- Chỉ dùng BGM ``license_status == approved``; ducking nhạc khi có voice;
  SFX do AudioDirector chọn và tự bỏ khi nội dung nhạy cảm.
- TTS hook hoặc script thất bại -> chặn (ValueError ``TTS_FAILED``), không
  xuất video thiếu câu mở đầu/kết.
- Encode xong chạy VideoQA bắt buộc (KE_HOACH §8.5: 1080x1920/30fps/H.264/AAC,
  safe-zone, khung đen, freeze, silence, loudness); kết quả ghi kèm
  ``final_report.json`` và video không đạt bị chặn (``QA_FAILED``).
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable, Mapping

from adsup_central_hub.backend.production_jobs import (
    JOBS_DIR,
    load_job_artifact,
)
from apps.creator_article.video_renderer import (
    FINAL_VIDEO_ARGS,
    MIN_SEGMENT_SECONDS,
    build_render_plan,
    concat_segments,
    load_content_safe_zone,
    probe_video,
    render_segment_files,
)
from shared.core.beat_timeline import plan_beat_timeline
from shared.core.channel_editorial import TARGET_VOICE_SPEED
from shared.core.video_encoding import CLEAN_METADATA_ARGS, FINAL_AUDIO_ARGS
from shared.core.video_qa import run_video_qa
from shared.modules.subtitle_renderer import (
    generate_text_ass,
    generate_word_ass,
    get_subtitle_preset,
)
from shared.services.audio_director import plan_audio_cues
from shared.services.music_selector import build_ducked_mix_filter, select_music
from shared.services.tts_api import (
    DEFAULT_PROFILE_ID,
    create_voice_full_pipeline,
    probe_audio_duration,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SFX_DIR = os.path.join(PROJECT_ROOT, "assets", "sfx")


def resolve_voice_profile(id_tiktok: str, tone: str = "") -> str:
    """Voice ID theo kênh (voice_config.json: tone -> voice_id), mặc định chung."""

    config_path = os.path.join(
        PROJECT_ROOT, "assets", "channels", str(id_tiktok or ""), "voice_config.json"
    )
    try:
        import json

        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        if isinstance(config, Mapping):
            candidates = (
                (str(tone).strip(), "Trung tính", "trung_tinh", "default")
                if str(tone or "").strip()
                else ("Trung tính", "trung_tinh", "default")
            )
            for key in candidates:
                voice_id = str(config.get(key) or "").strip()
                if voice_id and "VD:" not in voice_id:
                    return voice_id
    except (OSError, ValueError):
        pass
    return DEFAULT_PROFILE_ID


def resolve_channel_overlay_config(id_tiktok: str) -> dict[str, Any]:
    """Đọc cấu hình frame_intro, frame_content, logo của kênh (nếu có trên đĩa)."""

    channel_id = str(id_tiktok or "").replace("@", "").strip()
    if not channel_id:
        return {}
    channel_dir = os.path.join(PROJECT_ROOT, "assets", "channels", channel_id)
    if not os.path.isdir(channel_dir):
        return {}

    custom_config: dict[str, Any] = {}
    config_path = os.path.join(channel_dir, "config.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                custom_config = loaded
        except (OSError, ValueError):
            pass

    frame_intro = os.path.join(channel_dir, "frame_intro.png")
    if (
        custom_config.get("frame_intro_disabled")
        or custom_config.get("has_frame_intro") is False
        or not os.path.isfile(frame_intro)
    ):
        frame_intro = ""

    frame_content = os.path.join(channel_dir, "frame_content.png")
    if (
        custom_config.get("frame_content_disabled")
        or custom_config.get("has_frame_content") is False
        or not os.path.isfile(frame_content)
    ):
        frame_content = ""

    logo_path = os.path.join(channel_dir, "logo.png")
    if (
        custom_config.get("logo_disabled")
        or custom_config.get("has_logo") is False
        or not os.path.isfile(logo_path)
    ):
        logo_path = ""

    return {
        "frame_intro_path": frame_intro,
        "frame_content_path": frame_content,
        "logo_path": logo_path,
        "logo_x": int(custom_config.get("logo_x", 50) or 50),
        "logo_y": int(custom_config.get("logo_y", 50) or 50),
    }


def produce_voice(
    directory: str,
    hook_text: str,
    script_text: str,
    id_tiktok: str,
    *,
    tone: str = "",
    tts_fn: Callable[..., str | None] | None = None,
) -> dict[str, Any]:
    """Sinh (hoặc tái dùng) hook/script voice trong ``job/voice``; đo duration thật."""

    tts_fn = tts_fn or create_voice_full_pipeline
    voice_dir = os.path.join(directory, "voice")
    os.makedirs(voice_dir, exist_ok=True)
    profile_id = resolve_voice_profile(id_tiktok, tone)

    result: dict[str, Any] = {}
    for name, text in (("hook_voice.wav", hook_text), ("script_voice.wav", script_text)):
        path = os.path.join(voice_dir, name)
        duration = probe_audio_duration(path)
        if duration <= 0:
            if not text:
                raise ValueError(f"TTS_FAILED: thiếu nội dung {name} trong kịch bản khoá.")
            path = tts_fn(text, voice_dir, name, profile_id, speed=TARGET_VOICE_SPEED)
            duration = probe_audio_duration(path) if path else 0.0
        if not path or duration <= 0:
            raise ValueError(f"TTS_FAILED: không tạo được {name} từ voice.adsup.vn.")
        result["hook_path" if name.startswith("hook") else "script_path"] = path
        result["hook_duration" if name.startswith("hook") else "script_duration"] = duration

    total = result["hook_duration"] + result["script_duration"]
    if total <= 0:
        raise ValueError("TTS_FAILED: tổng thời lượng voice không hợp lệ.")
    result["total_duration"] = round(total, 3)
    return result


def apply_real_timeline(segments: list[dict[str, Any]], timeline: Any) -> list[dict[str, Any]]:
    """Thay duration/start/transition của render plan bằng timeline audio thật."""

    timeline_segments = list(timeline.segments)
    if len(timeline_segments) != len(segments):
        raise ValueError(
            f"TIMELINE_MISMATCH: {len(segments)} segment vs {len(timeline_segments)} beat audio."
        )
    for segment, timeline_segment in zip(segments, timeline_segments):
        segment["duration"] = max(MIN_SEGMENT_SECONDS, round(float(timeline_segment.duration), 3))
        segment["start_sec"] = round(float(timeline_segment.start), 3)
        if timeline_segment.transition:
            segment["transition"] = str(timeline_segment.transition)
    return segments


def build_subtitle(
    directory: str,
    *,
    script_voice_path: str,
    script_text: str,
    hook_duration: float,
    script_duration: float,
    keywords: list[str],
    id_tiktok: str,
) -> tuple[str | None, str]:
    """Sinh ASS phụ đề ưu tiên trực tiếp từ script_text của JSON để chuẩn chính tả 100%;
    chỉ dùng Whisper dự phòng khi không có script_text.
    """

    preset = get_subtitle_preset(id_tiktok, {})
    ass_out = os.path.join(directory, "subs.ass")
    common = dict(
        time_offset=hook_duration,
        words_per_line=preset["max_words"],
        font_size=preset["font_size"],
        margin_v=preset["margin_v"],
        hex_color=preset["hex_color"],
        highlight_color=preset["highlight_color"],
        keywords=keywords,
        font_name=preset["font_name"],
        margin_l=preset["margin_l"],
        margin_r=preset["margin_r"],
        clamp_to_safe_zone=True,
    )
    path = None
    engine = "none"
    if str(script_text or "").strip():
        path = generate_text_ass(
            script_text,
            ass_out,
            duration=script_duration,
            **common,
        )
        engine = "text"
    if not path and script_voice_path:
        path = generate_word_ass(script_voice_path, ass_out, **common)
        engine = "whisper"
    if path and os.path.isfile(path) and os.path.getsize(path) > 0:
        return path, engine
    return None, "none"


def build_audio_filter(
    *,
    has_bgm: bool,
    bgm_input_index: int,
    total_duration: float,
    selection: Any = None,
    sfx_cues: list[Any] | None = None,
    sfx_input_start: int = 3,
) -> tuple[str, str]:
    """Filter âm thanh cuối: concat voice -> ducking BGM -> trộn SFX.

    Đầu vào: 0 video tĩnh, 1 hook, 2 script, 3 (tuỳ chọn) BGM, tiếp theo là SFX.
    Trả về (filter_complex_audio, output_label).
    """

    parts = ["[1:a][2:a]concat=n=2:v=0:a=1[a_voice]"]
    if has_bgm:
        parts.append(
            build_ducked_mix_filter(
                "a_voice",
                f"{bgm_input_index}:a",
                total_duration,
                selection,
                output_label="a_merged",
                label_prefix="final_music",
            )
        )
    else:
        parts.append("[a_voice]loudnorm=I=-14:LRA=9:TP=-1.5[a_merged]")

    cues = list(sfx_cues or [])
    if not cues:
        return ";".join(parts), "a_merged"

    sfx_labels = []
    for index, cue in enumerate(cues):
        delay_ms = int(float(cue.timestamp) * 1000)
        parts.append(
            f"[{sfx_input_start + index}:a]adelay={delay_ms}|{delay_ms},"
            f"volume={float(cue.gain):.2f}[sfx{index}]"
        )
        sfx_labels.append(f"[sfx{index}]")
    parts.append(
        "[a_merged]" + "".join(sfx_labels)
        + f"amix=inputs={1 + len(cues)}:duration=first:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.84[a_out]"
    )
    return ";".join(parts), "a_out"


def _escape_ass_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render_final_video(
    job_id: str,
    *,
    jobs_dir: str | None = None,
    out_name: str = "final.mp4",
) -> dict[str, Any]:
    """Dựng video hoàn chỉnh cho job. Ném ValueError/ValueError-like để API map."""

    from adsup_central_hub.backend.production_jobs import load_job

    directory = os.path.join(jobs_dir or JOBS_DIR, str(job_id or ""))
    storyboard = load_job_artifact(job_id, "storyboard", jobs_dir=jobs_dir)
    if not storyboard or not storyboard.get("beats"):
        raise ValueError("STORYBOARD_MISSING")
    media_plan = load_job_artifact(job_id, "media_plan", jobs_dir=jobs_dir)
    if not media_plan or not media_plan.get("beats"):
        raise ValueError("MEDIA_PLAN_MISSING")
    manifest = load_job_artifact(job_id, "assets_manifest", jobs_dir=jobs_dir) or []
    source_doc = load_job_artifact(job_id, "source", jobs_dir=jobs_dir) or {}
    meta = load_job(job_id, jobs_dir=jobs_dir) or {}
    id_tiktok = str(meta.get("id_tiktok") or meta.get("channel_id") or "")
    tone = str(storyboard.get("tone") or source_doc.get("tone") or "")
    music_cfg = storyboard.get("music") or {}
    mood = str(music_cfg.get("mood") or "neutral_news")
    energy = music_cfg.get("energy", 2)
    is_sensitive = bool(music_cfg.get("is_sensitive", False))

    warnings: list[str] = []

    # 1) Voice thật + thời lượng thật
    voice = produce_voice(
        directory,
        str(storyboard.get("hook") or ""),
        str(storyboard.get("script_voice") or ""),
        id_tiktok,
        tone=tone,
    )
    total_duration = float(voice["total_duration"])

    # 2) Re-time beat theo audio thật
    timeline = plan_beat_timeline(
        storyboard.get("beats"),
        total_duration=total_duration,
        hook_duration=float(voice["hook_duration"]),
        media_count=len(storyboard.get("beats") or []),
        hook_text=str(storyboard.get("hook") or ""),
        script_text=str(storyboard.get("script_voice") or ""),
    )

    safe = load_content_safe_zone()
    plan = build_render_plan(storyboard, media_plan, manifest, job_dir=directory, safe=safe)
    segments = plan["segments"]
    warnings.extend(plan["warnings"])
    apply_real_timeline(segments, timeline)

    # 3) Render segment (tái dùng renderer Giai đoạn 3) + nối không âm thanh
    render_dir = os.path.join(directory, "render")
    os.makedirs(render_dir, exist_ok=True)
    concat_path = os.path.join(directory, "final_silent.mp4")
    seg_paths: list[str] = []
    try:
        seg_paths = render_segment_files(segments, render_dir=render_dir, safe=safe)
        concat_segments(
            seg_paths,
            concat_path,
            list_path=os.path.join(render_dir, "concat_final.txt"),
        )
    finally:
        for path in seg_paths:
            try:
                os.unlink(path)
            except OSError:
                pass

    # 4) Phụ đề
    keywords = [value for segment in segments for value in (segment.get("must_show") or []) if value]
    subtitle_path, subtitle_engine = build_subtitle(
        directory,
        script_voice_path=voice["script_path"],
        script_text=str(storyboard.get("script_voice") or ""),
        hook_duration=float(voice["hook_duration"]),
        script_duration=float(voice["script_duration"]),
        keywords=keywords,
        id_tiktok=id_tiktok,
    )
    if subtitle_path is None:
        warnings.append("Không tạo được phụ đề — xuất video không có subtitle.")

    # 5) BGM (chỉ license approved) + SFX
    selection = select_music(
        mood,
        tone=tone or None,
        energy=energy,
        is_sensitive=is_sensitive,
        channel_id=id_tiktok,
    )
    if selection and selection.license_status != "approved":
        warnings.append(
            f"BGM {selection.track_id} có license_status={selection.license_status} — bỏ nhạc."
        )
        selection = None
    if selection:
        print(
            f"   🎵 BGM: {os.path.basename(str(selection.path))} | mood={selection.mood} | "
            f"bed={selection.bed_lufs:.1f} LUFS"
        )
    sfx_cues = plan_audio_cues(timeline, is_sensitive=is_sensitive, sfx_dir=SFX_DIR)
    if sfx_cues:
        print(f"   🔊 AudioDirector: {len(sfx_cues)} SFX")

    # 6) Encode cuối: frame/logo kênh (nếu có) + burn phụ đề + mix âm thanh
    output_path = os.path.join(directory, out_name)
    audio_filter, audio_label = build_audio_filter(
        has_bgm=selection is not None,
        bgm_input_index=3,
        total_duration=total_duration,
        selection=selection,
        sfx_cues=sfx_cues,
        sfx_input_start=4 if selection else 3,
    )
    filter_parts = [audio_filter]
    args: list[str] = ["-i", concat_path, "-i", voice["hook_path"], "-i", voice["script_path"]]
    if selection:
        # Giới hạn BGM bằng -t thay vì -shortest: ffmpeg 6.1 kết hợp -shortest
        # với -stream_loop -1 dừng encode sớm (~3s cuối bị cắt, mất câu kết).
        args += ["-stream_loop", "-1", "-t", f"{total_duration:.3f}", "-i", str(selection.path)]
    for cue in sfx_cues:
        args += ["-i", str(cue.asset_path)]

    next_input_idx = (4 if selection else 3) + len(sfx_cues)
    overlay_cfg = resolve_channel_overlay_config(id_tiktok)
    frame_intro_path = overlay_cfg.get("frame_intro_path") or ""
    frame_content_path = overlay_cfg.get("frame_content_path") or ""
    logo_path = overlay_cfg.get("logo_path") or ""
    hook_dur = float(voice["hook_duration"])
    cur_v = "0:v"

    if frame_intro_path and frame_content_path:
        tf_idx = next_input_idx
        cf_idx = next_input_idx + 1
        next_input_idx += 2
        args += [
            "-loop", "1", "-t", f"{total_duration:.3f}", "-i", frame_intro_path,
            "-loop", "1", "-t", f"{total_duration:.3f}", "-i", frame_content_path,
        ]
        filter_parts.append(
            f"[{cur_v}][{tf_idx}:v]overlay=0:0:shortest=1:enable='between(t,0,{hook_dur:.3f})'[v_tf]"
        )
        filter_parts.append(
            f"[v_tf][{cf_idx}:v]overlay=0:0:shortest=1:enable='gt(t,{hook_dur:.3f})'[v_cf]"
        )
        cur_v = "v_cf"
    elif frame_intro_path:
        tf_idx = next_input_idx
        next_input_idx += 1
        args += ["-loop", "1", "-t", f"{total_duration:.3f}", "-i", frame_intro_path]
        filter_parts.append(
            f"[{cur_v}][{tf_idx}:v]overlay=0:0:shortest=1:enable='between(t,0,{hook_dur:.3f})'[v_tf]"
        )
        cur_v = "v_tf"
    elif frame_content_path:
        cf_idx = next_input_idx
        next_input_idx += 1
        args += ["-loop", "1", "-t", f"{total_duration:.3f}", "-i", frame_content_path]
        filter_parts.append(f"[{cur_v}][{cf_idx}:v]overlay=0:0:shortest=1[v_cf]")
        cur_v = "v_cf"

    if logo_path:
        logo_idx = next_input_idx
        next_input_idx += 1
        lx = int(overlay_cfg.get("logo_x", 50))
        ly = int(overlay_cfg.get("logo_y", 50))
        args += ["-loop", "1", "-t", f"{total_duration:.3f}", "-i", logo_path]
        filter_parts.append(f"[{cur_v}][{logo_idx}:v]overlay={lx}:{ly}:shortest=1[v_logo]")
        cur_v = "v_logo"

    if subtitle_path:
        filter_parts.append(f"[{cur_v}]ass={_escape_ass_path(subtitle_path)}[vout]")
        video_map = "[vout]"
    else:
        video_map = f"[{cur_v}]" if cur_v != "0:v" else "0:v"

    args += [
        "-filter_complex", ";".join(filter_parts),
        "-map", video_map,
        "-map", f"[{audio_label}]",
        *FINAL_VIDEO_ARGS,
        *FINAL_AUDIO_ARGS,
        *CLEAN_METADATA_ARGS,
        output_path,
    ]
    _run_ffmpeg(args, what="dựng video hoàn chỉnh")

    try:
        os.unlink(concat_path)
    except OSError:
        pass

    # 7) VideoQA bắt buộc — ghi kết quả vào report trước, không đạt thì chặn.
    qa = run_video_qa(output_path, subtitle_ass_path=subtitle_path or "")
    report = {
        "output": out_name,
        "mode": "final",
        "timeline_source": "tts_real",
        "segment_count": len(segments),
        "voice": {
            "hook_duration": round(float(voice["hook_duration"]), 3),
            "script_duration": round(float(voice["script_duration"]), 3),
            "total_duration": round(total_duration, 3),
            "profile_id": resolve_voice_profile(id_tiktok, tone),
        },
        "bgm": (
            {
                "track_id": selection.track_id,
                "mood": selection.mood,
                "energy": selection.energy,
                "license_status": selection.license_status,
                "bed_lufs": selection.bed_lufs,
            }
            if selection
            else None
        ),
        "subtitle": {"engine": subtitle_engine, "path": os.path.basename(subtitle_path) if subtitle_path else None},
        "sfx_count": len(sfx_cues),
        "warnings": warnings,
        "probe": probe_video(output_path),
        "video_qa": qa.to_dict(),
    }
    _atomic_write_report(os.path.join(directory, "final_report.json"), report)
    if not qa.passed:
        raise ValueError("QA_FAILED: " + ",".join(qa.blocking_errors))
    return {"report": report, "output_path": output_path}


def _run_ffmpeg(args: list[str], *, what: str) -> None:
    binary = os.getenv("FFMPEG_BINARY", "ffmpeg")
    result = subprocess.run(
        [binary, "-y", *args], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        raise RuntimeError(f"FFmpeg lỗi khi {what}: {tail}")


def _atomic_write_report(path: str, payload: dict[str, Any]) -> None:
    import tempfile

    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False, suffix=".tmp")
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
