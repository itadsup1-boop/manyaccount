import customtkinter as ctk
import os
import json
from shared.services.supabase_api import SupabaseAPI

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOCAL_MACHINE_FILE = os.path.join(PROJECT_ROOT, "config", "local_machine.json")

class ApiSettingsPage:
    def __init__(self, parent_frame):
        self.parent = parent_frame

        self.title = ctk.CTkLabel(self.parent, text="🔑 Cấu hình API & Hệ thống", font=ctk.CTkFont(size=24, weight="bold"))
        self.title.pack(pady=(0, 20), anchor="w")

        # Đảm bảo có thư mục config
        os.makedirs(os.path.dirname(LOCAL_MACHINE_FILE), exist_ok=True)

        self.settings = SupabaseAPI.get_system_config("app_settings") or {}
        self.local_settings = self.load_local_settings()

        self.form_frame = ctk.CTkFrame(self.parent)
        self.form_frame.pack(fill="x", padx=10, pady=10)

        # 1. AI Studio
        ctk.CTkLabel(self.form_frame, text="1. Hệ thống AI Studio URL:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 0))
        self.inp_ai_url = ctk.CTkEntry(self.form_frame, width=600)
        self.inp_ai_url.pack(anchor="w", padx=10, pady=5)
        self.inp_ai_url.insert(0, self.settings.get("ai_studio_url", ""))

        # 2. Text-to-Speech
        ctk.CTkLabel(self.form_frame, text="2. Text-to-Speech (API Key EverAI):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 0))
        self.inp_api_key = ctk.CTkEntry(self.form_frame, width=600, show="*")
        self.inp_api_key.pack(anchor="w", padx=10, pady=5)
        self.inp_api_key.insert(0, self.settings.get("api_key", ""))

        ctk.CTkLabel(self.form_frame, text="Voice ID Mặc định:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 0))
        self.inp_voice_id = ctk.CTkEntry(self.form_frame, width=600)
        self.inp_voice_id.pack(anchor="w", padx=10, pady=5)
        self.inp_voice_id.insert(0, self.settings.get("voice_id", "vi_female_kieunhi_mn"))

        # 3. Google Sheet
        ctk.CTkLabel(self.form_frame, text="3. Google Sheet (Apps Script URL):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 0))
        self.inp_sheet_url = ctk.CTkEntry(self.form_frame, width=600)
        self.inp_sheet_url.pack(anchor="w", padx=10, pady=5)
        self.inp_sheet_url.insert(0, self.settings.get("sheet_url", ""))

        # ================= [MỚI BỔ SUNG] CẤU HÌNH TELEGRAM =================
        ctk.CTkLabel(self.form_frame, text="4. Bot Telegram Báo cáo (Tùy chọn):", font=ctk.CTkFont(weight="bold"), text_color="#00A8E8").pack(anchor="w", padx=10, pady=(20, 0))

        tele_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        tele_frame.pack(anchor="w", padx=10, pady=5)

        ctk.CTkLabel(tele_frame, text="Bot Token:").pack(side="left")
        self.inp_tele_token = ctk.CTkEntry(tele_frame, width=250, placeholder_text="7123...:AAH...")
        self.inp_tele_token.pack(side="left", padx=(5, 15))
        self.inp_tele_token.insert(0, self.settings.get("tele_token", ""))

        ctk.CTkLabel(tele_frame, text="Chat ID:").pack(side="left")
        self.inp_tele_chatid = ctk.CTkEntry(tele_frame, width=150, placeholder_text="-100... hoặc 123...")
        self.inp_tele_chatid.pack(side="left", padx=5)
        self.inp_tele_chatid.insert(0, self.settings.get("tele_chatid", ""))

        # ================= CẤU HÌNH CỤC BỘ (CHIA MÁY) =================
        ctk.CTkLabel(self.form_frame, text="5. Cấu hình Phân Máy (Chỉ lưu ở máy này, không lên Cloud):", font=ctk.CTkFont(weight="bold"), text_color="orange").pack(anchor="w", padx=10, pady=(20, 0))

        frame_machine = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        frame_machine.pack(anchor="w", padx=10, pady=5)
        ctk.CTkLabel(frame_machine, text="Định danh máy số:").pack(side="left", padx=(0, 10))

        self.inp_machine_id = ctk.CTkEntry(frame_machine, width=150)
        self.inp_machine_id.pack(side="left")
        self.inp_machine_id.insert(0, self.local_settings.get("machine_id", "1"))

        # Nút Lưu
        self.btn_save = ctk.CTkButton(self.form_frame, text="💾 LƯU TOÀN BỘ CẤU HÌNH", command=self.save_data, fg_color="green", hover_color="darkgreen")
        self.btn_save.pack(anchor="w", padx=10, pady=20)

        self.lbl_status = ctk.CTkLabel(self.form_frame, text="", text_color="green")
        self.lbl_status.pack(anchor="w", padx=10)

    def load_local_settings(self):
        try:
            with open(LOCAL_MACHINE_FILE, "r") as f: return json.load(f)
        except: return {"machine_id": "1"}

    def save_data(self):
        new_data = {
            "ai_studio_url": self.inp_ai_url.get().strip(),
            "api_key": self.inp_api_key.get().strip(),
            "voice_id": self.inp_voice_id.get().strip(),
            "sheet_url": self.inp_sheet_url.get().strip(),
            "tele_token": self.inp_tele_token.get().strip(),
            "tele_chatid": self.inp_tele_chatid.get().strip()
        }

        cloud_success = SupabaseAPI.update_system_config("app_settings", new_data)

        local_data = {"machine_id": self.inp_machine_id.get().strip() or "1"}
        with open(LOCAL_MACHINE_FILE, "w") as f:
            json.dump(local_data, f)

        if cloud_success:
            self.lbl_status.configure(text=f"✅ Đã lưu Cloud. Máy này được định danh là: Máy {local_data['machine_id']}", text_color="green")
        else:
            self.lbl_status.configure(text="❌ Lỗi khi lưu dữ liệu lên Cloud.", text_color="red")