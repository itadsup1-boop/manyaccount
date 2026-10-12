import os
import json
import logging
import sys


class _SafeStdout:
    """Giữ worker sống khi tiến trình cha đóng đường ống log."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, value):
        try:
            return self._stream.write(value)
        except (BrokenPipeError, OSError):
            return 0

    def flush(self):
        try:
            return self._stream.flush()
        except (BrokenPipeError, OSError):
            return None

    def __getattr__(self, name):
        return getattr(self._stream, name)

# Tìm về thư mục gốc dự án
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# [MỚI] Import API kết nối Supabase
from shared.services.supabase_api import SupabaseAPI

class AccountContext:
    def __init__(self, account_id):
        self.acc_id = account_id

        # Một số lệnh TTS/Playwright vẫn dùng print(). Bọc stdout ngay khi
        # worker khởi tạo để BrokenPipe không biến thành lỗi pipeline.
        if not isinstance(sys.stdout, _SafeStdout):
            sys.stdout = _SafeStdout(sys.stdout)

        # 1. Đường dẫn biệt lập (Isolated Paths)
        self.root_data = os.path.join(PROJECT_ROOT, "data", account_id)
        self.temp_dir = os.path.join(self.root_data, "temp") # File tải về nằm ở đây
        self.outbox_dir = os.path.join(self.root_data, "outbox")
        self.pending_results_file = os.path.join(self.root_data, "pending_results.json")
        self.state_file = os.path.join(self.root_data, "state.json")
        self.log_file = os.path.join(PROJECT_ROOT, "logs", f"{account_id}.log")

        # [ĐÃ XÓA] self.config_file = os.path.join(...)

        # 2. Tạo folder nếu thiếu
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.outbox_dir, exist_ok=True)
        os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)

        # 3. Setup Logger
        self.logger = self._setup_logger()

        # 4. [SỬA] Load Config từ Supabase thay vì Local JSON
        self.config = SupabaseAPI.get_account_by_id(account_id)
        if not self.config:
            self.logger.error(f"❌ Không tìm thấy cấu hình cho tài khoản '{account_id}' trên Supabase!")
            self.config = {}

    def _setup_logger(self):
        logger = logging.getLogger(self.acc_id)
        logger.setLevel(logging.INFO)
        if logger.hasHandlers(): logger.handlers.clear()

        # Ghi ra file log riêng
        fh = logging.FileHandler(self.log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        logger.addHandler(fh)

        # In ra màn hình console chung
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter(f'[{self.acc_id}] %(message)s'))
        logger.addHandler(sh)
        return logger

    def load_state(self):
        try:
            with open(self.state_file, "r", encoding="utf-8") as f: return json.load(f)
        except: return {"crawled_videos": []}

    def save_state(self, state_data):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=4)

    def load_pending_results(self):
        try:
            with open(self.pending_results_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, ValueError, TypeError):
            return []

    def save_pending_results(self, results):
        tmp_path = self.pending_results_file + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(list(results or []), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.pending_results_file)

    def enqueue_pending_result(self, result):
        results = self.load_pending_results()
        key = (str(result.get("candidate_url") or ""), str(result.get("row") or ""))
        results = [
            item for item in results
            if (str(item.get("candidate_url") or ""), str(item.get("row") or "")) != key
        ]
        results.append(dict(result))
        self.save_pending_results(results)

    def remove_pending_result(self, candidate_url, row):
        key = (str(candidate_url or ""), str(row or ""))
        results = [
            item for item in self.load_pending_results()
            if (str(item.get("candidate_url") or ""), str(item.get("row") or "")) != key
        ]
        self.save_pending_results(results)

    def cleanup_temp(self):
        # Chỉ xóa file trong folder temp của nick này
        for f in os.listdir(self.temp_dir):
            try: os.remove(os.path.join(self.temp_dir, f))
            except: pass
