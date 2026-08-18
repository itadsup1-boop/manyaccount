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
from datetime import datetime

# ═══════════════════════════════════════════════════════════
#  CẤU HÌNH
# ═══════════════════════════════════════════════════════════
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(APP_DIR)), ".env")

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
        self.title("📰 Facebook News Auto Remix")
        self.geometry("1100x780")
        self.minsize(900, 650)

        self.is_running = False
        self.process = None
        self.worker_thread = None
        self.sources_data = []

        self._build_ui()
        self._load_sources()
        self._load_voice_settings()

    # ═══════════════════════════════════════════════════════
    #  GIAO DIỆN CHÍNH
    # ═══════════════════════════════════════════════════════
    def _build_ui(self):
        # Grid layout: 1 cột, nhiều hàng
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)  # Log area expands

        # ── HEADER ──
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))

        ctk.CTkLabel(
            header,
            text="📰 Facebook News Auto Remix Pipeline",
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


        # ── CÀI ĐẶT GIỌNG TOÀN CỤC ──
        setting_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        setting_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=5)

        ctk.CTkLabel(
            setting_frame,
            text="⚙️ Cài đặt Voice ID mặc định (Áp dụng cho mọi kênh)",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=8, sticky="w", padx=15, pady=(12, 8))

        ctk.CTkLabel(setting_frame, text="Tích cực:", font=ctk.CTkFont(size=13)).grid(row=1, column=0, padx=(15, 2), pady=8, sticky="e")
        self.setting_voice_pos = ctk.CTkEntry(setting_frame, width=150, placeholder_text="ID Voice", height=35)
        self.setting_voice_pos.grid(row=1, column=1, padx=2, pady=8, sticky="w")

        ctk.CTkLabel(setting_frame, text="Trung tính:", font=ctk.CTkFont(size=13)).grid(row=1, column=2, padx=(10, 2), pady=8, sticky="e")
        self.setting_voice_neu = ctk.CTkEntry(setting_frame, width=150, placeholder_text="ID Voice", height=35)
        self.setting_voice_neu.grid(row=1, column=3, padx=2, pady=8, sticky="w")

        ctk.CTkLabel(setting_frame, text="Cảnh báo:", font=ctk.CTkFont(size=13)).grid(row=1, column=4, padx=(10, 2), pady=8, sticky="e")
        self.setting_voice_warn = ctk.CTkEntry(setting_frame, width=150, placeholder_text="ID Voice", height=35)
        self.setting_voice_warn.grid(row=1, column=5, padx=2, pady=8, sticky="w")

        ctk.CTkLabel(setting_frame, text="Đồng cảm:", font=ctk.CTkFont(size=13)).grid(row=1, column=6, padx=(10, 2), pady=8, sticky="e")
        self.setting_voice_emp = ctk.CTkEntry(setting_frame, width=150, placeholder_text="ID Voice", height=35)
        self.setting_voice_emp.grid(row=1, column=7, padx=2, pady=8, sticky="w")

        self.btn_save_settings = ctk.CTkButton(
            setting_frame, text="💾 Lưu", width=80, height=35,
            fg_color=COLORS["success"], hover_color=COLORS["success_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self._save_voice_settings,
        )
        self.btn_save_settings.grid(row=1, column=8, padx=(10, 15), pady=8)

        # Đẩy grid row của các phần tử sau xuống 1 bậc

        # ── THÊM NGUỒN ──
        add_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        add_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=5)

        ctk.CTkLabel(
            add_frame,
            text="➕ Thêm nguồn Facebook mới",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=15, pady=(12, 8))

        ctk.CTkLabel(add_frame, text="Tên:", font=ctk.CTkFont(size=13)).grid(row=1, column=0, padx=(15, 5), pady=8)
        self.input_name = ctk.CTkEntry(add_frame, width=200, placeholder_text="VD: VTV24 News", height=35)
        self.input_name.grid(row=1, column=1, padx=5, pady=8)

        ctk.CTkLabel(add_frame, text="URL:", font=ctk.CTkFont(size=13)).grid(row=1, column=2, padx=(15, 5), pady=8)
        self.input_url = ctk.CTkEntry(add_frame, width=380, placeholder_text="https://facebook.com/page-name", height=35)
        self.input_url.grid(row=1, column=3, padx=5, pady=8)

        ctk.CTkLabel(add_frame, text="Max giờ:", font=ctk.CTkFont(size=13)).grid(row=1, column=4, padx=(15, 5), pady=8)
        self.input_max_age = ctk.CTkEntry(add_frame, width=60, height=35)
        self.input_max_age.insert(0, "48")
        self.input_max_age.grid(row=1, column=5, padx=5, pady=8)

        ctk.CTkLabel(add_frame, text="Delogo:", font=ctk.CTkFont(size=13)).grid(row=1, column=6, padx=(15, 5), pady=8)
        self.input_delogo = ctk.CTkEntry(add_frame, width=150, placeholder_text="VD: x=683:y=231:w=280:h=85", height=35)
        self.input_delogo.grid(row=1, column=7, padx=5, pady=8)

        self.btn_add = ctk.CTkButton(
            add_frame, text="✅ Thêm", width=80, height=35,
            fg_color=COLORS["info"], hover_color=COLORS["info_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self._add_source,
        )
        self.btn_add.grid(row=1, column=8, padx=(10, 15), pady=8)

        # ── DANH SÁCH NGUỒN ──
        list_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        list_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=5)
        list_frame.grid_columnconfigure(0, weight=1)

        list_header = ctk.CTkFrame(list_frame, fg_color="transparent")
        list_header.pack(fill="x", padx=15, pady=(12, 5))

        ctk.CTkLabel(
            list_header,
            text="📋 Nguồn đang theo dõi",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")

        btn_row = ctk.CTkFrame(list_header, fg_color="transparent")
        btn_row.pack(side="right")

        self.btn_refresh = ctk.CTkButton(
            btn_row, text="🔄", width=40, height=32,
            fg_color=COLORS["muted"], hover_color=COLORS["muted_hover"],
            command=self._load_sources,
        )
        self.btn_refresh.pack(side="left", padx=3)

        self.btn_delete = ctk.CTkButton(
            btn_row, text="🗑️ Xóa", width=70, height=32,
            fg_color=COLORS["danger"], hover_color=COLORS["danger_hover"],
            command=self._delete_selected,
        )
        self.btn_delete.pack(side="left", padx=3)

        self.source_list = ctk.CTkTextbox(list_frame, height=110, state="disabled", font=ctk.CTkFont(family="monospace", size=12))
        self.source_list.pack(fill="x", padx=15, pady=(0, 5))

        self.selected_source_var = ctk.StringVar(value="-- Chọn nguồn để xóa --")
        self.source_dropdown = ctk.CTkOptionMenu(
            list_frame, variable=self.selected_source_var,
            values=["-- Chọn nguồn để xóa --"], width=500,
            fg_color="#374151", button_color=COLORS["muted"],
        )
        self.source_dropdown.pack(padx=15, pady=(0, 12))

        # ── NÚT ĐIỀU KHIỂN ──
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.grid(row=4, column=0, sticky="ew", padx=15, pady=5)
        ctrl_frame.grid_columnconfigure(0, weight=3)
        ctrl_frame.grid_columnconfigure(1, weight=1)

        self.btn_start = ctk.CTkButton(
            ctrl_frame,
            text="▶️   BẮT ĐẦU CHẠY PIPELINE",
            font=ctk.CTkFont(size=20, weight="bold"),
            fg_color=COLORS["success"], hover_color=COLORS["success_hover"],
            height=55,
            corner_radius=12,
            command=self._toggle_pipeline,
        )
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.btn_run_once = ctk.CTkButton(
            ctrl_frame,
            text="🔂 Chạy 1 lần",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["primary"], hover_color=COLORS["primary_hover"],
            height=55,
            corner_radius=12,
            command=self._run_once,
        )
        self.btn_run_once.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        # ── LOG ──
        log_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=12)
        log_frame.grid(row=5, column=0, sticky="nsew", padx=15, pady=(5, 15))
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

        self.log("🟢 Hệ thống Facebook News Auto Remix đã sẵn sàng!")
        self.log(f"📂 Thư mục pipeline: {APP_DIR}")
        if supabase_client:
            self.log("✅ Đã kết nối Supabase thành công.")
        else:
            self.log("❌ Chưa kết nối Supabase! Kiểm tra file .env")

    # ═══════════════════════════════════════════════════════

    def _load_voice_settings(self):
        settings_path = os.path.join(APP_DIR, "data", "global_voice_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.setting_voice_pos.insert(0, data.get("Tích cực", ""))
                self.setting_voice_neu.insert(0, data.get("Trung tính", ""))
                self.setting_voice_warn.insert(0, data.get("Cảnh báo", ""))
                self.setting_voice_emp.insert(0, data.get("Đồng cảm", ""))
            except:
                pass

    def _save_voice_settings(self):
        os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
        settings_path = os.path.join(APP_DIR, "data", "global_voice_settings.json")
        data = {
            "Tích cực": self.setting_voice_pos.get().strip(),
            "Trung tính": self.setting_voice_neu.get().strip(),
            "Cảnh báo": self.setting_voice_warn.get().strip(),
            "Đồng cảm": self.setting_voice_emp.get().strip()
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.log("✅ Đã lưu cấu hình Voice toàn cục thành công.")

    #  THÊM NGUỒN
    # ═══════════════════════════════════════════════════════
    def _add_source(self):
        name = self.input_name.get().strip()
        url = self.input_url.get().strip()
        max_age_str = self.input_max_age.get().strip()
        delogo_val = self.input_delogo.get().strip()

        if not name or not url:
            self.log("❌ Vui lòng điền đầy đủ Tên và URL.")
            return

        if "facebook.com" not in url and "fb.com" not in url and "fb.watch" not in url:
            self.log("⚠️ URL không phải link Facebook. Kiểm tra lại!")
            return

        if not supabase_client:
            self.log("❌ Chưa kết nối Supabase!")
            return

        max_age = 48
        try:
            max_age = int(max_age_str)
        except:
            pass

        url = url.rstrip("/")
        
        try:
            result = supabase_client.table("facebook_sources").insert({
                "source_name": name,
                "source_url": url,
                "platform": "facebook",
                "is_active": True,
                "max_video_age_hours": max_age,
                "scan_interval_min": 30,
                "delogo": delogo_val
            }).execute()

            if result.data:
                self.log(f"✅ Đã thêm: {name} → {url}")
                self.input_name.delete(0, "end")
                self.input_url.delete(0, "end")
                self.input_delogo.delete(0, "end")
                self._load_sources()
            else:
                self.log("❌ Thêm nguồn thất bại!")
        except Exception as e:
            err = str(e)
            if "duplicate" in err.lower() or "23505" in err:
                self.log(f"⚠️ Nguồn đã tồn tại: {url}")
            else:
                self.log(f"❌ Lỗi: {e}")

    # ═══════════════════════════════════════════════════════
    #  LOAD DANH SÁCH NGUỒN
    # ═══════════════════════════════════════════════════════
    def _load_sources(self):
        if not supabase_client:
            return

        try:
            result = supabase_client.table("facebook_sources").select("*").order("created_at").execute()
            sources = result.data or []
            self.sources_data = sources

            self.source_list.configure(state="normal")
            self.source_list.delete("1.0", "end")

            if not sources:
                self.source_list.insert("end", "  📭 Chưa có nguồn nào. Thêm nguồn Facebook ở phía trên.\n")
            else:
                header = f"  {'#':<4} {'Tên nguồn':<22} {'URL':<38} {'On':<5} {'Max h':<7} {'Delogo':<22} {'Quét cuối'}\n"
                self.source_list.insert("end", header)
                self.source_list.insert("end", "  " + "─" * 125 + "\n")

                for i, s in enumerate(sources, 1):
                    active = "✅" if s.get("is_active") else "❌"
                    last_scan = s.get("last_scan_at", "—")
                    if last_scan and last_scan != "—":
                        try:
                            dt = datetime.fromisoformat(last_scan.replace("Z", "+00:00"))
                            last_scan = dt.strftime("%d/%m %H:%M")
                        except:
                            last_scan = str(last_scan)[:16]

                    name = (s.get("source_name") or "")[:21]
                    url = (s.get("source_url") or "")[:37]
                    delogo_text = (s.get("delogo") or "")[:21]
                    if not delogo_text:
                        delogo_text = "Không"
                    line = f"  {i:<4} {name:<22} {url:<38} {active:<5} {s.get('max_video_age_hours', 48):<7} {delogo_text:<22} {last_scan}\n"
                    self.source_list.insert("end", line)

            self.source_list.configure(state="disabled")

            # Cập nhật dropdown xóa
            dropdown_vals = ["-- Chọn nguồn để xóa --"]
            for s in sources:
                dropdown_vals.append(f"{s.get('source_name', '')} | {s.get('source_url', '')}")
            self.source_dropdown.configure(values=dropdown_vals)
            self.selected_source_var.set(dropdown_vals[0])

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
            source_url = selected.split(" | ")[-1].strip()
            matched = [s for s in self.sources_data if s.get("source_url") == source_url]
            if matched:
                sid = matched[0]["id"]
                supabase_client.table("facebook_sources").delete().eq("id", sid).execute()
                self.log(f"🗑️ Đã xóa: {matched[0].get('source_name')}")
                self._load_sources()
            else:
                self.log("⚠️ Không tìm thấy nguồn này.")
        except Exception as e:
            self.log(f"❌ Lỗi xóa: {e}")

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
        """Chạy pipeline Python bằng subprocess"""
        try:
            # Dùng cùng Python interpreter đang chạy GUI
            python_exe = sys.executable
            cmd = [python_exe, "-u", "fb_pipeline.py", mode]
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
