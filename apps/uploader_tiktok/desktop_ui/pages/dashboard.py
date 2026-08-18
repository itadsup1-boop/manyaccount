import customtkinter as ctk
import subprocess
import threading
import sys
import os
import re
from shared.services.supabase_api import SupabaseAPI

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class DashboardPage:
    def __init__(self, parent_frame):
        self.parent = parent_frame
        self.bot_process = None

        self.title = ctk.CTkLabel(self.parent, text="Dashboard (Bảng điều khiển)", font=ctk.CTkFont(size=24, weight="bold"))
        self.title.pack(pady=(0, 10), anchor="w")

        # ================= LOGIC QUẢN LÝ LỊCH CHẠY =================
        self.schedule_frame = ctk.CTkFrame(self.parent)
        self.schedule_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(self.schedule_frame, text="Cấu hình Lịch chạy (Giờ:Phút):", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.inp_time = ctk.CTkEntry(self.schedule_frame, width=120, placeholder_text="Ví dụ: 08:30")
        self.inp_time.grid(row=0, column=1, padx=10, pady=10)

        self.btn_add_time = ctk.CTkButton(self.schedule_frame, text="➕ Thêm Giờ", width=100, fg_color="green", hover_color="darkgreen", command=self.add_time)
        self.btn_add_time.grid(row=0, column=2, padx=10, pady=10)

        self.lbl_schedule_error = ctk.CTkLabel(self.schedule_frame, text="", text_color="red")
        self.lbl_schedule_error.grid(row=0, column=3, padx=10)

        # Khung hiển thị các mốc thời gian đã thêm
        self.time_list_frame = ctk.CTkFrame(self.schedule_frame, fg_color="transparent")
        self.time_list_frame.grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="w")

        self.current_schedule = {"crawl_times": [], "nurture_windows": []}

        # ================= NÚT ĐIỀU KHIỂN BOT =================
        self.action_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        self.action_frame.pack(fill="x", pady=(0, 20))

        self.btn_start_bot = ctk.CTkButton(self.action_frame, text="🚀 KHỞI ĐỘNG HỆ THỐNG", font=ctk.CTkFont(weight="bold"), fg_color="blue", hover_color="darkblue", height=40, command=self.start_bot)
        self.btn_start_bot.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_stop_bot = ctk.CTkButton(self.action_frame, text="🛑 DỪNG HỆ THỐNG", font=ctk.CTkFont(weight="bold"), fg_color="gray", hover_color="darkred", height=40, state="disabled", command=self.stop_bot)
        self.btn_stop_bot.pack(side="left", fill="x", expand=True, padx=(5, 0))

        self.lbl_bot_status = ctk.CTkLabel(self.parent, text="⚪ Trạng thái: Đang chờ...", text_color="gray")
        self.lbl_bot_status.pack(anchor="w", pady=(0, 10))



        # ================= DANH SÁCH TÀI KHOẢN =================
        ctk.CTkLabel(self.parent, text="📋 Danh sách tài khoản trên Supabase:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")

        self.scroll_frame = ctk.CTkScrollableFrame(self.parent, width=800, height=400)
        self.scroll_frame.pack(fill="both", expand=True, pady=10)

        self.account_vars = []
        self.account_data_refs = []
        self.select_all_var = ctk.BooleanVar(value=False)

        self.load_schedule()
        self.load_accounts()

    # ================= HÀM XỬ LÝ LỊCH CHẠY =================
    def load_schedule(self):
        config = SupabaseAPI.get_system_config("schedule_config") or {}
        self.current_schedule["crawl_times"] = config.get("crawl_times", [])
        self.current_schedule["nurture_windows"] = config.get("nurture_windows", [])
        self._render_time_list()

    def _render_time_list(self):
        for widget in self.time_list_frame.winfo_children():
            widget.destroy()

        times = sorted(self.current_schedule.get("crawl_times", []))

        if not times:
            ctk.CTkLabel(self.time_list_frame, text="Chưa có lịch chạy nào. Hãy thêm mốc thời gian!").pack(side="left")
            return

        ctk.CTkLabel(self.time_list_frame, text="Các giờ bot sẽ chạy:").pack(side="left", padx=(0, 10))

        for t in times:
            tag_frame = ctk.CTkFrame(self.time_list_frame, fg_color="gray20", corner_radius=10)
            tag_frame.pack(side="left", padx=5)

            ctk.CTkLabel(tag_frame, text=t, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 5), pady=2)

            btn_del = ctk.CTkButton(tag_frame, text="✕", width=20, height=20, fg_color="transparent", hover_color="red", text_color="white",
                                    command=lambda time_val=t: self.delete_time(time_val))
            btn_del.pack(side="left", padx=(0, 5), pady=2)

    def add_time(self):
        self.lbl_schedule_error.configure(text="")
        new_time = self.inp_time.get().strip()

        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", new_time):
            self.lbl_schedule_error.configure(text="❌ Sai định dạng! Hãy nhập HH:MM (VD: 08:30)")
            return

        if len(new_time) == 4:
            new_time = "0" + new_time

        times = self.current_schedule["crawl_times"]
        if new_time in times:
            self.lbl_schedule_error.configure(text="⚠️ Giờ này đã có trong lịch!")
            return

        times.append(new_time)
        self._save_schedule_to_db()
        self.inp_time.delete(0, 'end')

    def delete_time(self, time_val):
        times = self.current_schedule["crawl_times"]
        if time_val in times:
            times.remove(time_val)
            self._save_schedule_to_db()

    def _save_schedule_to_db(self):
        if SupabaseAPI.update_system_config("schedule_config", self.current_schedule):
            self._render_time_list()
        else:
            self.lbl_schedule_error.configure(text="❌ Lỗi khi lưu lịch lên Supabase!")



    # ================= HÀM XỬ LÝ TÀI KHOẢN & LIMIT =================
    def load_accounts(self):
        accounts = SupabaseAPI.get_all_accounts()

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not accounts:
            ctk.CTkLabel(self.scroll_frame, text="📭 Chưa có tài khoản nào trên Database.").pack(pady=20)
            return

        # Tiêu đề các cột
        header_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=5)

        self.chk_select_all = ctk.CTkCheckBox(header_frame, text="Bật/Tắt", variable=self.select_all_var, command=self.toggle_all_accounts, width=80, font=ctk.CTkFont(weight="bold"))
        self.chk_select_all.pack(side="left", padx=10)

        ctk.CTkLabel(header_frame, text="TikTok ID", width=150, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkLabel(header_frame, text="Voice ID", width=250, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkLabel(header_frame, text="Max Video", width=80, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)

        self.account_vars.clear()
        self.account_data_refs.clear()

        all_active = True if accounts else False

        def truncate_text(text, max_len):
            if not text: return ""
            return text if len(text) <= max_len else text[:max_len-3] + "..."

        # Hiển thị từng tài khoản
        for acc in accounts:
            row_frame = ctk.CTkFrame(self.scroll_frame)
            row_frame.pack(fill="x", pady=2)

            is_active = acc.get("active", False)
            if not is_active: all_active = False

            chk_var = ctk.BooleanVar(value=is_active)
            self.account_vars.append(chk_var)
            self.account_data_refs.append(acc)

            chk = ctk.CTkCheckBox(row_frame, text="", variable=chk_var, width=80)
            chk.configure(command=lambda a=acc, v=chk_var: self.toggle_single_account(a, v))
            chk.pack(side="left", padx=10)

            display_id = truncate_text(acc.get("tiktok_id", "N/A"), 18)
            display_email = truncate_text(acc.get("email", "N/A"), 22)

            ctk.CTkLabel(row_frame, text=display_id, width=150, anchor="w").pack(side="left", padx=10)

            # =========================================================
            # VOICE ID RIÊNG CHO TỪNG KÊNH
            # =========================================================
            current_voice = acc.get("voice_id", "")
            inp_voice = ctk.CTkEntry(row_frame, width=250, placeholder_text="VD: uuid hoặc omnivoice")
            if current_voice:
                inp_voice.insert(0, str(current_voice))
            inp_voice.pack(side="left", padx=10)
            inp_voice.bind("<Return>", lambda e, a=acc, ent=inp_voice: self.update_account_voice_id(a, ent))
            inp_voice.bind("<FocusOut>", lambda e, a=acc, ent=inp_voice: self.update_account_voice_id(a, ent))

            # =========================================================
            # ĐỌC BIẾN: Lấy giá trị video_limit_per_run từ acc_data
            # =========================================================
            current_limit = acc.get("video_limit_per_run", 3)
            inp_limit = ctk.CTkEntry(row_frame, width=80, justify="center")
            inp_limit.insert(0, str(current_limit))
            inp_limit.pack(side="left", padx=10)

            # Gắn sự kiện (Dùng lambda truyền đúng account data và widget hiện tại)
            inp_limit.bind("<Return>", lambda e, a=acc, ent=inp_limit: self.update_account_limit(a, ent))
            inp_limit.bind("<FocusOut>", lambda e, a=acc, ent=inp_limit: self.update_account_limit(a, ent))

        self.select_all_var.set(all_active)

    def update_account_limit(self, acc_data, entry_widget):
        """CẬP NHẬT BIẾN: Hàm xử lý lưu giới hạn video một cách an toàn"""
        new_val_str = entry_widget.get().strip()
        current_limit = acc_data.get("video_limit_per_run", 3)

        # 1. Kiểm tra dữ liệu người dùng nhập có hợp lệ không
        try:
            new_limit = int(new_val_str)
            if new_limit < 1:
                new_limit = 1 # Chống nhập số âm
        except ValueError:
            # Nhập sai (vd gõ chữ), khôi phục lại giá trị cũ
            entry_widget.delete(0, 'end')
            entry_widget.insert(0, str(current_limit))
            entry_widget.configure(border_color="red")
            self.parent.after(1000, lambda: entry_widget.configure(border_color=["#979DA2", "#565B5E"]))
            return

        # 2. Format lại ô input cho gọn gàng (vd gõ ' 05 ' -> '5')
        entry_widget.delete(0, 'end')
        entry_widget.insert(0, str(new_limit))

        # 3. Chỉ gọi API lưu khi có sự thay đổi thực sự
        if new_limit != current_limit:
            acc_data["video_limit_per_run"] = new_limit

            if SupabaseAPI.save_account(acc_data):
                # Thành công: Báo viền xanh
                entry_widget.configure(border_color="green")
                self.parent.after(1000, lambda: entry_widget.configure(border_color=["#979DA2", "#565B5E"]))
            else:
                # Thất bại: Báo viền đỏ và lùi lại biến cũ
                acc_data["video_limit_per_run"] = current_limit
                entry_widget.configure(border_color="red")
                self.parent.after(1000, lambda: entry_widget.configure(border_color=["#979DA2", "#565B5E"]))

    def update_account_voice_id(self, acc_data, entry_widget):
        """Lưu Voice ID riêng cho từng account lên Supabase"""
        new_voice = entry_widget.get().strip()
        old_voice = acc_data.get("voice_id", "")
        
        if new_voice != old_voice:
            acc_data["voice_id"] = new_voice
            if SupabaseAPI.save_account(acc_data):
                entry_widget.configure(border_color="green")
                self.parent.after(1500, lambda: entry_widget.configure(border_color=["#979DA2", "#565B5E"]))
            else:
                acc_data["voice_id"] = old_voice
                entry_widget.configure(border_color="red")
                self.parent.after(1500, lambda: entry_widget.configure(border_color=["#979DA2", "#565B5E"]))

    def toggle_single_account(self, acc_data, chk_var):
        new_status = chk_var.get()
        acc_data["active"] = new_status
        SupabaseAPI.save_account(acc_data)

        all_checked = all(var.get() for var in self.account_vars)
        self.select_all_var.set(all_checked)

    def toggle_all_accounts(self):
        new_status = self.select_all_var.get()
        for i, var in enumerate(self.account_vars):
            if var.get() != new_status:
                var.set(new_status)
                acc_data = self.account_data_refs[i]
                acc_data["active"] = new_status
                SupabaseAPI.save_account(acc_data)

    # ================= HÀM XỬ LÝ KHỞI ĐỘNG BOT =================
    def start_bot(self):
        if self.bot_process is not None and self.bot_process.poll() is None:
            return

        self.btn_start_bot.configure(text="⏳ ĐANG CHẠY BOT...", fg_color="orange", state="disabled")
        self.btn_stop_bot.configure(fg_color="red", state="normal")
        self.lbl_bot_status.configure(text="🟢 Trạng thái: Hệ thống đang hoạt động và chờ lịch chạy...", text_color="green")

        def run_script():
            script_path = os.path.join(PROJECT_ROOT, "scheduler_manager.py")
            try:
                if sys.platform == "win32":
                    self.bot_process = subprocess.Popen([sys.executable, script_path], cwd=PROJECT_ROOT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                else:
                    self.bot_process = subprocess.Popen([sys.executable, script_path], cwd=PROJECT_ROOT, preexec_fn=os.setsid)

                self.bot_process.wait()
            except Exception as e:
                print(f"Lỗi khởi chạy: {e}")
            finally:
                self._reset_bot_ui()

        threading.Thread(target=run_script, daemon=True).start()

    def stop_bot(self):
        if self.bot_process is not None:
            self.lbl_bot_status.configure(text="🔴 Trạng thái: Đang tiến hành dừng hệ thống...", text_color="red")
            try:
                if sys.platform == "win32":
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.bot_process.pid)], capture_output=True)
                else:
                    # Gửi tín hiệu SIGKILL cho toàn bộ nhóm tiến trình (process group)
                    import signal
                    os.killpg(os.getpgid(self.bot_process.pid), signal.SIGKILL)
            except Exception as e:
                print(f"Lỗi khi dừng: {e}")
            finally:
                self.bot_process = None
                self._reset_bot_ui()

    def _reset_bot_ui(self):
        self.parent.after(0, self._update_ui_elements_to_default)

    def _update_ui_elements_to_default(self):
        self.btn_start_bot.configure(text="🚀 KHỞI ĐỘNG HỆ THỐNG", fg_color="blue", state="normal")
        self.btn_stop_bot.configure(fg_color="gray", state="disabled")
        self.lbl_bot_status.configure(text="⚪ Trạng thái: Đã dừng hoạt động.", text_color="gray")