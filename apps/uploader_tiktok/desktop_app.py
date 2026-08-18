import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(APP_DIR)) # /home/giang-adsup/Documents/mannyAccount
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, APP_DIR)

import customtkinter as ctk
from shared.services.supabase_api import supabase

from desktop_ui.pages.dashboard import DashboardPage
from desktop_ui.pages.api_settings import ApiSettingsPage
from desktop_ui.pages.account_manager import AccountManagerPage
from desktop_ui.pages.channel_manager import ChannelManagerPage
from desktop_ui.pages.auto_clone_worker_page import AutoCloneWorkerPage

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MatrixBotApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Matrix Bot")
        self.geometry("1200x750")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(7, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text=" MATRIX BOT", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))

        self.btn_dashboard = ctk.CTkButton(self.sidebar_frame, text="Dashboard (Chạy Bot)", command=self.show_dashboard)
        self.btn_dashboard.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.btn_accounts = ctk.CTkButton(self.sidebar_frame, text="Quản lý Tài khoản", command=self.show_accounts)
        self.btn_accounts.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.btn_channels = ctk.CTkButton(self.sidebar_frame, text="Quản lý Kênh", command=self.show_channels)
        self.btn_channels.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        self.btn_clone_channels = ctk.CTkButton(self.sidebar_frame, text="Treo Auto Remix", command=self.show_clone_channels)
        self.btn_clone_channels.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        self.btn_api = ctk.CTkButton(self.sidebar_frame, text="Cấu hình API", command=self.show_api_settings)
        self.btn_api.grid(row=5, column=0, padx=20, pady=10, sticky="ew")

        # ================= MAIN FRAME =================
        self.main_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # ================= TẠO TẤT CẢ CÁC TRANG 1 LẦN DUY NHẤT =================
        self.frames = {}

        # Khởi tạo sẵn tất cả các trang
        f_dash = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frames["dashboard"] = f_dash
        self.dashboard_page = DashboardPage(f_dash)

        f_acc = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frames["accounts"] = f_acc
        self.accounts_page = AccountManagerPage(f_acc)

        f_chan = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frames["channels"] = f_chan
        self.channels_page = ChannelManagerPage(f_chan)

        f_clone = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frames["clone"] = f_clone
        self.clone_page = AutoCloneWorkerPage(f_clone, supabase)

        f_api = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frames["api"] = f_api
        self.api_page = ApiSettingsPage(f_api)

        # Mặc định bật trang dashboard lên đầu tiên
        self.show_frame("dashboard")

    def hide_all_frames(self):
        """Hàm này chỉ làm ẩn các Frame đi, giữ nguyên mọi trạng thái bên trong"""
        for frame in self.frames.values():
            frame.grid_remove()

    def show_frame(self, frame_name):
        self.hide_all_frames()
        frame = self.frames[frame_name]
        frame.grid(row=0, column=0, sticky="nsew")

        # ================= TỰ ĐỘNG REFRESH DỮ LIỆU KHI MỞ TRANG =================

        # 1. Quay lại Dashboard -> Load lại list account & trạng thái
        if frame_name == "dashboard" and hasattr(self.dashboard_page, 'load_accounts'):
            self.dashboard_page.load_accounts()

        # 2. Vào Quản lý Tài khoản -> Lấy lại danh sách từ DB
        elif frame_name == "accounts" and hasattr(self.accounts_page, 'load_accounts'):
            self.accounts_page.load_accounts()

        # 3. Vào Quản lý Kênh -> Lấy lại dữ liệu Kênh mới nhất
        elif frame_name == "channels" and hasattr(self.channels_page, 'accounts'):
            from services.supabase_api import SupabaseAPI
            self.channels_page.accounts = SupabaseAPI.get_all_accounts() or []
            self.channels_page.acc_ids = [acc.get("tiktok_id") for acc in self.channels_page.accounts if acc.get("tiktok_id")]
            self.channels_page.acc_dropdown.configure(values=self.channels_page.acc_ids)

            if self.channels_page.current_account:
                selected_id = self.channels_page.current_account.get("tiktok_id")
                self.channels_page.on_account_select(selected_id)

    # Các nút bấm ở menu sẽ gọi hàm show_frame thay vì tạo mới class như cũ
    def show_dashboard(self): self.show_frame("dashboard")
    def show_accounts(self): self.show_frame("accounts")
    def show_channels(self): self.show_frame("channels")
    def show_clone_channels(self): self.show_frame("clone")
    def show_api_settings(self): self.show_frame("api")

    def on_closing(self):
        try:
            # Tắt bot ở dashboard nếu đang chạy
            if hasattr(self, 'dashboard_page') and getattr(self.dashboard_page, 'bot_process', None):
                self.dashboard_page.stop_bot()

            # Tắt luồng Auto Worker nếu đang chạy để tránh treo Python ngầm
            if hasattr(self, 'clone_page') and self.clone_page.is_auto_running:
                self.clone_page.is_auto_running = False

        except Exception as e:
            print(f"Lỗi khi đóng app: {e}")
        finally:
            self.destroy()

if __name__ == "__main__":
    app = MatrixBotApp()
    app.mainloop()