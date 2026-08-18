import customtkinter as ctk
import os
import requests
import re
from shared.services.supabase_api import SupabaseAPI

# =====================================================================
# 🛠 CƠ CHẾ DÒ TÌM ĐƯỜNG DẪN GỐC CHUẨN XÁC 100%
# =====================================================================
_current_dir = os.path.abspath(os.path.dirname(__file__))
# Lấy chính xác thư mục mannyAccount (cách channel_manager.py 4 thư mục)
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, "..", "..", "..", ".."))
class ChannelManagerPage:
    def __init__(self, parent_frame):
        self.parent = parent_frame
        self.editing_index = None

        self.title = ctk.CTkLabel(self.parent, text="📺 Quản lý Kênh Clone & Render", font=ctk.CTkFont(size=24, weight="bold"))
        self.title.pack(pady=(0, 10), anchor="w")

        self.accounts = SupabaseAPI.get_all_accounts() or []
        self.acc_ids = [acc.get("tiktok_id") for acc in self.accounts if acc.get("tiktok_id")]

        if not self.acc_ids:
            ctk.CTkLabel(self.parent, text="⚠️ Chưa có tài khoản nào. Vui lòng thêm tài khoản trước.").pack()
            return

        self.sel_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        self.sel_frame.pack(fill="x", pady=5)

        ctk.CTkLabel(self.sel_frame, text="👉 Chọn Tài khoản:").pack(side="left", padx=5)
        self.acc_dropdown = ctk.CTkOptionMenu(self.sel_frame, values=self.acc_ids, command=self.on_account_select)
        self.acc_dropdown.pack(side="left", padx=10)

        self.lbl_acc_limit = ctk.CTkLabel(self.sel_frame, text="Giới hạn tối đa/lần chạy: --", text_color="orange")
        self.lbl_acc_limit.pack(side="left", padx=20)

        self.current_account = None

        self.form_frame = ctk.CTkFrame(self.parent)
        self.form_frame.pack(fill="x", pady=10)

        row1 = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(row1, text="🔗 Link Nguồn:").pack(side="left", padx=5)
        self.inp_url = ctk.CTkEntry(row1, width=300, placeholder_text="https://tiktok.com/@...")
        self.inp_url.pack(side="left", padx=5)

        ctk.CTkLabel(row1, text="Số video lấy từ kênh này:").pack(side="left", padx=5)
        self.inp_limit = ctk.CTkEntry(row1, width=50)
        self.inp_limit.pack(side="left", padx=5)
        self.inp_limit.insert(0, "3")

        ctk.CTkLabel(row1, text="Chế độ Edit:").pack(side="left", padx=(15, 5))
        self.inp_edit_mode = ctk.CTkOptionMenu(row1, values=["Có Frame Full (Tiktok)", "Frame Intro + Gốc (Giống FB)"], width=200)
        self.inp_edit_mode.pack(side="left", padx=5)

        self.tabs = ctk.CTkTabview(self.form_frame, height=220)
        self.tabs.pack(fill="x", padx=10, pady=5)
        self.tabs.add("Vid Intro")
        self.tabs.add("Vid Content")
        self.tabs.add("Chữ Intro")
        self.tabs.add("Chữ Content")
        self.tabs.add("Assets")

        # ================= KHÔI PHỤC CÁC Ô ĐIỀU CHỈNH =================
        row1_intro = ctk.CTkFrame(self.tabs.tab("Vid Intro"), fg_color="transparent"); row1_intro.pack(fill="x")
        row2_intro = ctk.CTkFrame(self.tabs.tab("Vid Intro"), fg_color="transparent"); row2_intro.pack(fill="x", pady=(5,0))
        
        self.inp_intro_st = self._add_field(row1_intro, "Start (s):", "2.0")
        self.inp_intro_en = self._add_field(row1_intro, "End (s):", "5.0")
        self.inp_intro_zm = self._add_field(row1_intro, "Zoom:", "1.0")
        self.inp_intro_x  = self._add_field(row1_intro, "X Offset:", "0")
        self.inp_intro_y  = self._add_field(row1_intro, "Y Offset:", "100")
        
        self.inp_intro_logo_w = self._add_field(row2_intro, "Logo W %:", "0.14")
        self.inp_intro_logo_x = self._add_field(row2_intro, "Logo X:", "main_w-overlay_w-30")
        self.inp_intro_logo_y = self._add_field(row2_intro, "Logo Y:", "30")

        row1_cont = ctk.CTkFrame(self.tabs.tab("Vid Content"), fg_color="transparent"); row1_cont.pack(fill="x")
        row2_cont = ctk.CTkFrame(self.tabs.tab("Vid Content"), fg_color="transparent"); row2_cont.pack(fill="x", pady=(5,0))

        self.inp_cont_st = self._add_field(row1_cont, "Start (s):", "10.0")
        self.inp_cont_en = self._add_field(row1_cont, "End (s):", "auto")
        self.inp_cont_zm = self._add_field(row1_cont, "Zoom:", "1.05")
        self.inp_cont_x  = self._add_field(row1_cont, "X Offset:", "0")
        self.inp_cont_y  = self._add_field(row1_cont, "Y Offset:", "-11")

        self.inp_cont_logo_w = self._add_field(row2_cont, "Logo W %:", "0.14")
        self.inp_cont_logo_x = self._add_field(row2_cont, "Logo X:", "main_w-overlay_w-30")
        self.inp_cont_logo_y = self._add_field(row2_cont, "Logo Y:", "30")

        self.inp_txt_in_y1   = self._add_field(self.tabs.tab("Chữ Intro"), "Y Start:", "0.73")
        self.inp_txt_in_y2   = self._add_field(self.tabs.tab("Chữ Intro"), "Y End:", "0.83")
        self.inp_txt_in_w    = self._add_field(self.tabs.tab("Chữ Intro"), "Width %:", "0.65")
        self.inp_txt_in_sz   = self._add_field(self.tabs.tab("Chữ Intro"), "Size:", "45")
        self.inp_txt_in_clr  = self._add_field(self.tabs.tab("Chữ Intro"), "Màu (Hex):", "#ffffff")
        self.inp_txt_in_strk = self._add_field(self.tabs.tab("Chữ Intro"), "Stroke:", "0")

        self.inp_txt_co_y1   = self._add_field(self.tabs.tab("Chữ Content"), "Y Start:", "0.73")
        self.inp_txt_co_y2   = self._add_field(self.tabs.tab("Chữ Content"), "Y End:", "0.83")
        self.inp_txt_co_w    = self._add_field(self.tabs.tab("Chữ Content"), "Width %:", "0.65")
        self.inp_txt_co_sz   = self._add_field(self.tabs.tab("Chữ Content"), "Size:", "45")
        self.inp_txt_co_clr  = self._add_field(self.tabs.tab("Chữ Content"), "Màu (Hex):", "#ffffff")
        self.inp_txt_co_strk = self._add_field(self.tabs.tab("Chữ Content"), "Stroke:", "0")

        # ================= DROPDOWN TỪ ASSETS =================
        self.frame_list = self._load_local_only("frame")
        self.font_list = self._load_local_only("font")
        self.logo_list = self._load_local_only("logo")

        row1_assets = ctk.CTkFrame(self.tabs.tab("Assets"), fg_color="transparent")
        row1_assets.pack(fill="x", pady=2)
        row2_assets = ctk.CTkFrame(self.tabs.tab("Assets"), fg_color="transparent")
        row2_assets.pack(fill="x", pady=2)
        
        self.inp_frame_in = self._add_dropdown(row1_assets, "Khung Intro:", self.frame_list)
        self.inp_frame_co = self._add_dropdown(row1_assets, "Khung Content:", self.frame_list)
        self.inp_font     = self._add_dropdown(row1_assets, "Tên Font:", self.font_list, default="Inter_18pt-Bold.ttf")
        
        self.inp_logo_in  = self._add_dropdown(row2_assets, "Logo Intro:", self.logo_list)
        self.inp_logo_co  = self._add_dropdown(row2_assets, "Logo Content:", self.logo_list)
        
        self.btn_refresh = ctk.CTkButton(row2_assets, text="🔃 ĐỒNG BỘ CLOUD", width=120, fg_color="#D97706", hover_color="#B45309", command=self.refresh_files)
        self.btn_refresh.pack(side="left", padx=15, pady=5)

        self.action_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.action_frame.pack(pady=10)
        self.btn_save_chn = ctk.CTkButton(self.action_frame, text="➕ THÊM KÊNH MỚI", command=self.save_channel, fg_color="green")
        self.btn_save_chn.pack(side="left", padx=5)
        self.btn_cancel_edit = ctk.CTkButton(self.action_frame, text="❌ HỦY SỬA", command=self.cancel_edit, fg_color="gray")

        self.lbl_status = ctk.CTkLabel(self.form_frame, text="")
        self.lbl_status.pack()

        header_list = ctk.CTkFrame(self.parent, fg_color="transparent")
        header_list.pack(fill="x", pady=(10, 0))

        ctk.CTkLabel(header_list, text="📋 Danh sách Kênh đang theo dõi:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.lbl_total_expected = ctk.CTkLabel(header_list, text="📊 Tổng video dự kiến: 0", font=ctk.CTkFont(weight="bold"), text_color="cyan")
        self.lbl_total_expected.pack(side="right", padx=10)

        self.scroll_frame = ctk.CTkScrollableFrame(self.parent, width=800, height=200)
        self.scroll_frame.pack(fill="both", expand=True, pady=5)

        self.on_account_select(self.acc_ids[0])

    # ================= LOGIC ĐỒNG BỘ CLOUD =================
    def refresh_files(self):
        print("\n" + "="*50)
        print("🚀 BẮT ĐẦU ĐỒNG BỘ FILE TỪ SUPABASE STORAGE")
        print("="*50)
        self.btn_refresh.configure(state="disabled", text="⏳ Đang quét...")
        self.lbl_status.configure(text="🔄 Đang tải danh sách file từ Supabase...", text_color="blue")
        self.parent.update()

        api_file = os.path.join(PROJECT_ROOT, "shared", "services", "supabase_api.py")
        supa_url, supa_key = None, None
        try:
            with open(api_file, "r", encoding="utf-8") as f:
                content = f.read()
                supa_url = re.search(r'SUPABASE_URL\s*=\s*["\']([^"\']+)["\']', content).group(1)
                supa_key = re.search(r'SUPABASE_KEY\s*=\s*["\']([^"\']+)["\']', content).group(1)
        except: pass

        def sync_folder(folder_name):
            cloud_files = set()
            local_dir = os.path.join(PROJECT_ROOT, "assets", folder_name)
            os.makedirs(local_dir, exist_ok=True)

            if not supa_url or not supa_key: return set(os.listdir(local_dir))

            try:
                api_url = f"{supa_url}/storage/v1/object/list/assets"
                headers = {"apikey": supa_key, "Authorization": f"Bearer {supa_key}", "Content-Type": "application/json"}
                payload = {"prefix": f"{folder_name}/", "limit": 100}
                res = requests.post(api_url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    for item in data:
                        name = item.get('name', '')
                        clean_name = name.split('/')[-1] if '/' in name else name
                        if clean_name and clean_name != '.emptyFolderPlaceholder' and clean_name != folder_name:
                            cloud_files.add(clean_name)
                else: return set(os.listdir(local_dir))
            except Exception as e: return set(os.listdir(local_dir))

            if not cloud_files: return set(os.listdir(local_dir))

            local_files = set(os.listdir(local_dir))

            for f in cloud_files - local_files:
                try: SupabaseAPI.download_asset("assets", folder_name, local_dir, f)
                except: pass

            # Đã xóa đoạn code tự động xóa file local để tránh mất dữ liệu của người dùng

            return cloud_files.union(local_files)

        new_frames = sync_folder("frame")
        new_fonts = sync_folder("font")
        new_logos = sync_folder("logo")

        self.frame_list = [""] + sorted(list(new_frames), key=lambda x: x.lower())
        self.font_list = [""] + sorted(list(new_fonts), key=lambda x: x.lower())
        self.logo_list = [""] + sorted(list(new_logos), key=lambda x: x.lower())

        self.inp_frame_in.configure(values=self.frame_list)
        self.inp_frame_co.configure(values=self.frame_list)
        self.inp_font.configure(values=self.font_list)
        self.inp_logo_in.configure(values=self.logo_list)
        self.inp_logo_co.configure(values=self.logo_list)

        self.lbl_status.configure(text=f"✅ Đã đồng bộ xong! Kiểm tra danh sách trong Terminal.", text_color="green")
        self.btn_refresh.configure(state="normal", text="🔃 ĐỒNG BỘ CLOUD")

    def _load_local_only(self, folder_name):
        local_dir = os.path.join(PROJECT_ROOT, "assets", folder_name)
        if not os.path.exists(local_dir): return [""]
        files = [f for f in os.listdir(local_dir) if os.path.isfile(os.path.join(local_dir, f)) and not f.startswith('.')]
        return [""] + sorted(files, key=lambda x: x.lower())

    # ================= HÀM HỖ TRỢ GIAO DIỆN =================
    def _add_field(self, parent, label_text, default_val):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(side="left", padx=8, pady=5)
        ctk.CTkLabel(frame, text=label_text).pack(anchor="w")
        inp = ctk.CTkEntry(frame, width=95)
        inp.pack()
        inp.insert(0, default_val)
        return inp

    def _add_dropdown(self, parent, label, values, default=""):
        f = ctk.CTkFrame(parent, fg_color="transparent"); f.pack(side="left", padx=8, pady=5)
        ctk.CTkLabel(f, text=label).pack(anchor="w")
        inp = ctk.CTkOptionMenu(f, width=150, values=values); inp.pack()
        if default in values: inp.set(default)
        return inp

    def _set_val(self, widget, val):
        s = str(val) if val is not None else ""
        if isinstance(widget, ctk.CTkEntry):
            widget.configure(state="normal")
            widget.delete(0, 'end')
            widget.insert(0, s)
        elif isinstance(widget, ctk.CTkOptionMenu):
            v = list(widget.cget("values"))
            if s and s not in v:
                v.append(s)
                widget.configure(values=v)
            widget.set(s)

    def on_account_select(self, selected_id):
        self.current_account = next((acc for acc in self.accounts if acc["tiktok_id"] == selected_id), None)
        if self.current_account:
            limit_run = self.current_account.get("video_limit_per_run", "N/A")
            self.lbl_acc_limit.configure(text=f"Giới hạn tối đa/lần chạy: {limit_run}")

        self.lbl_status.configure(text="")
        self.cancel_edit()
        self.load_channels()

    def load_channels(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not self.current_account: return
        channels = self.current_account.get("channels", [])
        total_limit = 0

        if not channels:
            ctk.CTkLabel(self.scroll_frame, text="Chưa có kênh nào.").pack(pady=10)
            self.lbl_total_expected.configure(text="📊 Tổng video dự kiến: 0", text_color="cyan")
            return

        for i, chn in enumerate(channels):
            c_limit = chn.get('limit', 0)
            total_limit += c_limit

            row_frame = ctk.CTkFrame(self.scroll_frame)
            row_frame.pack(fill="x", pady=2)
            ctk.CTkLabel(row_frame, text=chn.get("url", "N/A"), width=400, anchor="w").pack(side="left", padx=10)
            ctk.CTkLabel(row_frame, text=f"Limit: {c_limit}", width=100).pack(side="left", padx=10)

            btn_del = ctk.CTkButton(row_frame, text="🗑️", width=30, fg_color="red", command=lambda idx=i: self.delete_channel(idx))
            btn_del.pack(side="right", padx=10)
            btn_edit = ctk.CTkButton(row_frame, text="✏️", width=30, command=lambda idx=i, data=chn: self.edit_channel(idx, data))
            btn_edit.pack(side="right", padx=5)

        self.lbl_total_expected.configure(text=f"📊 Tổng video dự kiến: {total_limit}")
        acc_max = self.current_account.get("video_limit_per_run", 999)
        self.lbl_total_expected.configure(text_color="red" if total_limit > acc_max else "cyan")

    # ================= KHÔI PHỤC HÀM EDIT HOÀN CHỈNH =================
    def edit_channel(self, index, chn_data):
        self.editing_index = index
        self.lbl_status.configure(text="✏️ Chế độ Sửa (Đã khóa chỉnh sửa Link)", text_color="orange")
        self.btn_cancel_edit.pack(side="left", padx=5)
        self.btn_save_chn.configure(text="💾 CẬP NHẬT KÊNH", fg_color="blue")

        rs = chn_data.get("render_settings", {})
        ts, cs = rs.get("title_settings", {}), rs.get("content_settings", {})
        txt_in, txt_co = rs.get("text_overlay_settings", {}), rs.get("text_content_settings", {})
        ast = rs.get("assets", {})

        self._set_val(self.inp_url, chn_data.get("url", ""))
        self.inp_url.configure(state="disabled")
        self._set_val(self.inp_limit, chn_data.get("limit", 3))
        self._set_val(self.inp_edit_mode, rs.get("edit_mode", "Có Frame Full (Tiktok)"))

        self._set_val(self.inp_intro_st, ts.get("source_start", 2.0))
        self._set_val(self.inp_intro_en, ts.get("source_end", 5.0))
        self._set_val(self.inp_intro_zm, ts.get("zoom_factor", 1.0))
        self._set_val(self.inp_intro_x, ts.get("manual_x_offset", 0))
        self._set_val(self.inp_intro_y, ts.get("manual_y_offset", 100))

        self._set_val(self.inp_cont_st, cs.get("source_start", 10.0))
        self._set_val(self.inp_cont_en, cs.get("source_end", "auto"))
        self._set_val(self.inp_cont_zm, cs.get("zoom_factor", 1.05))
        self._set_val(self.inp_cont_x, cs.get("manual_x_offset", 0))
        self._set_val(self.inp_cont_y, cs.get("manual_y_offset", -11))

        self._set_val(self.inp_txt_in_y1, txt_in.get("box_y_start", 0.73))
        self._set_val(self.inp_txt_in_y2, txt_in.get("box_y_end", 0.83))
        self._set_val(self.inp_txt_in_w, txt_in.get("box_width_percentage", 0.65))
        self._set_val(self.inp_txt_in_sz, txt_in.get("font_size", 45))
        self._set_val(self.inp_txt_in_clr, txt_in.get("text_color", "#ffffff"))
        self._set_val(self.inp_txt_in_strk, txt_in.get("stroke_width", 0))

        self._set_val(self.inp_txt_co_y1, txt_co.get("box_y_start", 0.73))
        self._set_val(self.inp_txt_co_y2, txt_co.get("box_y_end", 0.83))
        self._set_val(self.inp_txt_co_w, txt_co.get("box_width_percentage", 0.65))
        self._set_val(self.inp_txt_co_sz, txt_co.get("font_size", 45))
        self._set_val(self.inp_txt_co_clr, txt_co.get("text_color", "#ffffff"))
        self._set_val(self.inp_txt_co_strk, txt_co.get("stroke_width", 0))

        self._set_val(self.inp_frame_in, ast.get("title_frame_filename", ""))
        self._set_val(self.inp_frame_co, ast.get("content_frame_filename", ""))
        self._set_val(self.inp_font, txt_in.get("font_filename", "Inter_18pt-Bold.ttf"))
        
        old_logo = ast.get("logo_filename", "")
        self._set_val(self.inp_logo_in, ast.get("title_logo_filename", old_logo))
        self._set_val(self.inp_logo_co, ast.get("content_logo_filename", old_logo))
        
        self._set_val(self.inp_intro_logo_w, ast.get("title_logo_width_percentage", 0.14))
        self._set_val(self.inp_intro_logo_x, ast.get("title_logo_x", "main_w-overlay_w-30"))
        self._set_val(self.inp_intro_logo_y, ast.get("title_logo_y", "30"))

        self._set_val(self.inp_cont_logo_w, ast.get("content_logo_width_percentage", 0.14))
        self._set_val(self.inp_cont_logo_x, ast.get("content_logo_x", "main_w-overlay_w-30"))
        self._set_val(self.inp_cont_logo_y, ast.get("content_logo_y", "30"))

    # ================= KHÔI PHỤC HÀM SAVE HOÀN CHỈNH =================
    # ================= KHÔI PHỤC HÀM SAVE CHUẨN CÓ AUTO-FILL =================
    def save_channel(self):
        self.inp_url.configure(state="normal")
        url = self.inp_url.get().strip()

        if not url or not self.current_account:
            self.lbl_status.configure(text="❌ Phải điền Link nguồn!", text_color="red")
            return

        # ---------------------------------------------------------------------
        # CÁC HÀM "BẢO KÊ": NẾU RỖNG HOẶC LỖI -> TỰ ĐỘNG ĐIỀN SỐ CỨNG VÀO Ô
        # ---------------------------------------------------------------------
        def get_int(widget, default_val):
            val = widget.get().strip()
            if not val: # Nếu để trống
                widget.delete(0, 'end'); widget.insert(0, str(default_val))
                return default_val
            try: return int(val)
            except: # Nếu nhập linh tinh
                widget.delete(0, 'end'); widget.insert(0, str(default_val))
                return default_val

        def get_float(widget, default_val):
            val = widget.get().strip()
            if not val:
                widget.delete(0, 'end'); widget.insert(0, str(default_val))
                return default_val
            try: return float(val)
            except:
                widget.delete(0, 'end'); widget.insert(0, str(default_val))
                return default_val

        def get_offset(widget, default_val):
            val = widget.get().strip()
            if not val:
                widget.delete(0, 'end'); widget.insert(0, str(default_val))
                return default_val
            if val.lower() == "center": return "center" # Hỗ trợ chữ center
            try: return int(val)
            except:
                widget.delete(0, 'end'); widget.insert(0, str(default_val))
                return default_val

        def get_end_time(widget, default_val):
            val = widget.get().strip()
            if not val:
                widget.delete(0, 'end'); widget.insert(0, str(default_val))
                return default_val
            if val.lower() == "auto": return "auto"
            try: return float(val)
            except:
                widget.delete(0, 'end'); widget.insert(0, str(default_val))
                return default_val

        def get_color(widget, default_val):
            val = widget.get().strip()
            if not val or not val.startswith("#"):
                widget.delete(0, 'end'); widget.insert(0, default_val)
                return default_val
            return val
            
        def get_expression(widget, default_val):
            val = widget.get().strip()
            if not val:
                widget.delete(0, 'end'); widget.insert(0, str(default_val))
                return default_val
            return val

        # BẮT ĐẦU ĐỌC DỮ LIỆU (CÓ ĐIỀN CỨNG MẶC ĐỊNH NẾU RỖNG)
        new_chn = {
            "url": url,
            "limit": get_int(self.inp_limit, 3),
            "render_settings": {
                "edit_mode": self.inp_edit_mode.get(),
                "title_settings": {
                    "source_start": get_float(self.inp_intro_st, 2.0),
                    "source_end": get_end_time(self.inp_intro_en, 5.0),
                    "zoom_factor": get_float(self.inp_intro_zm, 1.0),
                    "manual_x_offset": get_offset(self.inp_intro_x, 0),
                    "manual_y_offset": get_offset(self.inp_intro_y, 100)
                },
                "content_settings": {
                    "source_start": get_float(self.inp_cont_st, 10.0),
                    "source_end": get_end_time(self.inp_cont_en, "auto"),
                    "zoom_factor": get_float(self.inp_cont_zm, 1.05),
                    "manual_x_offset": get_offset(self.inp_cont_x, 0),
                    "manual_y_offset": get_offset(self.inp_cont_y, -11)
                },
                "text_overlay_settings": {
                    "text_color": get_color(self.inp_txt_in_clr, "#ffffff"),
                    "stroke_width": get_int(self.inp_txt_in_strk, 0),
                    "font_size": get_int(self.inp_txt_in_sz, 45),
                    "box_y_start": get_float(self.inp_txt_in_y1, 0.73),
                    "box_y_end": get_float(self.inp_txt_in_y2, 0.83),
                    "box_width_percentage": get_float(self.inp_txt_in_w, 0.65),
                    "font_filename": self.inp_font.get() or "Inter_18pt-Bold.ttf" # Cứng font
                },
                "text_content_settings": {
                    "text_color": get_color(self.inp_txt_co_clr, "#ffffff"),
                    "stroke_width": get_int(self.inp_txt_co_strk, 0),
                    "font_size": get_int(self.inp_txt_co_sz, 45),
                    "box_y_start": get_float(self.inp_txt_co_y1, 0.73),
                    "box_y_end": get_float(self.inp_txt_co_y2, 0.83),
                    "box_width_percentage": get_float(self.inp_txt_co_w, 0.65),
                    "font_filename": self.inp_font.get() or "Inter_18pt-Bold.ttf" # Cứng font
                },
                "assets": {
                    "title_frame_filename": self.inp_frame_in.get(),
                    "content_frame_filename": self.inp_frame_co.get(),
                    "title_logo_filename": self.inp_logo_in.get(),
                    "content_logo_filename": self.inp_logo_co.get(),
                    "title_logo_width_percentage": get_float(self.inp_intro_logo_w, 0.14),
                    "title_logo_x": get_expression(self.inp_intro_logo_x, "main_w-overlay_w-30"),
                    "title_logo_y": get_expression(self.inp_intro_logo_y, "30"),
                    "content_logo_width_percentage": get_float(self.inp_cont_logo_w, 0.14),
                    "content_logo_x": get_expression(self.inp_cont_logo_x, "main_w-overlay_w-30"),
                    "content_logo_y": get_expression(self.inp_cont_logo_y, "30")
                }
            }
        }

        # Lưu vào Database
        channels = self.current_account.get("channels", [])
        is_new_channel = False

        if self.editing_index is not None:
            channels[self.editing_index] = new_chn
        else:
            found = False
            for i, chn in enumerate(channels):
                if chn.get("url") == url:
                    channels[i] = new_chn
                    found = True
                    break
            if not found:
                channels.append(new_chn)
                is_new_channel = True

        self.current_account["channels"] = channels
        tiktok_id = self.current_account.get("tiktok_id")

        if is_new_channel:
            SupabaseAPI.update_channel_videos_db(tiktok_id, url, [])

        if SupabaseAPI.save_account(self.current_account):
            self.lbl_status.configure(text="✅ Lưu thành công!", text_color="green")
            self.cancel_edit()
            self.load_channels()

    def cancel_edit(self):
        self.editing_index = None
        self.btn_cancel_edit.pack_forget()
        self.btn_save_chn.configure(text="➕ THÊM KÊNH MỚI", fg_color="green")
        self.inp_url.configure(state="normal")
        self._set_val(self.inp_url, "")
        self.lbl_status.configure(text="")

    def delete_channel(self, index):
        if self.current_account:
            channel_to_delete = self.current_account["channels"][index]
            tiktok_id = self.current_account.get("tiktok_id")
            channel_url = channel_to_delete.get("url")
            self.current_account["channels"].pop(index)
            if tiktok_id and channel_url:
                SupabaseAPI.delete_channel_videos_db(tiktok_id, channel_url)
            if SupabaseAPI.save_account(self.current_account):
                self.load_channels()