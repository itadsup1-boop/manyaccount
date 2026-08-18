import customtkinter as ctk
import threading
import subprocess
import os
import sys
import time
import json
from datetime import datetime

# ═══════════════════════════════════════════════════════════
#  Đường dẫn
# ═══════════════════════════════════════════════════════════
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FB_PIPELINE_DIR = os.path.join(PROJECT_ROOT, "fb-news-pipeline")

# Import Supabase
sys.path.insert(0, PROJECT_ROOT)
try:
    from services.supabase_api import supabase
except ImportError:
    supabase = None


class FBNewsPipelinePage:
    def __init__(self, parent_frame):
        self.parent = parent_frame
        self.is_running = False
        self.process = None
        self.worker_thread = None

        self._build_ui()
        self._load_sources()

    # ═══════════════════════════════════════════════════════
    #  GIAO DIỆN
    # ═══════════════════════════════════════════════════════
    def _build_ui(self):
        # ── Tiêu đề ──
        header = ctk.CTkFrame(self.parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header,
            text="📰 Facebook News Auto Remix",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(side="left")

        self.status_label = ctk.CTkLabel(
            header, text="⚪ Chờ lệnh",
            font=ctk.CTkFont(size=14),
            text_color="#888"
        )
        self.status_label.pack(side="right", padx=10)

        # ── Khu vực thêm nguồn ──
        add_frame = ctk.CTkFrame(self.parent)
        add_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            add_frame,
            text="➕ Thêm nguồn Facebook:",
            font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(add_frame, text="Tên:").grid(row=1, column=0, padx=(10, 5), pady=5)
        self.input_name = ctk.CTkEntry(add_frame, width=180, placeholder_text="VD: VTV24 News")
        self.input_name.grid(row=1, column=1, padx=5, pady=5)

        ctk.CTkLabel(add_frame, text="URL:").grid(row=1, column=2, padx=(10, 5), pady=5)
        self.input_url = ctk.CTkEntry(add_frame, width=350, placeholder_text="https://facebook.com/vtv24news")
        self.input_url.grid(row=1, column=3, padx=5, pady=5)

        ctk.CTkLabel(add_frame, text="Max giờ:").grid(row=2, column=0, padx=(10, 5), pady=5)
        self.input_max_age = ctk.CTkEntry(add_frame, width=80, placeholder_text="48")
        self.input_max_age.insert(0, "48")
        self.input_max_age.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(add_frame, text="Delogo:").grid(row=3, column=0, padx=(10, 5), pady=5)
        self.input_delogo = ctk.CTkEntry(add_frame, width=180, placeholder_text="VD: x=683:y=231:w=280:h=85")
        self.input_delogo.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        self.btn_add = ctk.CTkButton(
            add_frame, text="✅ Thêm nguồn", width=140,
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._add_source
        )
        self.btn_add.grid(row=3, column=3, padx=10, pady=5, sticky="e")

        # ── Danh sách nguồn ──
        list_frame = ctk.CTkFrame(self.parent)
        list_frame.pack(fill="x", pady=(0, 10))

        list_header = ctk.CTkFrame(list_frame, fg_color="transparent")
        list_header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            list_header, text="📋 Danh sách nguồn Facebook:",
            font=ctk.CTkFont(weight="bold")
        ).pack(side="left")

        self.btn_refresh = ctk.CTkButton(
            list_header, text="🔄 Refresh", width=100,
            fg_color="#6b7280", hover_color="#4b5563",
            command=self._load_sources
        )
        self.btn_refresh.pack(side="right")

        self.btn_delete = ctk.CTkButton(
            list_header, text="🗑️ Xóa chọn", width=100,
            fg_color="#dc2626", hover_color="#b91c1c",
            command=self._delete_selected
        )
        self.btn_delete.pack(side="right", padx=5)

        # Bảng nguồn (dùng Textbox giả lập bảng)
        self.source_list = ctk.CTkTextbox(list_frame, height=120, state="disabled")
        self.source_list.pack(fill="x", padx=10, pady=(0, 10))

        # Lưu data nguồn để xóa
        self.sources_data = []

        # ── Dropdown chọn nguồn xóa ──
        self.selected_source_var = ctk.StringVar(value="-- Chọn nguồn để xóa --")
        self.source_dropdown = ctk.CTkOptionMenu(
            list_frame,
            variable=self.selected_source_var,
            values=["-- Chọn nguồn để xóa --"],
            width=400
        )
        self.source_dropdown.pack(padx=10, pady=(0, 10))

        # ── Nút điều khiển chính ──
        control_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        control_frame.pack(fill="x", pady=5)

        self.btn_start = ctk.CTkButton(
            control_frame,
            text="▶️  BẮT ĐẦU CHẠY PIPELINE",
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color="#16a34a", hover_color="#15803d",
            height=50,
            command=self._toggle_pipeline
        )
        self.btn_start.pack(fill="x", padx=10, pady=5)

        self.btn_run_once = ctk.CTkButton(
            control_frame,
            text="🔂 Chạy 1 lần (Không lặp)",
            font=ctk.CTkFont(size=13),
            fg_color="#7c3aed", hover_color="#6d28d9",
            height=35,
            command=self._run_once
        )
        self.btn_run_once.pack(fill="x", padx=10, pady=(0, 5))

        # ── Log ──
        ctk.CTkLabel(
            self.parent, text="📋 Nhật ký hoạt động:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=5)

        self.log_textbox = ctk.CTkTextbox(self.parent, height=250, state="disabled")
        self.log_textbox.pack(fill="both", expand=True, pady=(5, 0), padx=5)

        self.log("Hệ thống sẵn sàng. Thêm nguồn Facebook rồi nhấn BẮT ĐẦU!")

    # ═══════════════════════════════════════════════════════
    #  THÊM NGUỒN
    # ═══════════════════════════════════════════════════════
    def _add_source(self):
        name = self.input_name.get().strip()
        url = self.input_url.get().strip()
        max_age_str = self.input_max_age.get().strip()
        delogo_val = self.input_delogo.get().strip()

        if not name or not url:
            self.log("❌ Vui lòng điền đầy đủ Tên và URL nguồn Facebook.")
            return

        if "facebook.com" not in url and "fb.com" not in url:
            self.log("⚠️ URL không giống link Facebook. Vui lòng kiểm tra lại.")
            return

        max_age = 48
        try:
            max_age = int(max_age_str)
        except:
            pass

        # Chuẩn hóa URL
        url = url.rstrip("/")

        try:
            if supabase:
                result = supabase.table("facebook_sources").insert({
                    "source_name": name,
                    "source_url": url,
                    "platform": "facebook",
                    "is_active": True,
                    "max_video_age_hours": max_age,
                    "scan_interval_min": 30,
                    "delogo": delogo_val
                }).execute()

                if result.data:
                    self.log(f"✅ Đã thêm nguồn: {name} ({url})")
                    self.input_name.delete(0, "end")
                    self.input_url.delete(0, "end")
                    self.input_delogo.delete(0, "end")
                    self._load_sources()
                else:
                    self.log(f"❌ Lỗi thêm nguồn: Không có data trả về")
            else:
                self.log("❌ Chưa kết nối Supabase!")
        except Exception as e:
            error_msg = str(e)
            if "duplicate key" in error_msg.lower() or "23505" in error_msg:
                self.log(f"⚠️ Nguồn này đã tồn tại trong hệ thống: {url}")
            else:
                self.log(f"❌ Lỗi thêm nguồn: {e}")

    # ═══════════════════════════════════════════════════════
    #  LOAD DANH SÁCH NGUỒN
    # ═══════════════════════════════════════════════════════
    def _load_sources(self):
        try:
            if not supabase:
                self.log("❌ Chưa kết nối Supabase!")
                return

            result = supabase.table("facebook_sources").select("*").order("created_at", desc=False).execute()
            sources = result.data or []
            self.sources_data = sources

            # Cập nhật bảng nguồn
            self.source_list.configure(state="normal")
            self.source_list.delete("1.0", "end")

            if not sources:
                self.source_list.insert("end", "  📭 Chưa có nguồn nào. Hãy thêm nguồn Facebook ở trên.\n")
            else:
                header = f"  {'STT':<5} {'Tên nguồn':<25} {'URL':<35} {'Active':<8} {'Max giờ':<10} {'Delogo':<25} {'Quét cuối'}\n"
                self.source_list.insert("end", header)
                self.source_list.insert("end", "  " + "─" * 135 + "\n")

                for i, s in enumerate(sources, 1):
                    active = "✅" if s.get("is_active") else "❌"
                    last_scan = s.get("last_scan_at", "Chưa")
                    if last_scan and last_scan != "Chưa":
                        try:
                            dt = datetime.fromisoformat(last_scan.replace("Z", "+00:00"))
                            last_scan = dt.strftime("%d/%m %H:%M")
                        except:
                            last_scan = str(last_scan)[:16]

                    name = s.get("source_name", "")[:24]
                    url = s.get("source_url", "")[:34]
                    delogo_text = s.get("delogo", "")[:24]
                    if not delogo_text:
                        delogo_text = "Không"
                    line = f"  {i:<5} {name:<25} {url:<35} {active:<8} {s.get('max_video_age_hours', 48):<10} {delogo_text:<25} {last_scan}\n"
                    self.source_list.insert("end", line)

            self.source_list.configure(state="disabled")

            # Cập nhật dropdown
            dropdown_values = ["-- Chọn nguồn để xóa --"]
            for s in sources:
                dropdown_values.append(f"{s.get('source_name', '')} | {s.get('source_url', '')}")
            self.source_dropdown.configure(values=dropdown_values)
            self.selected_source_var.set(dropdown_values[0])

        except Exception as e:
            self.log(f"❌ Lỗi load nguồn: {e}")

    # ═══════════════════════════════════════════════════════
    #  XÓA NGUỒN
    # ═══════════════════════════════════════════════════════
    def _delete_selected(self):
        selected = self.selected_source_var.get()
        if selected.startswith("--"):
            self.log("⚠️ Vui lòng chọn nguồn cần xóa từ dropdown.")
            return

        # Tìm source từ danh sách
        try:
            source_url = selected.split(" | ")[-1].strip()
            matched = [s for s in self.sources_data if s.get("source_url") == source_url]

            if matched:
                source_id = matched[0]["id"]
                supabase.table("facebook_sources").delete().eq("id", source_id).execute()
                self.log(f"🗑️ Đã xóa nguồn: {matched[0].get('source_name')}")
                self._load_sources()
            else:
                self.log("⚠️ Không tìm thấy nguồn này trong database.")
        except Exception as e:
            self.log(f"❌ Lỗi xóa: {e}")

    # ═══════════════════════════════════════════════════════
    #  CHẠY PIPELINE
    # ═══════════════════════════════════════════════════════
    def _toggle_pipeline(self):
        if self.is_running:
            self._stop_pipeline()
        else:
            self._start_pipeline(loop=True)

    def _run_once(self):
        if self.is_running:
            self.log("⚠️ Pipeline đang chạy, không thể chạy thêm.")
            return
        self._start_pipeline(loop=False)

    def _start_pipeline(self, loop=True):
        if not os.path.exists(FB_PIPELINE_DIR):
            self.log(f"❌ Không tìm thấy thư mục pipeline: {FB_PIPELINE_DIR}")
            self.log("💡 Kiểm tra lại đường dẫn fb-news-pipeline")
            return

        # Kiểm tra có nguồn nào active không
        if not self.sources_data or not any(s.get("is_active") for s in self.sources_data):
            self.log("⚠️ Chưa có nguồn Facebook nào active! Hãy thêm nguồn trước.")
            return

        self.is_running = True
        mode = "start" if loop else "run-once"

        self.btn_start.configure(
            text="⏸️  DỪNG PIPELINE",
            fg_color="#dc2626", hover_color="#b91c1c"
        )
        self.btn_run_once.configure(state="disabled")
        self.status_label.configure(text="🟢 Đang chạy...", text_color="#16a34a")

        self.log(f"\n{'='*50}")
        self.log(f"🚀 BẮT ĐẦU PIPELINE {'(Chạy liên tục)' if loop else '(Chạy 1 lần)'}")
        self.log(f"{'='*50}\n")

        self.worker_thread = threading.Thread(
            target=self._pipeline_worker,
            args=(mode,),
            daemon=True
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
            text="▶️  BẮT ĐẦU CHẠY PIPELINE",
            fg_color="#16a34a", hover_color="#15803d"
        )
        self.btn_run_once.configure(state="normal")
        self.status_label.configure(text="⚪ Đã dừng", text_color="#888")
        self.log("🛑 Đã dừng pipeline.")

    def _pipeline_worker(self, mode):
        """Chạy pipeline TypeScript qua subprocess"""
        try:
            # Tìm npx
            npx_path = "npx"

            cmd = [npx_path, "ts-node", "src/index.ts", mode]
            self.log(f"📂 Thư mục: {FB_PIPELINE_DIR}")
            self.log(f"🖥️ Lệnh: {' '.join(cmd)}")

            self.process = subprocess.Popen(
                cmd,
                cwd=FB_PIPELINE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ, "NODE_NO_WARNINGS": "1"}
            )

            # Đọc output realtime
            for line in iter(self.process.stdout.readline, ''):
                if not self.is_running:
                    break
                line = line.rstrip()
                if line:
                    self.log(line)

            exit_code = 0
            if self.process:
                self.process.wait()
                exit_code = self.process.returncode

            if exit_code == 0:
                self.log("\n✅ Pipeline kết thúc thành công!")
            else:
                self.log(f"\n⚠️ Pipeline thoát với mã: {exit_code}")

        except FileNotFoundError:
            self.log("❌ Không tìm thấy npx hoặc ts-node!")
            self.log("💡 Hãy cài Node.js và chạy: cd fb-news-pipeline && npm install")
        except Exception as e:
            self.log(f"❌ Lỗi chạy pipeline: {e}")
        finally:
            self.process = None
            # Reset UI trên main thread
            self.parent.after(0, self._stop_pipeline)

    # ═══════════════════════════════════════════════════════
    #  LOG
    # ═══════════════════════════════════════════════════════
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {message}\n"
        print(full_msg.strip())
        self.parent.after(0, self._update_log_ui, full_msg)

    def _update_log_ui(self, msg):
        try:
            if hasattr(self, 'log_textbox') and self.log_textbox.winfo_exists():
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", msg)
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
        except:
            pass
