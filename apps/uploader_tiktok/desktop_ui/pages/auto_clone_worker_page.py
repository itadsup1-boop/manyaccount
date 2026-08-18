import customtkinter as ctk
import threading
import time
import os
import sys
import json
import traceback
from datetime import datetime

# ================= CẤU HÌNH ĐƯỜNG DẪN =================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.append(PROJECT_ROOT)

FRAME_DIR = os.path.join(PROJECT_ROOT, "assets", "frame")
LOGO_DIR = os.path.join(PROJECT_ROOT, "assets", "logo")
FONT_DIR = os.path.join(PROJECT_ROOT, "assets", "font")
CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "config", "credentials.json")

for d in [FRAME_DIR, LOGO_DIR, FONT_DIR]:
    if not os.path.exists(d): os.makedirs(d)

from shared.services.supabase_api import SupabaseAPI
from shared.core.context import AccountContext
from shared.core.worker import handle_tts_and_update_sheet

try:
    from modules.video_handler import download_tiktok_video
    from modules.ai_studio_uploader import upload_worker
    from modules.video_remix import create_video_from_source_video
    from modules.upload_drive import upload_video_to_drive
    from services.sheet_api import get_latest_row_by_id, update_final_result, update_source_link, save_to_sheet
    from services.tele_reporter import TeleReporter
except ImportError as e:
    print(f"⚠️ Lỗi Import thư viện: {e}")

def load_credentials():
    if not os.path.exists(CREDENTIALS_FILE): return {}
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

# ================= CLASS XỬ LÝ AUTO KẾT HỢP CORE =================
class AutoCloneWorkerPage:
    def __init__(self, parent_frame, supabase_client):
        self.parent = parent_frame
        self.supabase = supabase_client
        self.is_auto_running = False
        self.worker_thread = None

        # --- GIAO DIỆN UI ---
        self.title = ctk.CTkLabel(self.parent, text="🤖 Trạm Auto Remix (Treo Máy - Task DB)", font=ctk.CTkFont(size=24, weight="bold"))
        self.title.pack(pady=(0, 10), anchor="w")

        self.control_frame = ctk.CTkFrame(self.parent)
        self.control_frame.pack(fill="x", pady=10)

        self.btn_toggle = ctk.CTkButton(
            self.control_frame,
            text="▶️ BẬT TREO AUTO",
            font=ctk.CTkFont(weight="bold", size=16),
            fg_color="green", hover_color="darkgreen",
            height=40,
            command=self.toggle_auto
        )
        self.btn_toggle.pack(pady=10)

        ctk.CTkLabel(self.parent, text="📋 Nhật ký hoạt động (Logs):", font=ctk.CTkFont(weight="bold")).pack(anchor="w")

        self.log_textbox = ctk.CTkTextbox(self.parent, width=800, height=450, state="disabled")
        self.log_textbox.pack(fill="both", expand=True, pady=5)
        self.log("Hệ thống đã kết nối với Core Worker. Nhấn BẬT TREO AUTO để bắt đầu!")

    def log(self, message):
        """Hàm ghi log an toàn, hỗ trợ in ra console và đẩy lên giao diện"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {message}\n"
        print(full_msg.strip())

        # Dùng .after() để đảm bảo Thread-safe cho UI
        self.parent.after(0, self._update_log_ui, full_msg)

    def _update_log_ui(self, full_msg):
        """Cập nhật giao diện an toàn: Có check chống crash khi đổi trang/tắt app"""
        try:
            if hasattr(self, 'log_textbox') and self.log_textbox.winfo_exists():
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", full_msg)
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
        except Exception:
            pass

    def toggle_auto(self):
        if self.is_auto_running:
            self.is_auto_running = False
            self.btn_toggle.configure(text="▶️ BẬT TREO AUTO", fg_color="green", hover_color="darkgreen")
            self.log("🛑 Đã gửi lệnh dừng. Chờ hệ thống xử lý xong task hiện tại...")
        else:
            self.is_auto_running = True
            self.btn_toggle.configure(text="⏸️ DỪNG AUTO", fg_color="red", hover_color="darkred")
            self.log("🚀 Đã BẬT Auto. Đang quét Database (60s/lần)...")
            self.worker_thread = threading.Thread(target=self._auto_loop, daemon=True)
            self.worker_thread.start()

    def _auto_loop(self):
        while self.is_auto_running:
            try:
                # 1. Tìm task đầu tiên có trạng thái 'chưa làm'
                response = self.supabase.table('task_links').select('*').eq('status', 'chưa làm').limit(1).execute()
                tasks = response.data

                if not tasks:
                    self.log("💤 Quét xong nhưng chưa có task 'chưa làm' mới. Chờ 60s...")
                    self._sleep_with_check(60) # Chờ 60s rồi quét lại
                    continue

                task = tasks[0]
                task_id = task['id']

                # 2. Khóa task ngay lập tức để tránh trùng lặp
                self.supabase.table('task_links').update({'status': 'đang xử lý'}).eq('id', task_id).execute()
                self.log(f"\n⚡ Đã nhận Task #{task_id} | Video: {task['url']}")

                # 3. Tiến hành xử lý
                result_data = self._process_task(task)

                # 4. Cập nhật kết quả cuối cùng lên Supabase
                # Kiểm tra nếu kết quả trả về là Dictionary và có chứa drive_link
                if isinstance(result_data, dict) and result_data.get("drive_link"):
                    self.supabase.table('task_links').update({
                        'status': 'hoàn thành',
                        'drive_link': result_data["drive_link"],
                        'title': result_data.get("title", "") # <-- LƯU THÊM TITLE Ở ĐÂY
                    }).eq('id', task_id).execute()
                    self.log(f"✅ Hoàn thành 100% Task #{task_id}!")
                else:
                    self.supabase.table('task_links').update({'status': 'lỗi'}).eq('id', task_id).execute()
                    self.log(f"❌ Task #{task_id} thất bại.")

                self._sleep_with_check(10)

            except Exception as e:
                self.log(f"⚠️ Lỗi hệ thống Auto Loop: {str(e)}")
                self._sleep_with_check(30)

    def _sleep_with_check(self, seconds):
        for _ in range(seconds):
            if not self.is_auto_running: break
            time.sleep(1)

    # ================= LOGIC XỬ LÝ CHÍNH =================
    def _process_task(self, task):
        tiktok_id = task.get('tiktok_id')
        vid_url = task.get('url')
        clone_channel_url = task.get('clone_channel_url')
        task_id = task.get('id') # Lấy ID của task để làm tên thư mục

        # 1. Khởi tạo môi trường
        ctx = AccountContext(tiktok_id)
        ctx.logger.info(f"Bắt đầu Task Link: {vid_url}")

        # TẠO THƯ MỤC CÁCH LY CHO RIÊNG TASK NÀY ĐỂ TRÁNH XUNG ĐỘT FILE
        task_temp_dir = os.path.join(ctx.temp_dir, f"task_{task_id}")
        os.makedirs(task_temp_dir, exist_ok=True)

        try:
            cfg = ctx.config
            if not cfg: raise Exception(f"Không lấy được config từ Supabase cho ID: {tiktok_id}")

            channels_json = cfg.get("channels", [])
            if isinstance(channels_json, str):
                try: channels_json = json.loads(channels_json)
                except: channels_json = []

            channel_data = next((chn for chn in channels_json if chn.get("url") == clone_channel_url), None)
            if not channel_data: raise Exception(f"Không tìm thấy cấu hình Edit cho kênh: {clone_channel_url}")

            render_settings = channel_data.get("render_settings", {})

            self.log("📥 [1/6] Đang lấy Setting Hệ thống (Sheet, API)...")
            settings = SupabaseAPI.get_system_config("app_settings") or {}
            sheet_url = settings.get("sheet_url") or settings.get("google_sheet_url")
            tts_api_key = settings.get("api_key") or settings.get("everai_api_key")
            tts_voice_id = cfg.get("voice_id") or settings.get("voice_id") or settings.get("everai_voice_id", "1")
            folder_id = load_credentials().get("id_folder")

            if not sheet_url or not tts_api_key: raise Exception("Thiếu cấu hình Sheet URL hoặc API Key TTS!")

            clean_tid = tiktok_id.replace("@", "").strip()
            profile_name = "manual_shared_profile"

            # 3. Tải Video gốc vào thư mục CÁCH LY (task_temp_dir)
            self.log(f"📥 [2/6] Đang tải TikTok: {vid_url}")
            


            paths = download_tiktok_video(vid_url, task_temp_dir)
            if not paths: raise Exception("Lỗi tải video TikTok.")
            
            # (Đã di chuyển phần update link lên Google Sheet xuống phía dưới, sau khi AI Studio chạy xong)

            self.log("🤖 [3/6] Đang Upload AI Studio (manual_shared_profile)...")
            acc_payload = {
                "tiktok_id": clean_tid, "chrome_profile": profile_name,
                "video_path": paths['ai_studio'], "email": cfg.get("email"), "password": cfg.get("password")
            }
            if not upload_worker(acc_payload): raise Exception("Lỗi Upload AI Studio.")
            time.sleep(10)

            self.log("🔎 [4/6] Đang đọc Kịch bản từ Google Sheet...")
            row_data = None
            for _ in range(3):
                row_data = get_latest_row_by_id(sheet_url, clean_tid)
                if row_data: break
                time.sleep(3)
            if not row_data: raise Exception("Không tìm thấy dữ liệu trên Sheet.")

            self.log("🗣️ [5/6] Đang tạo Voice TTS (Sử dụng module Core)...")
            link_ct, local_content = handle_tts_and_update_sheet(
                api_key=tts_api_key, text=row_data["content_text"], voice_id=tts_voice_id,
                row_idx=row_data['row'], sheet_url=sheet_url, is_title=False, save_dir=task_temp_dir
            )
            local_title = None
            if row_data.get("title_text"):
                _, local_title = handle_tts_and_update_sheet(
                    api_key=tts_api_key, text=row_data["title_text"], voice_id=tts_voice_id,
                    row_idx=row_data['row'], sheet_url=sheet_url, is_title=True, save_dir=task_temp_dir
                )
            if not local_content: raise Exception("Lỗi tạo Voice Content.")

            self.log("🎬 [6/6] Đang Render & Edit Video...")
            assets_conf = render_settings.get("assets", {})

            def download_if_missing(folder_type, local_dir, file_name):
                if not file_name: return None
                full_path = os.path.join(local_dir, file_name)
                if not os.path.exists(full_path): SupabaseAPI.download_asset("assets", folder_type, local_dir, file_name)
                return full_path if os.path.exists(full_path) else None

            t_frame_path = download_if_missing("frame", FRAME_DIR, assets_conf.get("title_frame_filename"))
            c_frame_path = download_if_missing("frame", FRAME_DIR, assets_conf.get("content_frame_filename"))
            download_if_missing("logo", LOGO_DIR, assets_conf.get("logo_filename"))
            download_if_missing("font", FONT_DIR, render_settings.get("text_overlay_settings", {}).get("font_filename"))

            final_path = create_video_from_source_video(
                audio_url=local_content,
                source_video_url=paths['original'],
                title_audio_url=local_title,
                title_tiktok=row_data.get("title_text", "Video Viral"),
                content_text=row_data.get("title_text", ""),
                script_url=sheet_url,
                row_index=row_data['row'],
                tiktok_id=clean_tid,
                override_config=render_settings,
                output_filename=f"autolink_{clean_tid}_{int(time.time())}.mp4",
                temp_dir=task_temp_dir,
                title_frame_path=t_frame_path,
                content_frame_path=c_frame_path,
                target_channel_url=clone_channel_url
            )
            if not final_path: raise Exception("Lỗi ghép Render Video.")

            self.log("☁️ Đang Upload lên Google Drive...")
            drv_link = upload_video_to_drive(final_path, folder_id=folder_id)
            if not drv_link: raise Exception("Lỗi Upload Drive.")

            if update_final_result(sheet_url, row_data['row'], drv_link):
                try:
                    os.remove(final_path)
                    TeleReporter.log_success_video(clean_tid, clone_channel_url)
                except: pass

                return {
                    "drive_link": drv_link,
                    "title": row_data.get("title_text", "")
                }
            else:
                raise Exception("Lỗi ghi link Drive lên Sheet.")

        except Exception as e:
            self.log(f"❌ Chi tiết lỗi Task: {traceback.format_exc()}")
            ctx.logger.error(f"Task Lỗi: {e}")
            return False

        finally:
            import shutil
            if os.path.exists(task_temp_dir):
                try: shutil.rmtree(task_temp_dir)
                except: pass
            self.log(f"🧹 Đã dọn dẹp bộ nhớ đệm (task_{task_id}).")