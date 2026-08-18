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
from playwright.sync_api import sync_playwright

# apps/creator_facebook/chatgpt_automator.py → creator_facebook → apps → mannyAccount (project root)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_DIR = PROJECT_ROOT
CHATGPT_PROFILE_BASE = os.path.join(PROJECT_ROOT, "data", "chrome_profiles", "chatgpt")
CHROME_PROFILE = os.path.join(CHATGPT_PROFILE_BASE, "chrome_chatgpt")
PROMPT_FILE = os.path.join(PROJECT_ROOT, "config", "prompts", "prompt_script.txt")


def sanitize_profile_id(profile_id: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(profile_id or "").replace("@", "").strip()).strip("_")


def get_chatgpt_profile_dir(profile_id: str | None = None, is_tele_bot: bool = False) -> str:
    if is_tele_bot:
        return os.path.join(CHATGPT_PROFILE_BASE, "chrome_chatgpt_telebot")
    clean_id = sanitize_profile_id(profile_id)
    if clean_id:
        return os.path.join(CHATGPT_PROFILE_BASE, f"chrome_chatgpt_{clean_id}")
    return CHROME_PROFILE


TRANSIENT_PROFILE_ITEMS = {
    "SingletonLock",
    "SingletonCookie",
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
    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "DevToolsActivePort"]:
        lock_file = os.path.join(profile_dir, lock_name)
        if os.path.lexists(lock_file):
            try:
                os.remove(lock_file)
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
            return target_dir
        shutil.rmtree(target_dir, ignore_errors=True)

    os.makedirs(os.path.dirname(target_dir), exist_ok=True)
    shutil.copytree(source_dir, target_dir, ignore=ignore_transient_profile_items)
    remove_profile_locks(target_dir)
    return target_dir


def ensure_chatgpt_profile(profile_id: str | None = None, is_tele_bot: bool = False) -> str:
    clean_id = sanitize_profile_id(profile_id)
    profile_dir = get_chatgpt_profile_dir(clean_id, is_tele_bot=is_tele_bot)
    if clean_id and not os.path.exists(profile_dir) and os.path.exists(CHROME_PROFILE):
        print(f"      🧬 Chưa có profile ChatGPT cho {clean_id}. Tự clone từ profile chung...")
        profile_dir = clone_shared_chatgpt_profile(clean_id, overwrite=False)
    remove_profile_locks(profile_dir)
    return profile_dir


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


def get_chatgpt_profile_label(profile_id: str | None = None, is_tele_bot: bool = False) -> str:
    if is_tele_bot:
        return "Tele Bot"
    clean_id = sanitize_profile_id(profile_id)
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


def wait_for_assistant_response(page, timeout_seconds: int = 360) -> str:
    start = time.time()
    last_text = ""
    stable_since = None

    while time.time() - start < timeout_seconds:
        stop_visible = False
        try:
            stop_btn = page.locator('[data-testid="stop-button"], button[aria-label="Stop"], button[aria-label="Dừng tạo"]').first
            stop_visible = stop_btn.count() > 0 and stop_btn.is_visible(timeout=1000)
        except Exception:
            stop_visible = False

        text = ""
        try:
            messages = page.locator('div[data-message-author-role="assistant"]')
            if messages.count() > 0:
                text = messages.last.inner_text(timeout=3000).strip()
        except Exception:
            text = ""

        if text:
            if text != last_text:
                last_text = text
                stable_since = time.time()
            elif not stop_visible and stable_since and time.time() - stable_since >= 12:
                return text

        time.sleep(3)

    return last_text


def extract_json_response(raw_text: str) -> dict:
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw_text or '', flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.MULTILINE).strip()

    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(cleaned)
        return obj




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
    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_file = os.path.join(profile_dir, lock_name)
        if os.path.lexists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass
    print("🧹 Đã kiểm tra và xóa Singleton* cũ")

    with sync_playwright() as p:
        # Dùng persistent context = Chrome profile thật
        # Không bị Cloudflare chặn như browser thường
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
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

        context.close()


def analyze_video_with_chatgpt(video_path: str, caption: str, is_tele_bot: bool = False, extra_content: str = "", profile_id: str | None = None) -> dict | None:
    """
    Tự động:
    1. Mở ChatGPT (dùng Chrome profile đã login)
    2. Upload file video
    3. Gửi prompt + caption + extra_content (nếu có)
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
            f"\n[PROFILE/CHỈ ĐẠO NỘI DUNG RIÊNG CHO NGUỒN FACEBOOK]:\n"
            f"{extra_content}\n\n"
            f"YÊU CẦU: Dùng phần trên làm ràng buộc ưu tiên khi chọn góc khai thác, hook, giọng văn, format, cảm xúc chính và điều cần tránh. "
            f"Nếu phần trên là thông điệp cụ thể thì hãy lấy làm trọng tâm kịch bản. Nếu là profile kênh/nguồn thì dùng để điều chỉnh phong cách, không được viết một kiểu chung cho mọi nguồn. "
            f"Vẫn phải bám sát hình ảnh và bối cảnh thật của video gốc, không bịa tình tiết.\n"
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
        
    full_prompt = (
        f"{prompt_text}\n\n"
        f"VIDEO GỐC:\n"
        f"Caption/Tiêu đề gốc: {caption}\n"
        f"{extra_instruction}\n"
        f"Hãy phân tích video được đính kèm và xuất đúng định dạng JSON."
    )

    profile_label = get_chatgpt_profile_label(clean_id, is_tele_bot=is_tele_bot)
    print(f"      🤖 Mở ChatGPT (Profile: {profile_label})...")

    # Xóa lock cũ
    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_file = os.path.join(profile_dir, lock_name)
        if os.path.lexists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1920, "height": 1080},
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            # Chờ ô nhập xuất hiện — chỉ khi KHÔNG thấy ô chat mới đi tìm nguyên nhân
            try:
                page.wait_for_selector("#prompt-textarea, [contenteditable='true']", timeout=20000)
            except:
                if is_cloudflare_challenge(page):
                    print("      ❌ Cloudflare chặn! Cần login lại.")
                else:
                    print("      ❌ Không thấy ô chat. Cookie hết hạn?")
                    print("      💡 Chạy lại: python3 chatgpt_automator.py login")
                context.close()
                return None

            # Upload video
            print("      📎 Upload video...")
            file_input = page.locator("input[type='file']")
            if file_input.count() > 0:
                file_input.first.set_input_files(video_path)
            else:
                print("      ❌ Không tìm thấy nút upload file")
                context.close()
                return None

            time.sleep(5)  # Chờ upload xong

            # Điền prompt vào ô chat
            print("      ✍️ Nhập prompt...")
            replace_prompt_text(page, full_prompt)
            time.sleep(1)

            # Click gửi
            print("      🚀 Gửi yêu cầu...")
            click_send_button(page)

            # Chờ ChatGPT trả lời xong và ổn định trước khi parse JSON
            print("      ⏳ Chờ ChatGPT phản hồi (có thể mất 1-3 phút)...")
            raw_text = wait_for_assistant_response(page, timeout_seconds=360)

            if not raw_text:
                print("      ❌ Không thấy phản hồi từ ChatGPT")
                context.close()
                return None

            print("      📥 Đọc kết quả...")
            result = extract_json_response(raw_text)

            print("      ✅ Nhận JSON thành công từ ChatGPT!")
            print(f"         Hook: {result.get('hook', '')[:60]}...")

            # Lưu JSON vào file (backup)
            backup_dir = os.path.join(APP_DIR, "data", "ai_results")
            os.makedirs(backup_dir, exist_ok=True)
            backup_file = os.path.join(backup_dir, f"chatgpt_{int(time.time())}.json")
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"         💾 Backup: {backup_file}")

            context.close()
            return result

        except json.JSONDecodeError:
            print(f"      ❌ ChatGPT không trả JSON hợp lệ")
            print(f"         Raw: {raw_text[:300]}...")
            try:
                raw_dir = os.path.join(APP_DIR, "data", "ai_results")
                os.makedirs(raw_dir, exist_ok=True)
                raw_file = os.path.join(raw_dir, f"chatgpt_invalid_{int(time.time())}.txt")
                with open(raw_file, "w", encoding="utf-8") as f:
                    f.write(raw_text or "")
                print(f"         💾 Raw backup: {raw_file}")
            except Exception:
                pass
            context.close()
            return None
        except Exception as e:
            print(f"      ❌ Lỗi: {e}")
            try:
                page.screenshot(path=os.path.join(APP_DIR, "chatgpt_error.png"))
                print(f"         📸 Screenshot: chatgpt_error.png")
            except:
                pass
            context.close()
            return None


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
        print("  python3 chatgpt_automator.py login                  → Đăng nhập ChatGPT profile chung")
        print("  python3 chatgpt_automator.py login <tiktok_id>      → Đăng nhập ChatGPT riêng cho TikTok ID")
        print("  python3 chatgpt_automator.py clone <id1> <id2>       → Clone profile chung sang các TikTok ID")
        print("  python3 chatgpt_automator.py login tele             → Đăng nhập ChatGPT cho Tele Bot")
        print("  python3 chatgpt_automator.py <video.mp4> <caption> [tiktok_id]  → Test phân tích")
