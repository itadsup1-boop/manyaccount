from fastapi import FastAPI, HTTPException, Query, Request, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
import os
import json
import time
import mimetypes
import sys
import signal
from dotenv import load_dotenv

# Load env file from the parent directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from shared.core.prompt_builder import (
    DEFAULT_CONTENT_PROFILE,
    extract_operator_overrides,
    get_content_profile,
    merge_content_profiles,
)
from shared.core.performance_dashboard import (
    dashboard_compat_stats,
    load_performance_dashboard,
)
from shared.core.quality_log import DEFAULT_QUALITY_LOG_PATH
from shared.services.performance_store import DEFAULT_PERFORMANCE_DB
from adsup_central_hub.backend.facebook_auth import FacebookAuthManager
from adsup_central_hub.backend.facebook_group_sources import (
    normalize_group_api_source,
    prepare_group_api_source_payload,
)
from adsup_central_hub.backend.facebook_group_review import (
    FacebookGroupReviewService,
)
from adsup_central_hub.backend.facebook_sources import (
    normalize_api_source,
    prepare_api_source_payload,
)

ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
# The project .env is the source of truth for a local Windows run. Override
# stale shell variables left by an earlier launcher/session.
load_dotenv(ENV_FILE, override=True)

PERFORMANCE_DB_PATH = os.getenv("PERFORMANCE_DB_PATH", DEFAULT_PERFORMANCE_DB)
QUALITY_LOG_PATH = os.getenv("QUALITY_LOG_PATH", DEFAULT_QUALITY_LOG_PATH)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client = None
_supabase_key_is_placeholder = not SUPABASE_KEY or SUPABASE_KEY.startswith("your_")
if SUPABASE_URL and SUPABASE_KEY and not _supabase_key_is_placeholder:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except BaseException as e:
        print(f"Error connecting to Supabase: {e}")

# Reuse the client used by the existing desktop pipelines when the local
# .env still contains the template placeholder. A real .env key overrides it.
if supabase_client is None:
    try:
        from shared.services.supabase_api import supabase as shared_supabase
        supabase_client = shared_supabase
        print("Using shared Supabase client; set SUPABASE_KEY in .env to override it.")
    except Exception as e:
        print(f"Shared Supabase client unavailable: {e}")

app = FastAPI(title="Adsup Central Hub API")
facebook_auth_manager = FacebookAuthManager(PROJECT_ROOT)
facebook_group_review_service = FacebookGroupReviewService(
    supabase_client,
    os.getenv("DRIVE_FOLDER_ID") or os.getenv("GDRIVE_FOLDER_ID") or "",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _running_process_count() -> int:
    process_names = (
        "pipeline_process",
        "fb_pipeline_process",
        "tiktok_process",
        "clone_worker_process",
    )
    return sum(
        process is not None and process.poll() is None
        for name in process_names
        if (process := globals().get(name)) is not None
    )


def _load_dashboard(**filters):
    try:
        return load_performance_dashboard(
            db_path=PERFORMANCE_DB_PATH,
            quality_log_path=QUALITY_LOG_PATH,
            **filters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/dashboard/performance")
def get_dashboard_performance(
    start_date: str = "",
    end_date: str = "",
    channel_id: str = "",
    measurement_window: str = "",
    min_samples: int = Query(default=30, ge=1, le=1000),
):
    return _load_dashboard(
        start_date=start_date,
        end_date=end_date,
        channel_id=channel_id,
        measurement_window=measurement_window,
        min_samples=min_samples,
    )


@app.get("/api/dashboard/pipeline-errors")
def get_dashboard_pipeline_errors(
    start_date: str = "",
    end_date: str = "",
    channel_id: str = "",
):
    dashboard = _load_dashboard(
        start_date=start_date,
        end_date=end_date,
        channel_id=channel_id,
    )
    return {
        "generated_at": dashboard["generated_at"],
        "filters": dashboard["filters"],
        "pipeline": dashboard["pipeline"],
    }


@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    dashboard = _load_dashboard()
    return dashboard_compat_stats(
        dashboard,
        active_tools=_running_process_count(),
    )

@app.get("/api/article/sources")
def get_article_sources():
    if not supabase_client:
        return {"error": "Supabase client not initialized"}
    try:
        res = supabase_client.table("article_sources").select("*").execute()
        return res.data
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/article/sources")
async def add_article_source(request: Request):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        data = await request.json()
        res = supabase_client.table("article_sources").insert(data).execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        return {"error": str(e)}

@app.put("/api/article/sources/{source_id}")
async def update_article_source(source_id: int, request: Request):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        data = await request.json()
        res = supabase_client.table("article_sources").update(data).eq("id", source_id).execute()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/api/article/sources/{source_id}")
def delete_article_source(source_id: int):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        res = supabase_client.table("article_sources").delete().eq("id", source_id).execute()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

import subprocess
import threading


def _stop_process_tree(process, process_group_id=None, timeout_seconds=5):
    """Stop a process and every worker it spawned.

    The TikTok scheduler starts account workers with ``Popen`` and redirects
    their output to files. Terminating only the scheduler therefore leaves
    those workers alive. The scheduler is started in its own process group so
    the whole batch can be stopped as one unit.
    """
    if process is None and process_group_id is None:
        return

    if os.name == "nt":
        if process is None:
            return
        # ``/T`` includes descendants; ``/F`` prevents a stuck browser worker
        # from surviving after the operator pressed Stop.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return

    try:
        if process_group_id is None:
            if process.poll() is not None:
                return
            process_group_id = os.getpgid(process.pid)
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.monotonic() + timeout_seconds
    while (
        process is not None
        and process.poll() is None
        and time.monotonic() < deadline
    ):
        time.sleep(0.1)

    if process is None or process.poll() is None:
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass

# Global state for the running pipeline process
pipeline_process = None
pipeline_logs = ["[Hệ thống] Sẵn sàng khởi động Tool Tin Tức..."]

def get_synced_content_profile(channel_id: str):
    """Profile trung tâm cộng override đã lưu, không có default viết cứng tại Hub."""
    clean_id = str(channel_id or "").replace("@", "").strip()
    synced = {}
    try:
        synced = get_tiktok_content_profiles().get(clean_id, {})
    except Exception:
        synced = {}
    return get_content_profile(clean_id, synced, include_runtime=False)


def read_logs(process):
    global pipeline_logs
    for line in iter(process.stdout.readline, ""):
        line = line.strip()
        if line:
            pipeline_logs.append(line)
            if len(pipeline_logs) > 200:
                pipeline_logs.pop(0)

@app.post("/api/article/start")
def start_article_tool():
    global pipeline_process, pipeline_logs
    if pipeline_process and pipeline_process.poll() is None:
        return {"status": "error", "message": "Pipeline is already running"}
        
    pipeline_logs = ["[Hệ thống] Đang khởi động tiến trình ngầm..."]
    
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    cmd = [python_exe, "-u", "apps/creator_article/article_pipeline_core.py", "start"]
    
    pipeline_process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        bufsize=1
    )
    
    threading.Thread(target=read_logs, args=(pipeline_process,), daemon=True).start()
    return {"status": "started", "message": "Article tool started"}

@app.post("/api/article/stop")
def stop_article_tool():
    global pipeline_process, pipeline_logs
    if pipeline_process and pipeline_process.poll() is None:
        pipeline_process.terminate()
        pipeline_process = None
        pipeline_logs.append("[Hệ thống] Đã gửi lệnh dừng an toàn (Terminate).")
        return {"status": "stopped", "message": "Article tool stopped"}
    return {"status": "error", "message": "No running pipeline found"}

@app.get("/api/article/logs")
def get_article_logs():
    is_running = pipeline_process is not None and pipeline_process.poll() is None
    return {"logs": pipeline_logs, "is_running": is_running}

@app.get("/api/article/processed-links")
def get_article_processed_links(limit: int = 300, search: str = ""):
    if not supabase_client:
        return {"error": "Supabase not initialized"}
    try:
        safe_limit = max(1, min(int(limit or 300), 1000))
        search_text = str(search or "").strip().lower()
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        fallback_path = os.path.join(project_root, "data", "article_processed_links.json")

        raw_items = []

        try:
            res = supabase_client.table("processed_links").select("*").limit(1000).execute()
            for item in res.data or []:
                if isinstance(item, dict) and str(item.get("url") or "").strip():
                    row = dict(item)
                    row.setdefault("source", "processed_links")
                    raw_items.append(row)
        except Exception:
            pass

        try:
            if os.path.exists(fallback_path):
                with open(fallback_path, "r", encoding="utf-8") as f:
                    local_data = json.load(f)
                if isinstance(local_data, list):
                    for item in local_data:
                        if isinstance(item, str):
                            row = {"url": item.strip(), "source": "local_fallback"}
                        elif isinstance(item, dict):
                            row = dict(item)
                            row.setdefault("source", "local_fallback")
                        else:
                            continue
                        if str(row.get("url") or "").strip():
                            raw_items.append(row)
        except Exception:
            pass

        try:
            db_res = supabase_client.table("system_configs").select("config_value").eq("config_name", ARTICLE_PROCESSED_LINKS_CONFIG_KEY).execute()
            db_links = (db_res.data or [{}])[0].get("config_value") or []
            if isinstance(db_links, list):
                for link in db_links:
                    clean_link = str(link or "").strip()
                    if clean_link:
                        raw_items.append({"url": clean_link, "source": "system_configs"})
        except Exception:
            pass

        try:
            sources_res = supabase_client.table("article_sources").select("id,id_tiktok,category_url,last_article_url,created_at").execute()
            for source in sources_res.data or []:
                checkpoint_url = str(source.get("last_article_url") or "").strip()
                if checkpoint_url:
                    raw_items.append({
                        "url": checkpoint_url,
                        "source": "last_article_url",
                        "id_tiktok": source.get("id_tiktok"),
                        "category_url": source.get("category_url"),
                        "created_at": source.get("created_at"),
                    })
        except Exception:
            pass

        deduped = []
        seen = set()
        for item in raw_items:
            url = str(item.get("url") or "").strip()
            if not url or url in seen:
                continue
            if search_text and search_text not in url.lower():
                continue
            seen.add(url)
            deduped.append(item)

        deduped.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        items = deduped[:safe_limit]
        counts = {}
        for item in deduped:
            url = str(item.get("url") or "").strip()
            if url:
                counts[url] = counts.get(url, 0) + 1
        duplicates = [{"url": url, "count": count} for url, count in counts.items() if count > 1]

        return {"items": items, "count": len(items), "duplicates": duplicates, "search": search_text}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/article/config/{channel_id}")
def get_channel_config(channel_id: str):
    import json
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    config_path = os.path.join(project_root, "assets", "channels", channel_id, "config.json")
    
    cfg = {
        "text_y1": 0.73, "text_y2": 0.83, "text_w": 0.65, "text_x": 0,
        "text_size": 45, "text_color": "#ffffff", "text_stroke": 0,
        "text_font": "RobotoCondensed-Bold.ttf",
        "text_position_mode": "manual",
        # Vị trí title khi video đã chuyển sang frame content (tỷ lệ 0-1 theo
        # chiều cao khung). 0 = tự tính thấp hơn vị trí ở frame title.
        "text_y_content": 0,
        "content_profile": dict(DEFAULT_CONTENT_PROFILE),
    }
    custom_config = {}
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                custom_config = json.load(f)
                cfg.update(custom_config)
        except:
            pass

    cfg["content_profile"] = merge_content_profiles(
        get_synced_content_profile(channel_id),
        custom_config.get("content_profile")
    )
            
    # Check for images locally
    channel_dir = os.path.join(project_root, "assets", "channels", channel_id)
    cfg["has_frame_intro"] = os.path.exists(os.path.join(channel_dir, "frame_intro.png")) and not cfg.get("frame_intro_disabled", False)
    cfg["frame_intro_name"] = cfg.get("frame_intro_name", "frame_intro.png")
    
    cfg["has_frame_content"] = os.path.exists(os.path.join(channel_dir, "frame_content.png")) and not cfg.get("frame_content_disabled", False)
    cfg["frame_content_name"] = cfg.get("frame_content_name", "frame_content.png")
    
    cfg["has_logo"] = os.path.exists(os.path.join(channel_dir, "logo.png")) and not cfg.get("logo_disabled", False)
    cfg["logo_name"] = cfg.get("logo_name", "logo.png")
    
    return cfg

@app.get("/api/article/channel-image/{channel_id}/{image_name}")
def get_channel_image(channel_id: str, image_name: str):
    """Serve frame/logo PNG images from channel assets directory."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    # Only allow specific image names for security
    allowed_names = ["frame_intro.png", "frame_content.png", "frame.png", "logo.png"]
    if image_name not in allowed_names:
        return Response(status_code=404)
    image_path = os.path.join(project_root, "assets", "channels", channel_id, image_name)
    if os.path.exists(image_path):
        return FileResponse(image_path, media_type="image/png")
    return Response(status_code=404)


@app.get("/api/tiktok/frame-image/{image_name}")
def get_tiktok_frame_image(image_name: str):
    """Serve a configured TikTok frame without exposing arbitrary files."""
    safe_name = os.path.basename(str(image_name or ""))
    extension = os.path.splitext(safe_name)[1].lower()
    if safe_name != image_name or extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        return Response(status_code=404)
    image_path = os.path.join(PROJECT_ROOT, "assets", "frame", safe_name)
    if not os.path.isfile(image_path):
        return Response(status_code=404)
    media_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
    return FileResponse(image_path, media_type=media_type)

@app.get("/api/article/library")
def get_article_library():
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    
    def get_files(folder):
        lib_dir = os.path.join(project_root, "assets", folder)
        if not os.path.exists(lib_dir):
            return []
        files = [f for f in os.listdir(lib_dir) if f.endswith(".png")]
        return sorted(files)
        
    return {
        "frames": get_files("frame"),
        "logos": get_files("logo")
    }

# ================= FACEBOOK ENDPOINTS =================

fb_pipeline_process = None
fb_pipeline_logs = ["[Hệ thống] Sẵn sàng khởi động Tool Facebook..."]
fb_pipeline_scope = ""
FACEBOOK_DEFAULT_TARGET_CHANNEL = "Adsupnews"


def normalize_facebook_source(source):
    return normalize_api_source(source)

def read_fb_logs(process):
    global fb_pipeline_logs
    for line in iter(process.stdout.readline, ""):
        line = line.strip()
        if line:
            fb_pipeline_logs.append(line)
            if len(fb_pipeline_logs) > 200:
                fb_pipeline_logs.pop(0)

@app.get("/api/facebook/sources")
def get_facebook_sources():
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        res = supabase_client.table("facebook_sources").select("*").order("created_at").execute()
        return [normalize_facebook_source(item) for item in (res.data or [])]
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/facebook/group-sources")
def get_facebook_group_sources():
    if not supabase_client:
        return {"error": "Supabase not initialized"}
    try:
        result = (
            supabase_client.table("facebook_group_sources")
            .select("*")
            .order("created_at")
            .execute()
        )
        return [normalize_group_api_source(item) for item in (result.data or [])]
    except Exception as error:
        return {"error": str(error)}


@app.get("/api/facebook/auth/status")
def get_facebook_auth_status():
    return facebook_auth_manager.status()


@app.post("/api/facebook/auth/login")
def start_facebook_auth_login():
    try:
        return facebook_auth_manager.start_login()
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

@app.get("/api/facebook/voice")
def get_facebook_voice():
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    settings_path = os.path.join(project_root, "apps", "creator_facebook", "data", "global_voice_settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"Tích cực": "", "Trung tính": "", "Cảnh báo": "", "Đồng cảm": ""}

@app.post("/api/facebook/voice")
async def update_facebook_voice(request: Request):
    try:
        data = await request.json()
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        settings_path = os.path.join(project_root, "apps", "creator_facebook", "data", "global_voice_settings.json")
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/facebook/sources")
async def add_facebook_source(request: Request):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        data = prepare_api_source_payload(await request.json())
        existing = (
            supabase_client.table("facebook_sources")
            .select("id")
            .eq("source_url", data["source_url"])
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=409,
                detail="Nguồn Facebook này đã tồn tại và đang được bật.",
            )
        res = supabase_client.table("facebook_sources").insert(data).execute()
        return {"status": "success", "data": res.data}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        return {"error": str(e)}

@app.put("/api/facebook/sources/{source_id}")
async def update_facebook_source(source_id: int, request: Request):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        data = prepare_api_source_payload(await request.json(), partial=True)
        res = supabase_client.table("facebook_sources").update(data).eq("id", source_id).execute()
        return {"status": "success", "data": res.data}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        return {"error": str(e)}

@app.delete("/api/facebook/sources/{source_id}")
def delete_facebook_source(source_id: int):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        res = supabase_client.table("facebook_sources").delete().eq("id", source_id).execute()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/facebook/group-sources")
async def add_facebook_group_source(request: Request):
    if not supabase_client:
        return {"error": "Supabase not initialized"}
    try:
        data = prepare_group_api_source_payload(await request.json())
        result = supabase_client.table("facebook_group_sources").insert(data).execute()
        return {"status": "success", "data": result.data}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        return {"error": str(error)}


@app.put("/api/facebook/group-sources/{source_id}")
async def update_facebook_group_source(source_id: int, request: Request):
    if not supabase_client:
        return {"error": "Supabase not initialized"}
    try:
        data = prepare_group_api_source_payload(
            await request.json(), partial=True
        )
        result = (
            supabase_client.table("facebook_group_sources")
            .update(data)
            .eq("id", source_id)
            .execute()
        )
        return {"status": "success", "data": result.data}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        return {"error": str(error)}


@app.delete("/api/facebook/group-sources/{source_id}")
def delete_facebook_group_source(source_id: int):
    if not supabase_client:
        return {"error": "Supabase not initialized"}
    try:
        supabase_client.table("facebook_group_sources").delete().eq(
            "id", source_id
        ).execute()
        return {"status": "success"}
    except Exception as error:
        return {"error": str(error)}


@app.get("/api/facebook/group-review")
def get_facebook_group_review_queue():
    try:
        return facebook_group_review_service.list_pending()
    except Exception as error:
        return {"error": str(error)}


@app.get("/api/facebook/group-review/{review_id}/video")
def get_facebook_group_review_video(review_id: str):
    try:
        return FileResponse(
            facebook_group_review_service.video_path(review_id),
            media_type="video/mp4",
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/facebook/group-review/{review_id}/approve")
def approve_facebook_group_review(review_id: str):
    try:
        return facebook_group_review_service.approve(review_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/facebook/group-review/{review_id}/reject")
def reject_facebook_group_review(review_id: str):
    try:
        return facebook_group_review_service.reject(review_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

# Independent Facebook Pipeline Processes for Page & Group
fb_page_process = None
fb_page_logs = ["[Hệ thống] Sẵn sàng khởi động Tool Facebook Page..."]

fb_group_process = None
fb_group_logs = ["[Hệ thống] Sẵn sàng khởi động Tool Facebook Group..."]

def read_fb_logs(process, source_scope: str):
    target_logs = fb_group_logs if source_scope == "group" else fb_page_logs
    for line in iter(process.stdout.readline, ""):
        line = line.strip()
        if line:
            target_logs.append(line)
            if len(target_logs) > 200:
                target_logs.pop(0)

@app.post("/api/facebook/start")
def start_facebook_tool(source_scope: str = "page"):
    global fb_page_process, fb_group_process, fb_page_logs, fb_group_logs
    if source_scope not in {"page", "group"}:
        raise HTTPException(status_code=422, detail="source_scope không hợp lệ")

    proc = fb_group_process if source_scope == "group" else fb_page_process
    if proc and proc.poll() is None:
        return {"status": "error", "message": f"Pipeline {source_scope.upper()} đang chạy rồi."}

    scope_label = "Group" if source_scope == "group" else "Page"
    logs = fb_group_logs if source_scope == "group" else fb_page_logs
    logs.clear()
    logs.append(f"[Hệ thống] Đang khởi động pipeline Facebook {scope_label}...")

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    
    cmd = [
        python_exe,
        "-u",
        "fb_pipeline.py",
        "start",
        "--source-scope",
        source_scope,
    ]
    new_proc = subprocess.Popen(
        cmd,
        cwd=os.path.join(project_root, "apps", "creator_facebook"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        bufsize=1
    )
    if source_scope == "group":
        fb_group_process = new_proc
    else:
        fb_page_process = new_proc

    threading.Thread(target=read_fb_logs, args=(new_proc, source_scope), daemon=True).start()
    return {
        "status": "started",
        "message": f"Facebook {scope_label} tool started",
        "source_scope": source_scope,
    }

@app.post("/api/facebook/start_once")
def start_once_facebook_tool(source_scope: str = "page"):
    global fb_page_process, fb_group_process, fb_page_logs, fb_group_logs
    if source_scope not in {"page", "group"}:
        raise HTTPException(status_code=422, detail="source_scope không hợp lệ")

    proc = fb_group_process if source_scope == "group" else fb_page_process
    if proc and proc.poll() is None:
        return {"status": "error", "message": f"Pipeline {source_scope.upper()} đang chạy rồi."}

    scope_label = "Group" if source_scope == "group" else "Page"
    logs = fb_group_logs if source_scope == "group" else fb_page_logs
    logs.clear()
    logs.append(f"[Hệ thống] Đang chạy 1 lần pipeline Facebook {scope_label}...")

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    
    cmd = [
        python_exe,
        "-u",
        "fb_pipeline.py",
        "run-once",
        "--source-scope",
        source_scope,
    ]
    new_proc = subprocess.Popen(
        cmd,
        cwd=os.path.join(project_root, "apps", "creator_facebook"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        bufsize=1
    )
    if source_scope == "group":
        fb_group_process = new_proc
    else:
        fb_page_process = new_proc

    threading.Thread(target=read_fb_logs, args=(new_proc, source_scope), daemon=True).start()
    return {
        "status": "started",
        "message": f"Facebook {scope_label} run-once started",
        "source_scope": source_scope,
    }

@app.post("/api/facebook/stop")
def stop_facebook_tool(source_scope: str = Query(default="all")):
    global fb_page_process, fb_group_process, fb_page_logs, fb_group_logs
    stopped = []
    if source_scope in {"page", "all"} and fb_page_process and fb_page_process.poll() is None:
        fb_page_process.terminate()
        fb_page_process = None
        fb_page_logs.append("[Hệ thống] Đã dừng an toàn Pipeline Page.")
        stopped.append("page")

    if source_scope in {"group", "all"} and fb_group_process and fb_group_process.poll() is None:
        fb_group_process.terminate()
        fb_group_process = None
        fb_group_logs.append("[Hệ thống] Đã dừng an toàn Pipeline Group.")
        stopped.append("group")

    return {"status": "stopped", "stopped": stopped}

@app.get("/api/facebook/logs")
def get_facebook_logs():
    page_running = fb_page_process is not None and fb_page_process.poll() is None
    group_running = fb_group_process is not None and fb_group_process.poll() is None
    return {
        "page": {
            "is_running": page_running,
            "logs": fb_page_logs,
        },
        "group": {
            "is_running": group_running,
            "logs": fb_group_logs,
        },
        "is_running": page_running or group_running,
        "logs": fb_page_logs if page_running or not group_running else fb_group_logs,
        "source_scope": "page" if page_running else ("group" if group_running else "")
    }

# ================= TIKTOK (MATRIX BOT) ENDPOINTS =================

TIKTOK_CONTENT_PROFILES_CONFIG_KEY = "tiktok_content_profiles"
ARTICLE_PROCESSED_LINKS_CONFIG_KEY = "article_processed_links"

def get_tiktok_content_profiles():
    if not supabase_client:
        return {}
    try:
        res = supabase_client.table("system_configs").select("config_value").eq("config_name", TIKTOK_CONTENT_PROFILES_CONFIG_KEY).execute()
        if not res.data:
            return {}
        value = res.data[0].get("config_value") or {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def save_tiktok_content_profile(tiktok_id: str, content_profile):
    profiles = get_tiktok_content_profiles()
    profiles[tiktok_id] = extract_operator_overrides(tiktok_id, content_profile)
    existing = supabase_client.table("system_configs").select("config_name").eq("config_name", TIKTOK_CONTENT_PROFILES_CONFIG_KEY).execute()
    payload = {"config_value": profiles}
    if existing.data:
        supabase_client.table("system_configs").update(payload).eq("config_name", TIKTOK_CONTENT_PROFILES_CONFIG_KEY).execute()
    else:
        supabase_client.table("system_configs").insert({"config_name": TIKTOK_CONTENT_PROFILES_CONFIG_KEY, **payload}).execute()

def attach_tiktok_content_profiles(accounts):
    profiles = get_tiktok_content_profiles()
    for account in accounts or []:
        tiktok_id = account.get("tiktok_id")
        if tiktok_id:
            account["content_profile"] = get_content_profile(
                tiktok_id,
                profiles.get(tiktok_id, {}),
                account.get("content_profile", {}),
                include_runtime=False,
            )
    return accounts

tiktok_process = None
tiktok_process_group_id = None
tiktok_logs = ["[Hệ thống] Sẵn sàng khởi động Matrix Bot..."]

def read_tiktok_logs(process):
    global tiktok_logs
    for line in iter(process.stdout.readline, ""):
        line = line.strip()
        if line:
            tiktok_logs.append(line)
            if len(tiktok_logs) > 200:
                tiktok_logs.pop(0)

@app.get("/api/tiktok/accounts")
def get_tiktok_accounts():
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        res = supabase_client.table("accounts").select("*").execute()
        return attach_tiktok_content_profiles(res.data)
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/tiktok/accounts")
async def add_tiktok_account(request: Request):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        data = await request.json()
        content_profile = data.pop("content_profile", None)
        res = supabase_client.table("accounts").insert(data).execute()
        if content_profile is not None and data.get("tiktok_id"):
            save_tiktok_content_profile(data["tiktok_id"], content_profile)
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.put("/api/tiktok/accounts/{tiktok_id}")
async def update_tiktok_account(tiktok_id: str, request: Request):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        data = await request.json()
        content_profile = data.pop("content_profile", None)
        if content_profile is not None:
            save_tiktok_content_profile(tiktok_id, content_profile)
        if data:
            supabase_client.table("accounts").update(data).eq("tiktok_id", tiktok_id).execute()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/api/tiktok/accounts/{tiktok_id}")
def delete_tiktok_account(tiktok_id: str):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        res = supabase_client.table("accounts").delete().eq("tiktok_id", tiktok_id).execute()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/tiktok/start")
def start_tiktok_tool():
    global tiktok_process, tiktok_process_group_id, tiktok_logs
    if tiktok_process and tiktok_process.poll() is None:
        return {"status": "error", "message": "Bot is already running"}
        
    tiktok_logs = ["[Hệ thống] Đang khởi động tiến trình ngầm Matrix Bot..."]
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    
    cmd = [python_exe, "-u", "scheduler_manager.py"]
    popen_kwargs = {
        "cwd": os.path.join(project_root, "apps", "uploader_tiktok"),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "encoding": "utf-8",
        "bufsize": 1,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        popen_kwargs["start_new_session"] = True

    tiktok_process = subprocess.Popen(cmd, **popen_kwargs)
    tiktok_process_group_id = (
        None if os.name == "nt" else tiktok_process.pid
    )
    threading.Thread(target=read_tiktok_logs, args=(tiktok_process,), daemon=True).start()
    return {"status": "started"}

@app.post("/api/tiktok/stop")
def stop_tiktok_tool():
    global tiktok_process, tiktok_process_group_id, tiktok_logs
    if tiktok_process or tiktok_process_group_id is not None:
        _stop_process_tree(tiktok_process, tiktok_process_group_id)
        tiktok_process = None
        tiktok_process_group_id = None
        tiktok_logs.append(
            "[Hệ thống] Đã dừng scheduler và toàn bộ worker con đang chạy."
        )
        return {"status": "stopped"}
    return {"status": "error"}

@app.get("/api/tiktok/logs")
def get_tiktok_logs():
    is_running = tiktok_process is not None and tiktok_process.poll() is None
    return {"logs": tiktok_logs, "is_running": is_running}

# ================= ADDITIONAL ARTICLE ENDPOINTS =================

@app.post("/api/article/config/{channel_id}")
async def save_channel_config(channel_id: str, request: Request):
    import json
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    config_path = os.path.join(project_root, "assets", "channels", channel_id, "config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    try:
        data = await request.json()
        content_profile = data.get("content_profile")
        if content_profile is not None and str(channel_id or "").strip():
            data["content_profile"] = extract_operator_overrides(
                channel_id,
                content_profile,
            )
            if supabase_client:
                save_tiktok_content_profile(channel_id, data["content_profile"])
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        # Keep the cloud asset in sync with the Web Hub. The renderer prefers
        # the local file when present, while this upload makes other workers
        # and new machines receive the same visual coordinates.
        cloud_warning = ""
        if supabase_client:
            try:
                storage_path = f"channels/{channel_id}/config.json"
                with open(config_path, "rb") as config_file:
                    try:
                        supabase_client.storage.from_("assets").upload(
                            storage_path, config_file, file_options={"upsert": True}
                        )
                    except Exception:
                        config_file.seek(0)
                        supabase_client.storage.from_("assets").update(
                            storage_path, config_file
                        )
            except Exception as cloud_error:
                cloud_warning = f" Cloud sync warning: {cloud_error}"
        return {"status": "success", "warning": cloud_warning}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/article/chrome/{channel_id}")
def open_article_chrome(channel_id: str):
    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    script = os.path.join(project_root, "apps", "creator_article", "article_chatgpt_automator.py")
    if not os.path.exists(script):
        return {
            "status": "error",
            "error": f"Không tìm thấy trình mở Chrome Article: {script}",
        }
    try:
        process = subprocess.Popen(
            [python_exe, script, "login", channel_id],
            cwd=os.path.dirname(script),
        )
    except Exception as exc:
        return {"status": "error", "error": f"Không thể khởi động Chrome Article: {exc}"}
    return {
        "status": "success",
        "pid": process.pid,
        "channel": channel_id,
        "profile": f"chrome_article_chatgpt_{channel_id}",
    }

@app.post("/api/chatgpt/chrome")
def open_shared_chatgpt_chrome():
    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    script = os.path.join(project_root, "apps", "creator_facebook", "chatgpt_automator.py")
    if os.path.exists(script):
        subprocess.Popen([python_exe, script, "login"], cwd=os.path.dirname(script))
    return {"status": "success"}

@app.post("/api/chatgpt/chrome/{tiktok_id}")
def open_chatgpt_chrome_for_tiktok(tiktok_id: str):
    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    script = os.path.join(project_root, "apps", "creator_facebook", "chatgpt_automator.py")
    if os.path.exists(script):
        subprocess.Popen([python_exe, script, "login", tiktok_id], cwd=os.path.dirname(script))
    return {"status": "success"}

@app.post("/api/gemini/chrome")
def open_shared_gemini_chrome():
    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    script = os.path.join(project_root, "apps", "creator_facebook", "gemini_automator.py")
    if os.path.exists(script):
        subprocess.Popen([python_exe, script, "login"], cwd=os.path.dirname(script))
    return {"status": "success"}

@app.post("/api/gemini/chrome/{tiktok_id}")
def open_gemini_chrome_for_tiktok(tiktok_id: str):
    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    script = os.path.join(project_root, "apps", "creator_facebook", "gemini_automator.py")
    if os.path.exists(script):
        subprocess.Popen([python_exe, script, "login", tiktok_id], cwd=os.path.dirname(script))
    return {"status": "success"}

@app.get("/api/ai/provider")
def get_ai_provider():
    from shared.core.ai_provider_factory import get_configured_ai_provider
    return {"provider": get_configured_ai_provider()}

@app.post("/api/ai/provider")
def set_ai_provider(payload: dict):
    from shared.core.ai_provider_factory import save_configured_ai_provider
    raw_provider = str(payload.get("provider", "chatgpt")).strip().lower()
    saved_provider = save_configured_ai_provider(raw_provider)
    return {"status": "success", "provider": saved_provider}

@app.post("/api/chatgpt/clone-profiles")
def clone_shared_chatgpt_profiles():
    import re
    import shutil

    if not supabase_client:
        return {"error": "Supabase not initialized"}

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    base_dir = os.path.join(project_root, "data", "chrome_profiles", "chatgpt")
    source_dir = os.path.join(base_dir, "chrome_chatgpt")
    if not os.path.exists(source_dir):
        return {"error": "Chưa có profile ChatGPT chung. Hãy bấm 'Mở ChatGPT chung' và đăng nhập trước."}

    transient_items = {
        "SingletonLock", "SingletonCookie", "SingletonSocket", "DevToolsActivePort",
        "Crashpad", "Cache", "Code Cache", "GPUCache", "ShaderCache",
        "GrShaderCache", "GraphiteDawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
    }

    def sanitize_profile_id(profile_id):
        return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(profile_id or "").replace("@", "").strip()).strip("_")

    def ignore_transient(_dir, names):
        return {name for name in names if name in transient_items}

    def remove_locks(profile_dir):
        for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "DevToolsActivePort"]:
            lock_file = os.path.join(profile_dir, lock_name)
            if os.path.lexists(lock_file):
                try:
                    os.remove(lock_file)
                except Exception:
                    pass

    try:
        accounts = supabase_client.table("accounts").select("tiktok_id").execute().data or []
        cloned = []
        for account in accounts:
            clean_id = sanitize_profile_id(account.get("tiktok_id"))
            if not clean_id:
                continue
            target_dir = os.path.join(base_dir, f"chrome_chatgpt_{clean_id}")
            if os.path.abspath(target_dir) == os.path.abspath(source_dir):
                continue
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
            shutil.copytree(source_dir, target_dir, ignore=ignore_transient)
            remove_locks(target_dir)
            cloned.append(clean_id)
        return {"status": "success", "cloned": cloned, "total": len(cloned)}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/gemini/clone-profiles")
def clone_shared_gemini_profiles():
    return {"status": "success", "message": "Hệ thống đã tự động dùng 1 Profile duy nhất (chrome_gemini) cho tất cả các kênh để bảo vệ phiên đăng nhập."}

# ================= ADDITIONAL TIKTOK ENDPOINTS =================

@app.post("/api/tiktok/chrome/{profile}")
def open_tiktok_chrome(profile: str):
    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    script = os.path.join(project_root, "apps", "uploader_tiktok", "desktop_ui", "pages", "account_manager.py") 
    # Just running playwright open directly is easier
    data_dir = os.path.join(project_root, "apps", "uploader_tiktok", "data", "browser_profiles", profile)
    subprocess.Popen([python_exe, "-m", "playwright", "codegen", "--user-data-dir", data_dir, "https://tiktok.com"])
    return {"status": "success"}

AUTO_REMIX_ENABLED = False
clone_worker_process = None
clone_worker_logs = ["[Hệ thống] Auto Remix đang tạm tắt."]

def read_clone_logs(process):
    global clone_worker_logs
    for line in iter(process.stdout.readline, ""):
        line = line.strip()
        if line:
            clone_worker_logs.append(line)
            if len(clone_worker_logs) > 200: clone_worker_logs.pop(0)

@app.post("/api/tiktok/clone/start")
def start_tiktok_clone():
    global clone_worker_process, clone_worker_logs
    if not AUTO_REMIX_ENABLED:
        clone_worker_logs = ["[Hệ thống] Auto Remix đang tạm tắt, không khởi động clone_worker."]
        return {"status": "disabled", "message": "Auto Remix is temporarily disabled"}
    if clone_worker_process and clone_worker_process.poll() is None: return {"status": "running"}
    clone_worker_logs = ["[Hệ thống] Đang chạy Auto Clone Worker..."]
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    cmd = [python_exe, "-u", "clone_worker.py"]
    clone_worker_process = subprocess.Popen(
        cmd, cwd=os.path.join(project_root, "apps", "uploader_tiktok", "workers"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", bufsize=1
    )
    threading.Thread(target=read_clone_logs, args=(clone_worker_process,), daemon=True).start()
    return {"status": "started"}

@app.post("/api/tiktok/clone/stop")
def stop_tiktok_clone():
    global clone_worker_process
    if clone_worker_process and clone_worker_process.poll() is None:
        clone_worker_process.terminate()
        clone_worker_process = None
        clone_worker_logs.append("[Hệ thống] Đã dừng Auto Clone Worker.")
    return {"status": "stopped"}

@app.get("/api/tiktok/clone/logs")
def get_tiktok_clone_logs():
    is_running = clone_worker_process is not None and clone_worker_process.poll() is None
    return {"logs": clone_worker_logs, "is_running": is_running}

# ================= SYSTEM CONFIGS ENDPOINTS =================

@app.get("/api/system/config/{config_key}")
def get_system_config(config_key: str):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        res = supabase_client.table("system_configs").select("config_value").eq("config_name", config_key).execute()
        if res.data: return res.data[0]["config_value"]
        return {}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/system/config/{config_key}")
async def update_system_config(config_key: str, request: Request):
    if not supabase_client: return {"error": "Supabase not initialized"}
    try:
        data = await request.json()
        res = supabase_client.table("system_configs").select("*").eq("config_name", config_key).execute()
        if res.data:
            supabase_client.table("system_configs").update({"config_value": data}).eq("config_name", config_key).execute()
        else:
            supabase_client.table("system_configs").insert({"config_name": config_key, "config_value": data}).execute()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/system/prompts/{prompt_type}")
def get_system_prompt(prompt_type: str):
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        # Map prompt_type to actual file names
        file_map = {
            "article": "prompt_article.txt",
            "facebook": "prompt_script.txt"
        }
        filename = file_map.get(prompt_type)
        if not filename: return {"error": "Invalid prompt type"}
        
        filepath = os.path.join(project_root, "config", "prompts", filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return {"content": f.read()}
        return {"content": ""}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/system/prompts/{prompt_type}")
async def update_system_prompt(prompt_type: str, request: Request):
    try:
        data = await request.json()
        content = data.get("content", "")
        
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        file_map = {
            "article": "prompt_article.txt",
            "facebook": "prompt_script.txt"
        }
        filename = file_map.get(prompt_type)
        if not filename: return {"error": "Invalid prompt type"}
        
        filepath = os.path.join(project_root, "config", "prompts", filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/article/start_once")
def start_article_pipeline_once():
    global pipeline_process, pipeline_logs
    if pipeline_process and pipeline_process.poll() is None: return {"status": "running"}
    pipeline_logs = ["[Hệ thống] Đang chạy Tool Tin Tức (Chạy 1 Lần)..."]
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    cmd = [python_exe, "-u", "article_pipeline_core.py", "--run-once"]
    pipeline_process = subprocess.Popen(
        cmd, cwd=os.path.join(project_root, "apps", "creator_article"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", bufsize=1
    )
    threading.Thread(target=read_logs, args=(pipeline_process,), daemon=True).start()
    return {"status": "started"}

@app.post("/api/facebook/start_once")
def start_facebook_pipeline_once(source_scope: str = "page"):
    global fb_pipeline_process, fb_pipeline_logs, fb_pipeline_scope
    if fb_pipeline_process and fb_pipeline_process.poll() is None: return {"status": "running"}
    if source_scope not in {"page", "group"}:
        raise HTTPException(status_code=422, detail="source_scope không hợp lệ")
    scope_label = "Group" if source_scope == "group" else "Page"
    fb_pipeline_scope = source_scope
    fb_pipeline_logs = [
        f"[Hệ thống] Đang chạy Facebook {scope_label} (1 lần)..."
    ]
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    python_exe = sys.executable
    cmd = [
        python_exe,
        "-u",
        "fb_pipeline.py",
        "run-once",
        "--source-scope",
        source_scope,
    ]
    fb_pipeline_process = subprocess.Popen(
        cmd, cwd=os.path.join(project_root, "apps", "creator_facebook"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", bufsize=1
    )
    threading.Thread(target=read_fb_logs, args=(fb_pipeline_process,), daemon=True).start()
    return {"status": "started", "source_scope": source_scope}

# ==========================================================================
# AFFILIATE VIDEO TOOL API ENDPOINTS
# ==========================================================================

AFFILIATE_BASE_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "..", "Video Affiliate"))
AFFILIATE_INPUTS_DIR = os.path.join(AFFILIATE_BASE_DIR, "assets", "inputs")
os.makedirs(os.path.join(AFFILIATE_INPUTS_DIR, "images"), exist_ok=True)
os.makedirs(os.path.join(AFFILIATE_INPUTS_DIR, "videos"), exist_ok=True)
os.makedirs(os.path.join(AFFILIATE_INPUTS_DIR, "audios"), exist_ok=True)

affiliate_queue = []
affiliate_is_rendering = False

@app.get("/api/affiliate/files")
def get_affiliate_files():
    images = []
    videos = []
    audios = []
    
    img_dir = os.path.join(AFFILIATE_INPUTS_DIR, "images")
    vid_dir = os.path.join(AFFILIATE_INPUTS_DIR, "videos")
    aud_dir = os.path.join(AFFILIATE_INPUTS_DIR, "audios")
    
    if os.path.exists(img_dir):
        images = [{"id": f, "name": f, "type": "image", "size": os.path.getsize(os.path.join(img_dir, f)), "url": f"/api/affiliate/file/images/{f}"} for f in os.listdir(img_dir) if not f.startswith(".")]
    if os.path.exists(vid_dir):
        videos = [{"id": f, "name": f, "type": "video", "size": os.path.getsize(os.path.join(vid_dir, f)), "url": f"/api/affiliate/file/videos/{f}"} for f in os.listdir(vid_dir) if not f.startswith(".")]
    if os.path.exists(aud_dir):
        audios = [{"id": f, "name": f, "type": "audio", "size": os.path.getsize(os.path.join(aud_dir, f)), "url": f"/api/affiliate/file/audios/{f}"} for f in os.listdir(aud_dir) if not f.startswith(".")]
        
    return {"images": images, "videos": videos, "audios": audios}

@app.get("/api/affiliate/file/{category}/{filename}")
def get_affiliate_media_file(category: str, filename: str):
    if category not in ["images", "videos", "audios"]:
        raise HTTPException(status_code=400, detail="Invalid media category")
        
    file_path = os.path.join(AFFILIATE_INPUTS_DIR, category, filename)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    mime_type, _ = mimetypes.guess_type(file_path)
    return FileResponse(file_path, media_type=mime_type or "application/octet-stream")

@app.post("/api/affiliate/upload")
async def upload_affiliate_media(category: str = Form(...), files: list[UploadFile] = File(...)):
    if category not in ["image", "video", "audio"]:
        raise HTTPException(status_code=400, detail="Invalid category")
        
    target_folder = os.path.join(AFFILIATE_INPUTS_DIR, f"{category}s")
    os.makedirs(target_folder, exist_ok=True)
    
    saved_files = []
    for file in files:
        file_path = os.path.join(target_folder, file.filename)
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        saved_files.append(file.filename)
        
    return {"status": "success", "saved": saved_files}

@app.post("/api/affiliate/chrome/grok")
def open_grok_chrome():
    import subprocess
    import threading
    user_data_dir = os.path.abspath(os.path.join(AFFILIATE_BASE_DIR, "assets", "grok"))
    os.makedirs(user_data_dir, exist_ok=True)
    
    def run_browser():
        try:
            import undetected_chromedriver as uc
            options = uc.ChromeOptions()
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument('--no-first-run')
            options.add_argument('--no-service-autorun')
            options.add_argument('--password-store=basic')
            options.add_argument('--profile-directory=Default')
            driver = uc.Chrome(options=options, use_subprocess=True)
            driver.get("https://grok.com/")
            while len(driver.window_handles) > 0:
                time.sleep(1)
        except Exception as e:
            print(f"Lỗi mở Grok Chrome: {e}")

    threading.Thread(target=run_browser, daemon=True).start()
    return {"status": "success", "message": "Đã mở trình duyệt Chrome cho Grok AI"}

@app.post("/api/affiliate/chrome/nano")
def open_nano_chrome():
    import subprocess
    import threading
    user_data_dir = os.path.abspath(os.path.join(AFFILIATE_BASE_DIR, "assets", "nano_banana"))
    os.makedirs(user_data_dir, exist_ok=True)

    def run_browser():
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser_context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                page = browser_context.new_page()
                page.goto("https://labs.google/fx/tools/nano-banana")
                browser_context.wait_for_event("close", timeout=0)
        except Exception as e:
            print(f"Lỗi mở Nano Banana Chrome: {e}")

    threading.Thread(target=run_browser, daemon=True).start()
    return {"status": "success", "message": "Đã mở trình duyệt Chrome cho Nano Banana"}

@app.get("/api/affiliate/prompt/motion")
def get_motion_prompt():
    prompt_file = os.path.join(AFFILIATE_BASE_DIR, "assets", "prompts", "motion_analysis.txt")
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                content = f.read()
            return {"status": "success", "prompt": content}
        except Exception as e:
            return {"status": "error", "message": str(e), "prompt": ""}
    return {"status": "success", "prompt": "Grok AI Analysis: Analyze subject movement, camera pan, zoom, body posture, lighting dynamics"}

@app.post("/api/affiliate/prompt/motion")
def save_motion_prompt(payload: dict):
    prompt_content = payload.get("prompt", "")
    prompt_dir = os.path.join(AFFILIATE_BASE_DIR, "assets", "prompts")
    os.makedirs(prompt_dir, exist_ok=True)
    prompt_file = os.path.join(prompt_dir, "motion_analysis.txt")
    try:
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt_content)
        return {"status": "success", "message": "Đã lưu Prompt Phân tích Chuyển động"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/affiliate/outputs")
def get_affiliate_outputs():
    downloads_dir = os.path.join(AFFILIATE_BASE_DIR, "assets", "downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    outputs = []
    if os.path.exists(downloads_dir):
        for f in os.listdir(downloads_dir):
            if f.endswith((".mp4", ".mov", ".mkv", ".webm")) and not f.startswith("."):
                fpath = os.path.join(downloads_dir, f)
                outputs.append({
                    "id": f,
                    "filename": f,
                    "size": os.path.getsize(fpath),
                    "created_at": time.ctime(os.path.getmtime(fpath)),
                    "url": f"/api/affiliate/output-file/{f}"
                })
    outputs.sort(key=lambda x: x["created_at"], reverse=True)
    return {"outputs": outputs}

@app.get("/api/affiliate/output-file/{filename}")
def serve_affiliate_output_file(filename: str):
    downloads_dir = os.path.join(AFFILIATE_BASE_DIR, "assets", "downloads")
    file_path = os.path.join(downloads_dir, filename)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File video kết quả không tồn tại")
    mime_type, _ = mimetypes.guess_type(file_path)
    return FileResponse(file_path, media_type=mime_type or "video/mp4")

@app.get("/api/affiliate/queue-status")
def get_affiliate_queue_status():
    return {
        "queue": affiliate_queue,
        "is_rendering": affiliate_is_rendering
    }

@app.post("/api/affiliate/start-render")
def add_affiliate_render_job(job: dict):
    global affiliate_queue
    job["status"] = "pending"
    job["note"] = "Sẵn sàng render"
    job["progress"] = 0
    affiliate_queue.append(job)
    return {"status": "queued", "job": job}

@app.post("/api/affiliate/start")
def start_affiliate_rendering():
    global affiliate_is_rendering
    affiliate_is_rendering = True
    return {"status": "started"}

@app.post("/api/affiliate/stop")
def stop_affiliate_rendering():
    global affiliate_is_rendering
    affiliate_is_rendering = False
    return {"status": "stopped"}

# ═══════════════════════════════════════════════════════
#  AUTHENTICATION & ROLE-BASED ACCESS CONTROL (GOOGLE OAUTH)
# ═══════════════════════════════════════════════════════
USER_ROLES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "user_roles.json")

def load_user_roles() -> dict:
    os.makedirs(os.path.dirname(USER_ROLES_FILE), exist_ok=True)
    if os.path.exists(USER_ROLES_FILE):
        try:
            with open(USER_ROLES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_user_roles(roles: dict):
    os.makedirs(os.path.dirname(USER_ROLES_FILE), exist_ok=True)
    try:
        with open(USER_ROLES_FILE, "w", encoding="utf-8") as f:
            json.dump(roles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving user roles: {e}")

@app.post("/api/auth/google")
def google_login(payload: dict):
    email = str(payload.get("email") or "").strip().lower()
    name = str(payload.get("name") or "").strip() or email.split("@")[0]
    picture = str(payload.get("picture") or "").strip()
    
    if not email:
        return JSONResponse(status_code=400, content={"error": "Email is required"})
        
    roles = load_user_roles()
    admin_env = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]
    
    if email in roles:
        role = roles[email].get("role", "user")
    else:
        if admin_env:
            role = "admin" if email in admin_env else "user"
        elif not roles or "admin" in email:
            role = "admin"
        else:
            role = "user"
            
    roles[email] = {
        "email": email,
        "name": name,
        "picture": picture,
        "role": role,
        "last_login": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_user_roles(roles)
    
    return {
        "status": "success",
        "user": {
            "email": email,
            "name": name,
            "picture": picture,
            "role": role
        }
    }

@app.get("/api/auth/users")
def get_user_roles_list():
    roles = load_user_roles()
    return {"users": list(roles.values())}

@app.post("/api/auth/users/role")
def update_user_role(payload: dict):
    email = str(payload.get("email") or "").strip().lower()
    new_role = str(payload.get("role") or "user").strip().lower()
    if new_role not in {"admin", "user"}:
        new_role = "user"
        
    roles = load_user_roles()
    if email in roles:
        roles[email]["role"] = new_role
        save_user_roles(roles)
        return {"status": "success", "email": email, "role": new_role}
    return JSONResponse(status_code=404, content={"error": "User not found"})

# Mount frontend/dist as static files for production
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_path):
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")
    
    # Catch-all route to serve index.html for React SPA
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index_file = os.path.join(frontend_path, "index.html")
        requested_file = os.path.join(frontend_path, full_path)
        if os.path.exists(requested_file) and os.path.isfile(requested_file):
            return FileResponse(requested_file)
        return FileResponse(index_file)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
