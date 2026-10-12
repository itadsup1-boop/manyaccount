import os
import sys
import json
import customtkinter as ctk
import subprocess
import threading

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(APP_DIR))
sys.path.insert(0, PROJECT_ROOT)

from shared.services.supabase_api import SupabaseAPI

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(APP_DIR, "channels_config.json")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TeleBotConfigApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Cấu hình Kênh TeleBot")
        self.geometry("900x750")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.channels = self.load_config()
        self.bot_process = None

        self._build_ui()
        self._refresh_list()

    def load_config(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return {}

    def save_config(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.channels, f, ensure_ascii=False, indent=4)

    def _build_form(self, parent, mode="add"):
        widgets = {}
        row_offset = 0
        if mode == "edit":
            ctk.CTkLabel(parent, text="Chọn kênh để sửa:").grid(row=0, column=0, padx=10, pady=5, sticky="e")
            widgets["select_id_var"] = ctk.StringVar(value="-- Chọn kênh --")
            channel_ids = ["-- Chọn kênh --"] + list(self.channels.keys())
            
            def on_select(val):
                if val == "-- Chọn kênh --" or val not in self.channels: return
                c_info = self.channels[val]
                widgets["name"].delete(0, "end")
                widgets["name"].insert(0, c_info.get("name", ""))
                widgets["id"].configure(state="normal")
                widgets["id"].delete(0, "end")
                widgets["id"].insert(0, val)
                widgets["id"].configure(state="disabled")
                
                tf = c_info.get("title_frame_path", "-- Trống --")
                widgets["title_frame_var"].set(tf if tf in self.frames_list else "-- Trống --")
                
                cf = c_info.get("content_frame_path", "-- Trống --")
                widgets["content_frame_var"].set(cf if cf in self.frames_list else "-- Trống --")
                
                lg = c_info.get("logo_path", "-- Trống --")
                widgets["logo_var"].set(lg if lg in self.logos_list else "-- Trống --")
                
                ft = c_info.get("font_path", "-- Trống --")
                widgets["font_var"].set(ft if ft in self.fonts_list else "-- Trống --")
                
                widgets["sheet_var"].set(c_info.get("sheet_type", "tong"))
                
                widgets["text_y1"].delete(0, "end")
                widgets["text_y1"].insert(0, c_info.get("text_y1", "0.64"))
                
                widgets["text_size"].delete(0, "end")
                widgets["text_size"].insert(0, c_info.get("text_size", "50"))
                
                widgets["text_color"].delete(0, "end")
                widgets["text_color"].insert(0, c_info.get("text_color", "white"))
                
                if "text_x" in widgets:
                    widgets["text_x"].delete(0, "end")
                    widgets["text_x"].insert(0, c_info.get("text_x", "65"))
                
            widgets["opt_select"] = ctk.CTkOptionMenu(parent, variable=widgets["select_id_var"], values=channel_ids, width=250, command=on_select)
            widgets["opt_select"].grid(row=0, column=1, padx=10, pady=5, sticky="w")
            row_offset = 1

        ctk.CTkLabel(parent, text="Tên kênh:").grid(row=row_offset, column=0, padx=10, pady=5, sticky="e")
        widgets["name"] = ctk.CTkEntry(parent, width=250)
        widgets["name"].grid(row=row_offset, column=1, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(parent, text="ID Kênh (vd: adsup1):").grid(row=row_offset, column=2, padx=10, pady=5, sticky="e")
        widgets["id"] = ctk.CTkEntry(parent, width=150)
        widgets["id"].grid(row=row_offset, column=3, padx=10, pady=5, sticky="w")
        if mode == "edit":
            widgets["id"].configure(state="disabled")

        widgets["title_frame_var"] = ctk.StringVar(value="-- Trống --")
        ctk.CTkLabel(parent, text="Frame Title (Supabase):").grid(row=row_offset+1, column=0, padx=10, pady=5, sticky="e")
        ctk.CTkOptionMenu(parent, variable=widgets["title_frame_var"], values=self.frames_list, width=250).grid(row=row_offset+1, column=1, padx=10, pady=5, sticky="w")

        widgets["content_frame_var"] = ctk.StringVar(value="-- Trống --")
        ctk.CTkLabel(parent, text="Frame Content:").grid(row=row_offset+2, column=0, padx=10, pady=5, sticky="e")
        ctk.CTkOptionMenu(parent, variable=widgets["content_frame_var"], values=self.frames_list, width=250).grid(row=row_offset+2, column=1, padx=10, pady=5, sticky="w")

        widgets["logo_var"] = ctk.StringVar(value="-- Trống --")
        ctk.CTkLabel(parent, text="Logo:").grid(row=row_offset+3, column=0, padx=10, pady=5, sticky="e")
        ctk.CTkOptionMenu(parent, variable=widgets["logo_var"], values=self.logos_list, width=250).grid(row=row_offset+3, column=1, padx=10, pady=5, sticky="w")

        widgets["font_var"] = ctk.StringVar(value="-- Trống --")
        ctk.CTkLabel(parent, text="Font:").grid(row=row_offset+4, column=0, padx=10, pady=5, sticky="e")
        ctk.CTkOptionMenu(parent, variable=widgets["font_var"], values=self.fonts_list, width=250).grid(row=row_offset+4, column=1, padx=10, pady=5, sticky="w")

        widgets["sheet_var"] = ctk.StringVar(value="tong")
        ctk.CTkLabel(parent, text="Google Sheet:").grid(row=row_offset+5, column=0, padx=10, pady=5, sticky="e")
        ctk.CTkOptionMenu(parent, variable=widgets["sheet_var"], values=["tong", "facebook"]).grid(row=row_offset+5, column=1, padx=10, pady=5, sticky="w")

        widgets["text_y1"] = ctk.CTkEntry(parent, width=150)
        widgets["text_y1"].insert(0, "0.64")
        ctk.CTkLabel(parent, text="Y Start (0.64):").grid(row=row_offset+6, column=0, padx=10, pady=5, sticky="e")
        widgets["text_y1"].grid(row=row_offset+6, column=1, padx=10, pady=5, sticky="w")

        widgets["text_size"] = ctk.CTkEntry(parent, width=150)
        widgets["text_size"].insert(0, "50")
        ctk.CTkLabel(parent, text="Text Size:").grid(row=row_offset+6, column=2, padx=10, pady=5, sticky="e")
        widgets["text_size"].grid(row=row_offset+6, column=3, padx=10, pady=5, sticky="w")

        widgets["text_color"] = ctk.CTkEntry(parent, width=150)
        widgets["text_color"].insert(0, "white")
        ctk.CTkLabel(parent, text="Màu chữ:").grid(row=row_offset+7, column=0, padx=10, pady=5, sticky="e")
        widgets["text_color"].grid(row=row_offset+7, column=1, padx=10, pady=5, sticky="w")

        widgets["text_x"] = ctk.CTkEntry(parent, width=150)
        widgets["text_x"].insert(0, "65")
        ctk.CTkLabel(parent, text="X Start (65):").grid(row=row_offset+7, column=2, padx=10, pady=5, sticky="e")
        widgets["text_x"].grid(row=row_offset+7, column=3, padx=10, pady=5, sticky="w")

        def open_drag_drop():
            try: current_y = float(widgets["text_y1"].get())
            except: current_y = 0.64
            
            try: current_x = int(widgets["text_x"].get())
            except: current_x = 65
            
            try: current_size = int(widgets["text_size"].get())
            except: current_size = 50
                
            top = ctk.CTkToplevel(self)
            top.title("Kéo thả vị trí Text")
            top.attributes('-topmost', True)
            
            w, h = 360, 640
            scale = 1080 / w
            top.geometry(f"{w+40}x{h+100}")
            
            import tkinter as tk
            from PIL import Image, ImageTk
            import threading
            
            canvas = tk.Canvas(top, width=w, height=h, bg="black", highlightthickness=0)
            canvas.pack(pady=10)
            
            # Khung chữ mẫu
            box_id = canvas.create_rectangle(0, 0, 0, 0, fill="gray", outline="white")
            text_id = canvas.create_text(0, 0, text="Kéo thả!\nCuộn chuột để To/Nhỏ", fill="white", font=("Arial", 12, "bold"))
            bg_id = canvas.create_image(0, 0, anchor="nw")
            canvas.tag_lower(bg_id)
            
            # Tải ảnh nền frame
            def load_bg():
                frame_name = widgets["title_frame_var"].get()
                if frame_name == "-- Trống --": frame_name = widgets["content_frame_var"].get()
                if frame_name != "-- Trống --":
                    temp_dir = os.path.join(APP_DIR, "temp_frames")
                    os.makedirs(temp_dir, exist_ok=True)
                    SupabaseAPI.download_asset("assets", "frame", temp_dir, frame_name)
                    local_path = os.path.join(temp_dir, frame_name)
                    if os.path.exists(local_path):
                        img = Image.open(local_path).resize((w, h))
                        photo = ImageTk.PhotoImage(img)
                        canvas.image = photo
                        canvas.itemconfig(bg_id, image=photo)
            
            threading.Thread(target=load_bg, daemon=True).start()
            
            # Trạng thái hiện tại
            state = {"x": current_x / scale, "y": current_y * h, "size": current_size / scale}
            
            def draw():
                # x_start là góc trái trên, y_start cũng vậy. Text canh giữa box.
                bx, by, bsize = state["x"], state["y"], max(10, state["size"])
                # Giả lập hộp text rộng 200px
                bw = 250
                canvas.coords(box_id, bx, by, bx + bw, by + bsize*2.5)
                canvas.coords(text_id, bx + bw/2, by + bsize*1.25)
                canvas.itemconfig(text_id, font=("Arial", int(bsize), "bold"))
                
                # Cập nhật ô nhập liệu
                widgets["text_x"].delete(0, "end")
                widgets["text_x"].insert(0, str(int(bx * scale)))
                
                widgets["text_y1"].delete(0, "end")
                widgets["text_y1"].insert(0, str(round(by / h, 3)))
                
                widgets["text_size"].delete(0, "end")
                widgets["text_size"].insert(0, str(int(bsize * scale)))
                
            draw()
            
            def on_drag(event):
                # Ràng buộc không cho kéo lố ra ngoài viền
                y = min(max(0, event.y), h)
                x = min(max(0, event.x), w)
                state["y"] = y
                state["x"] = x
                draw()
                
            def on_scroll(event):
                if event.delta > 0 or event.num == 4:
                    state["size"] += 2
                elif event.delta < 0 or event.num == 5:
                    state["size"] -= 2
                draw()
                
            canvas.tag_bind(box_id, "<B1-Motion>", on_drag)
            canvas.tag_bind(text_id, "<B1-Motion>", on_drag)
            canvas.bind("<MouseWheel>", on_scroll)
            canvas.bind("<Button-4>", on_scroll)
            canvas.bind("<Button-5>", on_scroll)
            
            ctk.CTkLabel(top, text="Kéo thả hộp màu xám để di chuyển (X, Y).\nCuộn chuột lên/xuống để Phóng to/Thu nhỏ chữ.", text_color="orange").pack()
            
            def close_and_apply():
                top.destroy()
                
            ctk.CTkButton(top, text="✅ Áp dụng & Đóng", command=close_and_apply, fg_color="green", hover_color="darkgreen", height=40).pack(pady=10)

        ctk.CTkButton(parent, text="🖱️ Căn chỉnh (Kéo Thả/Zoom)", command=open_drag_drop, width=150, fg_color="purple", hover_color="darkmagenta").grid(row=row_offset+8, column=0, columnspan=4, padx=10, pady=5)

        def submit():
            c_id = widgets["id"].get().strip()
            c_name = widgets["name"].get().strip()
            if not c_id or not c_name:
                self.log("❌ Lỗi: ID Kênh và Tên Kênh không được để trống!")
                return
            if mode == "add" and c_id in self.channels:
                self.log(f"❌ Lỗi: ID Kênh '{c_id}' đã tồn tại! Hãy dùng tab Sửa.")
                return

            self.channels[c_id] = {
                "name": c_name,
                "title_frame_path": widgets["title_frame_var"].get().strip(),
                "content_frame_path": widgets["content_frame_var"].get().strip(),
                "logo_path": widgets["logo_var"].get().strip(),
                "font_path": widgets["font_var"].get().strip(),
                "sheet_type": widgets["sheet_var"].get(),
                "text_y1": widgets["text_y1"].get().strip(),
                "text_size": widgets["text_size"].get().strip(),
                "text_color": widgets["text_color"].get().strip(),
                "text_x": widgets["text_x"].get().strip()
            }
            self.save_config()
            self.log(f"✅ Đã lưu kênh: {c_name} (ID: {c_id})")
            
            self._refresh_list()
            if hasattr(self, 'edit_widgets'):
                channel_ids = ["-- Chọn kênh --"] + list(self.channels.keys())
                self.edit_widgets["opt_select"].configure(values=channel_ids)
                
            if mode == "add":
                widgets["id"].delete(0, "end")
                widgets["name"].delete(0, "end")

        btn_text = "💾 Lưu Kênh Mới" if mode == "add" else "💾 Cập nhật Kênh"
        ctk.CTkButton(parent, text=btn_text, command=submit, fg_color="green", hover_color="darkgreen").grid(row=row_offset+9, column=0, columnspan=4, pady=15)
        
        return widgets

    def _build_ui(self):
        print("⏳ Đang tải danh sách file từ Supabase...")
        self.frames_list = ["-- Trống --"] + self._load_asset_names("frame")
        self.logos_list = ["-- Trống --"] + self._load_asset_names("logo")
        self.fonts_list = ["-- Trống --"] + self._load_asset_names("font")

        self.tabview = ctk.CTkTabview(self, corner_radius=10, height=350)
        self.tabview.pack(fill="x", padx=15, pady=5)
        
        tab_add = self.tabview.add("➕ Thêm Kênh")
        tab_edit = self.tabview.add("✏️ Sửa Kênh")

        self.add_widgets = self._build_form(tab_add, "add")
        self.edit_widgets = self._build_form(tab_edit, "edit")

        list_frame = ctk.CTkFrame(self, corner_radius=10)
        list_frame.pack(fill="both", expand=True, padx=15, pady=5)

        ctk.CTkLabel(list_frame, text="📋 Danh sách kênh đã lưu:", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=5)
        
        self.textbox_list = ctk.CTkTextbox(list_frame, height=120, state="disabled")
        self.textbox_list.pack(fill="both", expand=True, padx=10, pady=5)

        btn_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(btn_frame, text="Nhập ID kênh cần xóa:").pack(side="left", padx=5)
        self.entry_action_id = ctk.CTkEntry(btn_frame, width=100)
        self.entry_action_id.pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="🗑 Xóa Kênh", fg_color="red", hover_color="darkred", width=80, command=self.delete_channel).pack(side="left", padx=5)

        bot_frame = ctk.CTkFrame(self, corner_radius=10)
        bot_frame.pack(fill="x", padx=15, pady=10)

        self.btn_bot = ctk.CTkButton(bot_frame, text="▶️ KHỞI ĐỘNG TELEGRAM BOT", height=40, font=ctk.CTkFont(weight="bold", size=14), command=self.toggle_bot)
        self.btn_bot.pack(pady=10, padx=20, fill="x")

        self.log_box = ctk.CTkTextbox(bot_frame, height=80, state="disabled")
        self.log_box.pack(fill="x", padx=10, pady=(0, 10))

    def _load_asset_names(self, folder_name):
        """Đọc asset từ Supabase, fallback sang bản local khi mất mạng."""
        remote_names = SupabaseAPI.get_list_storage_files(
            "assets", folder_name, quiet=True
        )
        if remote_names:
            return remote_names

        names = set()
        for base_dir in (
            os.path.join(PROJECT_ROOT, "assets", folder_name),
            os.path.join(PROJECT_ROOT, "shared", "assets", folder_name),
        ):
            if not os.path.isdir(base_dir):
                continue
            for filename in os.listdir(base_dir):
                path = os.path.join(base_dir, filename)
                if os.path.isfile(path):
                    names.add(filename)
        if names:
            print(
                f"⚠️ Không truy cập được Supabase Storage ({folder_name}); "
                "đang dùng danh sách asset local."
            )
        return sorted(names)

    def delete_channel(self):
        c_id = self.entry_action_id.get().strip()
        if c_id in self.channels:
            name = self.channels[c_id]['name']
            del self.channels[c_id]
            self.save_config()
            self.log(f"🗑 Đã xóa kênh: {name} ({c_id})")
            self._refresh_list()
            if hasattr(self, 'edit_widgets'):
                channel_ids = ["-- Chọn kênh --"] + list(self.channels.keys())
                self.edit_widgets["opt_select"].configure(values=channel_ids)
        else:
            self.log(f"⚠️ Không tìm thấy kênh với ID: {c_id}")

    def _refresh_list(self):
        self.textbox_list.configure(state="normal")
        self.textbox_list.delete("1.0", "end")
        if not self.channels:
            self.textbox_list.insert("end", "Chưa có kênh nào được cấu hình.")
        else:
            for c_id, c_info in self.channels.items():
                self.textbox_list.insert("end", f"ID: {c_id} | Tên: {c_info.get('name')} | Sheet: {c_info.get('sheet_type')}\n")
                self.textbox_list.insert("end", f"  - Title: {c_info.get('title_frame_path')} | Content: {c_info.get('content_frame_path')}\n")
                self.textbox_list.insert("end", f"  - Logo: {c_info.get('logo_path')} | Font: {c_info.get('font_path')}\n")
                self.textbox_list.insert("end", f"  - Text: X={c_info.get('text_x')}, Y={c_info.get('text_y1')}, Size={c_info.get('text_size')}, Color={c_info.get('text_color')}\n\n")
        self.textbox_list.configure(state="disabled")

    def toggle_bot(self):
        if self.bot_process is None:
            self.start_bot()
        else:
            self.stop_bot()

    def start_bot(self):
        self.log("🚀 Đang khởi động bot...")
        script_path = os.path.join(APP_DIR, "tele_bot.py")
        self.bot_process = subprocess.Popen([sys.executable, "-u", script_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
        self.btn_bot.configure(text="⏸️ DỪNG TELEGRAM BOT", fg_color="red", hover_color="darkred")
        threading.Thread(target=self.read_bot_output, daemon=True).start()

    def stop_bot(self):
        if self.bot_process:
            self.bot_process.terminate()
            self.bot_process = None
            self.log("🛑 Đã dừng bot.")
            self.btn_bot.configure(text="▶️ KHỞI ĐỘNG TELEGRAM BOT", fg_color="#1f538d", hover_color="#14375e")

    def on_close(self):
        """Dừng bot con trước khi đóng giao diện cấu hình."""
        if self.bot_process:
            self.stop_bot()
        self.destroy()

    def read_bot_output(self):
        if self.bot_process:
            for line in iter(self.bot_process.stdout.readline, ''):
                if line:
                    self.log(f"[BOT] {line.strip()}")
            self.bot_process = None
            self.btn_bot.configure(text="▶️ KHỞI ĐỘNG TELEGRAM BOT", fg_color="#1f538d", hover_color="#14375e")

    def log(self, msg):
        print(msg, flush=True)
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

if __name__ == "__main__":
    app = TeleBotConfigApp()
    app.mainloop()
