"""Render an approved News Video Production JSON v2 plan with HyperFrames.

This is deliberately isolated from the legacy FFmpeg article slideshow.  It
receives an operator-approved JSON file and optional downloaded stock assets;
it never crawls the publisher page or DuckDuckGo.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
from pathlib import Path
import json
import shutil
import subprocess
import sys
import uuid

from apps.news_hyperframes.production_json import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    ProductionJsonError,
    ProductionPlan,
    approved_local_assets,
    filename_safe,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOB_ROOT = PROJECT_ROOT / "data" / "news_hyperframes_jobs"
HYPERFRAMES_VERSION = "0.9.26"


@dataclass(frozen=True)
class RenderResult:
    job_dir: Path
    project_dir: Path
    output_path: Path
    approved_assets: int


def _copy_asset(path: Path, assets_dir: Path, asset_id: str) -> str:
    suffix = path.suffix.lower()
    filename = f"{filename_safe(asset_id, 'stock')}{suffix}"
    destination = assets_dir / filename
    shutil.copy2(path, destination)
    return f"assets/{filename}"


def _asset_markup(asset_path: str | None, alt: str) -> str:
    if not asset_path:
        return '<div class="fallback-orb" aria-hidden="true"></div>'
    safe_path = escape(asset_path, quote=True)
    if Path(asset_path).suffix.lower() in VIDEO_EXTENSIONS:
        return (
            f'<video class="beat-media" src="{safe_path}" muted playsinline preload="auto"></video>'
        )
    return f'<img class="beat-media" src="{safe_path}" alt="{escape(alt, quote=True)}" />'


def _scene_document(index: int, beat: object, media_path: str | None, total: int) -> str:
    """Return one mounted scene as a HyperFrames sub-composition."""
    primary = escape(beat.on_screen_text, quote=False)
    fallback = escape(beat.visual_fallback, quote=False)
    media = _asset_markup(media_path, beat.on_screen_text)
    return f'''<template id="scene-{index}-template">
  <div data-composition-id="scene-{index}" data-width="1080" data-height="1920" data-duration="{beat.duration:.3f}">
    <div class="scene-media">{media}</div>
    <div class="scene-scrim"></div>
    <div id="scene-{index}-content" class="scene-content">
      <div class="eyebrow"><span class="eyebrow-index">{index:02d}</span><span>NEWS BRIEF</span></div>
      <div id="scene-{index}-rule" class="scene-rule"></div>
      <h2>{primary}</h2>
      <p class="fallback-note">{fallback}</p>
    </div>
    <div id="caption-{index}" class="caption">{escape(beat.voice_over, quote=False)}</div>
    <div id="progress-{index}" class="progress"></div>
    <style>
      [data-composition-id="scene-{index}"] {{ position:relative; width:1080px; height:1920px; overflow:hidden; color:#F5F1E8; font-family:"Outfit",Arial,sans-serif; background:#13171D; }}
      [data-composition-id="scene-{index}"] .scene-media {{ position:absolute; inset:0; background:#20252C; overflow:hidden; }}
      [data-composition-id="scene-{index}"] .beat-media {{ width:100%; height:100%; display:block; object-fit:cover; filter:saturate(.78) contrast(1.04); }}
      [data-composition-id="scene-{index}"] .scene-scrim {{ position:absolute; inset:0; background:linear-gradient(180deg,rgba(19,23,29,.24) 0%,rgba(19,23,29,.38) 42%,rgba(19,23,29,.94) 100%); }}
      [data-composition-id="scene-{index}"] .fallback-orb {{ position:absolute; width:980px; height:980px; left:-240px; top:170px; border-radius:50%; background:#2B3440; box-shadow:370px 430px 0 -190px #202A36; }}
      [data-composition-id="scene-{index}"] .fallback-orb::after {{ content:""; position:absolute; width:330px; height:330px; right:-80px; top:310px; border:22px solid #F4A340; border-radius:50%; opacity:.86; }}
      [data-composition-id="scene-{index}"] .scene-content {{ position:absolute; left:72px; right:72px; bottom:490px; z-index:3; }}
      [data-composition-id="scene-{index}"] .eyebrow {{ display:flex; gap:18px; align-items:center; color:#AEB4BF; font-size:25px; font-weight:750; letter-spacing:.13em; }}
      [data-composition-id="scene-{index}"] .eyebrow-index {{ color:#F4A340; font-variant-numeric:tabular-nums; }}
      [data-composition-id="scene-{index}"] .scene-rule {{ width:110px; height:8px; margin:26px 0 30px; background:#F4A340; }}
      [data-composition-id="scene-{index}"] h2 {{ max-width:890px; font-size:76px; line-height:1.05; letter-spacing:-.052em; font-weight:800; text-wrap:balance; }}
      [data-composition-id="scene-{index}"] .fallback-note {{ max-width:760px; margin-top:28px; color:#AEB4BF; font-size:27px; line-height:1.35; font-weight:550; }}
      [data-composition-id="scene-{index}"] .caption {{ position:absolute; z-index:5; left:72px; right:96px; bottom:216px; padding:22px 25px; border-left:7px solid #F4A340; background:rgba(19,23,29,.88); color:#F5F1E8; font-size:35px; font-weight:700; line-height:1.25; letter-spacing:-.025em; }}
      [data-composition-id="scene-{index}"] .progress {{ position:absolute; z-index:6; left:72px; bottom:136px; width:936px; height:7px; background:#F4A340; transform-origin:left center; }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <script>
      const tl = gsap.timeline({{ paused:true, defaults:{{ ease:"power2.out" }} }});
      tl.from("#scene-{index}-content", {{ autoAlpha:0, y:42, duration:.42, ease:"power3.out" }}, 0);
      tl.from("#caption-{index}", {{ autoAlpha:0, y:22, duration:.30 }}, .18);
      tl.from("#scene-{index}-rule", {{ scaleX:0, transformOrigin:"left center", duration:.36 }}, .10);
      tl.from("#progress-{index}", {{ scaleX:0, transformOrigin:"left center", duration:.44 }}, 0);
      window.__timelines = window.__timelines || {{}};
      window.__timelines["scene-{index}"] = tl;
      tl.seek(0);
    </script>
  </div>
</template>'''


def build_composition(plan: ProductionPlan, asset_paths: dict[str, str], voice_relative: str | None, music_relative: str | None) -> tuple[str, dict[str, str]]:
    """Create one deterministic, seekable 1080x1920 HyperFrames composition."""
    audio = ""
    if voice_relative:
        audio += f'<audio id="voice-track" class="audio-track clip" src="{escape(voice_relative, quote=True)}" data-start="0" data-duration="{plan.duration_sec:.3f}"></audio>'
    if music_relative:
        audio += f'<audio id="music-track" class="music-track clip" src="{escape(music_relative, quote=True)}" data-start="0" data-duration="{plan.duration_sec:.3f}"></audio>'
    title = escape(plan.title, quote=False)
    scene_hosts = []
    scene_files: dict[str, str] = {}
    for index, beat in enumerate(plan.beats, start=1):
        media_path = next((asset_paths[item] for item in beat.asset_ids if item in asset_paths), None)
        scene_files[f"scene-{index}.html"] = _scene_document(index, beat, media_path, len(plan.beats))
        scene_hosts.append(
            f'<div id="scene-host-{index}" class="clip" data-composition-id="scene-{index}" '
            f'data-composition-src="compositions/scene-{index}.html" data-start="{beat.start_sec:.3f}" '
            f'data-duration="{beat.duration:.3f}" data-track-index="{index}"></div>'
        )
    root = f'''<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=1080, height=1920" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
  <style>
    :root {{ --ground:#13171D; --ink:#F5F1E8; --muted:#AEB4BF; --accent:#F4A340; }}
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    html, body {{ width:1080px; height:1920px; overflow:hidden; background:var(--ground); }}
    #root {{ width:1080px; height:1920px; overflow:hidden; position:relative; font-family:"Outfit",Arial,sans-serif; color:var(--ink); background:var(--ground); }}
    .clip {{ position:absolute; inset:0; width:100%; height:100%; overflow:hidden; }}
    h1 {{ position:absolute; top:112px; left:72px; right:72px; z-index:8; font-size:30px; font-weight:700; color:var(--ink); letter-spacing:-.02em; }}
    .audio-track,.music-track {{ display:none; }}
  </style>
</head>
<body>
  <div id="root" data-composition-id="news-main" data-start="0" data-duration="{plan.duration_sec:.3f}" data-width="1080" data-height="1920">
    <h1 id="hero-title" class="clip" data-start="0" data-duration="{plan.duration_sec:.3f}">{title}</h1>
    {chr(10).join(scene_hosts)}
    {audio}
  </div>
  <script>
    const tl = gsap.timeline({{ paused:true, defaults:{{ ease:"power2.out" }} }});
    window.__timelines = window.__timelines || {{}};
    window.__timelines["news-main"] = tl;
    tl.seek(0);
  </script>
</body>
</html>'''
    return root, scene_files


def _write_project_files(job_dir: Path, composition: str, scene_files: dict[str, str] | None = None) -> Path:
    project_dir = job_dir / "hyperframes"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "assets").mkdir(exist_ok=True)
    compositions_dir = project_dir / "compositions"
    compositions_dir.mkdir(exist_ok=True)
    for filename, content in (scene_files or {}).items():
        (compositions_dir / filename).write_text(content, encoding="utf-8")
    (project_dir / "index.html").write_text(composition, encoding="utf-8")
    (project_dir / "hyperframes.json").write_text(
        json.dumps({"$schema": "https://hyperframes.heygen.com/schema/hyperframes.json", "paths": {"assets": "assets"}}, indent=2),
        encoding="utf-8",
    )
    (project_dir / "package.json").write_text(
        json.dumps({"private": True, "type": "module", "scripts": {"check": f"npx --yes hyperframes@{HYPERFRAMES_VERSION} check", "render": f"npx --yes hyperframes@{HYPERFRAMES_VERSION} render"}}, indent=2),
        encoding="utf-8",
    )
    return project_dir


def _create_voice(plan: ProductionPlan, destination: Path, voice_id: str) -> Path:
    from shared.services.tts_api import create_voice_full_pipeline

    output = create_voice_full_pipeline(plan.voice_over, str(destination.parent), destination.name, voice_id)
    if not output:
        raise RuntimeError("Không tạo được voice-over từ dịch vụ TTS.")
    return Path(output)


def render_plan(
    json_path: str | Path,
    *,
    asset_root: str | Path | None = None,
    voice_path: str | Path | None = None,
    voice_id: str = "",
    music_path: str | Path | None = None,
    render: bool = False,
) -> RenderResult:
    """Validate and prepare a job; `render=True` invokes HyperFrames explicitly."""
    plan = ProductionPlan.from_path(json_path)
    job_dir = JOB_ROOT / f"{filename_safe(plan.title)}-{uuid.uuid4().hex[:8]}"
    job_dir.mkdir(parents=True, exist_ok=False)
    (job_dir / "production.json").write_text(json.dumps(plan.raw, ensure_ascii=False, indent=2), encoding="utf-8")
    project_dir = _write_project_files(job_dir, "")
    assets_dir = project_dir / "assets"
    approved = approved_local_assets(plan, asset_root)
    copied_assets = {asset_id: _copy_asset(path, assets_dir, asset_id) for asset_id, path in approved.items()}

    copied_voice: str | None = None
    if voice_path:
        voice_source = Path(voice_path).expanduser().resolve()
        if not voice_source.is_file():
            raise FileNotFoundError(f"Không tìm thấy voice-over: {voice_source}")
        copied_voice = _copy_asset(voice_source, assets_dir, "voice-over")
    elif voice_id:
        created_voice = _create_voice(plan, job_dir / "voice-over.wav", voice_id)
        copied_voice = _copy_asset(created_voice, assets_dir, "voice-over")

    copied_music: str | None = None
    if music_path:
        music_source = Path(music_path).expanduser().resolve()
        if not music_source.is_file():
            raise FileNotFoundError(f"Không tìm thấy nhạc nền: {music_source}")
        copied_music = _copy_asset(music_source, assets_dir, "music-bed")

    composition, scene_files = build_composition(plan, copied_assets, copied_voice, copied_music)
    (project_dir / "index.html").write_text(composition, encoding="utf-8")
    for filename, content in scene_files.items():
        (project_dir / "compositions" / filename).write_text(content, encoding="utf-8")
    output_path = project_dir / "renders" / "news-video.mp4"
    if render:
        if not copied_voice:
            raise ProductionJsonError("Cần --voice-path hoặc --voice-id trước khi xuất MP4 có lời đọc.")
        command = ["npx", "--yes", f"hyperframes@{HYPERFRAMES_VERSION}", "check"]
        subprocess.run(command, cwd=project_dir, check=True)
        subprocess.run(["npx", "--yes", f"hyperframes@{HYPERFRAMES_VERSION}", "render"], cwd=project_dir, check=True)
    return RenderResult(job_dir, project_dir, output_path, len(copied_assets))


def main() -> int:
    parser = argparse.ArgumentParser(description="Dựng JSON v2 bằng HyperFrames.")
    parser.add_argument("json_path", help="News Video Production JSON v2 đã tải từ ChatGPT")
    parser.add_argument("--asset-root", help="Thư mục chỉ chứa real stock đã được cấp phép")
    parser.add_argument("--voice-path", help="File voice-over đã duyệt")
    parser.add_argument("--voice-id", help="Voice ID Voicebox để tạo tiếng Việt")
    parser.add_argument("--music-path", help="File nhạc đã có license approved")
    parser.add_argument("--render", action="store_true", help="Lint và xuất MP4 bằng HyperFrames")
    args = parser.parse_args()
    try:
        result = render_plan(
            args.json_path,
            asset_root=args.asset_root,
            voice_path=args.voice_path,
            voice_id=args.voice_id,
            music_path=args.music_path,
            render=args.render,
        )
    except (ProductionJsonError, FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"job_dir": str(result.job_dir), "project_dir": str(result.project_dir), "output_path": str(result.output_path), "approved_assets": result.approved_assets}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
