#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  Facebook News Auto Remix — Ứng dụng Desktop độc lập
#  Chạy độc lập, không phụ thuộc vào tool TikTok (mannyAccount)
# ═══════════════════════════════════════════════════════════════════

import customtkinter as ctk
import threading
import subprocess
import os
import sys
import json
import shutil
from datetime import datetime

# ═══════════════════════════════════════════════════════════
#  CẤU HÌNH
# ═══════════════════════════════════════════════════════════
APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_FILE = os.path.join(APP_DIR, ".env")

# Đọc .env thủ công (không cần python-dotenv cho GUI)
def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip()
    return env

ENV = load_env()
SUPABASE_URL = ENV.get("SUPABASE_URL", "")
SUPABASE_KEY = ENV.get("SUPABASE_KEY", "")

# Khởi tạo Supabase client
supabase_client = None
try:
    from supabase import create_client
    if SUPABASE_URL and SUPABASE_KEY:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
except ImportError:
    print("⚠️ Chưa cài supabase: pip install supabase")
except Exception as e:
    print(f"⚠️ Lỗi kết nối Supabase: {e}")

# ═══════════════════════════════════════════════════════════
#  THEME
# ═══════════════════════════════════════════════════════════
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "primary": "#7c3aed",
    "primary_hover": "#6d28d9",
    "success": "#16a34a",
    "success_hover": "#15803d",
    "danger": "#dc2626",
    "danger_hover": "#b91c1c",
    "info": "#2563eb",
    "info_hover": "#1d4ed8",
    "muted": "#6b7280",
    "muted_hover": "#4b5563",
    "bg_card": "#1e1e2e",
    "text_dim": "#888888",
}


class FBNewsApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("📰 Tool Đọc Báo Mạng Tự Động")
        self.geometry("1100x780")
        self.minsize(900, 650)

        self.is_running = False
        self.process = None
        self.worker_thread = None
        self.sources_data = []

        self._build_ui()
        self._load_sources()

    # ═══════════════════════════════════════════════════════
    #  GIAO DIỆN CHÍNH
    # ═══════════════════════════════════════════════════════
    def _build_ui(self):
        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=3)  # Tabview co giãn
        self.grid_rowconfigure(2, weight=0)  # Nút bấm không co giãn
        self.grid_rowconfigure(3, weight=2)  # Log co giãn

        # ── HEADER ──
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))

        ctk.CTkLabel(
            header,
            text="📰 Hệ Thống Dựng Video Từ Báo Mạng",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(side="left", padx=20, pady=15)

        self.status_badge = ctk.CTkLabel(
            header,
            text="  ⚪ SẴN SÀNG  ",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            fg_color="#374151",
            text_color="#9ca3af",
        )
        self.status_badge.pack(side="right", padx=20, pady=15)

        # ── TABVIEW CHÍNH ──
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=15, pady=5)
        
        self.tabview.add("📰 Chạy Pipeline")
        self.tabview.add("🌐 Quản lý Trình duyệt")
        self.tabview.add("🖼️ Quản lý Frame & Logo")
        self.tabview.add("🎙️ Quản lý Voice")
        
        tab_pipeline = self.tabview.tab("📰 Chạy Pipeline")
        tab_chrome = self.tabview.tab("🌐 Quản lý Trình duyệt")
        tab_assets = self.tabview.tab("🖼️ Quản lý Frame & Logo")
        tab_voice = self.tabview.tab("🎙️ Quản lý Voice")

        # ═══════════════════════════════════════════════════════
        #  TAB 1: PIPELINE RUNNER
        # ═══════════════════════════════════════════════════════
        
        # ── THÊM NGUỒN ──
        add_frame = ctk.CTkFrame(tab_pipeline, fg_color=COLORS["bg_card"], corner_radius=12)
        add_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            add_frame,
            text="➕ Thêm danh mục Báo Mạng mới",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=15, pady=(12, 8))

        ctk.CTkLabel(add_frame, text="ID TikTok:", font=ctk.CTkFont(size=13)).grid(row=1, column=0, padx=(15, 5), pady=8)
        self.input_name = ctk.CTkComboBox(add_frame, width=200, height=35)
        self.input_name.grid(row=1, column=1, padx=5, pady=8)

        ctk.CTkLabel(add_frame, text="URL Danh mục:", font=ctk.CTkFont(size=13)).grid(row=1, column=2, padx=(15, 5), pady=8)
        self.input_url = ctk.CTkEntry(add_frame, width=380, placeholder_text="VD: https://kenh14.vn/doi-song.chn", height=35)
        self.input_url.grid(row=1, column=3, padx=5, pady=8)

        self.btn_add = ctk.CTkButton(
            add_frame, text="✅ Thêm", width=80, height=35,
            fg_color=COLORS["info"], hover_color=COLORS["info_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self._add_source,
        )
        self.btn_add.grid(row=1, column=4, padx=(10, 15), pady=8)

        # ── DANH SÁCH NGUỒN ──
        list_frame = ctk.CTkFrame(tab_pipeline, fg_color=COLORS["bg_card"], corner_radius=12)
        list_frame.pack(fill="x", padx=15, pady=5)

        list_header = ctk.CTkFrame(list_frame, fg_color="transparent")
        list_header.pack(fill="x", padx=15, pady=(12, 5))

        ctk.CTkLabel(
            list_header,
            text="📋 Quản lý Kênh & Nguồn Báo (Tích để chạy tự động)",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")

        self.btn_refresh = ctk.CTkButton(
            list_header, text="🔄 Làm mới", width=80, height=30,
            fg_color=COLORS["muted"], hover_color=COLORS["muted_hover"],
            command=self._load_sources,
        )
        self.btn_refresh.pack(side="right")

        self.sources_scroll_frame = ctk.CTkScrollableFrame(list_frame, height=220, fg_color="transparent")
        self.sources_scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        self.channel_checkboxes = {}

        # ═══════════════════════════════════════════════════════
        #  TAB CHROME: QUẢN LÝ TRÌNH DUYỆT CHATGPT
        # ═══════════════════════════════════════════════════════
        chrome_frame = ctk.CTkFrame(tab_chrome, fg_color=COLORS["bg_card"], corner_radius=12)
        chrome_frame.pack(fill="x", padx=15, pady=15)
        
        ctk.CTkLabel(
            chrome_frame,
            text="🌐 Quản lý Trình duyệt ChatGPT",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 8))
        
        self.selected_chrome_var = ctk.StringVar(value="-- Chọn kênh để đăng nhập ChatGPT --")
        self.chrome_dropdown = ctk.CTkOptionMenu(
            chrome_frame, variable=self.selected_chrome_var,
            values=["-- Chọn kênh để đăng nhập ChatGPT --"], width=300,
            fg_color="#374151", button_color=COLORS["muted"],
        )
        self.chrome_dropdown.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
        
        self.btn_login = ctk.CTkButton(
            chrome_frame, text="🔑 Mở Chrome Đăng Nhập", width=160, height=32,
            fg_color=COLORS["success"], hover_color=COLORS["success_hover"],
            command=self._login_selected,
        )
        self.btn_login.grid(row=1, column=1, padx=5, pady=(0, 15), sticky="w")




        # ═══════════════════════════════════════════════════════
        #  TAB 2: FRAME & LOGO MANAGER
        # ═══════════════════════════════════════════════════════
        tab_assets.grid_columnconfigure(0, weight=1)
        tab_assets.grid_columnconfigure(1, weight=1)
        tab_assets.grid_rowconfigure(0, weight=1)

        # Cột trái: Chọn kênh & Upload files
        left_frame = ctk.CTkScrollableFrame(tab_assets, fg_color=COLORS["bg_card"], corner_radius=12)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(15, 10), pady=15)
        
        ctk.CTkLabel(
            left_frame,
            text="🖼️ Quản lý tài nguyên (PNG)",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(15, 10))
        
        self.btn_sync_library = ctk.CTkButton(
            left_frame, text="🔄 Đồng bộ Thư Viện Ảnh (Cloud)", width=250, height=32,
            fg_color=COLORS["info"], hover_color=COLORS["info_hover"],
            command=self._sync_global_assets
        )
        self.btn_sync_library.pack(anchor="w", padx=20, pady=(0, 15))

        # Dropdown chọn kênh
        ctk.CTkLabel(left_frame, text="Chọn kênh TikTok:", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=(5, 2))
        
        self.asset_channel_var = ctk.StringVar(value="-- Chọn kênh --")
        self.asset_channel_dropdown = ctk.CTkOptionMenu(
            left_frame,
            variable=self.asset_channel_var,
            values=["-- Chọn kênh --"],
            command=self._on_asset_channel_select,
            fg_color="#374151",
            button_color=COLORS["muted"],
            width=250,
        )
        self.asset_channel_dropdown.pack(anchor="w", padx=20, pady=(0, 15))

        # Status & Upload cho Khung Intro
        frame_intro_box = ctk.CTkFrame(left_frame, fg_color="transparent")
        frame_intro_box.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(frame_intro_box, text="Khung Intro (frame_intro.png):", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.lbl_frame_intro_status = ctk.CTkLabel(frame_intro_box, text="Chưa chọn kênh", text_color=COLORS["text_dim"])
        self.lbl_frame_intro_status.pack(anchor="w", pady=(0, 5))
        
        btn_frame_intro_row = ctk.CTkFrame(frame_intro_box, fg_color="transparent")
        btn_frame_intro_row.pack(anchor="w")
        
        self.library_frame_intro_var = ctk.StringVar(value="-- Chọn từ Thư viện --")
        self.library_frame_intro_dropdown = ctk.CTkOptionMenu(
            btn_frame_intro_row, variable=self.library_frame_intro_var,
            values=self._get_library_files("frame"),
            command=lambda val: self._apply_library_asset(val, "frame_intro"),
            width=180
        )
        self.library_frame_intro_dropdown.pack(side="left", padx=(0, 5))
        
        self.btn_up_frame_intro = ctk.CTkButton(
            btn_frame_intro_row, text="💻 Từ máy", width=90, height=32,
            fg_color=COLORS["primary"], hover_color=COLORS["primary_hover"],
            command=lambda: self._upload_asset_from_pc("frame_intro")
        )
        self.btn_up_frame_intro.pack(side="left", padx=(0, 5))
        
        self.btn_del_frame_intro = ctk.CTkButton(
            btn_frame_intro_row, text="🗑️ Xóa", width=70, height=32,
            fg_color=COLORS["danger"], hover_color=COLORS["danger_hover"],
            command=lambda: self._delete_asset("frame_intro"),
            state="disabled"
        )
        self.btn_del_frame_intro.pack(side="left")

        # Status & Upload cho Khung Content
        frame_content_box = ctk.CTkFrame(left_frame, fg_color="transparent")
        frame_content_box.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(frame_content_box, text="Khung Content (frame_content.png):", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.lbl_frame_content_status = ctk.CTkLabel(frame_content_box, text="Chưa chọn kênh", text_color=COLORS["text_dim"])
        self.lbl_frame_content_status.pack(anchor="w", pady=(0, 5))
        
        btn_frame_content_row = ctk.CTkFrame(frame_content_box, fg_color="transparent")
        btn_frame_content_row.pack(anchor="w")
        
        self.library_frame_content_var = ctk.StringVar(value="-- Chọn từ Thư viện --")
        self.library_frame_content_dropdown = ctk.CTkOptionMenu(
            btn_frame_content_row, variable=self.library_frame_content_var,
            values=self._get_library_files("frame"),
            command=lambda val: self._apply_library_asset(val, "frame_content"),
            width=180
        )
        self.library_frame_content_dropdown.pack(side="left", padx=(0, 5))
        
        self.btn_up_frame_content = ctk.CTkButton(
            btn_frame_content_row, text="💻 Từ máy", width=90, height=32,
            fg_color=COLORS["primary"], hover_color=COLORS["primary_hover"],
            command=lambda: self._upload_asset_from_pc("frame_content")
        )
        self.btn_up_frame_content.pack(side="left", padx=(0, 5))
        
        self.btn_del_frame_content = ctk.CTkButton(
            btn_frame_content_row, text="🗑️ Xóa", width=70, height=32,
            fg_color=COLORS["danger"], hover_color=COLORS["danger_hover"],
            command=lambda: self._delete_asset("frame_content"),
            state="disabled"
        )
        self.btn_del_frame_content.pack(side="left")

        # Status & Upload cho Logo
        logo_box = ctk.CTkFrame(left_frame, fg_color="transparent")
        logo_box.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkLabel(logo_box, text="Logo (Logo.png):", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.lbl_logo_status = ctk.CTkLabel(logo_box, text="Chưa chọn kênh", text_color=COLORS["text_dim"])
        self.lbl_logo_status.pack(anchor="w", pady=(0, 5))
        
        btn_logo_row = ctk.CTkFrame(logo_box, fg_color="transparent")
        btn_logo_row.pack(anchor="w")
        
        self.library_logo_var = ctk.StringVar(value="-- Chọn từ Thư viện --")
        self.library_logo_dropdown = ctk.CTkOptionMenu(
            btn_logo_row, variable=self.library_logo_var,
            values=self._get_library_files("logo"),
            command=lambda val: self._apply_library_asset(val, "logo"),
            width=180
        )
        self.library_logo_dropdown.pack(side="left", padx=(0, 5))
        
        self.btn_up_logo = ctk.CTkButton(
            btn_logo_row, text="💻 Từ máy", width=90, height=32,
            fg_color=COLORS["primary"], hover_color=COLORS["primary_hover"],
            command=lambda: self._upload_asset_from_pc("logo")
        )
        self.btn_up_logo.pack(side="left", padx=(0, 5))
        
        self.btn_del_logo = ctk.CTkButton(
            btn_logo_row, text="🗑️ Xóa", width=70, height=32,
            fg_color=COLORS["danger"], hover_color=COLORS["danger_hover"],
            command=lambda: self._delete_asset("logo"),
            state="disabled"
        )
        self.btn_del_logo.pack(side="left")

        # Cột phải: Cấu hình toạ độ Logo
        right_frame = ctk.CTkFrame(tab_assets, fg_color=COLORS["bg_card"], corner_radius=12)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 15), pady=15)
        
        ctk.CTkLabel(
            right_frame,
            text="⚙️ Thông số Chữ Content",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(15, 10))

        # Row 1: Y Start, Y End, Width %
        row1 = ctk.CTkFrame(right_frame, fg_color="transparent")
        row1.pack(fill="x", padx=15, pady=(5,0))
        
        ctk.CTkLabel(row1, text="Y Start:", font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=(5,2))
        self.input_text_y1 = ctk.CTkEntry(row1, width=60, height=28)
        self.input_text_y1.grid(row=0, column=1, padx=2)
        
        ctk.CTkLabel(row1, text="Y End:", font=ctk.CTkFont(size=12)).grid(row=0, column=2, padx=(10,2))
        self.input_text_y2 = ctk.CTkEntry(row1, width=60, height=28)
        self.input_text_y2.grid(row=0, column=3, padx=2)
        
        ctk.CTkLabel(row1, text="Width %:", font=ctk.CTkFont(size=12)).grid(row=0, column=4, padx=(10,2))
        self.input_text_w = ctk.CTkEntry(row1, width=60, height=28)
        self.input_text_w.grid(row=0, column=5, padx=2)
        
        ctk.CTkLabel(row1, text="X Offset:", font=ctk.CTkFont(size=12)).grid(row=0, column=6, padx=(10,2))
        self.input_text_x = ctk.CTkEntry(row1, width=60, height=28)
        self.input_text_x.grid(row=0, column=7, padx=2)

        # Row 2: Size, Màu, Stroke
        row2 = ctk.CTkFrame(right_frame, fg_color="transparent")
        row2.pack(fill="x", padx=15, pady=(10,0))
        
        ctk.CTkLabel(row2, text="Size:", font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=(5,2))
        self.input_text_size = ctk.CTkEntry(row2, width=60, height=28)
        self.input_text_size.grid(row=0, column=1, padx=2)
        
        ctk.CTkLabel(row2, text="Màu(Hex):", font=ctk.CTkFont(size=12)).grid(row=0, column=2, padx=(10,2))
        self.input_text_color = ctk.CTkEntry(row2, width=70, height=28)
        self.input_text_color.grid(row=0, column=3, padx=2)
        
        ctk.CTkLabel(row2, text="Stroke:", font=ctk.CTkFont(size=12)).grid(row=0, column=4, padx=(10,2))
        self.input_text_stroke = ctk.CTkEntry(row2, width=60, height=28)
        self.input_text_stroke.grid(row=0, column=5, padx=2)

        # Row 3: Font Name
        row3 = ctk.CTkFrame(right_frame, fg_color="transparent")
        row3.pack(fill="x", padx=15, pady=(10,5))
        
        ctk.CTkLabel(row3, text="Tên Font:", font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=(5,2))
        self.input_text_font = ctk.CTkEntry(row3, width=150, height=28)
        self.input_text_font.grid(row=0, column=1, padx=2)

        # Nút Lưu Cấu Hình
        self.btn_save_config = ctk.CTkButton(
            right_frame, text="💾 Lưu Cấu Hình", width=180, height=38,
            fg_color=COLORS["success"], hover_color=COLORS["success_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self._save_asset_config
        )
        self.btn_save_config.pack(anchor="w", padx=20, pady=10)

        # ═══════════════════════════════════════════════════════
        #  TAB 3: VOICE MANAGER
        # ═══════════════════════════════════════════════════════
        tab_voice.grid_columnconfigure(0, weight=1)
        
        voice_frame = ctk.CTkFrame(tab_voice, fg_color=COLORS["bg_card"], corner_radius=12)
        voice_frame.pack(fill="x", padx=15, pady=15)
        
        ctk.CTkLabel(
            voice_frame,
            text="🎙️ Quản lý Voice ID theo Kênh (Sắc thái AI phân tích)",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(15, 10))

        ctk.CTkLabel(voice_frame, text="Chọn kênh TikTok:", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=(5, 2))
        
        self.voice_channel_var = ctk.StringVar(value="-- Chọn kênh --")
        self.voice_channel_dropdown = ctk.CTkOptionMenu(
            voice_frame,
            variable=self.voice_channel_var,
            values=["-- Chọn kênh --"],
            command=self._on_voice_channel_select,
            fg_color="#374151",
            button_color=COLORS["muted"],
            width=250,
        )
        self.voice_channel_dropdown.pack(anchor="w", padx=20, pady=(0, 15))

        voices_container = ctk.CTkFrame(voice_frame, fg_color="transparent")
        voices_container.pack(fill="x", padx=20, pady=5)
        
        self.input_voice_positive = ctk.CTkEntry(voices_container, width=350, placeholder_text="Tích cực (VD: f46c9ad4...)")
        self.input_voice_neutral = ctk.CTkEntry(voices_container, width=350, placeholder_text="Trung tính (VD: 3595ed2b...)")
        self.input_voice_warning = ctk.CTkEntry(voices_container, width=350, placeholder_text="Cảnh báo (VD: fe810b49...)")
        self.input_voice_empathy = ctk.CTkEntry(voices_container, width=350, placeholder_text="Đồng cảm (VD: 3595ed2b...)")
        
        ctk.CTkLabel(voices_container, text="Giọng Tích cực:").grid(row=0, column=0, sticky="w", padx=5, pady=8)
        self.input_voice_positive.grid(row=0, column=1, padx=10, pady=8)

        ctk.CTkLabel(voices_container, text="Giọng Trung tính:").grid(row=1, column=0, sticky="w", padx=5, pady=8)
        self.input_voice_neutral.grid(row=1, column=1, padx=10, pady=8)

        ctk.CTkLabel(voices_container, text="Giọng Cảnh báo:").grid(row=2, column=0, sticky="w", padx=5, pady=8)
        self.input_voice_warning.grid(row=2, column=1, padx=10, pady=8)

        ctk.CTkLabel(voices_container, text="Giọng Đồng cảm:").grid(row=3, column=0, sticky="w", padx=5, pady=8)
        self.input_voice_empathy.grid(row=3, column=1, padx=10, pady=8)

        self.btn_save_voice = ctk.CTkButton(
            voice_frame, text="💾 Lưu Voice ID", width=180, height=38,
            fg_color=COLORS["success"], hover_color=COLORS["success_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self._save_voice_config
        )
        self.btn_save_voice.pack(anchor="w", padx=20, pady=15)


        # ═══════════════════════════════════════════════════════
        #  NÚT ĐIỀU KHIỂN (BÊN NGOÀI TABVIEW)
        # ═══════════════════════════════════════════════════════
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 5))

        self.btn_start = ctk.CTkButton(
            ctrl_frame,
            text="▶️   BẮT ĐẦU CHẠY TỰ ĐỘNG",
            font=ctk.CTkFont(size=20, weight="bold"),
            fg_color=COLORS["success"], hover_color=COLORS["success_hover"],
            height=55,
            corner_radius=12,
            command=self._toggle_pipeline,
        )
        self.btn_start.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.btn_run_once = ctk.CTkButton(
            ctrl_frame,
            text="🔂 Chạy 1 bài báo",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["primary"], hover_color=COLORS["primary_hover"],
            height=55,
            width=150,
            corner_radius=12,
            command=self._run_once,
        )
        self.btn_run_once.pack(side="right", padx=(5, 0))

        # ═══════════════════════════════════════════════════════
        #  LOG AREA (BÊN NGOÀI TABVIEW - LUÔN HIỂN THỊ)
        # ═══════════════════════════════════════════════════════
        log_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        log_frame.grid(row=3, column=0, sticky="nsew", padx=15, pady=(5, 15))
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=15, pady=(12, 5))

        ctk.CTkLabel(
            log_header,
            text="📋 Nhật ký hoạt động",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            log_header, text="🧹 Xóa log", width=80, height=28,
            fg_color=COLORS["muted"], hover_color=COLORS["muted_hover"],
            command=self._clear_log,
        ).pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            log_frame, state="disabled",
            font=ctk.CTkFont(family="monospace", size=12),
        )
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))

        self.log("🟢 Hệ thống Auto Báo Mạng đã sẵn sàng!")
        self.log(f"📂 Thư mục pipeline: {APP_DIR}")
        if supabase_client:
            self.log("✅ Đã kết nối Supabase thành công.")
        else:
            self.log("❌ Chưa kết nối Supabase! Kiểm tra file .env")

    # ═══════════════════════════════════════════════════════
    #  CÁC HÀM QUẢN LÝ ASSETS (FRAME/LOGO)
    # ═══════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════
    #  CÁC HÀM QUẢN LÝ ASSETS (FRAME/LOGO)
    # ═══════════════════════════════════════════════════════
    def _on_asset_channel_select(self, selected_channel):
        if not selected_channel or selected_channel.startswith("--"):
            self.lbl_frame_intro_status.configure(text="Chưa chọn kênh", text_color=COLORS["text_dim"])
            self.lbl_frame_content_status.configure(text="Chưa chọn kênh", text_color=COLORS["text_dim"])
            self.lbl_logo_status.configure(text="Chưa chọn kênh", text_color=COLORS["text_dim"])
            self.input_text_y1.delete(0, "end")
            self.input_text_y2.delete(0, "end")
            self.input_text_w.delete(0, "end")
            self.input_text_size.delete(0, "end")
            self.input_text_color.delete(0, "end")
            self.input_text_stroke.delete(0, "end")
            self.input_text_font.delete(0, "end")
            return
            
        channel_dir = os.path.join(APP_DIR, "assets", "channels", selected_channel)
        os.makedirs(channel_dir, exist_ok=True)
        
        frame_intro_path = os.path.join(channel_dir, "frame_intro.png")
        frame_content_path = os.path.join(channel_dir, "frame_content.png")
        logo_path = os.path.join(channel_dir, "logo.png")
        config_path = os.path.join(channel_dir, "config.json")
        
        # 1. Kiểm tra trạng thái trên Supabase Storage & Đồng bộ về local
        has_cloud_frame_intro = False
        has_cloud_frame_content = False
        has_cloud_logo = False
        has_cloud_config = False
        
        if supabase_client:
            try:
                res = supabase_client.storage.from_("assets").list(f"channels/{selected_channel}")
                if isinstance(res, list):
                    cloud_files = [f.get("name") for f in res if isinstance(f, dict) and f.get("name")]
                    
                    if "frame_intro.png" in cloud_files:
                        has_cloud_frame_intro = True
                        try:
                            data = supabase_client.storage.from_("assets").download(f"channels/{selected_channel}/frame_intro.png")
                            with open(frame_intro_path, "wb") as f:
                                f.write(data)
                        except Exception as e:
                            self.log(f"⚠️ Lỗi đồng bộ Frame Intro từ Cloud: {e}")
                            
                    if "frame_content.png" in cloud_files:
                        has_cloud_frame_content = True
                        try:
                            data = supabase_client.storage.from_("assets").download(f"channels/{selected_channel}/frame_content.png")
                            with open(frame_content_path, "wb") as f:
                                f.write(data)
                        except Exception as e:
                            self.log(f"⚠️ Lỗi đồng bộ Frame Content từ Cloud: {e}")
                            
                    if "logo.png" in cloud_files:
                        has_cloud_logo = True
                        try:
                            data = supabase_client.storage.from_("assets").download(f"channels/{selected_channel}/logo.png")
                            with open(logo_path, "wb") as f:
                                f.write(data)
                        except Exception as e:
                            self.log(f"⚠️ Lỗi đồng bộ Logo từ Cloud: {e}")
                            
                    if "config.json" in cloud_files:
                        has_cloud_config = True
                        try:
                            data = supabase_client.storage.from_("assets").download(f"channels/{selected_channel}/config.json")
                            with open(config_path, "wb") as f:
                                f.write(data)
                        except Exception as e:
                            self.log(f"⚠️ Lỗi đồng bộ cấu hình từ Cloud: {e}")
            except Exception as e:
                self.log(f"⚠️ Không kiểm tra được storage Cloud: {e}")
                
        # Đọc cấu hình config.json (đã được đồng bộ ở trên)
        cfg = {
            "logo_x": 50, "logo_y": 50, "logo_scale": 250,
            "text_y1": 0.73, "text_y2": 0.83, "text_w": 0.65,
            "text_size": 45, "text_color": "#ffffff", "text_stroke": 0,
            "text_font": "RobotoCondensed-Bold.ttf"
        }
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except:
                pass

        # 2. Cập nhật UI
        frame_intro_exists = has_cloud_frame_intro or os.path.exists(frame_intro_path)
        if cfg.get("frame_intro_disabled"):
            self.lbl_frame_intro_status.configure(text="⏸️ Đã tắt (File vẫn được giữ)", text_color="orange")
            self.btn_del_frame_intro.configure(state="normal")
        elif frame_intro_exists:
            frame_intro_name = cfg.get("frame_intro_name", "frame_intro.png")
            self.lbl_frame_intro_status.configure(text=f"✅ Đang dùng: {frame_intro_name} {'(Cloud)' if has_cloud_frame_intro else '(Máy)'}", text_color=COLORS["success"])
            self.btn_del_frame_intro.configure(state="normal")
        else:
            self.lbl_frame_intro_status.configure(text="❌ Chưa có file Khung Intro", text_color="orange")
            self.btn_del_frame_intro.configure(state="disabled")
            
        frame_content_exists = has_cloud_frame_content or os.path.exists(frame_content_path)
        if cfg.get("frame_content_disabled"):
            self.lbl_frame_content_status.configure(text="⏸️ Đã tắt (File vẫn được giữ)", text_color="orange")
            self.btn_del_frame_content.configure(state="normal")
        elif frame_content_exists:
            frame_content_name = cfg.get("frame_content_name", "frame_content.png")
            self.lbl_frame_content_status.configure(text=f"✅ Đang dùng: {frame_content_name} {'(Cloud)' if has_cloud_frame_content else '(Máy)'}", text_color=COLORS["success"])
            self.btn_del_frame_content.configure(state="normal")
        else:
            self.lbl_frame_content_status.configure(text="❌ Chưa có file Khung Content", text_color="orange")
            self.btn_del_frame_content.configure(state="disabled")
            
        logo_exists = has_cloud_logo or os.path.exists(logo_path)
        if cfg.get("logo_disabled"):
            self.lbl_logo_status.configure(text="⏸️ Đã tắt (Không chèn Logo)", text_color="orange")
            self.btn_del_logo.configure(state="normal")
        elif logo_exists:
            logo_name = cfg.get("logo_name", "logo.png")
            self.lbl_logo_status.configure(text=f"✅ Đang dùng: {logo_name} {'(Cloud)' if has_cloud_logo else '(Máy)'}", text_color=COLORS["success"])
            self.btn_del_logo.configure(state="normal")
        else:
            self.lbl_logo_status.configure(text="❌ Chưa có file logo.png (Dùng mặc định)", text_color="orange")
            self.btn_del_logo.configure(state="disabled")
            


        self.input_text_y1.delete(0, "end")
        self.input_text_y1.insert(0, str(cfg.get("text_y1", 0.73)))
        
        self.input_text_y2.delete(0, "end")
        self.input_text_y2.insert(0, str(cfg.get("text_y2", 0.83)))
        
        self.input_text_w.delete(0, "end")
        self.input_text_w.insert(0, str(cfg.get("text_w", 0.65)))
        
        self.input_text_size.delete(0, "end")
        self.input_text_size.insert(0, str(cfg.get("text_size", 45)))
        
        self.input_text_color.delete(0, "end")
        self.input_text_color.insert(0, str(cfg.get("text_color", "#ffffff")))
        
        self.input_text_stroke.delete(0, "end")
        self.input_text_stroke.insert(0, str(cfg.get("text_stroke", 0)))
        
        self.input_text_font.delete(0, "end")
        self.input_text_font.insert(0, str(cfg.get("text_font", "RobotoCondensed-Bold.ttf")))
        
        self.input_text_x.delete(0, "end")
        self.input_text_x.insert(0, str(cfg.get("text_x", 0)))

        # Bỏ đi việc load voice_profile_id ở tab asset

    def _get_library_files(self, folder):
        lib_dir = os.path.join(APP_DIR, "assets", folder)
        if not os.path.exists(lib_dir):
            return ["-- Chọn từ Thư viện --", "-- Trống --"]
        files = [f for f in os.listdir(lib_dir) if f.endswith(".png")]
        if not files:
            return ["-- Chọn từ Thư viện --", "-- Trống --"]
        return ["-- Chọn từ Thư viện --", "-- Trống --"] + sorted(files)

    def _apply_asset_file(self, asset_type, source_path):
        channel = self.asset_channel_var.get()
        if not channel or channel.startswith("--"):
            self.log(f"⚠️ Hãy chọn 1 kênh trước khi áp dụng {asset_type.capitalize()}.")
            return
            
        if not supabase_client:
            self.log("❌ Lỗi: Chưa kết nối Supabase.")
            return
            
        channel_dir = os.path.join(APP_DIR, "assets", "channels", channel)
        os.makedirs(channel_dir, exist_ok=True)
        dest = os.path.join(channel_dir, f"{asset_type}.png")
        config_path = os.path.join(channel_dir, "config.json")
        
        cfg = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except:
                pass
        cfg[f"{asset_type}_name"] = os.path.basename(source_path)
        cfg[f"{asset_type}_disabled"] = False
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        
        try:
            shutil.copy(source_path, dest)
            storage_path = f"channels/{channel}/{asset_type}.png"
            with open(dest, "rb") as f:
                try:
                    supabase_client.storage.from_("assets").upload(storage_path, f, file_options={"upsert": True})
                except Exception:
                    supabase_client.storage.from_("assets").update(storage_path, f)
                    
            # Upload config.json to sync the name too
            storage_config_path = f"channels/{channel}/config.json"
            with open(config_path, "rb") as f:
                try:
                    supabase_client.storage.from_("assets").upload(storage_config_path, f, file_options={"upsert": True})
                except Exception:
                    supabase_client.storage.from_("assets").update(storage_config_path, f)
                    
            self.log(f"✅ Đã áp dụng {asset_type.capitalize()} cho kênh {channel} lên Supabase Storage.")
            self._on_asset_channel_select(channel)
        except Exception as e:
            self.log(f"❌ Lỗi khi áp dụng {asset_type.capitalize()} lên Supabase: {e}")

    def _apply_library_asset(self, selected_file, asset_type):
        if not selected_file: return
        
        # Nếu chọn "-- Trống --", nghĩa là tắt frame (không dùng) nhưng không xóa file
        if selected_file == "-- Trống --":
            channel = self.asset_channel_var.get()
            if not channel or channel.startswith("--") or not supabase_client: return
            
            channel_dir = os.path.join(APP_DIR, "assets", "channels", channel)
            os.makedirs(channel_dir, exist_ok=True)
            config_path = os.path.join(channel_dir, "config.json")
            
            cfg = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except: pass
                
            cfg[f"{asset_type}_disabled"] = True
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                
            storage_config_path = f"channels/{channel}/config.json"
            with open(config_path, "rb") as f:
                try:
                    supabase_client.storage.from_("assets").upload(storage_config_path, f, file_options={"upsert": True})
                except Exception:
                    supabase_client.storage.from_("assets").update(storage_config_path, f)
                    
            self.log(f"⏸️ Đã TẮT (vô hiệu hóa) {asset_type} của kênh {channel} (File vẫn được giữ lại).")
            self._on_asset_channel_select(channel)
            return

        if selected_file.startswith("--"): return

        # Mặc định lấy từ thư mục frame (cho intro, content) hoặc logo (cho logo)
        lib_folder = "frame" if "frame" in asset_type else "logo"
        source_path = os.path.join(APP_DIR, "assets", lib_folder, selected_file)
        self._apply_asset_file(asset_type, source_path)
        
    def _upload_asset_from_pc(self, asset_type):
        from tkinter import filedialog
        file_path = filedialog.askopenfilename(initialdir=os.path.expanduser("~"), filetypes=[("Image files", "*.png")])
        if file_path:
            self._apply_asset_file(asset_type, file_path)

    def _delete_asset(self, asset_type):
        channel = self.asset_channel_var.get()
        if not channel or channel.startswith("--"):
            return
            
        if not supabase_client:
            return
            
        storage_path = f"channels/{channel}/{asset_type}.png"
        try:
            supabase_client.storage.from_("assets").remove([storage_path])
        except Exception as e:
            self.log(f"⚠️ Lỗi xóa {asset_type} trên Cloud: {e}")
            
        channel_dir = os.path.join(APP_DIR, "assets", "channels", channel)
        asset_path = os.path.join(channel_dir, f"{asset_type}.png")
        if os.path.exists(asset_path):
            try:
                os.remove(asset_path)
            except Exception as e:
                pass
                
        # Cập nhật config.json để đánh dấu file này bị disable hoàn toàn (không dùng fallback)
        config_path = os.path.join(channel_dir, "config.json")
        cfg = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except: pass
        cfg[f"{asset_type}_disabled"] = True
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            
        # Upload config lên Supabase
        storage_config_path = f"channels/{channel}/config.json"
        with open(config_path, "rb") as f:
            try:
                supabase_client.storage.from_("assets").upload(storage_config_path, f, file_options={"upsert": True})
            except Exception:
                supabase_client.storage.from_("assets").update(storage_config_path, f)
                
        self.log(f"🗑️ Đã xóa file {asset_type} của kênh {channel}")
        self._on_asset_channel_select(channel)

    def _save_asset_config(self):
        channel = self.asset_channel_var.get()
        if not channel or channel.startswith("--"):
            self.log("⚠️ Hãy chọn 1 kênh trước khi lưu cấu hình.")
            return
            
        if not supabase_client:
            self.log("❌ Lỗi: Chưa kết nối Supabase, không thể lưu cấu hình lên Cloud.")
            return
            
        try:
            # We no longer read logo inputs here, just preserve existing config
            pass
        except Exception as e:
            self.log(f"❌ Lỗi: {e}")
            return
            
        channel_dir = os.path.join(APP_DIR, "assets", "channels", channel)
        os.makedirs(channel_dir, exist_ok=True)
        config_path = os.path.join(channel_dir, "config.json")
        
        cfg_old = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg_old = json.load(f)
            except:
                pass
                
        cfg = {
            **cfg_old,
            "text_y1": float(self.input_text_y1.get().strip() or "0.73"),
            "text_y2": float(self.input_text_y2.get().strip() or "0.83"),
            "text_w": float(self.input_text_w.get().strip() or "0.65"),
            "text_size": int(self.input_text_size.get().strip() or "45"),
            "text_color": self.input_text_color.get().strip() or "#ffffff",
            "text_stroke": int(self.input_text_stroke.get().strip() or "0"),
            "text_font": self.input_text_font.get().strip() or "RobotoCondensed-Bold.ttf",
            "text_x": int(self.input_text_x.get().strip() or "0")
        }
        
        try:
            # Lưu local trước
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                
            # Upload lên Supabase Storage
            storage_path = f"channels/{channel}/config.json"
            with open(config_path, "rb") as f:
                try:
                    supabase_client.storage.from_("assets").upload(storage_path, f, file_options={"upsert": True})
                except Exception:
                    supabase_client.storage.from_("assets").update(storage_path, f)
                    
            self.log(f"💾 Đã lưu Cấu Hình cho kênh {channel} thành công!")
        except Exception as e:
            self.log(f"❌ Lỗi lưu cấu hình lên Cloud: {e}")

    def _on_voice_channel_select(self, selected_channel):
        if not selected_channel or selected_channel.startswith("--"):
            self.input_voice_positive.delete(0, "end")
            self.input_voice_neutral.delete(0, "end")
            self.input_voice_warning.delete(0, "end")
            self.input_voice_empathy.delete(0, "end")
            return
            
        channel_dir = os.path.join(APP_DIR, "assets", "channels", selected_channel)
        os.makedirs(channel_dir, exist_ok=True)
        voice_config_path = os.path.join(channel_dir, "voice_config.json")
        
        has_cloud_config = False
        if supabase_client:
            try:
                res = supabase_client.storage.from_("assets").list(f"channels/{selected_channel}")
                if isinstance(res, list):
                    cloud_files = [f.get("name") for f in res if isinstance(f, dict) and f.get("name")]
                    if "voice_config.json" in cloud_files:
                        has_cloud_config = True
                        try:
                            data = supabase_client.storage.from_("assets").download(f"channels/{selected_channel}/voice_config.json")
                            with open(voice_config_path, "wb") as f:
                                f.write(data)
                        except Exception as e:
                            self.log(f"⚠️ Lỗi đồng bộ Voice Config từ Cloud: {e}")
            except: pass
            
        cfg = {}
        if os.path.exists(voice_config_path):
            try:
                with open(voice_config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except: pass
            
        self.input_voice_positive.delete(0, "end")
        self.input_voice_positive.insert(0, str(cfg.get("Tích cực", "")))
        
        self.input_voice_neutral.delete(0, "end")
        self.input_voice_neutral.insert(0, str(cfg.get("Trung tính", "")))
        
        self.input_voice_warning.delete(0, "end")
        self.input_voice_warning.insert(0, str(cfg.get("Cảnh báo", "")))
        
        self.input_voice_empathy.delete(0, "end")
        self.input_voice_empathy.insert(0, str(cfg.get("Đồng cảm", "")))
        
    def _save_voice_config(self):
        channel = self.voice_channel_var.get()
        if not channel or channel.startswith("--"):
            self.log("⚠️ Hãy chọn 1 kênh trước khi lưu Voice ID.")
            return
            
        channel_dir = os.path.join(APP_DIR, "assets", "channels", channel)
        os.makedirs(channel_dir, exist_ok=True)
        voice_config_path = os.path.join(channel_dir, "voice_config.json")
        
        cfg = {
            "Tích cực": self.input_voice_positive.get().strip(),
            "Trung tính": self.input_voice_neutral.get().strip(),
            "Cảnh báo": self.input_voice_warning.get().strip(),
            "Đồng cảm": self.input_voice_empathy.get().strip()
        }
        
        try:
            with open(voice_config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                
            if supabase_client:
                storage_path = f"channels/{channel}/voice_config.json"
                with open(voice_config_path, "rb") as f:
                    try:
                        supabase_client.storage.from_("assets").upload(storage_path, f, file_options={"upsert": True})
                    except Exception:
                        supabase_client.storage.from_("assets").update(storage_path, f)
                        
            self.log(f"💾 Đã lưu Voice ID cho kênh {channel} thành công!")
        except Exception as e:
            self.log(f"❌ Lỗi lưu Voice ID: {e}")

    def _sync_global_assets(self):
        if not supabase_client:
            self.log("❌ Lỗi: Chưa kết nối Supabase.")
            return
            
        def _sync_task():
            self.log("🔄 Bắt đầu đồng bộ Thư Viện ảnh từ Supabase (bucket: assets)...")
            self.btn_sync_library.configure(state="disabled", text="⏳ Đang tải...")
            for folder in ["frame", "logo"]:
                local_dir = os.path.join(APP_DIR, "assets", folder)
                os.makedirs(local_dir, exist_ok=True)
                
                try:
                    res = supabase_client.storage.from_("assets").list(folder)
                    if isinstance(res, list):
                        files = [f.get("name") for f in res if isinstance(f, dict) and f.get("name") and f.get("name") != ".emptyFolderPlaceholder"]
                        for file_name in files:
                            self.log(f"   📥 Đang tải {folder}/{file_name}...")
                            try:
                                data = supabase_client.storage.from_("assets").download(f"{folder}/{file_name}")
                                with open(os.path.join(local_dir, file_name), "wb") as f:
                                    f.write(data)
                            except Exception as e:
                                self.log(f"   ⚠️ Lỗi tải {file_name}: {e}")
                except Exception as e:
                    self.log(f"⚠️ Lỗi đọc thư mục {folder} trên Storage: {e}")
            self.log("✅ Đồng bộ Thư Viện Ảnh hoàn tất! Các tuỳ chọn Thư viện đã được cập nhật.")
            self.btn_sync_library.configure(state="normal", text="🔄 Đồng bộ Thư Viện Ảnh (Cloud)")
            
            # Cập nhật lại list dropdown
            self.library_frame_intro_dropdown.configure(values=self._get_library_files("frame"))
            self.library_frame_content_dropdown.configure(values=self._get_library_files("frame"))
            self.library_logo_dropdown.configure(values=self._get_library_files("logo"))
            self.library_frame_intro_var.set("-- Chọn từ Thư viện --")
            self.library_frame_content_var.set("-- Chọn từ Thư viện --")
            self.library_logo_var.set("-- Chọn từ Thư viện --")
            
        threading.Thread(target=_sync_task, daemon=True).start()

    # ═══════════════════════════════════════════════════════
    #  THÊM NGUỒN
    # ═══════════════════════════════════════════════════════
    def _add_source(self):
        id_tiktok = self.input_name.get().strip()
        category_url = self.input_url.get().strip()

        if not id_tiktok or not category_url:
            self.log("❌ Vui lòng điền đầy đủ ID TikTok và URL Danh mục.")
            return

        if not supabase_client:
            self.log("❌ Chưa kết nối Supabase!")
            return

        category_url = category_url.rstrip("/")

        try:
            result = supabase_client.table("article_sources").insert({
                "id_tiktok": id_tiktok,
                "category_url": category_url,
                "is_active": True
            }).execute()

            if result.data:
                self.log(f"✅ Đã thêm nguồn Báo cho: {id_tiktok} → {category_url}")
                self.input_name.set("")
                self.input_url.delete(0, "end")
                self._load_sources()
            else:
                self.log("❌ Thêm nguồn thất bại!")
        except Exception as e:
            err = str(e)
            if "duplicate" in err.lower() or "23505" in err:
                self.log(f"⚠️ Nguồn báo đã tồn tại: {category_url}")
            else:
                self.log(f"❌ Lỗi: {e}")

    # ═══════════════════════════════════════════════════════
    #  LOAD DANH SÁCH NGUỒN
    # ═══════════════════════════════════════════════════════
    def _delete_source_by_id(self, sid):
        if not supabase_client: return
        try:
            supabase_client.table("article_sources").delete().eq("id", sid).execute()
            self.log(f"🗑️ Đã xóa nguồn thành công.")
            self._load_sources()
        except Exception as e:
            self.log(f"❌ Lỗi xóa nguồn: {e}")

    def _load_sources(self):
        if not supabase_client:
            return

        try:
            result = supabase_client.table("article_sources").select("*").order("created_at").execute()
            sources = result.data or []
            self.sources_data = sources

            # Xóa các widget cũ
            for widget in self.sources_scroll_frame.winfo_children():
                widget.destroy()
            self.channel_checkboxes.clear()

            unique_ids = []
            if not sources:
                ctk.CTkLabel(self.sources_scroll_frame, text="📭 Chưa có nguồn nào. Hãy thêm nguồn Báo Mạng ở phía trên.", text_color=COLORS["text_dim"]).pack(pady=20)
                self.input_name.configure(values=["-- Nhập ID mới --"])
            else:
                # Nhóm theo kênh
                grouped = {}
                for s in sources:
                    tid = s.get("id_tiktok") or "Unknown"
                    if tid not in grouped: grouped[tid] = []
                    grouped[tid].append(s)
                    
                unique_ids = list(grouped.keys())
                self.input_name.configure(values=unique_ids)

                for tid, items in grouped.items():
                    # Frame của từng kênh
                    chan_frame = ctk.CTkFrame(self.sources_scroll_frame, fg_color="#27273a", corner_radius=8)
                    chan_frame.pack(fill="x", pady=(0, 10))
                    
                    # Header của kênh: Chứa checkbox
                    header_frame = ctk.CTkFrame(chan_frame, fg_color="transparent")
                    header_frame.pack(fill="x", padx=10, pady=8)
                    
                    cb_var = ctk.BooleanVar(value=True)
                    self.channel_checkboxes[tid] = cb_var
                    cb = ctk.CTkCheckBox(
                        header_frame, text=f"Kênh: {tid} ({len(items)} nguồn)", 
                        variable=cb_var, font=ctk.CTkFont(size=14, weight="bold"),
                        text_color=COLORS["primary"]
                    )
                    cb.pack(side="left")

                    # Các nguồn bên dưới
                    for s in items:
                        row_frame = ctk.CTkFrame(chan_frame, fg_color="transparent")
                        row_frame.pack(fill="x", padx=(35, 10), pady=4)
                        
                        ctk.CTkLabel(row_frame, text=f"📄 {s['category_url']}", text_color="#d1d5db").pack(side="left")
                        
                        btn_del = ctk.CTkButton(
                            row_frame, text="🗑️", width=30, height=24,
                            fg_color="transparent", text_color=COLORS["danger"], hover_color="#374151",
                            command=lambda sid=s['id']: self._delete_source_by_id(sid)
                        )
                        btn_del.pack(side="right")

            # Cập nhật các danh sách dropdown phụ trợ
            chrome_vals = ["-- Chọn kênh --"] + unique_ids if unique_ids else ["-- Chọn kênh --"]
            
            self.chrome_dropdown.configure(values=chrome_vals)
            self.selected_chrome_var.set(chrome_vals[0])
            
            # Cập nhật dropdown quản lý assets
            asset_vals = chrome_vals if unique_ids else ["-- Chọn kênh --"]
            self.asset_channel_dropdown.configure(values=asset_vals)
            self.voice_channel_dropdown.configure(values=asset_vals)
            
            # Giữ nguyên kênh đang chọn ở tab Asset nếu có
            current_asset_sel = self.asset_channel_var.get()
            if current_asset_sel not in asset_vals:
                self.asset_channel_var.set(asset_vals[0])
                self._on_asset_channel_select(asset_vals[0])

        except Exception as e:
            self.log(f"❌ Lỗi load nguồn: {e}")

    # ═══════════════════════════════════════════════════════
    #  XÓA NGUỒN
    # ═══════════════════════════════════════════════════════
    def _delete_selected(self):
        selected = self.selected_source_var.get()
        if selected.startswith("--"):
            self.log("⚠️ Chọn nguồn cần xóa từ dropdown trước.")
            return

        try:
            category_url = selected.split(" | ")[-1].strip()
            matched = [s for s in self.sources_data if s.get("category_url") == category_url]
            if matched:
                sid = matched[0]["id"]
                supabase_client.table("article_sources").delete().eq("id", sid).execute()
                self.log(f"🗑️ Đã xóa nguồn: {category_url}")
                self._load_sources()
            else:
                self.log("⚠️ Không tìm thấy nguồn này.")
        except Exception as e:
            self.log(f"❌ Lỗi xóa: {e}")

    # ═══════════════════════════════════════════════════════
    #  ĐĂNG NHẬP CHATGPT
    # ═══════════════════════════════════════════════════════
    def _login_selected(self):
        selected = self.selected_chrome_var.get()
        if selected.startswith("--"):
            self.log("⚠️ Hãy chọn 1 kênh từ mục Quản lý Trình duyệt trước.")
            return

        id_tiktok = selected.strip()
        self.log(f"🔑 Đang mở trình duyệt đăng nhập ChatGPT cho kênh: {id_tiktok}...")
        self.log("👉 Vui lòng thao tác trên cửa sổ Chrome vừa bật lên!")

        def run_login():
            try:
                python_exe = sys.executable
                cmd = [python_exe, "apps/creator_article/article_chatgpt_automator.py", "login", id_tiktok]
                subprocess.run(cmd, cwd=APP_DIR)
                self.log(f"✅ Đã đóng cửa sổ đăng nhập ChatGPT của {id_tiktok}.")
            except Exception as e:
                self.log(f"❌ Lỗi khi mở Chrome: {e}")
                
        threading.Thread(target=run_login, daemon=True).start()

    # ═══════════════════════════════════════════════════════
    #  ĐIỀU KHIỂN PIPELINE
    # ═══════════════════════════════════════════════════════
    def _toggle_pipeline(self):
        if self.is_running:
            self._stop_pipeline()
        else:
            self._start_pipeline(loop=True)

    def _run_once(self):
        if self.is_running:
            self.log("⚠️ Pipeline đang chạy!")
            return
        self._start_pipeline(loop=False)

    def _start_pipeline(self, loop=True):
        # Kiểm tra có nguồn active không
        active_sources = [s for s in self.sources_data if s.get("is_active")]
        if not active_sources:
            self.log("⚠️ Chưa có nguồn Facebook active! Thêm nguồn trước.")
            return

        self.is_running = True
        mode = "start" if loop else "run-once"

        self.btn_start.configure(
            text="⏸️   DỪNG PIPELINE",
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
        )
        self.btn_run_once.configure(state="disabled")
        self.status_badge.configure(
            text="  🟢 ĐANG CHẠY  ",
            fg_color="#166534",
            text_color="#4ade80",
        )

        self.log("")
        self.log("═" * 55)
        self.log(f"🚀 BẮT ĐẦU PIPELINE {'(Liên tục)' if loop else '(1 lần)'}")
        self.log(f"📡 {len(active_sources)} nguồn active")
        self.log("═" * 55)
        self.log("")

        self.worker_thread = threading.Thread(
            target=self._pipeline_worker,
            args=(mode,),
            daemon=True,
        )
        self.worker_thread.start()

    def _stop_pipeline(self):
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except:
                pass
            self.process = None

        self.btn_start.configure(
            text="▶️   BẮT ĐẦU CHẠY PIPELINE",
            fg_color=COLORS["success"],
            hover_color=COLORS["success_hover"],
        )
        self.btn_run_once.configure(state="normal")
        self.status_badge.configure(
            text="  ⚪ SẴN SÀNG  ",
            fg_color="#374151",
            text_color="#9ca3af",
        )
        self.log("🛑 Đã dừng pipeline.")

    def _pipeline_worker(self, mode):
        """Chạy pipeline Bài báo bằng subprocess"""
        # Lấy danh sách kênh được chọn
        selected_channels = [tid for tid, var in self.channel_checkboxes.items() if var.get()]
        if not selected_channels:
            self.log("⚠️ LỖI: Bạn chưa tích chọn kênh nào để chạy!")
            self.after(0, self._stop_pipeline)
            return
            
        try:
            # Dùng cùng Python interpreter đang chạy GUI
            python_exe = sys.executable
            # Gọi file điều phối chính của Báo (Sẽ viết sau)
            cmd = [python_exe, "-u", "apps/creator_article/article_pipeline_core.py", mode]
            cmd.extend(["--channels", ",".join(selected_channels)])
            
            self.log(f"🖥️ Lệnh: {' '.join(cmd)}")

            self.process = subprocess.Popen(
                cmd,
                cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                bufsize=1,
            )

            for line in iter(self.process.stdout.readline, ""):
                if not self.is_running:
                    break
                line = line.rstrip()
                if line:
                    self.log(line)

            code = 0
            if self.process:
                self.process.wait()
                code = self.process.returncode

            if code == 0:
                self.log("\n✅ Pipeline hoàn thành!")
            elif code is not None:
                self.log(f"\n⚠️ Pipeline thoát: code {code}")

        except Exception as e:
            self.log(f"❌ Lỗi: {e}")
        finally:
            self.process = None
            self.after(0, self._stop_pipeline)

    # ═══════════════════════════════════════════════════════
    #  LOG
    # ═══════════════════════════════════════════════════════
    def log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        full = f"[{ts}] {message}\n"
        print(full.strip())
        self.after(0, self._write_log, full)

    def _write_log(self, msg):
        try:
            if self.log_textbox.winfo_exists():
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", msg)
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
        except:
            pass

    def _clear_log(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")
        self.log("🧹 Đã xóa log.")

    # ═══════════════════════════════════════════════════════
    #  ĐÓNG APP
    # ═══════════════════════════════════════════════════════
    def on_closing(self):
        if self.is_running:
            self._stop_pipeline()
        self.destroy()


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = FBNewsApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
