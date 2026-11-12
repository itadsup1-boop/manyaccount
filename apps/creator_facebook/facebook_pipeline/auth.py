"""Quản lý phiên Facebook dùng chung cho crawler và downloader."""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
COOKIE_DIR = PACKAGE_ROOT / "data" / "fb_cookies"
STORAGE_STATE_PATH = COOKIE_DIR / "fb_state.json"
NETSCAPE_COOKIE_PATH = COOKIE_DIR / "fb_cookies.txt"
SESSION_LOCK_PATH = COOKIE_DIR / "facebook_session.lock"


def _storage_data() -> dict[str, Any]:
    try:
        with STORAGE_STATE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def facebook_login_status() -> dict[str, Any]:
    data = _storage_data()
    now = time.time()
    user_cookie = next(
        (
            item
            for item in data.get("cookies", [])
            if item.get("name") == "c_user" and "facebook.com" in item.get("domain", "")
        ),
        None,
    )
    expires = float((user_cookie or {}).get("expires") or 0)
    logged_in = bool(user_cookie) and (expires <= 0 or expires > now)
    expires_at = ""
    if expires > 0:
        expires_at = datetime.fromtimestamp(expires, tz=timezone.utc).isoformat()
    return {
        "logged_in": logged_in,
        "expires_at": expires_at,
        "storage_state_exists": STORAGE_STATE_PATH.exists(),
    }


def export_netscape_cookies(storage_data: dict[str, Any] | None = None) -> None:
    data = storage_data or _storage_data()
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Netscape HTTP Cookie File", "# Exported for Facebook yt-dlp"]
    for cookie in data.get("cookies", []):
        domain = str(cookie.get("domain") or "")
        name = str(cookie.get("name") or "")
        if not domain or not name:
            continue
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        secure = "TRUE" if cookie.get("secure") else "FALSE"
        expires = int(float(cookie.get("expires") or 0))
        path = str(cookie.get("path") or "/")
        value = str(cookie.get("value") or "").replace("\t", "")
        lines.append(
            "\t".join((domain, include_subdomains, path, secure, str(expires), name, value))
        )
    NETSCAPE_COOKIE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_browser_storage(context: Any) -> None:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    state = context.storage_state(path=str(STORAGE_STATE_PATH))
    export_netscape_cookies(state if isinstance(state, dict) else None)


def browser_context_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1920, "height": 1080},
        "locale": "vi-VN",
        "timezone_id": "Asia/Ho_Chi_Minh",
    }
    if STORAGE_STATE_PATH.exists():
        options["storage_state"] = str(STORAGE_STATE_PATH)
    return options


def chromium_launch_options(*, headless: bool) -> dict[str, Any]:
    """Ưu tiên Chrome hệ thống; headless-shell đi kèm Playwright hay SIGTRAP Linux."""

    options: dict[str, Any] = {
        "headless": headless,
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    }
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if chrome:
        options["executable_path"] = chrome
    return options


def login_facebook_interactive(timeout_seconds: int = 600) -> dict[str, Any]:
    """Mở Chromium có giao diện và tự lưu cookie khi phát hiện ``c_user``."""

    from playwright.sync_api import sync_playwright

    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(SESSION_LOCK_PATH))
    try:
        with lock.acquire(timeout=2):
            print("🌐 Đang mở Facebook. Hãy đăng nhập trong cửa sổ vừa mở...")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    **chromium_launch_options(headless=False)
                )
                context = browser.new_context(**browser_context_options())
                page = context.new_page()
                page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
                deadline = time.monotonic() + timeout_seconds
                while time.monotonic() < deadline:
                    cookies = context.cookies("https://www.facebook.com/")
                    logged_in = any(cookie.get("name") == "c_user" for cookie in cookies)
                    blocked = "/checkpoint" in page.url or "/login" in page.url
                    if logged_in and not blocked:
                        save_browser_storage(context)
                        browser.close()
                        print(f"✅ Đã lưu phiên Facebook: {STORAGE_STATE_PATH}")
                        return facebook_login_status()
                    if not context.pages or all(item.is_closed() for item in context.pages):
                        break
                    page.wait_for_timeout(1000)
                try:
                    browser.close()
                except Exception:
                    pass
    except Timeout as exc:
        raise RuntimeError("Một crawler hoặc cửa sổ đăng nhập Facebook khác đang chạy.") from exc
    raise RuntimeError("Chưa phát hiện đăng nhập Facebook hoặc đã hết thời gian chờ.")


def open_facebook_browse() -> dict[str, Any]:
    """Mở cửa sổ Facebook giữ mở tới khi người dùng tự đóng.

    Khác ``login_facebook_interactive`` (đóng ngay khi bắt được cookie c_user —
    khiến cửa sổ chớp lên rồi tắt nếu phiên còn hạn), cửa sổ này dùng để xem/
    thao tác Facebook: giữ phiên hiện có, và nếu người dùng đăng nhập trong cửa
    sổ thì phiên được lưu cho crawler. Chỉ giữ lock phiên trong lúc ghi cookie
    để không chặn crawler pipeline chạy song song.
    """

    from playwright.sync_api import sync_playwright

    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    save_lock = FileLock(str(SESSION_LOCK_PATH))

    def _has_session_cookie(context: Any) -> bool:
        try:
            cookies = context.cookies("https://www.facebook.com/")
        except Exception:
            return False
        return any(cookie.get("name") == "c_user" for cookie in cookies)

    def _save_session(context: Any) -> None:
        try:
            with save_lock.acquire(timeout=5):
                save_browser_storage(context)
            print(f"✅ Đã lưu phiên Facebook: {STORAGE_STATE_PATH}")
        except Timeout:
            print("   ⚠️ Lock phiên đang bận — bỏ lượt lưu cookie này.")
        except Exception as exc:
            print(f"   ⚠️ Lưu phiên Facebook lỗi: {exc}")

    print("🌐 Mở trình duyệt Facebook (giữ mở đến khi bạn tự đóng cửa sổ)...")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**chromium_launch_options(headless=False))
        context = browser.new_context(**browser_context_options())
        page = context.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        saved_logged = False
        while True:
            try:
                pages = context.pages
            except Exception:
                break
            if not pages or all(item.is_closed() for item in pages):
                break
            logged_in = _has_session_cookie(context)
            if logged_in and not saved_logged:
                _save_session(context)
                saved_logged = True
            elif not logged_in:
                saved_logged = False
            time.sleep(2)
        if _has_session_cookie(context):
            _save_session(context)
        try:
            browser.close()
        except Exception:
            pass
    return facebook_login_status()
