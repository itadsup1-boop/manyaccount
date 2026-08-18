import undetected_chromedriver as uc
import os
import time
import sys

# ================= CẤU HÌNH ĐƯỜNG DẪN PROFILE =================
CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_DIR = os.path.dirname(CURRENT_FILE_DIR)

if sys.platform == "win32":
    CHROME_BIN_PATH = os.path.join(PROJECT_ROOT_DIR, "assets", "ChromePortable", "GoogleChromePortable", "App", "Chrome-bin", "chrome.exe")
else:
    # Linux search paths
    CHROME_BIN_PATH = None
    possible_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
        "/usr/bin/google-chrome-stable"
    ]
    for p in possible_paths:
        if os.path.exists(p):
            CHROME_BIN_PATH = p
            break

# Tên thư mục chứa dữ liệu profile
PROFILE_FOLDER_NAME = "data/chrome_profiles/tiktok_upload/tintucthammy24h_profile"
USER_DATA_DIR = os.path.join(PROJECT_ROOT_DIR, PROFILE_FOLDER_NAME)

try:
    from modules.proxy_helper import create_proxy_auth_extension
except ImportError:
    create_proxy_auth_extension = None

# Tạo thư mục nếu chưa có
if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR)

print(f"📂 Dữ liệu sẽ được lưu tại: {USER_DATA_DIR}")

def manual_login():
    print("🚀 Đang khởi động Chrome để đăng nhập...")

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={USER_DATA_DIR}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")
    options.add_argument("--start-maximized")

    try:
        # [ĐÃ SỬA] Ép cứng về bản 144
        driver = uc.Chrome(
            options=options,
            use_subprocess=True,
            version_main=145,
            browser_executable_path=CHROME_BIN_PATH
        )
    except Exception as e:
        print(f"❌ Lỗi khởi tạo: {e}")
        print("💡 GỢI Ý: Hãy tắt tất cả cửa sổ Chrome đang mở và thử lại.")
        return

    print("🔗 Đang truy cập trang đăng nhập Google...")
    driver.get("https://accounts.google.com/")

    print("\n" + "="*50)
    print("⚠️ HƯỚNG DẪN:")
    print("1. Trình duyệt đã mở. Hãy đăng nhập tài khoản Google của bạn.")
    print("2. Sau khi đăng nhập thành công và vào được tài khoản.")
    print("3. QUAY LẠI CỬA SỔ ĐEN NÀY VÀ NHẤN PHÍM 'ENTER' ĐỂ LƯU VÀ THOÁT.")
    print("="*50 + "\n")

    input("👉 ĐÃ ĐĂNG NHẬP XONG? Nhấn [ENTER] để đóng tool và lưu cookie...")

    print("💾 Đang lưu dữ liệu và thoát...")
    driver.quit()
    print("✅ Đã xong! Bạn có thể chạy tool Upload ngay bây giờ.")

def open_browser_for_login(profile_id, proxy=None):
    """
    Hàm mở trình duyệt để login thủ công.
    """
    print(f"🚀 Đang khởi động Chrome cho Profile: [{profile_id}]...")

    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.dirname(current_file_dir)
    user_data_dir = os.path.join(project_root_dir, "data", "chrome_profiles", "tiktok_upload", profile_id)

    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir)
        print(f"📂 [Backend] Đã tạo thư mục data: {user_data_dir}")

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")

    plugin_path = None
    if proxy and create_proxy_auth_extension:
        print(f"🌐 Đang cài đặt Proxy: {proxy}")
        plugin_path = create_proxy_auth_extension(proxy, project_root_dir)
        if plugin_path:
            options.add_extension(plugin_path)

    driver = None
    try:
        driver = uc.Chrome(
            options=options,
            use_subprocess=True,
            version_main=145,
            browser_executable_path=CHROME_BIN_PATH,
        )

        driver.get("https://accounts.google.com/")

        print("="*50)
        print(f"✅ ĐÃ MỞ CHROME CHO: {profile_id}")
        print("👉 Đăng nhập Google xong hãy đóng cửa sổ Chrome.")
        print("="*50)

        while True:
            try:
                if driver.service.process.poll() is not None:
                    print("🛑 Trình duyệt đã đóng.")
                    break
                time.sleep(1)
            except:
                break

    except Exception as e:
        print(f"❌ Lỗi Chrome: {e}")
        if "version" in str(e).lower():
            print("💡 Gợi ý: Hãy cập nhật undetected-chromedriver.")

    finally:
        if driver:
            try: driver.quit()
            except: pass
        if plugin_path and os.path.exists(plugin_path):
            try: os.remove(plugin_path)
            except: pass

if __name__ == "__main__":
    manual_login()