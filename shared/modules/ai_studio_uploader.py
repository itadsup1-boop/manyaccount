import json
import os
import time
import sys
import random
import glob
import subprocess
import concurrent.futures
from playwright.sync_api import sync_playwright
from shared.services.supabase_api import SupabaseAPI

# ================= CẤU HÌNH ĐƯỜNG DẪN =================
CURRENT_SCRIPT_PATH = os.path.abspath(__file__)
MODULES_DIR = os.path.dirname(CURRENT_SCRIPT_PATH)
PROJECT_ROOT = os.path.dirname(os.path.dirname(MODULES_DIR))

ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
AI_STUDIO_DIR = os.path.join(DATA_DIR, "chrome_profiles", "tiktok_upload")
TEMP_DIR = os.path.join(ASSETS_DIR, "temp_downloads")

if not os.path.exists(ASSETS_DIR): os.makedirs(ASSETS_DIR)
if not os.path.exists(TEMP_DIR): os.makedirs(TEMP_DIR)

_has_killed_chrome_globally = False

# ================= CÁC HÀM HỖ TRỢ =================

def load_settings():
    try:
        settings = SupabaseAPI.get_system_config("app_settings") or {}
        target_url = settings.get("ai_studio_url")
        return (target_url, None, None, None)
    except Exception as e:
        print(f"❌ Lỗi lấy cấu hình AI Studio từ Supabase: {e}")
        return None, None, None, None

def kill_chrome_globally():
    global _has_killed_chrome_globally
    if _has_killed_chrome_globally:
        return
    print("🧹 Dọn dẹp Chrome processes trước khi chạy song song (Lần đầu)...")
    try:
        if sys.platform == "win32":
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else:
            # Linux/Mac: Chỉ kill chrome của playwright, không kill trình duyệt gốc của người dùng
            subprocess.run("pkill -f ms-playwright", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(2)
        _has_killed_chrome_globally = True
    except: pass

def handle_google_login(page, email, password):
    print(f"[{email}] 🕵️ Kiểm tra trạng thái đăng nhập...")
    try:
        time.sleep(10)
        if "accounts.google.com" in page.url or page.locator('input[type="email"]').count() > 0:
            print(f"[{email}] ⚠️ Chưa đăng nhập! Bắt đầu tự động điền thông tin...")
            if not email or not password:
                print(f"[{email}] ❌ Thiếu Email hoặc Mật khẩu trong cấu hình của ID này. Không thể tự đăng nhập.")
                return

            # Điền Email
            email_input = page.locator('input[type="email"]').first
            email_input.wait_for(state="visible", timeout=10000)
            email_input.fill(email)
            time.sleep(1)
            page.keyboard.press("Enter")
            time.sleep(5) # Chờ Google load form password

            # Điền Password
            pass_input = page.locator('input[type="password"]').first
            pass_input.wait_for(state="visible", timeout=10000)
            pass_input.click()
            pass_input.fill(password)
            time.sleep(1)
            page.keyboard.press("Enter")

            print(f"[{email}] ✅ Đã điền thông tin. Chờ Google xác thực...")

            page.wait_for_url("**/ai.studio/**", timeout=60000)
            print(f"[{email}] 🎉 Đăng nhập thành công, đã quay lại AI Studio!")
            time.sleep(5)
        else:
            print(f"[{email}] ✅ Tài khoản đã được đăng nhập sẵn (Cookie còn hạn).")
    except Exception as e:
        print(f"[{email}] ⚠️ Lỗi trong lúc tự đăng nhập Google: {e}")
        print(f"💡 Gợi ý: Google có thể đang đòi xác minh 2 bước. Hãy dùng chức năng 'Mở Chrome' để giải quyết thủ công 1 lần.")

def upload_worker(account_config):
    # 1. Lấy thông tin từ config riêng của nick
    profile_name = account_config.get("chrome_profile")
    tiktok_id = account_config.get("tiktok_id")
    local_video_path = account_config.get("video_path")
    gg_email = account_config.get("email")
    gg_pass = account_config.get("password")
    target_url, _, _, _ = load_settings()

    if not target_url:
        print(f"❌ [{tiktok_id}] Lỗi: Thiếu AI Studio URL.")
        return False

    if not profile_name:
        print(f"❌ [{tiktok_id}] Lỗi: Thiếu tên Chrome Profile.")
        return False

    current_user_data_dir = os.path.join(AI_STUDIO_DIR, profile_name)

    print(f"🚀 [Start] {tiktok_id} - Profile: {profile_name}")

    if not os.path.exists(local_video_path):
        print(f"❌ [{tiktok_id}] Lỗi: Không tìm thấy file video {local_video_path}")
        return False

    # Dọn dẹp tiến trình Chrome cũ (chỉ kill các process dùng chung profile này để tránh crash Playwright & không ảnh hưởng Chrome gốc)
    try:
        if sys.platform == "win32":
            # wmic process where "name='chrome.exe' and commandline like '%profile_name%'" call terminate
            subprocess.run(f'wmic process where "name=\'chrome.exe\' and commandline like \'%{profile_name}%\'" call terminate', shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else:
            subprocess.run(f"pkill -f '{current_user_data_dir}'", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(1)
    except: pass

    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=current_user_data_dir,
                headless=False,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-background-networking",
                    "--disable-session-crashed-bubble"
                ],
                viewport=None,
                ignore_default_args=["--enable-automation"]
            )

            while len(browser.pages) > 1:
                browser.pages[-1].close()
            page = browser.pages[0] if browser.pages else browser.new_page()

            print(f"🔗 [{tiktok_id}] Vào AI Studio...")
            page.goto(target_url, timeout=60000)
            time.sleep(5)

            try:
                login_btn = page.locator('button:has-text("Log in"), button:has-text("Sign in")').first
                if login_btn.is_visible(timeout=3000):
                    login_btn.click()
                    time.sleep(2)

                google_btn = page.locator('button:has-text("Continue with Google"), button:has-text("Sign in with Google")').first
                if google_btn.is_visible(timeout=3000):
                    google_btn.click()
                    time.sleep(5)
            except:
                pass
            handle_google_login(page, gg_email, gg_pass)
            try: page.wait_for_load_state("networkidle", timeout=10000)
            except: pass

            # 5. Vào App
            try:
                continue_btn = page.locator('button:has-text("Continue to the app")')
                if continue_btn.is_visible(timeout=5000): continue_btn.click(); time.sleep(2)
            except: pass

            print(f"🔍 [{tiktok_id}] Tìm App 'Video Viral Clone'...")
            app_btn_selectors = [
                'button:has-text("Video Viral Clone")',
                'button.text-slate-500:has-text("Video Viral Clone")',
                'div[role="button"]:has-text("Video Viral Clone")',
                '[role="button"]:has-text("Video Viral Clone")',
                'text="Video Viral Clone"'
            ]
            clicked_app = False

            start_app_search = time.time()
            while time.time() - start_app_search < 30:
                # Cập nhật danh sách frame liên tục
                all_frames = [page.main_frame] + page.frames
                for frame in all_frames:
                    for sel in app_btn_selectors:
                        try:
                            btn = frame.locator(sel).first
                            # Click force luôn nếu tồn tại (đôi khi is_visible() bị false do CSS/vị trí)
                            if btn.count() > 0:
                                btn.scroll_into_view_if_needed()
                                btn.click(force=True)
                                clicked_app = True
                                break
                        except: continue
                    if clicked_app: break
                if clicked_app: break
                time.sleep(1)

            if not clicked_app:
                # Kiểm tra xem có thực sự đã ở trong App sẵn không (tránh false positive)
                already_in_app = False
                for frame in [page.main_frame] + page.frames:
                    try:
                        if (frame.locator('input[placeholder="username hoặc ID video..."]').count() > 0 or 
                            frame.locator('button:has-text("Chọn Video")').count() > 0 or 
                            frame.locator('button:has-text("Choose Video")').count() > 0):
                            already_in_app = True
                            break
                    except: continue
                if already_in_app:
                    print(f"✨ [{tiktok_id}] Đã ở trong App sẵn.")
                else:
                    print(f"❌ [{tiktok_id}] Không thể tìm thấy App 'Video Viral Clone' và giao diện App chưa load.")
                    return False
            time.sleep(5)

            # 6. Điền ID TikTok
            if tiktok_id:
                print(f"✍️ [{tiktok_id}] Điền ID: {tiktok_id}...")
                id_filled = False
                id_selector = 'input[placeholder="username hoặc ID video..."]'
                start_fill = time.time()
                while time.time() - start_fill < 10:
                    for frame in [page.main_frame] + page.frames:
                        try:
                            inp = frame.locator(id_selector).first
                            if inp.is_visible():
                                inp.click(); inp.fill(""); time.sleep(0.5)
                                inp.fill(str(tiktok_id))
                                id_filled = True; break
                        except: continue
                    if id_filled: break
                    time.sleep(1)
                time.sleep(2)

            # 7. Upload Video
            print(f"📤 [{tiktok_id}] Upload Video...")
            upload_btn_selectors = ['button:has-text("Chọn Video")', 'button:has-text("Choose Video")', 'div.border-dashed']
            
            target_frame = None
            target_btn = None
            
            start_search = time.time()
            while time.time() - start_search < 15:
                for frame in [page.main_frame] + page.frames:
                    for sel in upload_btn_selectors:
                        try:
                            btn = frame.locator(sel).first
                            if btn.is_visible(timeout=500):
                                target_frame = frame
                                target_btn = btn
                                break
                        except: continue
                    if target_btn: break
                if target_btn: break
                time.sleep(1)

            upload_success = False
            if target_btn and target_frame:
                print(f"🎯 [{tiktok_id}] Thấy nút 'Chọn Video'. Thử mở File Chooser mô phỏng người dùng...")
                try:
                    with page.expect_file_chooser(timeout=10000) as fc_info:
                        target_btn.click(force=True)
                    file_chooser = fc_info.value
                    file_chooser.set_files(local_video_path)
                    print(f"⏳ [{tiktok_id}] Đã chọn file qua File Chooser. Đang chờ tải lên...")
                    upload_success = True
                except Exception as e:
                    print(f"⚠️ [{tiktok_id}] Lỗi File Chooser ({e}). Chuyển sang set_input_files trực tiếp...")

            if not upload_success:
                upload_selectors = ['input[type="file"][accept="video/*"]', 'input[type="file"]']
                file_input = None
                for frame in [page.main_frame] + page.frames:
                    for sel in upload_selectors:
                        try:
                            loc = frame.locator(sel).first
                            if loc.count() > 0:
                                file_input = loc
                                break
                        except: continue
                    if file_input: break

                if file_input:
                    try:
                        file_input.wait_for(state="attached", timeout=10000)
                        file_input.set_input_files(local_video_path)
                        print(f"⏳ [{tiktok_id}] Đã chọn file qua set_input_files. Đang chờ tải lên...")
                        upload_success = True
                    except Exception as e:
                        print(f"❌ [{tiktok_id}] Lỗi set_input_files: {e}")
                        return False
                else:
                    print(f"❌ [{tiktok_id}] Lỗi: Không tìm thấy ô Upload hay nút Chọn Video.")
                    return False

            if upload_success:
                uploading_keywords = ['Uploading', 'uploading', 'Đang tải', 'đang tải', 'Loading', 'loading']
                for wait_sec in range(60):
                    is_uploading = False
                    for frame in [page.main_frame] + page.frames:
                        for kw in uploading_keywords:
                            try:
                                if frame.locator(f'text="{kw}"').first.is_visible(timeout=200):
                                    is_uploading = True
                                    break
                            except: pass
                        if is_uploading: break
                    
                    has_video_preview = False
                    for frame in [page.main_frame] + page.frames:
                        try:
                            if frame.locator('video').first.is_visible(timeout=200):
                                has_video_preview = True
                                break
                        except: pass

                    if has_video_preview and not is_uploading and wait_sec > 5:
                        print(f"🎥 [{tiktok_id}] Thấy video preview, tải lên hoàn tất!")
                        break
                    elif not is_uploading and wait_sec > 60:
                        break
                    
                    if wait_sec % 5 == 0:
                        print(f"   ... [{tiktok_id}] Đang tải file lên ({wait_sec}/60s)...")
                    time.sleep(1)

                print(f"✅ [{tiktok_id}] Upload OK (File đã tải lên server)!")
                time.sleep(5)

            # 8. Click Start
            print(f"▶️ [{tiktok_id}] Click 'Bắt đầu Clone Viral'...")
            start_btn_selectors = [
                'button:has-text("Bắt đầu Clone Viral")',
                'button:has-text("Bắt đầu Clone")',
                'button:has-text("Bắt đầu")',
                'button:has-text("Start")',
                'div[role="button"]:has-text("Bắt đầu")',
                'div[role="button"]:has-text("Start")',
                '[role="button"]:has-text("Bắt đầu")',
                '[role="button"]:has-text("Start")'
            ]
            clicked_start = False
            
            start_search_time = time.time()
            while time.time() - start_search_time < 30:
                all_frames = [page.main_frame] + page.frames
                for frame in all_frames:
                    for sel in start_btn_selectors:
                        try:
                            start_btn = frame.locator(sel).first
                            if start_btn.count() > 0:
                                start_btn.scroll_into_view_if_needed()
                                start_btn.click(force=True)
                                clicked_start = True
                                break
                        except Exception as e:
                            print(f"⚠️ [{tiktok_id}] Lỗi click nút Start với '{sel}': {e}")
                            continue
                    if clicked_start: break
                if clicked_start: break
                time.sleep(1)

            if not clicked_start:
                print(f"❌ [{tiktok_id}] Không thấy nút Start.")
                return False

            # 9. Chờ AI xử lý & Lưu
            print(f"⏳ [{tiktok_id}] Chờ AI xử lý...")
            save_selectors = ['button:has-text("Lưu vào Sheet")', 'button:has-text("Save to Sheet")', 'button.bg-blue-600:has-text("Lưu")']
            resume_selectors = ['button:has-text("Launch")', 'button:has-text("Resume")', 'button:has-text("Continue")']

            clicked_save = False
            for i in range(40): # Max 5 phút
                all_frames = [page.main_frame] + page.frames

                # Check nút Lưu
                for frame in all_frames:
                    for selector in save_selectors:
                        try:
                            save_btn = frame.locator(selector).first
                            if save_btn.is_visible():
                                print(f"✅ [{tiktok_id}] Thấy nút Lưu! Click...");
                                save_btn.scroll_into_view_if_needed(); save_btn.click(force=True)
                                clicked_save = True; break
                        except: continue
                    if clicked_save: break
                if clicked_save: break

                try:
                    vp = page.viewport_size or {'width':1280, 'height':720}
                    page.mouse.move(random.randint(10, vp['width']-10), random.randint(10, vp['height']-10))

                    for frame in all_frames:
                        for res_sel in resume_selectors:
                            try:
                                res_btn = frame.locator(res_sel).first
                                if res_btn.is_visible(timeout=500):
                                    print(f"🚀 [{tiktok_id}] Resume..."); res_btn.click(force=True)
                            except: continue
                except: pass

                if i % 2 == 0: print(f"... [{tiktok_id}] ({i+1}/60)")
                time.sleep(5)

            if clicked_save:
                print(f"🎉 [{tiktok_id}] HOÀN THÀNH!")
                time.sleep(5)
                return True
            else:
                print(f"❌ [{tiktok_id}] Timeout nút Lưu.")
                return False

    except Exception as e:
        print(f"🔥 [{tiktok_id}] Lỗi Crash: {e}")
        return False
    finally:
        try: browser.close()
        except: pass

def run_parallel_uploads(list_accounts_to_run):
    kill_chrome_globally()
    max_workers = len(list_accounts_to_run)
    if max_workers == 0:
        print("⚠️ Không có tài khoản nào để chạy.")
        return

    print(f"⚡ BẮT ĐẦU CHẠY {max_workers} LUỒNG ĐỒNG THỜI...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit task
        future_to_acc = {executor.submit(upload_worker, acc): acc["tiktok_id"] for acc in list_accounts_to_run}
        # Chờ kết quả
        for future in concurrent.futures.as_completed(future_to_acc):
            tid = future_to_acc[future]
            try:
                result = future.result()
                status = "THÀNH CÔNG" if result else "THẤT BẠI"
                print(f"🏁 [Kết thúc] {tid}: {status}")
            except Exception as e:
                print(f"💀 [Crash] {tid}: {e}")

def run_ai_studio_uploader(local_video_path, specific_profile_name=None, tiktok_id=None):
    _, def_email, def_pass, _ = load_settings()
    acc_config = {
        "tiktok_id": tiktok_id or "Unknown",
        "chrome_profile": specific_profile_name or "Default",
        "video_path": local_video_path,
        "email": def_email,
        "password": def_pass
    }
    global _has_killed_chrome_globally
    _has_killed_chrome_globally = False
    return upload_worker(acc_config)
