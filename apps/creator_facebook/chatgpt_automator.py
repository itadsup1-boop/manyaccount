#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  chatgpt_automator.py — Tự động hóa ChatGPT qua trình duyệt

  Dùng Chrome profile thật (persistent context) để:
  - Bypass Cloudflare
  - Giữ phiên đăng nhập vĩnh viễn
  - Upload video + gửi prompt + lấy JSON
═══════════════════════════════════════════════════════
"""

import os
import json
import time
import re
import shutil
import sys
import threading
from playwright.sync_api import sync_playwright

import fcntl


class ProcessFileLock:
    """Lock liên tiến trình (OS Inter-Process Lock) dùng fcntl.flock.
    Đảm bảo 100% hai tiến trình worker (PID khác nhau) KHÔNG BAO GIỜ cùng lúc mở Chrome profile.
    """
    def __init__(self, profile_dir: str):
        self.profile_dir = profile_dir
        self.lock_file_path = os.path.join(profile_dir, "chatgpt_profile_process.lock")
        self._file = None

    def acquire(self, blocking: bool = True, timeout: float = 450) -> bool:
        os.makedirs(self.profile_dir, exist_ok=True)
        try:
            self._file = open(self.lock_file_path, "a+")
        except Exception:
            return False

        start_time = time.time()
        printed_wait = False
        while True:
            try:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (BlockingIOError, IOError, OSError):
                if not blocking:
                    return False
                if not printed_wait:
                    print("      ⏳ ChatGPT Web Profile đang được dùng bởi tiến trình khác, đang chờ đến lượt...")
                    printed_wait = True
                if time.time() - start_time >= timeout:
                    return False
                time.sleep(1)

    def release(self):
        if self._file:
            try:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
                self._file.close()
            except Exception:
                pass
            self._file = None


def _get_profile_lock(profile_dir: str) -> ProcessFileLock:
    return ProcessFileLock(profile_dir)

# apps/creator_facebook/chatgpt_automator.py → creator_facebook → apps → mannyAccount (project root)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
from shared.core.experiment_manager import apply_experiment_metadata
from shared.core.prompt_builder import build_prompt, resolve_prompt_experiment
from shared.core.chatgpt_logger import save_chatgpt_log
from apps.creator_facebook.facebook_pipeline.hook_mode import build_hook_prompt
from apps.creator_facebook.facebook_pipeline.source_config import (
    EDIT_MODE_HOOK_THEN_ORIGINAL,
)

APP_DIR = PROJECT_ROOT
CHATGPT_PROFILE_BASE = os.path.join(PROJECT_ROOT, "data", "chrome_profiles", "chatgpt")
CHROME_PROFILE = os.path.join(CHATGPT_PROFILE_BASE, "chrome_chatgpt")
PROMPT_FILE = os.path.join(PROJECT_ROOT, "config", "prompts", "prompt_script.txt")


def sanitize_profile_id(profile_id: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(profile_id or "").replace("@", "").strip()).strip("_")


def get_chatgpt_profile_dir(profile_id: str | None = None, is_tele_bot: bool = False) -> str:
    clean_id = sanitize_profile_id(profile_id)
    # Telegram jobs belong to the selected TikTok channel. Reuse that
    # channel's logged-in Chrome profile instead of forcing every bot job into
    # one shared ``chrome_chatgpt_telebot`` session. The shared TeleBot profile
    # remains a fallback only when no channel/profile id was supplied.
    if clean_id:
        return os.path.join(CHATGPT_PROFILE_BASE, f"chrome_chatgpt_{clean_id}")
    if is_tele_bot:
        return os.path.join(CHATGPT_PROFILE_BASE, "chrome_chatgpt_telebot")
    return CHROME_PROFILE


TRANSIENT_PROFILE_ITEMS = {
    "SingletonLock",
    "SingletonSocket",
    "DevToolsActivePort",
    "Crashpad",
    "Cache",
    "Code Cache",
    "GPUCache",
    "ShaderCache",
    "GrShaderCache",
    "GraphiteDawnCache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
}


def ignore_transient_profile_items(_dir, names):
    return {name for name in names if name in TRANSIENT_PROFILE_ITEMS}


def remove_profile_locks(profile_dir: str):
    for lock_name in ["SingletonLock", "SingletonSocket", "DevToolsActivePort"]:
        lock_file = os.path.join(profile_dir, lock_name)
        if os.path.lexists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass


def mark_profile_exited_cleanly(profile_dir: str):
    """Xoá cờ 'crashed' trong hồ sơ Chrome trước khi mở lại.

    Playwright thường tắt Chromium bằng cách kill tiến trình thay vì đóng cửa
    sổ bình thường, nên lần mở sau Chromium hay tưởng nhầm là bị crash và hiện
    2 popup 'Đã xảy ra lỗi hồ sơ' + 'Bạn có muốn khôi phục trang không?' che
    mất ô chat. Ép exit_type về "Normal" trước mỗi lần mở để tránh việc đó.
    """
    pref_path = os.path.join(profile_dir, "Default", "Preferences")
    if not os.path.isfile(pref_path):
        return
    try:
        with open(pref_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile_state = data.setdefault("profile", {})
        changed = False
        if profile_state.get("exit_type") != "Normal":
            profile_state["exit_type"] = "Normal"
            changed = True
        if profile_state.get("exited_cleanly") is not True:
            profile_state["exited_cleanly"] = True
            changed = True
        if changed:
            with open(pref_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
    except Exception:
        # Không để lỗi đọc/ghi Preferences chặn cả pipeline.
        pass

    # Xóa các file SQLite hay bị hỏng (corrupted) gây ra popup "Đã xảy ra lỗi hồ sơ"
    # ChatGPT chỉ cần Cookies và Local Storage, không cần Web Data (Autofill) hay History.
    try:
        default_dir = os.path.join(profile_dir, "Default")
        if os.path.isdir(default_dir):
            for db_file in ["Web Data", "Web Data-journal", "History", "History-journal"]:
                db_path = os.path.join(default_dir, db_file)
                if os.path.lexists(db_path):
                    try:
                        os.remove(db_path)
                    except:
                        pass
    except Exception:
        pass


def clone_shared_chatgpt_profile(profile_id: str, overwrite: bool = False) -> str:
    clean_id = sanitize_profile_id(profile_id)
    if not clean_id:
        raise ValueError("Thiếu TikTok ID để clone profile ChatGPT")

    source_dir = CHROME_PROFILE
    target_dir = get_chatgpt_profile_dir(clean_id)

    if not os.path.exists(source_dir):
        raise FileNotFoundError(f"Chưa có profile ChatGPT chung: {source_dir}")

    if os.path.abspath(source_dir) == os.path.abspath(target_dir):
        return target_dir

    if os.path.exists(target_dir):
        if not overwrite:
            remove_profile_locks(target_dir)
            mark_profile_exited_cleanly(target_dir)
            return target_dir
        shutil.rmtree(target_dir, ignore_errors=True)

    os.makedirs(os.path.dirname(target_dir), exist_ok=True)
    shutil.copytree(source_dir, target_dir, ignore=ignore_transient_profile_items)
    remove_profile_locks(target_dir)
    mark_profile_exited_cleanly(target_dir)
    return target_dir


def ensure_chatgpt_profile(profile_id: str | None = None, is_tele_bot: bool = False) -> str:
    clean_id = sanitize_profile_id(profile_id)
    profile_dir = get_chatgpt_profile_dir(clean_id, is_tele_bot=is_tele_bot)
    if clean_id and not os.path.exists(profile_dir) and os.path.exists(CHROME_PROFILE):
        print(f"      🧬 Chưa có profile ChatGPT cho {clean_id}. Tự clone từ profile chung...")
        profile_dir = clone_shared_chatgpt_profile(clean_id, overwrite=False)
    remove_profile_locks(profile_dir)
    return profile_dir


def is_profile_launch_crash(error: Exception) -> bool:
    """Nhận diện trường hợp Chromium sập ngay khi đọc profile persistent."""
    message = str(error or "").casefold()
    return (
        "launch_persistent_context" in message
        and "target page, context or browser has been closed" in message
    ) or "signal=sigtrap" in message


def rebuild_chatgpt_profile_from_shared(
    profile_dir: str,
    source_dir: str | None = None,
) -> str:
    """Sao lưu profile hỏng rồi tạo lại từ profile ChatGPT chung.

    Profile cũ chỉ được đổi tên, không bị xóa, nên cookie hoặc dữ liệu cũ vẫn
    có thể phục hồi thủ công. Nếu sao chép thất bại, profile cũ được đưa về
    đúng vị trí ban đầu.
    """
    source_dir = os.path.abspath(source_dir or CHROME_PROFILE)
    profile_dir = os.path.abspath(profile_dir)
    if source_dir == profile_dir:
        raise RuntimeError("Không thể tự phục hồi profile ChatGPT chung từ chính nó")
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"Không có profile ChatGPT chung: {source_dir}")
    if not os.path.isdir(profile_dir):
        raise FileNotFoundError(f"Không có profile cần phục hồi: {profile_dir}")

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = f"{profile_dir}.broken-{timestamp}"
    suffix = 2
    while os.path.lexists(backup_dir):
        backup_dir = f"{profile_dir}.broken-{timestamp}-{suffix}"
        suffix += 1

    remove_profile_locks(profile_dir)
    shutil.move(profile_dir, backup_dir)
    try:
        shutil.copytree(
            source_dir,
            profile_dir,
            ignore=ignore_transient_profile_items,
        )
        remove_profile_locks(profile_dir)
        mark_profile_exited_cleanly(profile_dir)
    except Exception:
        if not os.path.exists(profile_dir) and os.path.exists(backup_dir):
            shutil.move(backup_dir, profile_dir)
        raise
    return backup_dir


def load_prompt() -> str:
    if os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def wait_for_login_finish(context):
    try:
        input("👉 Đăng nhập xong → nhấn ENTER ở đây... ")
        return
    except EOFError:
        print("👉 Đang chạy từ giao diện web nên không có terminal để nhấn ENTER.")
        print("👉 Hãy đăng nhập ChatGPT trong cửa sổ Chrome vừa mở, sau đó ĐÓNG cửa sổ Chrome để lưu phiên.")

    while True:
        try:
            pages = context.pages
            if not pages or all(page.is_closed() for page in pages):
                return
        except Exception:
            return
        time.sleep(1)


def is_cloudflare_challenge(page) -> bool:
    title = (page.title() or "")
    if "challenge" in page.url:
        return True
    if "Just a moment" in title or "Attention Required" in title:
        return True
    if page.locator("iframe[src*='challenges.cloudflare.com']").count() > 0:
        return True
    return False


RATE_LIMIT_MARKERS = ("too many requests", "quá nhiều yêu cầu", "making requests too quickly")
RATE_LIMIT_RETRY_WAIT_SECONDS = 10
RECOVERY_RELOAD_WAIT_SECONDS = 2
# A response attempt can wait up to six minutes.  Thirty attempts made one
# stuck video hold the whole scheduler for hours, so keep this bounded while
# still allowing a few transient UI retries.  It remains configurable for
# operators who need a longer rate-limit window.
try:
    MAX_RATE_LIMIT_RETRIES = max(1, int(os.environ.get("CHATGPT_MAX_RETRIES", "3")))
except (TypeError, ValueError):
    MAX_RATE_LIMIT_RETRIES = 3
RESPONSE_POLL_INTERVAL_SECONDS = 1
INCOMPLETE_RESPONSE_STUCK_SECONDS = 18
try:
    CHATGPT_RESPONSE_TIMEOUT_SECONDS = max(
        60,
        int(os.environ.get("CHATGPT_RESPONSE_TIMEOUT_SECONDS", "180")),
    )
except (TypeError, ValueError):
    CHATGPT_RESPONSE_TIMEOUT_SECONDS = 180
DIALOG_DISMISS_LABELS = ("Đã hiểu", "Got it", "OK", "Okay", "Close", "Đóng")
CHATGPT_HOME_URL = "https://chatgpt.com/"
UPLOAD_READY = "ready"
UPLOAD_RATE_LIMITED = "rate_limited"
UPLOAD_FAILED = "failed"

# ChatGPT has changed the wrapper around assistant turns several times.  Keep
# the old selector first, but also support the current conversation-turn
# wrappers.  The old implementation only looked for the first selector and
# therefore treated a perfectly valid response as an empty response.
ASSISTANT_MESSAGE_SELECTORS = (
    'div[data-message-author-role="assistant"]',
    '[data-message-author-role="assistant"]',
    'article[data-testid*="conversation-turn-assistant"]',
    '[data-testid="conversation-turn-assistant"]',
    '[data-testid*="conversation-turn-assistant"]',
    '[data-testid*="assistant-turn"]',
    '[data-markdown-text-style="assistant-message"]',
    '[class*="MarkdownRoot"]',
    # Current ChatGPT fallback renderer (the HTML pasted from the browser):
    # the assistant turn is keyed as `fallback-turn-...:assistant` and the
    # actual JSON lives in its nested MarkdownRoot div.
    'div[data-content-search-unit-key$=":assistant"]',
    '[data-chatgpt-search-unit-key$=":assistant"]',
    'div:has(> h4[data-conversation-role="assistant"])',
)
ASSISTANT_MESSAGE_SELECTOR = ", ".join(ASSISTANT_MESSAGE_SELECTORS)


def _blocking_dialog_text(page) -> str:
    """Đóng dialog đang che ô chat (vd 'Too many requests') nếu đang hiện,
    bằng cách bấm nút 'Đã hiểu'/'Got it'... Trả về text đã đọc được ("" nếu
    không có dialog) để nơi gọi biết có đang bị rate limit không.
    """
    try:
        dialog = page.locator('div[role="dialog"]').first
        if dialog.count() == 0 or not dialog.is_visible(timeout=1000):
            return ""
        try:
            text = (dialog.inner_text(timeout=2000) or "").strip()
        except Exception:
            text = ""
        for label in DIALOG_DISMISS_LABELS:
            try:
                button = dialog.locator(f'button:has-text("{label}")').first
                if button.count() > 0 and button.is_visible(timeout=1000):
                    button.click(timeout=5000, force=True)
                    time.sleep(1)
                    return text
            except Exception:
                continue
        # Không tìm được nút quen thuộc thì thử Escape.
        try:
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass
        return text
    except Exception:
        return ""


def is_rate_limited_text(text: str) -> bool:
    lowered = (text or "").casefold()
    return any(marker in lowered for marker in RATE_LIMIT_MARKERS)


def dismiss_rate_limit_dialog(page) -> bool:
    """Close a visible rate-limit dialog and report whether one was found."""
    return is_rate_limited_text(_blocking_dialog_text(page))


def remember_active_chat_url(page, fallback_url: str, timeout_seconds: int = 0) -> str:
    """Keep the exact conversation URL after ChatGPT creates the chat.

    A rate-limit reload can redirect the browser back to the home page. Only a
    real /c/ conversation URL is allowed to replace the remembered value, so
    retries can always navigate back to the chat that received the prompt.
    """
    deadline = time.time() + max(0, int(timeout_seconds))
    while True:
        try:
            current_url = str(page.url or "")
        except Exception:
            current_url = ""
        if "/c/" in current_url and current_url.startswith("https://chatgpt.com/"):
            return current_url
        if time.time() >= deadline:
            return fallback_url or CHATGPT_HOME_URL
        time.sleep(0.5)


def get_chatgpt_profile_label(profile_id: str | None = None, is_tele_bot: bool = False) -> str:
    clean_id = sanitize_profile_id(profile_id)
    if clean_id:
        return f"TikTok/{clean_id}" if is_tele_bot else clean_id
    if is_tele_bot:
        return "Tele Bot"
    return clean_id or "Profile chung"


def focus_prompt_box(page, timeout: int = 30000):
    textarea = page.locator("#prompt-textarea, [contenteditable='true']").first
    textarea.wait_for(state="visible", timeout=timeout)
    try:
        textarea.click(timeout=15000, force=True)
    except Exception:
        handle = textarea.element_handle(timeout=5000)
        if not handle:
            raise
        page.evaluate("(el) => el.focus()", handle)
    return textarea


def replace_prompt_text(page, text: str):
    focus_prompt_box(page)

    import platform
    modifier = "Meta" if platform.system() == "Darwin" else "Control"
    page.keyboard.press(f"{modifier}+A")
    time.sleep(0.2)
    page.keyboard.press("Backspace")
    time.sleep(0.2)

    try:
        page.keyboard.insert_text(text)
        return
    except Exception:
        pass

    page.evaluate(
        """(text) => {
            const el = document.querySelector('#prompt-textarea, [contenteditable="true"]');
            if (!el) throw new Error('prompt textarea not found');
            el.focus();
            if (el.isContentEditable) {
                document.execCommand('selectAll', false, null);
                document.execCommand('insertText', false, text);
            } else {
                el.value = text;
                el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
            }
        }""",
        text,
    )


def click_send_button(page):
    selector = '[data-testid="send-button"], button[aria-label="Send"], button[aria-label="Gửi lời nhắc"]'
    send_btn = page.locator(selector).first

    deadline = time.time() + 120
    last_error = None
    while time.time() < deadline:
        try:
            if send_btn.count() > 0 and send_btn.is_visible(timeout=1000) and send_btn.is_enabled(timeout=1000):
                send_btn.click(timeout=15000, force=True)
                return
        except Exception as e:
            last_error = e
        time.sleep(1)

    try:
        page.evaluate(
            """(selector) => {
                const btn = document.querySelector(selector);
                if (!btn) throw new Error('send button not found');
                btn.click();
            }""",
            selector,
        )
        return
    except Exception as e:
        last_error = e

    try:
        focus_prompt_box(page, timeout=5000)
        page.keyboard.press("Enter")
        return
    except Exception:
        if last_error:
            raise last_error
        raise


def wait_for_video_upload(page, video_path: str, timeout_seconds: int = 90) -> str:
    """Wait until ChatGPT visibly acknowledges the uploaded video.

    ``set_input_files`` only proves that the browser input received a local
    path; it does not prove that ChatGPT attached the file to the message.
    Sending the prompt immediately can therefore produce a confident JSON
    based only on the caption.  Require an attachment/file-name signal before
    sending so the evidence gate can trust the visual analysis.
    """
    filename = os.path.basename(video_path or "").strip().lower()
    deadline = time.time() + max(10, int(timeout_seconds))
    upload_error_markers = (
        "upload failed", "failed to upload", "couldn't upload",
        "không thể tải lên", "tải lên thất bại", "file quá lớn",
    )

    while time.time() < deadline:
        # The popup can appear after set_input_files(), not only on page load.
        # Close it immediately instead of misclassifying it as upload failure.
        if dismiss_rate_limit_dialog(page):
            return UPLOAD_RATE_LIMITED

        try:
            body_text = page.locator("body").inner_text(timeout=2000).lower()
        except Exception:
            body_text = ""
        if any(marker in body_text for marker in upload_error_markers):
            return UPLOAD_FAILED

        try:
            attachment_state = page.evaluate(
                """(name) => {
                    const nodes = Array.from(document.querySelectorAll(
                        '[data-testid], [aria-label], [title], img, video, button, [role="button"]'
                    ));
                    const text = (node) => [
                        node.getAttribute('data-testid') || '',
                        node.getAttribute('aria-label') || '',
                        node.getAttribute('title') || '',
                        node.getAttribute('alt') || '',
                        node.textContent || '',
                    ].join(' ').toLowerCase();
                    const named = Boolean(name) && nodes.some((node) => text(node).includes(name));
                    const attachment = nodes.some((node) => {
                        const value = text(node);
                        return /remove.*(file|attachment)|attachment.*(file|video)|file.*(attached|uploaded)/.test(value);
                    });
                    const uploading = /uploading|đang tải lên|processing video|đang xử lý video/.test(
                        document.body.innerText.toLowerCase()
                    );
                    return { named, attachment, uploading };
                }""",
                filename,
            )
        except Exception:
            attachment_state = {}

        if (
            (attachment_state.get("named") or attachment_state.get("attachment"))
            and not attachment_state.get("uploading")
        ):
            print("      ✅ ChatGPT đã xác nhận video đính kèm.")
            return UPLOAD_READY
        time.sleep(2)

    print(
        "      ❌ ChatGPT không xác nhận video đính kèm sau "
        f"{timeout_seconds} giây; không gửi prompt chỉ có caption."
    )
    return UPLOAD_FAILED


def has_complete_json_object(value: str) -> bool:
    """Return True only after the first JSON object has closed completely."""
    text_value = str(value or "")
    start = text_value.find("{")
    if start < 0:
        return False
    depth = 0
    in_string = False
    escaped = False
    for char in text_value[start:]:
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return True
    return False


def extract_last_json_object(value: str) -> str:
    """Return the last complete top-level JSON object visible in a page.

    ChatGPT can render the answer without the usual assistant wrapper while it
    is showing a stack of agent-activity rows. In that layout, scanning the
    visible body is safer than depending on one CSS class, but the prompt itself
    also contains a JSON schema. Selecting the last balanced top-level object
    and excluding the pre-send object avoids returning that schema as a result.
    """
    text_value = str(value or "")
    last_object = ""
    object_start = None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text_value):
        if object_start is None:
            if char == "{":
                object_start = index
                depth = 1
                in_string = False
                escaped = False
            continue
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                last_object = text_value[object_start : index + 1].strip()
                object_start = None
    return last_object if has_complete_json_object(last_object) else ""


def looks_like_generated_result(value: str) -> bool:
    """Reject the JSON schema still visible in the user prompt."""
    try:
        data = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return bool(
        str(data.get("hook") or "").strip()
        or str(data.get("script_voice") or "").strip()
        or str(data.get("title_tiktok") or "").strip()
        or str(data.get("skip_reason") or "").strip()
        or data.get("should_make_video") is False
    )


def scroll_chat_to_bottom(page) -> bool:
    """Scroll ChatGPT's real conversation container so lazy content is rendered."""
    try:
        messages = page.locator(ASSISTANT_MESSAGE_SELECTOR)
        if messages.count() > 0:
            try:
                messages.last.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass
        return bool(page.evaluate(
            """(selector) => {
                const messages = Array.from(document.querySelectorAll(selector));
                const target = messages[messages.length - 1] ||
                    document.querySelector('main') || document.body;
                target.scrollIntoView({block: 'end', behavior: 'instant'});

                let moved = false;
                let node = target;
                while (node) {
                    if (node.scrollHeight > node.clientHeight + 8) {
                        node.scrollTop = node.scrollHeight;
                        moved = true;
                    }
                    node = node.parentElement;
                }
                const root = document.scrollingElement;
                if (root && root.scrollHeight > root.clientHeight + 8) {
                    root.scrollTop = root.scrollHeight;
                    moved = true;
                }
                return moved;
            }""",
            ASSISTANT_MESSAGE_SELECTOR,
        ))
    except Exception:
        return False


def assistant_message_count(page) -> int:
    try:
        return page.locator(ASSISTANT_MESSAGE_SELECTOR).count()
    except Exception:
        return 0


def assistant_activity_count(page) -> int:
    """Count ChatGPT's expandable activity rows, not assistant answers."""
    try:
        return page.locator(
            '[class*="activity-header"], [data-agent-activity], '
            '[data-testid*="agent-activity"]'
        ).count()
    except Exception:
        return 0


def read_latest_assistant_text(
    page,
    minimum_count: int = 0,
    *,
    fallback_to_body: bool = False,
    exclude_json: str = "",
) -> str:
    """Read the newest assistant turn, including nested markdown/code blocks.

    The ChatGPT UI may put the visible answer in a nested ``pre``, ``code`` or
    markdown wrapper while the outer assistant node contains only the task
    status (``Analyzed``, ``Worked for ...``).  Prefer the longest visible
    text from the newest assistant turn so the JSON is not discarded merely
    because the outer wrapper is short or virtualized.
    """
    scroll_chat_to_bottom(page)
    # Keep selector/virtualization failures isolated from the body fallback.
    # ChatGPT can detach an activity node between count() and inner_text();
    # that must not prevent reading JSON still visible in document.body.
    try:
        messages = page.locator(ASSISTANT_MESSAGE_SELECTOR)
        count = messages.count()
        if count > minimum_count:
            try:
                result = page.evaluate(
                """({selector, minimumCount}) => {
                const nodes = Array.from(document.querySelectorAll(selector));
                if (nodes.length <= minimumCount) return {text: '', count: nodes.length};
                const node = nodes[nodes.length - 1];
                const candidates = [node, ...node.querySelectorAll(
                    // The current renderer puts the real answer in this node;
                    // activity headers such as "Analyzed/Đã phân tích" must
                    // never be treated as the assistant response.
                    '[data-markdown-text-style="assistant-message"], '
                    'pre, code, .markdown, .prose, [class*="markdown"], '
                    '[data-testid*="response"], [data-testid*="message-content"]'
                )];
                const texts = candidates
                    .filter((item) => !item.matches(
                        '[class*="activity-header"], [data-agent-activity], '
                        '[data-testid*="agent-activity"]'
                    ))
                    .map((item) => (item.innerText || item.textContent || '').trim())
                    .filter(Boolean);
                texts.sort((a, b) => b.length - a.length);
                return {text: texts[0] || '', count: nodes.length};
                }""",
                    {"selector": ASSISTANT_MESSAGE_SELECTOR, "minimumCount": minimum_count},
                )
                text = (result or {}).get("text", "")
                if text:
                    text = str(text).strip()
                    # A status-only activity node can say "Analyzed" or
                    # "Đã phân tích" (and may be repeated several times). It is not a
                    # script. Expected responses are JSON objects, so do not expose a
                    # status string to the retry/parser pipeline.
                    if "{" in text and text != exclude_json:
                        return text
            except Exception:
                pass

            # A detached virtualized node must not skip the body fallback.
            try:
                fallback_text = (messages.last.inner_text(timeout=3000) or "").strip()
                if "{" in fallback_text and fallback_text != exclude_json:
                    return fallback_text
            except Exception:
                pass
    except Exception:
        pass

    if fallback_to_body:
        try:
            body_text = page.locator("body").inner_text(timeout=3000) or ""
            body_json = extract_last_json_object(body_text)
            if (
                body_json
                and body_json != exclude_json
                and looks_like_generated_result(body_json)
            ):
                print(
                    "      🧭 Đã lấy JSON từ nội dung hiển thị của ChatGPT "
                    "(fallback toàn trang).",
                    flush=True,
                )
                return body_json
        except Exception:
            pass
    return ""


def save_chatgpt_reader_debug(page, profile_id: str | None, attempt: int, reason: str) -> None:
    """Persist a small local diagnostic when the UI response cannot be read."""
    try:
        debug_dir = os.path.join(PROJECT_ROOT, "data", "chatgpt_logs")
        os.makedirs(debug_dir, exist_ok=True)
        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=2000) or ""
        except Exception:
            pass
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "profile_id": sanitize_profile_id(profile_id),
            "attempt": attempt,
            "reason": reason,
            "url": str(getattr(page, "url", "") or ""),
            "assistant_count": assistant_message_count(page),
            "assistant_text": read_latest_assistant_text(page, 0)[:20000],
            "body_tail": body_text[-12000:],
        }
        filename = f"reader_debug_{int(time.time())}_{sanitize_profile_id(profile_id) or 'general'}.json"
        with open(os.path.join(debug_dir, filename), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        print(f"         🧪 Reader debug: {os.path.join(debug_dir, filename)}")
    except Exception as debug_error:
        print(f"         ⚠️ Không lưu được reader debug: {debug_error}")


def wait_for_assistant_response(
    page,
    timeout_seconds: int = CHATGPT_RESPONSE_TIMEOUT_SECONDS,
    previous_assistant_count: int = 0,
    previous_json_text: str = "",
) -> tuple[str, bool]:
    start = time.time()
    last_text = ""
    stable_since = None
    activity_notice_shown = False

    while time.time() - start < timeout_seconds:
        # Detect and dismiss rate limiting while the answer is being rendered.
        if dismiss_rate_limit_dialog(page):
            return last_text, True

        stop_visible = False
        try:
            stop_btn = page.locator('[data-testid="stop-button"], button[aria-label="Stop"], button[aria-label="Dừng tạo"]').first
            stop_visible = stop_btn.count() > 0 and stop_btn.is_visible(timeout=1000)
        except Exception:
            stop_visible = False

        # ChatGPT virtualizes/lazy-renders long answers. Without scrolling the
        # conversation container, inner_text() can keep returning only the
        # intermediate task summary although the final JSON already exists.
        text = read_latest_assistant_text(
            page,
            previous_assistant_count,
            fallback_to_body=True,
            exclude_json=previous_json_text,
        )

        # Some ChatGPT builds reuse the same assistant-turn node for a new
        # response.  In that case the node count does not increase, even
        # though its text has changed.  Once generation has stopped, read the
        # newest node without the count gate as a compatibility fallback.
        if not text and not stop_visible and previous_assistant_count:
            text = read_latest_assistant_text(page, 0)

        if not text and not activity_notice_shown:
            activity_count = assistant_activity_count(page)
            if activity_count:
                print(
                    f"      ℹ️ ChatGPT đang hiển thị {activity_count} dòng activity "
                    "(Đã phân tích/Analyzed); chưa có JSON để lấy, tiếp tục chờ...",
                    flush=True,
                )
                activity_notice_shown = True

        if text:
            if text != last_text:
                last_text = text
                stable_since = time.time()

            # Prompt yêu cầu một JSON độc lập. Ngay khi dấu ngoặc đã cân bằng,
            # dữ liệu cần lấy đã hoàn chỉnh; không cần chờ nội dung đứng yên
            # thêm 10-12 giây như trước.
            if has_complete_json_object(text):
                return text, False

            if not stop_visible and stable_since:
                stable_seconds = time.time() - stable_since
                if stable_seconds >= INCOMPLETE_RESPONSE_STUCK_SECONDS:
                    print("      ⚠️ Phản hồi JSON đứng yên nhưng chưa hoàn chỉnh; "
                          "sẽ tải lại đúng chat để thử tiếp.")
                    return text, False

        time.sleep(RESPONSE_POLL_INTERVAL_SECONDS)

    return last_text, False


_JSON_KEY_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _sanitize_json_text(value: str) -> str:
    """Normalize control characters ChatGPT sometimes inserts inside JSON
    strings (notably raw CR/LF from a word-wrapped long URL in source_url).

    Không dùng lookbehind "(?<!\\\\)": lớp ký tự này chỉ khớp ký tự điều khiển
    THẬT (0x00-0x1f), không phải chuỗi hai ký tự "\\n". Ký tự điều khiển thật
    luôn không hợp lệ trong JSON string, kể cả sau dấu gạch chéo.
    """
    value = str(value or "")
    # Gạch chéo lẻ + xuống dòng thật = ChatGPT ngắt dòng giữa chuỗi; bỏ cả cặp
    # để không tạo escape sequence rác ("\ ").
    value = re.sub(r"\\[\r\n]+\s*", " ", value)
    return re.sub(
        r"[\x00-\x1f\x7f]",
        lambda match: " " if match.group(0) in "\r\n\t" else "",
        value,
    )


def _repair_json_string_quotes(value: str) -> str:
    """Escape an occasional unescaped quote inside a JSON string.

    ChatGPT sometimes writes a quoted phrase inside a text field without
    escaping it. A quote is only treated as closing the string when the next
    non-space character is a JSON delimiter — and ``:`` only counts when the
    text read so far looks like a real JSON key (plain ASCII identifier, no
    spaces), otherwise a natural-language colon (e.g. "Đại diện cho biết:",
    a time like "20:30") would be misread as ending a value string and
    corrupt everything that follows.
    """
    output = []
    in_string = False
    escaped = False
    current: list[str] = []
    length = len(value)
    for index, char in enumerate(value):
        if not in_string:
            output.append(char)
            if char == '"':
                in_string = True
                current = []
            continue
        if escaped:
            output.append(char)
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            output.append(char)
            current.append(char)
            escaped = True
            continue
        if char == '"':
            lookahead = index + 1
            while lookahead < length and value[lookahead].isspace():
                lookahead += 1
            next_char = value[lookahead] if lookahead < length else ""
            buffered = "".join(current)
            if next_char == ":":
                # Only a real JSON key ends with `":` — a colon inside prose
                # ("Đại diện cho biết:", "20:30") does not.
                is_closer = bool(_JSON_KEY_PATTERN.match(buffered))
            elif next_char == ",":
                # A closing quote is followed by the next key/element, so after
                # the comma we expect `"`, `{`, `[`, or a literal. Free-flowing
                # prose after the comma means this quote belongs to the text
                # (e.g. ChatGPT wrote \"Quốc ca", cổ vũ ... leaving the closing
                # quote unescaped).
                after = lookahead + 1
                while after < length and value[after].isspace():
                    after += 1
                following = value[after] if after < length else ""
                is_closer = (
                    following in '"{[' or following.isdigit()
                    or following in "-+" or following == ""
                    or value[after:after + 4].lower() in ("true", "null")
                    or value[after:after + 5].lower() == "false"
                )
            elif next_char in "}]":
                is_closer = True
            elif not next_char:
                is_closer = True
            else:
                is_closer = False
            if not is_closer:
                output.append('\\"')
                current.append('"')
            else:
                output.append(char)
                in_string = False
            continue
        output.append(char)
        current.append(char)
    return "".join(output)


def _prepare_json_candidate(value: str) -> str:
    cleaned = _repair_json_string_quotes(_sanitize_json_text(value))
    return re.sub(r',\s*([}\]])', r'\1', cleaned)


def extract_json_response(raw_text: str) -> dict:
    """Parse ChatGPT's reply, trying progressively stronger repairs.

    Raises json.JSONDecodeError when no variant parses, so the caller can log
    the raw payload for diagnosis.
    """
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw_text or '', flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.MULTILINE).strip()
    cleaned = cleaned.replace('“', '"').replace('”', '"')
    cleaned = cleaned.replace('‘', "'").replace('’', "'")

    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    sanitized = _sanitize_json_text(cleaned)
    variants = [
        cleaned,
        sanitized,
        re.sub(r',\s*([}\]])', r'\1', sanitized),
        _repair_json_string_quotes(sanitized),
        _prepare_json_candidate(cleaned),
    ]
    first_error = None
    for candidate in variants:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as error:
            if first_error is None:
                first_error = error
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(candidate.strip())
            return obj
        except json.JSONDecodeError:
            continue
    raise first_error if first_error else json.JSONDecodeError("No JSON found", cleaned or "", 0)




def login_chatgpt_interactive(is_tele_bot: bool = False, profile_id: str | None = None):
    """
    Mở Chrome thật (có profile) để đăng nhập ChatGPT.
    Profile lưu vĩnh viễn → lần sau không cần login lại.
    """
    clean_id = sanitize_profile_id(profile_id)
    profile_dir = get_chatgpt_profile_dir(clean_id, is_tele_bot=is_tele_bot)
    if is_tele_bot:
        print("╔═══════════════════════════════════════════════════╗")
        print("║  🔑 ĐĂNG NHẬP CHATGPT (TELEGRAM BOT)              ║")
        print("╚═══════════════════════════════════════════════════╝")
    elif clean_id:
        print("╔═══════════════════════════════════════════════════╗")
        print(f"║  🔑 ĐĂNG NHẬP CHATGPT CHO {clean_id[:22]:<22}║")
        print("╚═══════════════════════════════════════════════════╝")
    else:
        print("╔═══════════════════════════════════════════════════╗")
        print("║  🔑 ĐĂNG NHẬP CHATGPT (PROFILE CHUNG)             ║")
        print("╚═══════════════════════════════════════════════════╝")
    print()
    print("📋 Hướng dẫn:")
    print("   1. Chrome sẽ mở trang ChatGPT")
    print("   2. Tick ô 'Xác minh bạn là con người' nếu có")
    print("   3. Đăng nhập tài khoản ChatGPT")
    print("   4. Khi thấy ô chat → quay lại terminal nhấn ENTER")
    print()


    os.makedirs(profile_dir, exist_ok=True)
    # Xóa lock cũ nếu có (tránh lỗi "profile already in use")
    for lock_name in ["SingletonLock", "SingletonSocket"]:
        lock_file = os.path.join(profile_dir, lock_name)
        if os.path.lexists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass
    mark_profile_exited_cleanly(profile_dir)
    print("🧹 Đã kiểm tra và xóa Singleton* cũ")

    with sync_playwright() as p:
        # Dùng persistent context = Chrome profile thật
        # Không bị Cloudflare chặn như browser thường
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            args=[
                "--no-sandbox",
                "--test-type",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-session-crashed-bubble",
                "--hide-crash-restore-bubble",
            ],
            viewport={"width": 1280, "height": 800},
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
            # Không set user_agent → dùng UA mặc định của Chrome = tự nhiên nhất
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded")

        print("🌐 Chrome đã mở. Hãy đăng nhập ChatGPT...")
        print()
        wait_for_login_finish(context)

        print()
        print(f"✅ Profile đã lưu: {profile_dir}")
        print("🎉 Lần sau pipeline sẽ tự động dùng phiên này!")

        try:
            context.close()
        except Exception:
            pass


def analyze_video_with_chatgpt(
    video_path: str,
    caption: str,
    is_tele_bot: bool = False,
    extra_content: str = "",
    profile_id: str | None = None,
    repair_instruction: str = "",
    source_type: str = "facebook",
    experiment_content_key: str = "",
    edit_mode: str = "",
    whisper_transcript: str = "",
) -> dict | None:
    """
    Tự động:
    1. Mở ChatGPT (dùng Chrome profile đã login)
    2. Upload file video
    3. Gửi prompt + caption + extra_content (nếu có) + whisper_transcript (nếu có)
    4. Chờ ChatGPT trả lời
    5. Parse JSON từ phản hồi
    """
    clean_id = sanitize_profile_id(profile_id)
    profile_dir = ensure_chatgpt_profile(clean_id, is_tele_bot=is_tele_bot)

    if not os.path.exists(profile_dir):
        print("      ❌ CHƯA LOGIN CHATGPT!")
        if is_tele_bot:
            print("      💡 Chạy: python3 chatgpt_automator.py login tele")
        elif clean_id:
            print(f"      💡 Chạy: python3 chatgpt_automator.py login {clean_id}")
        else:
            print("      💡 Chạy: python3 chatgpt_automator.py login")
        return None

    prompt_text = load_prompt()
    
    extra_instruction = ""
    if extra_content:
        extra_instruction = (
            "\n[CHỈ ĐẠO OPERATOR]: Phần chỉ đạo riêng đã được PromptBuilder "
            "chèn vào HỒ SƠ KÊNH và được ưu tiên sau định vị trung tâm.\n"
        )
    else:
        extra_instruction = "\n[CHỈ ĐẠO]: Hãy bám sát vào hình ảnh và nội dung của video gốc để viết content.\n"
    extra_instruction += (
        "\n[YÊU CẦU ĐỊNH DẠNG BẮT BUỘC]:\n"
        "- TUYỆT ĐỐI KHÔNG viết tắt. Mọi từ ngữ phải được viết đầy đủ bằng tiếng Việt chuẩn (Ví dụ: phải viết 'không' thay vì 'ko', 'được' thay vì 'đc', 'thành phố Hồ Chí Minh' thay vì 'TPHCM').\n"
    )
        
    if is_tele_bot:
        extra_instruction += (
            "\n[YÊU CẦU RIÊNG CỦA TELEGRAM BOT]:\n"
            "- TUYỆT ĐỐI KHÔNG sử dụng bất kỳ hashtag nào (ví dụ: #tintuc).\n"
            "- TUYỆT ĐỐI KHÔNG sử dụng emoji, icon hay ký tự đặc biệt trang trí (ví dụ: 🔥, 😊, 📌).\n"
        )

    transcript_block = ""
    if whisper_transcript and whisper_transcript.strip():
        transcript_block = (
            f"\n[THOẠI GỐC TỪ VIDEO (WHISPER TRANSCRIPT BÓC TÁCH)]:\n"
            f"\"{whisper_transcript.strip()}\"\n\n"
            f"[QUY TẮC PHÂN BỔ NỘI DUNG 70/30 & SỬA CHÍNH TẢ BẮT BUỘC]:\n"
            f"1. TỶ LỆ DỮ KIỆN (70% THOẠI WHISPER / 30% HÌNH ẢNH):\n"
            f"   - 70% Nội dung kịch bản (bao gồm CÂU MỞ ĐẦU/HOOK, THÂN BÀI/SCRIPT_VOICE và TIÊU ĐỀ/TITLE) PHẢI dựa trực tiếp trên LỜI THOẠI GỐC WHISPER bóc tách ở trên.\n"
            f"   - 30% Nội dung tham khảo bổ sung từ bối cảnh, chi tiết trực quan trong video.\n"
            f"2. TỰ ĐỘNG SỬA LỖI CHÍNH TẢ WHISPER:\n"
            f"   - Lời thoại từ Whisper có thể chứa từ viết sai chính tả hoặc lỗi nhận diện âm thanh. Hãy tự động sửa lại đúng chính tả tiếng Việt chuẩn, đảm bảo câu văn mượt mà và đúng ngữ cảnh.\n"
            f"3. TUYỆT ĐỐI KHÔNG BỊA DỮ KIỆN SAI SỰ THẬT:\n"
            f"   - Mọi sự việc, tên riêng, nội dung phát biểu chính trong CÂU MỞ ĐẦU và THÂN BÀI phải bám sát lời thoại gốc, không tự đoán mò hay bịa thoại sai sự thật từ hình ảnh.\n"
        )
        
    task_input = (
        f"VIDEO GỐC\nCaption/Tiêu đề gốc: {caption}\n"
        f"{transcript_block}"
        f"{extra_instruction}\n"
        "An toàn dữ kiện: không bịa; thông tin chỉ có trong caption phải được dẫn nguồn một lần tự nhiên; "
        "chi tiết chưa xác nhận phải dùng ngôn ngữ điều kiện.\n"
        "Hãy dùng lời thoại bóc tách (70%), hình ảnh video (30%) và caption làm nguồn để viết một bản tin liền mạch, "
        "không kể tuần tự các khung hình."
    )
    if edit_mode == EDIT_MODE_HOOK_THEN_ORIGINAL:
        # Không dựng prompt bản tin 150 từ cho Mode chỉ dùng một câu hook.
        # Điều này giảm đáng kể thời gian sinh và kích thước JSON ChatGPT.
        experiment_assignment = None
        full_prompt = build_hook_prompt(
            caption=caption,
            channel_id=clean_id,
            extra_content=extra_content,
            repair_instruction=repair_instruction,
        )
    else:
        experiment_assignment = resolve_prompt_experiment(
            clean_id,
            source_type=source_type,
            content_key=(
                experiment_content_key
                or f"{os.path.basename(video_path)}|{caption}"
            ),
            task_input=task_input,
        )
        full_prompt = build_prompt(
            prompt_text,
            clean_id,
            source_type=source_type,
            task_input=task_input,
            repair_instruction=repair_instruction,
            operator_profiles=(extra_content,) if extra_content else (),
            experiment_assignment=experiment_assignment,
        )

    profile_label = get_chatgpt_profile_label(clean_id, is_tele_bot=is_tele_bot)
    print(f"      🤖 Mở ChatGPT (Profile: {profile_label})...")

    # Lấy lock riêng cho profile này – chặn worker thứ 2 mở cùng profile
    _profile_lock = _get_profile_lock(profile_dir)
    if not _profile_lock.acquire(blocking=True, timeout=300):
        print("      ❌ Không thể lấy profile lock sau 5 phút – bỏ qua video này.")
        return None

    playwright = None
    try:
        # Xóa lock cũ
        for lock_name in ["SingletonLock", "SingletonSocket"]:
            lock_file = os.path.join(profile_dir, lock_name)
            if os.path.lexists(lock_file):
                try:
                    os.remove(lock_file)
                except Exception:
                    pass
        mark_profile_exited_cleanly(profile_dir)

        playwright = sync_playwright().start()
        launch_options = {
            "user_data_dir": profile_dir,
            "headless": False,
            "args": [
                "--no-sandbox",
                "--test-type",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-session-crashed-bubble",
                "--hide-crash-restore-bubble",
            ],
            "viewport": {"width": 1920, "height": 1080},
        }
        try:
            context = playwright.chromium.launch_persistent_context(
                **launch_options,
            )
        except Exception as launch_error:
            can_rebuild = (
                bool(clean_id)
                and profile_dir != os.path.abspath(CHROME_PROFILE)
                and is_profile_launch_crash(launch_error)
            )
            if not can_rebuild:
                print(f"      ❌ Không khởi động được Chromium cho ChatGPT: {launch_error}")
                return None

            print(
                "      🩹 Profile Chrome bị sập khi khởi động; "
                "đang sao lưu và phục hồi từ profile ChatGPT chung..."
            )
            try:
                broken_profile_backup = rebuild_chatgpt_profile_from_shared(
                    profile_dir,
                )
                print(
                    "      💾 Đã giữ profile hỏng tại: "
                    f"{broken_profile_backup}"
                )
                context = playwright.chromium.launch_persistent_context(
                    **launch_options,
                )
                print("      ✅ Phục hồi profile Chrome thành công.")
            except Exception as recovery_error:
                print(
                    "      ❌ Không khởi động được Chromium sau khi phục hồi: "
                    f"{recovery_error}"
                )
                return None

        page = context.pages[0] if context.pages else context.new_page()

        try:
            raw_text = ""
            chat_url = CHATGPT_HOME_URL
            for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
                page.goto(chat_url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(5)
                chat_url = remember_active_chat_url(page, chat_url)

                # Popup "Too many requests" phủ lên ô chat khiến mọi thao tác
                # sau đó treo tới timeout. Gặp thì bấm Got it rồi tải đúng chat.
                if dismiss_rate_limit_dialog(page):
                    print(f"      ⏳ ChatGPT báo 'Too many requests' (lần {attempt}/{MAX_RATE_LIMIT_RETRIES}), "
                          f"đã bấm Got it; nghỉ {RATE_LIMIT_RETRY_WAIT_SECONDS}s rồi tải lại đúng chat...")
                    time.sleep(RATE_LIMIT_RETRY_WAIT_SECONDS)
                    continue

                # Chờ ô nhập xuất hiện
                try:
                    page.wait_for_selector("#prompt-textarea, [contenteditable='true']", timeout=45000)
                except Exception:
                    if is_cloudflare_challenge(page):
                        print("      ❌ Cloudflare chặn! Cần login lại.")
                        context.close()
                        return None
                    rate_limited = dismiss_rate_limit_dialog(page)
                    if rate_limited:
                        print(f"      ⏳ ChatGPT báo 'Too many requests' (lần {attempt}/{MAX_RATE_LIMIT_RETRIES}), "
                              f"đã bấm Got it; nghỉ {RATE_LIMIT_RETRY_WAIT_SECONDS}s rồi tải lại đúng chat...")
                    else:
                        print(f"      🔄 Lần {attempt}/{MAX_RATE_LIMIT_RETRIES}: Chưa thấy ô chat, "
                              f"tải lại đúng chat sau {RECOVERY_RELOAD_WAIT_SECONDS}s...")
                    time.sleep(
                        RATE_LIMIT_RETRY_WAIT_SECONDS
                        if rate_limited else RECOVERY_RELOAD_WAIT_SECONDS
                    )
                    continue

                # Khi tải lại đúng chat sau một lần chờ, cuộn xuống đáy trước.
                # Nếu ChatGPT đã hoàn tất JSON trong lúc reload thì lấy luôn,
                # không upload và gửi trùng video thêm một lần nữa.
                if attempt > 1 and "/c/" in chat_url:
                    existing_text = read_latest_assistant_text(page)
                    if has_complete_json_object(existing_text):
                        print("      ✅ Đã lấy được JSON hoàn chỉnh sau khi cuộn xuống cuối chat.")
                        raw_text = existing_text
                        break

                # Upload video
                print("      📎 Upload video...")
                file_input = page.locator("input[type='file']")
                try:
                    if file_input.count() == 0:
                        raise RuntimeError("Không tìm thấy nút upload file")
                    file_input.first.set_input_files(video_path)
                except Exception as upload_start_error:
                    chat_url = remember_active_chat_url(page, chat_url)
                    rate_limited = dismiss_rate_limit_dialog(page)
                    if rate_limited:
                        print(f"      ⏳ Upload bị chặn bởi 'Too many requests' (lần {attempt}/{MAX_RATE_LIMIT_RETRIES}); "
                              f"đã bấm Got it, nghỉ {RATE_LIMIT_RETRY_WAIT_SECONDS}s rồi tải lại đúng chat...")
                    else:
                        print(f"      🔄 Không bắt đầu được upload: {upload_start_error}. "
                              f"Tải lại đúng chat sau {RECOVERY_RELOAD_WAIT_SECONDS}s...")
                    time.sleep(
                        RATE_LIMIT_RETRY_WAIT_SECONDS
                        if rate_limited else RECOVERY_RELOAD_WAIT_SECONDS
                    )
                    continue

                upload_status = wait_for_video_upload(page, video_path)
                chat_url = remember_active_chat_url(page, chat_url)
                if upload_status != UPLOAD_READY:
                    if upload_status == UPLOAD_RATE_LIMITED:
                        print(f"      ⏳ ChatGPT báo 'Too many requests' trong lúc upload "
                              f"(lần {attempt}/{MAX_RATE_LIMIT_RETRIES}); đã bấm Got it.")
                    else:
                        try:
                            debug_dir = os.path.join(APP_DIR, "data", "logs")
                            os.makedirs(debug_dir, exist_ok=True)
                            debug_path = os.path.join(
                                debug_dir, f"chatgpt_upload_failed_{int(time.time())}.png"
                            )
                            page.screenshot(path=debug_path)
                            print(f"         📸 Screenshot upload: {debug_path}")
                        except Exception:
                            pass
                        print("      🔄 Upload chưa thành công; sẽ tải lại đúng cuộc chat hiện tại.")
                    time.sleep(
                        RATE_LIMIT_RETRY_WAIT_SECONDS
                        if upload_status == UPLOAD_RATE_LIMITED
                        else RECOVERY_RELOAD_WAIT_SECONDS
                    )
                    continue

                # Điền prompt vào ô chat
                try:
                    print("      ✍️ Nhập prompt...")
                    replace_prompt_text(page, full_prompt)
                    time.sleep(1)
                except Exception as prompt_error:
                    chat_url = remember_active_chat_url(page, chat_url)
                    rate_limited = dismiss_rate_limit_dialog(page)
                    if rate_limited:
                        print(f"      ⏳ Không nhập được prompt vì 'Too many requests'; "
                              f"đã bấm Got it, nghỉ {RATE_LIMIT_RETRY_WAIT_SECONDS}s.")
                    else:
                        print(f"      🔄 Không nhập được prompt: {prompt_error}. "
                              "Sẽ tải lại đúng cuộc chat hiện tại.")
                    time.sleep(
                        RATE_LIMIT_RETRY_WAIT_SECONDS
                        if rate_limited else RECOVERY_RELOAD_WAIT_SECONDS
                    )
                    continue

                # Click gửi
                try:
                    previous_assistant_count = assistant_message_count(page)
                    try:
                        previous_json_text = extract_last_json_object(
                            page.locator("body").inner_text(timeout=5000)
                        )
                    except Exception:
                        previous_json_text = ""
                    # The prompt can be in a textarea/contenteditable that is
                    # not included in body.inner_text(). Exclude its schema too,
                    # otherwise the body fallback could mistake the prompt's
                    # example JSON for ChatGPT's answer.
                    try:
                        prompt_box = page.locator(
                            "#prompt-textarea, [contenteditable='true']"
                        ).first
                        prompt_value = ""
                        try:
                            prompt_value = prompt_box.input_value(timeout=1000) or ""
                        except Exception:
                            prompt_value = prompt_box.inner_text(timeout=1000) or ""
                        prompt_json = extract_last_json_object(prompt_value)
                        if prompt_json:
                            previous_json_text = prompt_json
                    except Exception:
                        pass
                    print("      🚀 Gửi yêu cầu...")
                    click_send_button(page)
                    chat_url = remember_active_chat_url(page, chat_url, timeout_seconds=15)
                except Exception as send_error:
                    chat_url = remember_active_chat_url(page, chat_url)
                    rate_limited = dismiss_rate_limit_dialog(page)
                    if rate_limited:
                        print(f"      ⏳ Không gửi được vì 'Too many requests'; đã bấm Got it, "
                              f"nghỉ {RATE_LIMIT_RETRY_WAIT_SECONDS}s.")
                    else:
                        print(f"      🔄 Không gửi được yêu cầu: {send_error}. "
                              "Sẽ tải lại đúng cuộc chat hiện tại.")
                    time.sleep(
                        RATE_LIMIT_RETRY_WAIT_SECONDS
                        if rate_limited else RECOVERY_RELOAD_WAIT_SECONDS
                    )
                    continue

                # Chờ ChatGPT trả lời xong và ổn định trước khi parse JSON
                print("      ⏳ Chờ ChatGPT phản hồi (có thể mất 1-3 phút)...")
                raw_text, response_rate_limited = wait_for_assistant_response(
                    page,
                    timeout_seconds=CHATGPT_RESPONSE_TIMEOUT_SECONDS,
                    previous_assistant_count=previous_assistant_count,
                    previous_json_text=previous_json_text,
                )
                chat_url = remember_active_chat_url(page, chat_url)

                if response_rate_limited or dismiss_rate_limit_dialog(page):
                    print(f"      ⏳ ChatGPT báo 'Too many requests' sau khi gửi (lần {attempt}/{MAX_RATE_LIMIT_RETRIES}), "
                          f"đã bấm Got it; nghỉ {RATE_LIMIT_RETRY_WAIT_SECONDS}s rồi tải lại đúng chat...")
                    time.sleep(RATE_LIMIT_RETRY_WAIT_SECONDS)
                    continue

                if not raw_text:
                    rate_limited = dismiss_rate_limit_dialog(page)
                    if rate_limited:
                        print(f"      ⏳ Không có nội dung vì 'Too many requests' "
                              f"(lần {attempt}/{MAX_RATE_LIMIT_RETRIES}); đã bấm Got it.")
                    else:
                        print(f"      🔄 Không lấy được nội dung ChatGPT trả về "
                              f"(lần {attempt}/{MAX_RATE_LIMIT_RETRIES}); sẽ tải lại đúng chat.")
                    time.sleep(
                        RATE_LIMIT_RETRY_WAIT_SECONDS
                        if rate_limited else RECOVERY_RELOAD_WAIT_SECONDS
                    )
                    continue

                if not has_complete_json_object(raw_text):
                    rate_limited = dismiss_rate_limit_dialog(page)
                    if rate_limited:
                        print(f"      ⏳ JSON dở dang do 'Too many requests' "
                              f"(lần {attempt}/{MAX_RATE_LIMIT_RETRIES}); đã bấm Got it.")
                    else:
                        print(f"      🔄 ChatGPT trả JSON chưa hoàn chỉnh "
                              f"(lần {attempt}/{MAX_RATE_LIMIT_RETRIES}); sẽ tải lại đúng chat.")
                    time.sleep(
                        RATE_LIMIT_RETRY_WAIT_SECONDS
                        if rate_limited else RECOVERY_RELOAD_WAIT_SECONDS
                    )
                    continue

                break
            else:
                print(f"      ❌ Vẫn không lấy được phản hồi hợp lệ sau {MAX_RATE_LIMIT_RETRIES} lần thử.")
                save_chatgpt_reader_debug(
                    page,
                    clean_id,
                    MAX_RATE_LIMIT_RETRIES,
                    "no_complete_json_after_retries",
                )
                context.close()
                return None

            print("      📥 Đọc kết quả...")
            parsed_dict = extract_json_response(raw_text)
            result = apply_experiment_metadata(
                parsed_dict,
                experiment_assignment,
            )

            print("      ✅ Nhận JSON thành công từ ChatGPT!")
            print(f"         Hook: {result.get('hook', '')[:60]}...")

            # Lưu log chi tiết đầy đủ prompt + raw response + parsed json
            log_file = save_chatgpt_log(
                prompt=full_prompt,
                raw_response=raw_text,
                parsed_result=result,
                id_tiktok=clean_id or "general",
                source_url=video_path or caption[:100],
                source_type=source_type or "facebook",
                status="SUCCESS",
            )
            print(f"         💾 ChatGPT Log: {log_file}")

            context.close()
            return result

        except json.JSONDecodeError as err:
            print(f"      ❌ ChatGPT không trả JSON hợp lệ: {err}")
            save_chatgpt_log(
                prompt=full_prompt if 'full_prompt' in locals() else "",
                raw_response=raw_text if 'raw_text' in locals() else "",
                parsed_result=None,
                id_tiktok=clean_id or "general",
                source_url=video_path or caption[:100],
                source_type=source_type or "facebook",
                status="JSON_DECODE_ERROR",
                error_message=str(err),
            )
            context.close()
            return None
        except Exception as e:
            print(f"      ❌ Lỗi: {e}")
            save_chatgpt_log(
                prompt=full_prompt if 'full_prompt' in locals() else "",
                raw_response=raw_text if 'raw_text' in locals() else "",
                parsed_result=None,
                id_tiktok=clean_id or "general",
                source_url=video_path or caption[:100],
                source_type=source_type or "facebook",
                status="EXCEPTION",
                error_message=str(e),
            )
            try:
                page.screenshot(path=os.path.join(APP_DIR, "chatgpt_error.png"))
                print(f"         📸 Screenshot: chatgpt_error.png")
            except:
                pass
            context.close()
            return None

    finally:
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
        _profile_lock.release()

# ── CLI ──
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        if len(sys.argv) > 2 and sys.argv[2] == "tele":
            login_chatgpt_interactive(is_tele_bot=True)
        elif len(sys.argv) > 2:
            login_chatgpt_interactive(profile_id=sys.argv[2])
        else:
            login_chatgpt_interactive()
    elif len(sys.argv) > 1 and sys.argv[1] == "clone_all":
        # Clone profile chung sang tất cả các kênh đã có trong data/chrome_profiles/chatgpt hoặc danh sách kênh
        if not os.path.exists(CHROME_PROFILE):
            print(f"❌ Chưa có Profile ChatGPT chung: {CHROME_PROFILE}")
            print("   Vui lòng mở 'python3 chatgpt_automator.py login' và đăng nhập 1 lần trước.")
            sys.exit(1)

        # Lấy danh sách kênh đã tồn tại
        channels = set()
        if os.path.exists(CHATGPT_PROFILE_BASE):
            for folder in os.listdir(CHATGPT_PROFILE_BASE):
                if folder.startswith("chrome_chatgpt_") and folder != "chrome_chatgpt":
                    channels.add(folder.replace("chrome_chatgpt_", ""))

        if not channels:
            print("ℹ️ Chưa tìm thấy kênh riêng nào. Bạn có thể truyền ID kênh: python3 chatgpt_automator.py clone <id1> <id2>")
        else:
            print(f"🧬 Đang nhân bản Profile ChatGPT chung sang {len(channels)} kênh...")
            for target_id in sorted(channels):
                try:
                    cloned_path = clone_shared_chatgpt_profile(target_id, overwrite=True)
                    print(f"   ✅ [{target_id}] -> {cloned_path}")
                except Exception as ex:
                    print(f"   ❌ [{target_id}] Lỗi: {ex}")
            print("✅ Đã hoàn tất nhân bản tất cả các kênh!")
    elif len(sys.argv) > 2 and sys.argv[1] == "clone":
        for target_id in sys.argv[2:]:
            cloned_path = clone_shared_chatgpt_profile(target_id, overwrite=True)
            print(f"✅ Đã clone ChatGPT chung sang {target_id}: {cloned_path}")
    elif len(sys.argv) > 2:
        profile_id = sys.argv[3] if len(sys.argv) > 3 else None
        res = analyze_video_with_chatgpt(sys.argv[1], sys.argv[2], profile_id=profile_id)
        if res:
            print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print("Cách dùng:")
        print("  python3 chatgpt_automator.py login                  → Đăng nhập ChatGPT profile chung (1 lần)")
        print("  python3 chatgpt_automator.py login <tiktok_id>      → Đăng nhập ChatGPT riêng cho TikTok ID")
        print("  python3 chatgpt_automator.py clone <id1> <id2>       → Clone profile chung sang các TikTok ID cụ thể")
        print("  python3 chatgpt_automator.py clone_all              → Clone profile chung sang TẤT CẢ các kênh TikTok")
        print("  python3 chatgpt_automator.py login tele             → Đăng nhập ChatGPT cho Tele Bot")
        print("  python3 chatgpt_automator.py <video.mp4> <caption> [tiktok_id]  → Test phân tích")
