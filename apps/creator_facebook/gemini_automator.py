#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  gemini_automator.py — Tự động hóa Gemini qua trình duyệt (Web Playwright)

  Dùng Chrome profile thật (persistent context) để:
  - Tự động hóa tương tác trên gemini.google.com
  - Bypass xác thực và giữ phiên đăng nhập vĩnh viễn
  - Upload video + gửi prompt + bóc tách JSON trả về
═══════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import threading
from typing import Any

from playwright.sync_api import sync_playwright

import fcntl


class ProcessFileLock:
    """Lock liên tiến trình (OS Inter-Process Lock) dùng fcntl.flock.
    Đảm bảo 100% hai tiến trình worker (PID khác nhau) KHÔNG BAO GIỜ cùng lúc mở Chrome profile.
    """
    def __init__(self, profile_dir: str):
        self.profile_dir = profile_dir
        self.lock_file_path = os.path.join(profile_dir, "gemini_profile_process.lock")
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
                    print("      ⏳ Gemini Web Profile đang được dùng bởi tiến trình khác, đang chờ đến lượt...")
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


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from shared.core.experiment_manager import apply_experiment_metadata
from shared.core.prompt_builder import build_prompt, resolve_prompt_experiment
from apps.creator_facebook.facebook_pipeline.hook_mode import build_hook_prompt
from apps.creator_facebook.facebook_pipeline.source_config import (
    EDIT_MODE_HOOK_THEN_ORIGINAL,
)
from shared.services.gemini_response_reader import (
    extract_json_from_text as extract_gemini_json,
    is_refusal_response,
    select_latest_script_response,
)

GEMINI_PROFILE_BASE = os.path.join(PROJECT_ROOT, "data", "chrome_profiles", "gemini")
CHROME_PROFILE = os.path.join(GEMINI_PROFILE_BASE, "chrome_gemini")
PROMPT_FILE = os.path.join(PROJECT_ROOT, "config", "prompts", "prompt_script.txt")

GEMINI_CAPABILITY_CLARIFICATION = (
    "Đây là tác vụ PHÂN TÍCH nội dung nguồn và SOẠN VĂN BẢN JSON. "
    "Bạn không cần trực tiếp tạo, chỉnh sửa, xuất bản hoặc tải video lên bất kỳ nền tảng nào. "
    "Chỉ cần xem tệp/ngữ liệu người dùng đã cung cấp, viết nội dung theo yêu cầu và trả về JSON thuần."
)

GEMINI_REFUSAL_FOLLOWUP = (
    "Làm rõ yêu cầu trước: bạn chỉ cần phân tích tệp/ngữ liệu đã được đính kèm và viết một "
    "câu trả lời dạng văn bản JSON; không cần tạo hay chỉnh sửa file video, không cần thực hiện "
    "hành động bên ngoài. Hãy tiếp tục yêu cầu trước đó và chỉ trả JSON thuần đúng cấu trúc đã nêu. "
    "Nếu nguồn không đủ dữ kiện hoặc không phù hợp, vẫn trả JSON hợp lệ với "
    "should_make_video=false và nêu lý do trong skip_reason; tuyệt đối không bịa thêm dữ kiện."
)


def sanitize_profile_id(profile_id: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(profile_id or "").replace("@", "").strip()).strip("_")


def get_gemini_profile_dir(profile_id: str | None = None) -> str:
    # Luôn dùng 1 profile Chrome duy nhất (chrome_gemini) cho tất cả các kênh
    # Đảm bảo Google không phát hiện việc copy cookie trên nhiều profile dẫn đến bắt đăng nhập lại.
    return CHROME_PROFILE


def remove_profile_locks(profile_dir: str):
    if not profile_dir or not os.path.exists(profile_dir):
        return
    targets = [profile_dir]
    default_dir = os.path.join(profile_dir, "Default")
    if os.path.exists(default_dir):
        targets.append(default_dir)

    for target in targets:
        try:
            for name in os.listdir(target):
                # TUYỆT ĐỐI KHÔNG XÓA SingletonCookie (chứa key bảo mật cookie đăng nhập Google)!
                if name in ["SingletonLock", "SingletonSocket", "DevToolsActivePort", "lockfile"]:
                    lock_file = os.path.join(target, name)
                    if os.path.lexists(lock_file):
                        try:
                            if os.path.isdir(lock_file) and not os.path.islink(lock_file):
                                shutil.rmtree(lock_file, ignore_errors=True)
                            else:
                                os.unlink(lock_file)
                        except Exception:
                            pass
        except Exception:
            pass


def mark_profile_exited_cleanly(profile_dir: str):
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
        pass


def ensure_gemini_profile(profile_id: str | None = None) -> str:
    profile_dir = get_gemini_profile_dir(profile_id)
    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir


def load_prompt() -> str:
    if os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def open_gemini_login_session(profile_id: str | None = None):
    """Mở Chrome cho người dùng đăng nhập tài khoản Gemini trên gemini.google.com"""
    profile_dir = ensure_gemini_profile(profile_id)
    remove_profile_locks(profile_dir)
    mark_profile_exited_cleanly(profile_dir)

    print("      🌐 Đang mở Chrome cho Gemini. Vui lòng đăng nhập Google/Gemini...")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-profile-error-dialogs",
                "--no-errdialogs",
            ],
        )
        page = context.new_page()
        page.goto("https://gemini.google.com", wait_until="domcontentloaded")
        print("      ✅ Vui lòng đăng nhập trên cửa sổ Chrome vừa mở.")
        print("      Ấn ENTER tại đây sau khi hoàn tất đăng nhập (hoặc đóng cửa sổ Chrome)...")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
        try:
            context.close()
        except Exception:
            pass
        print(f"      🎉 Đã lưu thành công phiên đăng nhập Gemini tại: {profile_dir}")


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


def clone_shared_gemini_profile(profile_id: str, overwrite: bool = False) -> str:
    """Nhân bản Chrome Profile Gemini dùng chung sang profile riêng của một TikTok ID."""
    clean_id = sanitize_profile_id(profile_id)
    if not clean_id:
        raise ValueError("Thiếu TikTok ID để clone profile Gemini")

    source_dir = CHROME_PROFILE
    target_dir = get_gemini_profile_dir(clean_id)

    if not os.path.exists(source_dir):
        raise FileNotFoundError(f"Chưa có profile Gemini chung: {source_dir}. Vui lòng đăng nhập lần đầu!")

    if os.path.abspath(source_dir) == os.path.abspath(target_dir):
        return target_dir

    if os.path.exists(target_dir):
        if not overwrite:
            return target_dir
        shutil.rmtree(target_dir, ignore_errors=True)

    shutil.copytree(source_dir, target_dir, ignore=ignore_transient_profile_items)
    remove_profile_locks(target_dir)
    return target_dir


def extract_json_from_text(text: str) -> dict | None:
    """Backward-compatible wrapper used by older callers/tests."""
    return extract_gemini_json(text)


def _scroll_to_latest_gemini_response(page) -> None:
    """Scroll the page and Gemini's nested containers to the latest response."""
    page.evaluate(
        """() => {
            const rootSelectors = [
                'model-response',
                '[data-test-id="model-response"]',
                '.model-response',
                '.model-response-text'
            ];
            let latest = null;
            for (const selector of rootSelectors) {
                const matches = document.querySelectorAll(selector);
                if (matches.length) latest = matches[matches.length - 1];
                if (latest) break;
            }

            if (latest) latest.scrollIntoView({block: 'end', inline: 'nearest'});

            const containers = document.querySelectorAll(
                '.chat-history, .conversation-container, main, [role="main"], chat-window'
            );
            containers.forEach((node) => {
                if (node.scrollHeight > node.clientHeight) node.scrollTop = node.scrollHeight;
            });

            let parent = latest ? latest.parentElement : null;
            while (parent) {
                if (parent.scrollHeight > parent.clientHeight) parent.scrollTop = parent.scrollHeight;
                parent = parent.parentElement;
            }
            const scrolling = document.scrollingElement || document.documentElement;
            if (scrolling) scrolling.scrollTop = scrolling.scrollHeight;
        }"""
    )


def _collect_gemini_response_texts(page) -> list[str]:
    """Read complete textContent from the newest Gemini model response."""
    result = page.evaluate(
        """() => {
            const rootSelectors = [
                'model-response',
                '[data-test-id="model-response"]',
                '.model-response',
                'div[class*="model-response"]'
            ];
            let root = null;
            for (const selector of rootSelectors) {
                const matches = document.querySelectorAll(selector);
                if (matches.length) root = matches[matches.length - 1];
                if (root) break;
            }

            const texts = [];
            const addText = (node) => {
                if (!node) return;
                const text = (node.textContent || node.innerText || '').trim();
                if (text && !texts.includes(text)) texts.push(text);
            };

            if (root) {
                // Descendants are added first and the full response last. The
                // Python side scans backwards, so the complete root wins.
                root.querySelectorAll(
                    'message-content, .model-response-text, .markdown, code-block, pre, code, '
                    + '[data-test-id="response-text"]'
                ).forEach(addText);
                addText(root);
                return texts;
            }

            // Fallback for a Gemini layout that has no model-response wrapper.
            const fallback = document.querySelectorAll(
                'message-content, .model-response-text, [data-test-id="response-text"], '
                + 'div[class*="response_container"], div[class*="response-container"]'
            );
            fallback.forEach(addText);
            return texts;
        }"""
    )
    return [str(text) for text in (result or []) if str(text).strip()]


def _count_gemini_model_responses(page) -> int:
    return int(
        page.evaluate(
            """() => {
                const selectors = [
                    'model-response',
                    '[data-test-id="model-response"]',
                    '.model-response',
                    'div[class*="model-response"]'
                ];
                for (const selector of selectors) {
                    const count = document.querySelectorAll(selector).length;
                    if (count) return count;
                }
                return 0;
            }"""
        )
        or 0
    )


def _submit_gemini_prompt(page, text: str) -> bool:
    """Fill Gemini's composer and submit one prompt/follow-up."""
    prompt_selectors = (
        "rich-textarea div[contenteditable='true']",
        "div[role='textbox']",
        "div[aria-label*='Nhập câu lệnh cho Gemini']",
        "div[aria-label*='Nhập câu lệnh']",
        "div[aria-label*='Enter a prompt']",
        "div[aria-label*='Prompt']",
        ".ql-editor",
        "div[contenteditable='true']",
        "textarea",
    )
    prompt_input = None
    deadline = time.time() + 30
    while prompt_input is None and time.time() < deadline:
        for selector in prompt_selectors:
            matches = page.locator(selector)
            for index in range(matches.count()):
                candidate = matches.nth(index)
                try:
                    if candidate.is_visible():
                        prompt_input = candidate
                        break
                except Exception:
                    continue
            if prompt_input is not None:
                break
        if prompt_input is None:
            time.sleep(0.5)

    if prompt_input is None:
        return False

    try:
        prompt_input.click()
        # Playwright's fill updates both the visible DOM and Gemini's internal
        # editor state. Direct innerText mutation could leave stray characters
        # such as the "gr" prefix seen in production.
        prompt_input.fill(text, timeout=30000)
        entered_text = prompt_input.evaluate(
            """(element) => ('value' in element ? element.value : element.innerText || element.textContent || '')"""
        )
        if str(entered_text or "").strip() != text.strip():
            prompt_input.press("Control+A")
            prompt_input.press("Backspace")
            page.keyboard.insert_text(text)
    except Exception:
        return False

    time.sleep(1)
    send_btn = page.locator(
        "button[aria-label*='Gửi tin nhắn'], "
        "button[aria-label*='Send prompt'], "
        "button[aria-label*='Send'], "
        "button[aria-label*='Gửi'], "
        ".send-button"
    ).first
    try:
        send_btn.wait_for(state="visible", timeout=40000)
        for _ in range(30):
            if send_btn.is_enabled():
                send_btn.click()
                return True
            time.sleep(1)
    except Exception:
        pass

    try:
        page.keyboard.press("Control+Enter")
        return True
    except Exception:
        return False


def analyze_video_with_gemini_web(
    video_path: str,
    caption: str,
    extra_content: str = "",
    profile_id: str | None = None,
    repair_instruction: str = "",
    source_type: str = "tiktok",
    experiment_content_key: str = "",
    edit_mode: str = "",
    whisper_transcript: str = "",
) -> dict | None:
    """Tự động hóa Playwright trên gemini.google.com"""
    clean_id = sanitize_profile_id(profile_id)
    profile_dir = CHROME_PROFILE
    pref_file = os.path.join(profile_dir, "Default", "Preferences")

    if not os.path.exists(profile_dir) or not os.path.exists(pref_file):
        print(f"      ⚠️ CHƯA KHỞI TẠO PROFILE GEMINI WEB ({profile_dir})! Vui lòng đăng nhập lần đầu.")
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
        "- TUYỆT ĐỐI KHÔNG viết tắt. Mọi từ ngữ phải được viết đầy đủ bằng tiếng Việt chuẩn (Ví dụ: 'không' thay vì 'ko', 'được' thay vì 'đc').\n"
        "- chỉ được trả về text json.\n"
    )

    transcript_block = ""
    if whisper_transcript and whisper_transcript.strip():
        transcript_block = (
            f"\n[THOẠI GỐC TỪ VIDEO (WHISPER TRANSCRIPT BÓC TÁCH)]:\n"
            f"\"{whisper_transcript.strip()}\"\n\n"
            f"[QUY TẮC PHÂN BỔ NỘI DUNG 70/30 & SỬA CHÍNH TẢ BẮT BUỘC]:\n"
            f"1. TỶ LỆ DỮ KIỆN (70% THOẠI WHISPER / 30% HÌNH ẢNH):\n"
            f"   - 70% Nội dung kịch bản PHẢI dựa trực tiếp trên LỜI THOẠI GỐC WHISPER.\n"
            f"   - 30% Nội dung tham khảo bổ sung từ bối cảnh, chi tiết trực quan trong video.\n"
            f"2. TỰ ĐỘNG SỬA LỖI CHÍNH TẢ WHISPER.\n"
            f"3. TUYỆT ĐỐI KHÔNG BỊA DỮ KIỆN SAI SỰ THẬT.\n"
        )

    task_input = (
        f"VIDEO GỐC\nCaption/Tiêu đề gốc: {caption}\n"
        f"{transcript_block}"
        f"{extra_instruction}\n"
        "An toàn dữ kiện: không bịa; thông tin chỉ có trong caption phải được dẫn nguồn một lần tự nhiên.\n"
        "Hãy dùng lời thoại bóc tách (70%), hình ảnh video (30%) và caption làm nguồn để viết một bản tin liền mạch."
    )

    if edit_mode == EDIT_MODE_HOOK_THEN_ORIGINAL:
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

    # Gemini occasionally interprets "sản xuất video" in the editorial role as
    # a request to operate external tools and refuses. State the actual scope
    # once, outside all source-specific prompts, including Facebook hook mode.
    full_prompt = (
        f"[PHẠM VI THỰC HIỆN]\n{GEMINI_CAPABILITY_CLARIFICATION}\n\n"
        f"{full_prompt}"
    )

    max_wait_sec = int(os.environ.get("GEMINI_WEB_TIMEOUT", "420"))
    max_ticks = max(1, (max_wait_sec + 1) // 2)

    _profile_lock = _get_profile_lock(profile_dir)
    if not _profile_lock.acquire(blocking=True, timeout=max(600, max_wait_sec + 200)):
        print("      ❌ Lock Gemini Profile bận – bỏ qua.")
        return None

    try:
        remove_profile_locks(profile_dir)
        mark_profile_exited_cleanly(profile_dir)

        print(f"      🤖 Đang mở Gemini Web (Profile: {os.path.basename(profile_dir)})...")
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-profile-error-dialogs",
                    "--no-errdialogs",
                ],
            )
            page = context.new_page()
            page.goto("https://gemini.google.com", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

            # Upload video nếu file tồn tại
            if video_path and os.path.exists(video_path):
                print(f"      📤 Đang upload video lên Gemini Web ({os.path.basename(video_path)})...")
                uploaded = False
                try:
                    # 1. Nhấp nút + (Nội dung tải lên và công cụ)
                    upload_menu_btn = page.locator(
                        "button[aria-label*='Nội dung tải lên'], "
                        "button[aria-label*='Upload'], "
                        "button[aria-label*='thêm'], "
                        "button[aria-label*='Thêm'], "
                        "button[aria-label*='Add']"
                    ).first
                    if upload_menu_btn.count() > 0 and upload_menu_btn.is_visible():
                        upload_menu_btn.click()
                        time.sleep(1)

                        # 2. Tìm mục 'Tải tệp lên' trong menu vừa mở
                        file_item = page.locator(
                            "button:has-text('Tải tệp lên'), "
                            "[aria-label*='Tải tệp lên'], "
                            "[role='menuitem']:has-text('Tải tệp lên'), "
                            "button:has-text('Upload file'), "
                            "[aria-label*='Upload file']"
                        ).first
                        if file_item.count() > 0:
                            with page.expect_file_chooser(timeout=5000) as fc_info:
                                file_item.click()
                            file_chooser = fc_info.value
                            file_chooser.set_files(video_path)
                            uploaded = True
                except Exception as ex_upload:
                    print(f"      ⚠️ Thử upload qua menu gặp cảnh báo: {ex_upload}")

                if not uploaded:
                    try:
                        file_input = page.locator("input[type='file']").first
                        if file_input.count() > 0:
                            file_input.set_input_files(video_path)
                            uploaded = True
                    except Exception as ex:
                        print(f"      ⚠️ Upload file trực tiếp gặp cảnh báo: {ex}")

                # 3. Chờ chip xem trước video (uploader-file-preview) xuất hiện trọn vẹn trong ô prompt
                if uploaded:
                    print("      ⏳ Đang chờ Gemini đính kèm video vào ô nhập liệu...")
                    for _ in range(15):
                        time.sleep(1)
                        chips = page.locator("uploader-file-preview, .file-preview, file-chip, [data-test-id*='file']").count()
                        if chips > 0:
                            print("      ✅ Video đã được đính kèm thành công vào Gemini Web!")
                            break
                    time.sleep(2)

            if not _submit_gemini_prompt(page, full_prompt):
                print("      ❌ Không thể nhập hoặc gửi yêu cầu tới Gemini Web.")
                try:
                    context.close()
                except Exception:
                    pass
                return None
            print("      🚀 Đã gửi yêu cầu tới Gemini Web thành công!")

            print(f"      ⏳ Đang chờ Gemini sinh kịch bản JSON hoàn chỉnh (tối đa {max_wait_sec}s, tự động cuộn chuột)...")
            time.sleep(8)

            last_length = 0
            stable_ticks = 0
            parse_warning_shown = False
            refusal_retries = 0
            handled_refusal_counts: set[int] = set()

            for i in range(max_ticks):
                time.sleep(2)

                # 1. Tự động cuộn xuống đáy trang để Gemini render trọn vẹn toàn bộ văn bản dài
                try:
                    _scroll_to_latest_gemini_response(page)
                except Exception:
                    pass

                # 2. Kiểm tra xem Gemini có đang còn viết dở không (Nút Stop / Dừng tạo)
                is_generating = False
                try:
                    stop_btn = page.locator("button[aria-label*='Dừng'], button[aria-label*='Stop'], .stop-button, [data-tooltip*='Stop']").first
                    if stop_btn.count() > 0 and stop_btn.is_visible():
                        is_generating = True
                except Exception:
                    pass

                # 3. Đọc nội dung phản hồi mới nhất
                response_texts = _collect_gemini_response_texts(page)
                if response_texts:
                    parsed, current_text = select_latest_script_response(response_texts)
                    current_len = len(current_text)
                    response_count = _count_gemini_model_responses(page)

                    # Kiểm tra độ dài văn bản ổn định (không tăng thêm)
                    if current_len > 0 and current_len == last_length:
                        stable_ticks += 1
                    else:
                        stable_ticks = 0
                        last_length = current_len

                    # JSON hợp lệ là tín hiệu chắc chắn hơn việc đếm độ dài DOM.
                    # Chỉ chờ nút Stop biến mất để tránh lấy một JSON đang viết dở.
                    if parsed and not is_generating:
                        print(f"      ✅ Gemini Web đã lấy được kịch bản JSON đầy đủ ({current_len} ký tự)!")
                        try:
                            context.close()
                        except Exception:
                            pass
                        return apply_experiment_metadata(parsed, experiment_assignment)

                    if (
                        not parsed
                        and not is_generating
                        and stable_ticks >= 2
                        and is_refusal_response(current_text)
                        and response_count not in handled_refusal_counts
                    ):
                        handled_refusal_counts.add(response_count)
                        if refusal_retries >= 2:
                            print(
                                "      ❌ Gemini đã từ chối yêu cầu sau 2 lần làm rõ; "
                                "dừng sớm để không chờ hết thời gian."
                            )
                            try:
                                context.close()
                            except Exception:
                                pass
                            return None

                        refusal_retries += 1
                        print(
                            f"      🔄 Gemini trả lời từ chối (lần {refusal_retries}/2); "
                            "đang làm rõ đây chỉ là tác vụ phân tích và viết JSON..."
                        )
                        if not _submit_gemini_prompt(page, GEMINI_REFUSAL_FOLLOWUP):
                            print("      ❌ Không gửi được yêu cầu làm rõ tới Gemini.")
                            try:
                                context.close()
                            except Exception:
                                pass
                            return None
                        last_length = 0
                        stable_ticks = 0
                        parse_warning_shown = False
                        time.sleep(5)
                        continue

                    if (
                        not parsed
                        and not is_generating
                        and stable_ticks >= 2
                        and not parse_warning_shown
                    ):
                        print(
                            "      ⚠️ Gemini đã ngừng trả lời nhưng chưa đọc được toàn bộ JSON; "
                            "đang cuộn và đọc lại khối phản hồi..."
                        )
                        parse_warning_shown = True

            try:
                context.close()
            except Exception:
                pass
            print(f"      ❌ Hết thời gian chờ Gemini Web ({max_wait_sec}s) trả về kịch bản đầy đủ.")
            return None
    except Exception as e:
        print(f"      ❌ Lỗi Gemini Web Automator: {e}")
        return None
    finally:
        _profile_lock.release()


def analyze_video_with_gemini(
    video_path: str,
    caption: str,
    extra_content: str = "",
    profile_id: str | None = None,
    repair_instruction: str = "",
    source_type: str = "tiktok",
    experiment_content_key: str = "",
    edit_mode: str = "",
    whisper_transcript: str = "",
) -> dict | None:
    """Hàm wrapper hỗ trợ thử Gemini Web trước, nếu thất bại thử Gemini API dự phòng."""
    print("   🤖 Kích hoạt AI Provider: GEMINI...")
    res = analyze_video_with_gemini_web(
        video_path=video_path,
        caption=caption,
        extra_content=extra_content,
        profile_id=profile_id,
        repair_instruction=repair_instruction,
        source_type=source_type,
        experiment_content_key=experiment_content_key,
        edit_mode=edit_mode,
        whisper_transcript=whisper_transcript,
    )
    if res:
        return res

    print("   ⚠️ Gemini Web không trả về kịch bản. Vui lòng kiểm tra đăng nhập Gemini Profile.")
    return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "login":
            pid = sys.argv[2] if len(sys.argv) > 2 else None
            open_gemini_login_session(pid)
        elif cmd == "clone" and len(sys.argv) > 2:
            pids = sys.argv[2:]
            for pid in pids:
                try:
                    clone_shared_gemini_profile(pid, overwrite=True)
                    print(f"  ✅ Đã clone Gemini Profile chung -> {pid}")
                except Exception as ex:
                    print(f"  ❌ Lỗi clone {pid}: {ex}")
        elif cmd == "test" and len(sys.argv) > 3:
            vpath = sys.argv[2]
            cap = sys.argv[3]
            out = analyze_video_with_gemini(vpath, cap)
            print("KẾT QUẢ:", json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print("Cách dùng:")
            print("  python3 gemini_automator.py login [profile_id]      → Đăng nhập Gemini Profile chung hoặc riêng")
            print("  python3 gemini_automator.py clone <id1> <id2> ...    → Clone profile Gemini chung sang các TikTok ID")
            print("  python3 gemini_automator.py test <video.mp4> <cap>  → Test phân tích video")
