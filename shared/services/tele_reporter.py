import os
import json
import requests
from datetime import datetime
from shared.services.supabase_api import SupabaseAPI

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATS_FILE = os.path.join(PROJECT_ROOT, "assets", "temp_downloads", "run_stats.json")
FAILURE_STATS_FILE = os.path.join(
    PROJECT_ROOT, "assets", "temp_downloads", "pipeline_failures.json"
)
MACHINE_FILE = os.path.join(PROJECT_ROOT, "config", "local_machine.json")

class TeleReporter:
    @staticmethod
    def log_success_video(tiktok_id, channel_url):
        os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)

        stats = {}
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    stats = json.load(f)
            except: pass

        if tiktok_id not in stats:
            stats[tiktok_id] = {}
        if channel_url not in stats[tiktok_id]:
            stats[tiktok_id][channel_url] = 0

        stats[tiktok_id][channel_url] += 1

        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)

    @staticmethod
    def log_pipeline_failure(tiktok_id, failure):
        """Count structured failures without sending a Telegram message per job."""
        os.makedirs(os.path.dirname(FAILURE_STATS_FILE), exist_ok=True)
        payload = (
            failure.to_dict() if hasattr(failure, "to_dict") else dict(failure or {})
        )
        error_code = str(payload.get("error_code") or "PIPELINE_FAILED")
        stage = str(payload.get("stage") or "unknown")
        key = f"{stage}:{error_code}"
        stats = {}
        if os.path.exists(FAILURE_STATS_FILE):
            try:
                with open(FAILURE_STATS_FILE, "r", encoding="utf-8") as file:
                    stats = json.load(file)
            except (OSError, json.JSONDecodeError):
                stats = {}
        channel_stats = stats.setdefault(str(tiktok_id or "unknown"), {})
        channel_stats[key] = int(channel_stats.get(key, 0)) + 1
        with open(FAILURE_STATS_FILE, "w", encoding="utf-8") as file:
            json.dump(stats, file, ensure_ascii=False, indent=2)

    @staticmethod
    def send_summary_report(schedule_time):
        if not os.path.exists(STATS_FILE) and not os.path.exists(FAILURE_STATS_FILE):
            return

        stats = {}
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    stats = json.load(f)
            except (OSError, json.JSONDecodeError):
                stats = {}
        failures = {}
        if os.path.exists(FAILURE_STATS_FILE):
            try:
                with open(FAILURE_STATS_FILE, "r", encoding="utf-8") as file:
                    failures = json.load(file)
            except (OSError, json.JSONDecodeError):
                failures = {}

        settings = SupabaseAPI.get_system_config("app_settings") or {}
        token = settings.get("tele_token")
        chat_id = settings.get("tele_chatid")

        if not token or not chat_id:
            print("⚠️ Chưa cấu hình Telegram. Bỏ qua gửi báo cáo.")
            return

        machine_id = "1"
        try:
            with open(MACHINE_FILE, "r") as f: machine_id = json.load(f).get("machine_id", "1")
        except: pass

        # ================= TẠO NỘI DUNG TIN NHẮN =================
        total_videos = 0
        msg = f"🟢 <b>BÁO CÁO MÁY {machine_id} (Đợt {schedule_time})</b>\n"
        msg += f"Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        msg += "-"*30 + "\n"

        for tiktok_id, channels in stats.items():
            msg += f"👤 <b>{tiktok_id}</b>\n"
            for url, count in channels.items():
                short_url = url.split('@')[-1] if '@' in url else url
                msg += f" ├ 📺 @{short_url}: {count} video\n"
                total_videos += count
            msg += "\n"

        msg += "-"*30 + "\n"
        msg += f"🎉 <b>TỔNG CỘNG: {total_videos} VIDEO</b>"
        if failures:
            msg += "\n\n🔴 <b>LỖI PIPELINE</b>\n"
            for channel_id, failure_counts in failures.items():
                msg += f"👤 <b>{channel_id}</b>\n"
                for key, count in failure_counts.items():
                    msg += f" ├ {key}: {count}\n"

        url = f"https://api.telegram.org/bot{token}/sendMessage"

        list_chat_ids = [cid.strip() for cid in str(chat_id).split(',') if cid.strip()]

        send_success = False

        for cid in list_chat_ids:
            payload = {
                "chat_id": cid,
                "text": msg,
                "parse_mode": "HTML"
            }
            try:
                res = requests.post(url, json=payload)
                if res.status_code == 200:
                    print(f"✅ Đã gửi báo cáo Tele cho ID: {cid}")
                    send_success = True
                else:
                    print(f"❌ Lỗi gửi Tele cho {cid}: {res.text}")
            except Exception as e:
                print(f"❌ Lỗi mạng khi gửi Tele cho {cid}: {e}")

        if send_success and os.path.exists(STATS_FILE):
            try:
                os.remove(STATS_FILE)
            except:
                pass
        if send_success and os.path.exists(FAILURE_STATS_FILE):
            try:
                os.remove(FAILURE_STATS_FILE)
            except OSError:
                pass

def test_telegram_connection(bot_token, chat_ids):
    """
    Hàm gửi tin nhắn test đến một hoặc nhiều Chat ID.
    """
    print("⏳ Đang kiểm tra kết nối Telegram...")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Hỗ trợ tách nhiều ID nếu bạn nhập cách nhau bằng dấu phẩy
    list_chat_ids = [cid.strip() for cid in str(chat_ids).split(',') if cid.strip()]

    if not list_chat_ids:
        print("❌ Lỗi: Bạn chưa nhập Chat ID.")
        return

    for cid in list_chat_ids:
        payload = {
            "chat_id": cid,
            "text": "🟢 <b>TEST KẾT NỐI THÀNH CÔNG!</b>\nHệ thống MATRIX BOT đã liên kết chuẩn xác với Telegram của bạn 🚀",
            "parse_mode": "HTML"
        }

        try:
            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                print(f"✅ Đã gửi tin nhắn test thành công đến ID: {cid}")
            else:
                # In ra lỗi chi tiết từ Telegram để dễ bắt bệnh (sai token, sai ID, hoặc chưa /start bot)
                error_desc = response.json().get('description', 'Lỗi không xác định')
                print(f"❌ Gửi thất bại đến ID {cid}. Lỗi: {error_desc}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Lỗi mạng khi gửi đến {cid}: {e}")

# ================= TEST THỰC TẾ =================
if __name__ == "__main__":
    print(
        "Dùng test_telegram_connection(bot_token, chat_ids) từ giao diện cấu hình; "
        "không lưu token/chat ID trong mã nguồn."
    )
