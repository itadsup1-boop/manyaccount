import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "apps", "creator_facebook"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "apps", "creator_article"))

import telebot
import threading
import queue
from dotenv import load_dotenv
import re
import time
from contextlib import contextmanager
from fb_pipeline import FBNewsPipeline
from article_pipeline_core import ArticlePipelineCore
import uuid
from shared.core.ffmpeg_utils import ffmpeg_command

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    print("⚠️ Vui lòng thêm TELEGRAM_BOT_TOKEN vào file .env")
    exit(1)

@contextmanager
def _single_instance_lock():
    """Giữ một bot polling duy nhất trên máy hiện tại.

    Telegram chỉ cho phép một long-polling consumer cho mỗi token. Khóa này
    tránh việc người vận hành mở nhầm hai cửa sổ bot trên cùng máy. Đây là
    advisory lock nên tự giải phóng khi tiến trình chết, không để lại PID rác.
    """
    lock_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, "telegram_bot.polling.lock")
    lock_file = open(lock_path, "a+", encoding="utf-8")
    # msvcrt.locking() cần ít nhất một byte trong file.
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write("1")
        lock_file.flush()
    lock_file.seek(0)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
            except OSError:
                locked = False
        else:
            import fcntl

            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                locked = False

        if not locked:
            print(
                "❌ Bot đã chạy ở một tiến trình khác trên máy này. "
                "Hãy dừng cửa sổ bot đang mở trước khi khởi động lại."
            )
            yield False
            return

        yield True
    finally:
        if locked:
            try:
                if os.name == "nt":
                    import msvcrt

                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock_file.close()


def _is_polling_conflict(error):
    """Trả về True khi Telegram báo token đang bị consumer khác giữ."""
    return getattr(error, "error_code", None) == 409 or (
        "409" in str(error) and "getUpdates" in str(error)
    )


def _print_webhook_diagnostic():
    """In URL webhook nếu token đang bị webhook giữ (không in token)."""
    try:
        webhook_info = bot.get_webhook_info()
        webhook_url = getattr(webhook_info, "url", "") or ""
        if webhook_url:
            print(
                f"ℹ️ Webhook hiện đang bật tại: {webhook_url}. "
                "Hãy tắt webhook trước khi dùng polling."
            )
    except Exception:
        # Chẩn đoán không được làm che mất lỗi 409 gốc.
        pass


class ConflictAwareTeleBot(telebot.TeleBot):
    """Cho phép main() nhận 409 thay vì để pyTelegramBotAPI retry vô hạn."""

    def _handle_exception(self, exception):
        if _is_polling_conflict(exception):
            raise exception
        return super()._handle_exception(exception)


bot = ConflictAwareTeleBot(BOT_TOKEN)

def extract_video_id(url):
    # Dùng regex đơn giản để bóc ID hoặc trả về uuid ngẫu nhiên nếu không tìm thấy
    match = re.search(r'/video/(\d+)', url) or re.search(r'v=(\d+)', url) or re.search(r'/(?:reel|shorts)/(\d+)', url) or re.search(r'/videos/(\d+)', url)
    if match:
        return match.group(1)
    return uuid.uuid4().hex[:8]


def _clean_url(url):
    """Bỏ dấu câu thường dính ở cuối link khi người dùng gửi qua Telegram."""
    return str(url or "").strip().rstrip(".,!?;:)]}>")


def classify_url(url):
    """Phân loại link Telegram thành video mạng xã hội hoặc bài báo."""
    clean_url = _clean_url(url)
    lowered = clean_url.lower()
    if any(host in lowered for host in ("tiktok.com", "facebook.com", "fb.watch")):
        return "video", clean_url
    if lowered.startswith(("http://", "https://")):
        return "article", clean_url
    return "unsupported", clean_url

import json

def load_channels():
    cfg_path = os.path.join(CURRENT_DIR, "channels_config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def process_video_thread(message, url, c_id, c_info, extra_content=""):
    chat_id = message.chat.id
    try:
        # Giả lập video object
        video = {
            "url": url,
            "video_id": extract_video_id(url),
            "caption": "Telegram Link"
        }
        
        # Giả lập source object lấy từ channels config
        source = {
            "id": c_id,
            "source_name": c_info.get("name"),
            "id_tiktok": c_id,
            "delogo": "", 
            "logo_path": c_info.get("logo_path", ""),
            "title_frame_path": c_info.get("title_frame_path", ""),
            "content_frame_path": c_info.get("content_frame_path", ""),
            "font_path": c_info.get("font_path", ""),
            "sheet_type": c_info.get("sheet_type", "tong"),
            "is_telegram_bot": True,
            "extra_content": extra_content,
            "text_y1": c_info.get("text_y1", ""),
            "text_size": c_info.get("text_size", ""),
            "text_color": c_info.get("text_color", ""),
            "text_x": c_info.get("text_x", "65")
        }
        
        pipeline = FBNewsPipeline()
        
        def on_success(drive_link, final_path, sheet_row=None):
            msg = f"🎉 Đã làm xong video!"
            if sheet_row:
                msg += f"\n📊 Ghi thành công lên Google Sheet tại dòng: {sheet_row}"
            msg += f"\n🔗 Link Google Drive: {drive_link}"
            
            bot.send_message(chat_id, msg)
            
            # Gửi video trực tiếp vào Telegram (nén trước)
            try:
                if os.path.exists(final_path):
                    import subprocess
                    compressed_path = final_path.replace(".mp4", "_compressed.mp4")
                    bot.send_message(chat_id, "🗜 Đang nén video để gửi trực tiếp vào Telegram...")
                    
                    # Lệnh nén video bằng FFmpeg (giảm bitrate, nhanh)
                    cmd = [
                        *ffmpeg_command("-y", "-i", final_path),
                        "-vcodec", "libx264", "-crf", "18", "-preset", "fast",
                        "-c:a", "aac", "-b:a", "64k",
                        compressed_path
                    ]
                    subprocess.run(cmd, capture_output=True)
                    
                    # Lấy dung lượng file sau khi nén
                    send_path = compressed_path if os.path.exists(compressed_path) else final_path
                    size_mb = os.path.getsize(send_path) / 1024 / 1024
                    
                    if size_mb < 50:
                        bot.send_message(chat_id, f"📤 Đang tải video lên Telegram ({size_mb:.1f}MB)...")
                        with open(send_path, 'rb') as f:
                            bot.send_video(chat_id, f, caption="🎬 Thành phẩm của bạn đây!")
                    else:
                        bot.send_message(chat_id, f"⚠️ Video dù đã nén vẫn có dung lượng {size_mb:.1f}MB (> 50MB), vượt quá giới hạn gửi trực tiếp của Telegram API. Vui lòng tải qua link Google Drive.")
                        
                    if os.path.exists(compressed_path):
                        os.remove(compressed_path)
            except Exception as e:
                bot.send_message(chat_id, f"⚠️ Lỗi khi tải file lên Telegram: {e}")
                
        def on_error(err_msg):
            safe_err = str(err_msg).replace('<', '&lt;').replace('>', '&gt;')
            bot.send_message(chat_id, f"❌ <b>LỖI HỆ THỐNG:</b>\n<code>{safe_err}</code>\n\nVui lòng thử lại sau hoặc liên hệ Admin.", parse_mode="HTML")
            
        bot.send_message(chat_id, "⏳ Bắt đầu phân tích kịch bản và render video (mất khoảng 2-3 phút)...")
        
        result = pipeline._process_one_video(video, source, on_success=on_success, on_error=on_error)
        
        if result == "duplicate":
            bot.send_message(chat_id, "⚠️ Video này đã được làm trước đó rồi (Trùng nội dung). Hệ thống sẽ bỏ qua để tránh trùng lặp.")
        elif result == "skip":
            bot.send_message(chat_id, "⏭️ ChatGPT đánh giá video này KHÔNG CẦN THIẾT phải làm (Ví dụ: MC dẫn chương trình, tin rác). Đã bỏ qua tự động.")
        elif not result:
            pass # Lỗi đã được xử lý trong on_error
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ Có lỗi xảy ra trong Bot: {e}")


def process_article_thread(message, url, c_id, c_info, extra_content=""):
    """Tạo video bài báo thủ công từ một URL gửi qua Telegram."""
    chat_id = message.chat.id
    pipeline = ArticlePipelineCore()
    source_id = f"telegram-{c_id}"
    success_notified = {"value": False}

    def on_success(drive_link, final_path, sheet_row=None):
        success_notified["value"] = True
        text = "📰 Đã tạo bài viết thủ công thành công!"
        if sheet_row:
            text += f"\n📊 Google Sheet: dòng {sheet_row}"
        text += f"\n🔗 Link Google Drive: {drive_link}"
        bot.send_message(chat_id, text)
        _send_video_to_telegram(chat_id, final_path)

    def on_error(error_message):
        safe_err = str(error_message).replace("<", "&lt;").replace(">", "&gt;")
        bot.send_message(
            chat_id,
            f"❌ <b>Không tạo được bài viết:</b>\n<code>{safe_err}</code>",
            parse_mode="HTML",
        )

    bot.send_message(
        chat_id,
        "⏳ Đã nhận bài báo. Đang cào nội dung, viết kịch bản và dựng video "
        "(có thể mất vài phút)...",
    )
    try:
        result = pipeline.process_single_article(
            c_id,
            source_id,
            url,
            operator_instruction=extra_content,
            manual_approval=True,
            on_success=on_success,
            on_error=on_error,
        )
        if result == "skipped":
            bot.send_message(chat_id, "⏭️ Bài báo đã được AI đánh dấu không phù hợp.")
        elif result is True and not success_notified["value"]:
            bot.send_message(chat_id, "⚠️ Link bài báo này đã được xử lý trước đó; hệ thống không tạo trùng.")
        elif not result:
            # Chi tiết lỗi đã được gửi qua on_error.
            pass
    except Exception as error:
        on_error(error)


def _send_video_to_telegram(chat_id, final_path):
    """Gửi bản nén thành phẩm nếu Telegram Bot API còn đủ hạn mức."""
    try:
        if not final_path or not os.path.exists(final_path):
            return
        import subprocess
        compressed_path = final_path.replace(".mp4", "_compressed.mp4")
        bot.send_message(chat_id, "🗜 Đang nén video để gửi trực tiếp vào Telegram...")
        cmd = [
            *ffmpeg_command("-y", "-i", final_path),
            "-vcodec", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "64k", compressed_path,
        ]
        subprocess.run(cmd, capture_output=True, check=False)
        send_path = compressed_path if os.path.exists(compressed_path) else final_path
        size_mb = os.path.getsize(send_path) / 1024 / 1024
        if size_mb < 50:
            bot.send_message(chat_id, f"📤 Đang tải video lên Telegram ({size_mb:.1f}MB)...")
            with open(send_path, "rb") as video_file:
                bot.send_video(chat_id, video_file, caption="🎬 Thành phẩm của bạn đây!")
        else:
            bot.send_message(
                chat_id,
                f"⚠️ Video {size_mb:.1f}MB vượt giới hạn gửi trực tiếp; "
                "vui lòng tải từ link Google Drive.",
            )
        if os.path.exists(compressed_path):
            os.remove(compressed_path)
    except Exception as error:
        bot.send_message(chat_id, f"⚠️ Không gửi được video trực tiếp: {error}")

# Queue chứa các link chờ xử lý
video_queue = queue.Queue()
pending_urls = {}

def worker_loop():
    while True:
        task = video_queue.get()
        if task is None:
            break
        
        # task = (kind, message, url, c_id, c_info, extra_content)
        if len(task) == 6:
            kind, message, url, c_id, c_info, extra_content = task
        elif len(task) == 5:  # Tương thích task video đời cũ
            message, url, c_id, c_info, extra_content = task
            kind = "video"
        else:
            message, url, c_id, c_info = task
            kind, extra_content = "video", ""
        
        bot.send_message(message.chat.id, f"⚙️ Đến lượt bạn! Hệ thống đang xử lý link cho kênh {c_info.get('name')}...")
        if kind == "article":
            process_article_thread(message, url, c_id, c_info, extra_content)
        else:
            process_video_thread(message, url, c_id, c_info, extra_content)
        video_queue.task_done()

# Khởi chạy 1 worker duy nhất
threading.Thread(target=worker_loop, daemon=True).start()

QUALITY_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "quality_log.jsonl")


def _read_quality_log(days=1):
    """Đọc quality_log.jsonl, trả về các entry trong N ngày gần nhất."""
    import datetime
    entries = []
    if not os.path.exists(QUALITY_LOG_PATH):
        return entries
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        with open(QUALITY_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if e.get("ts", "") >= cutoff:
                        entries.append(e)
                except Exception:
                    continue
    except Exception:
        pass
    return entries


@bot.message_handler(commands=['quality'])
def handle_quality(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ Đang tổng hợp báo cáo chất lượng hôm nay...")

    def fetch_quality():
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        entries = [e for e in _read_quality_log(days=1) if e.get("ts", "").startswith(today)]

        if not entries:
            bot.send_message(chat_id, "📭 Chưa có dữ liệu chất lượng hôm nay.\n💡 Dữ liệu sẽ xuất hiện khi pipeline chạy và AI trả về quality_score.")
            return

        fb_done = [e for e in entries if e["pl"] == "facebook" and e["st"] == "done"]
        fb_skip = [e for e in entries if e["pl"] == "facebook" and e["st"] == "skip"]
        art_done = [e for e in entries if e["pl"] == "article" and e["st"] == "done"]
        art_skip = [e for e in entries if e["pl"] == "article" and e["st"] == "skip"]

        def avg_score(lst):
            return round(sum(e["score"] for e in lst) / len(lst), 1) if lst else 0

        skip_reasons = {}
        for e in fb_skip + art_skip:
            r = e.get("reason", "Không rõ") or "Không rõ"
            skip_reasons[r] = skip_reasons.get(r, 0) + 1
        top_reasons = sorted(skip_reasons.items(), key=lambda x: -x[1])[:3]
        reasons_text = "\n".join(f"  • {r} ({c})" for r, c in top_reasons) if top_reasons else "  (chưa có)"

        today_str = datetime.datetime.now().strftime("%d/%m/%Y")
        msg = (
            f"📊 <b>Báo cáo chất lượng — {today_str}</b>\n\n"
            f"📘 <b>Facebook:</b> {len(fb_done) + len(fb_skip)} phân tích → "
            f"{len(fb_done)} pass (avg {avg_score(fb_done)}/10), {len(fb_skip)} skip\n"
            f"📗 <b>Article:</b> {len(art_done) + len(art_skip)} phân tích → "
            f"{len(art_done)} pass (avg {avg_score(art_done)}/10), {len(art_skip)} skip\n\n"
            f"🚫 <b>Lý do skip phổ biến:</b>\n{reasons_text}"
        )
        bot.send_message(chat_id, msg, parse_mode="HTML")

    threading.Thread(target=fetch_quality, daemon=True).start()


@bot.message_handler(commands=['sources'])
def handle_sources(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ Đang tổng hợp top nguồn Facebook 7 ngày qua...")

    def fetch_sources():
        entries = [e for e in _read_quality_log(days=7) if e["pl"] == "facebook"]
        if not entries:
            bot.send_message(chat_id, "📭 Chưa có đủ dữ liệu (cần chạy ít nhất 1 ngày).")
            return

        from collections import defaultdict
        src_data = defaultdict(list)
        for e in entries:
            src_data[e.get("src", "?")].append(e["score"])

        ranked = sorted(
            [(src, scores) for src, scores in src_data.items() if len(scores) >= 2],
            key=lambda x: -sum(x[1]) / len(x[1])
        )[:7]

        if not ranked:
            bot.send_message(chat_id, "📭 Chưa đủ dữ liệu (mỗi nguồn cần ít nhất 2 video).")
            return

        lines = []
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
        for i, (src, scores) in enumerate(ranked):
            avg = round(sum(scores) / len(scores), 1)
            lines.append(f"{medals[i]} <b>{src}</b> — avg {avg}/10 ({len(scores)} video)")

        msg = "🏆 <b>Top nguồn Facebook (7 ngày)</b>\n\n" + "\n".join(lines)
        bot.send_message(chat_id, msg, parse_mode="HTML")

    threading.Thread(target=fetch_sources, daemon=True).start()


@bot.message_handler(commands=['stats', 'tiendo'])
def handle_stats(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ Đang tổng hợp số lượng video hoàn thành hôm nay...")
    
    def fetch_stats():
        import datetime
        today_str = datetime.datetime.now().strftime('%Y-%m-%d')
        today_display = datetime.datetime.now().strftime('%d/%m/%Y')
        
        # Đọc dữ liệu từ file log cục bộ (siêu tốc)
        entries = _read_quality_log(days=1)
        today_entries = [e for e in entries if e.get("ts", "").startswith(today_str) and e.get("st") == "done"]
        
        total_tong = sum(1 for e in today_entries if e.get("pl") == "article")
        total_fb = sum(1 for e in today_entries if e.get("pl") == "facebook")
        
        bot.send_message(chat_id, f"📊 <b>Thống kê hôm nay ({today_display}):</b>\n\n"
                                  f"🔹 Báo mạng (Sheet Tổng): <b>{total_tong}</b> video\n"
                                  f"🔹 Facebook (Sheet FB): <b>{total_fb}</b> video\n\n"
                                  f"📈 Tổng cộng: <b>{total_tong + total_fb}</b> video đã xử lý thành công!", parse_mode="HTML")

    threading.Thread(target=fetch_stats, daemon=True).start()

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text or ""
    chat_id = message.chat.id
    
    urls = [_clean_url(item) for item in re.findall(r'(https?://[^\s]+)', text)]
    if not urls:
        bot.send_message(
            chat_id,
            "👋 Hãy gửi link TikTok/Facebook để làm video, hoặc gửi link bài báo "
            "kèm tin nhắn chỉ đạo để tạo bài viết thủ công.\n\n"
            "💡 Bạn cũng có thể dùng lệnh /stats để xem tiến độ hôm nay.",
        )
        return
        
    classified = [classify_url(url) for url in urls]
    unsupported = [url for kind, url in classified if kind == "unsupported"]
    if unsupported:
        bot.send_message(chat_id, "⚠️ Có link không hợp lệ. Hãy gửi URL bắt đầu bằng http:// hoặc https://.")
        return

    kinds = {kind for kind, _ in classified}
    if len(kinds) > 1:
        bot.send_message(
            chat_id,
            "⚠️ Vui lòng gửi riêng link video và link bài báo; một tin nhắn không nên trộn hai loại.",
        )
        return

    channels = load_channels()
    if not channels:
        bot.send_message(chat_id, "⚠️ Chưa cấu hình kênh nào. Vui lòng mở công cụ quản lý để thêm kênh trước!")
        return

    markup = telebot.types.InlineKeyboardMarkup()
    for c_id, c_info in channels.items():
        btn = telebot.types.InlineKeyboardButton(c_info.get('name', c_id), callback_data=f"chan_{c_id}")
        markup.add(btn)

    link_kind = next(iter(kinds))
    inline_instruction = re.sub(r'https?://[^\s]+', ' ', text).strip()
    pending_urls[message.message_id] = {
        "kind": link_kind,
        "urls": [url for _, url in classified],
        "initial_content": inline_instruction,
    }
    action = "tạo bài viết thủ công" if link_kind == "article" else "làm video"
    bot.reply_to(
        message,
        f"📥 Đã nhận {len(urls)} link.\nVui lòng chọn kênh để {action}:",
        reply_markup=markup,
    )

# Dict lưu trạng thái chờ nhập content: { chat_id: { "urls", "c_id", "c_info", "reply_msg", "waiting": True } }
pending_content = {}

@bot.callback_query_handler(func=lambda call: call.data.startswith('chan_'))
def callback_channel(call):
    c_id = call.data.replace('chan_', '', 1)
    msg_id = call.message.reply_to_message.message_id if call.message.reply_to_message else None
    
    if msg_id and msg_id in pending_urls:
        pending_request = pending_urls.pop(msg_id)
        if isinstance(pending_request, dict):
            urls = pending_request.get("urls", [])
            link_kind = pending_request.get("kind", "video")
            initial_content = pending_request.get("initial_content", "")
        else:  # Tương thích dữ liệu pending của bản cũ
            urls, link_kind, initial_content = pending_request, "video", ""
        channels = load_channels()
        c_info = channels.get(c_id, {})
        c_name = c_info.get("name", c_id)
        item_label = "bài báo" if link_kind == "article" else "video"
        
        # Tạo nút "Bỏ qua"
        skip_markup = telebot.types.InlineKeyboardMarkup()
        skip_markup.add(telebot.types.InlineKeyboardButton("⏭ Bỏ qua (Dùng nội dung gốc)", callback_data=f"skip_content_{call.message.chat.id}"))
        
        bot.edit_message_text(
            f"✅ Đã chọn kênh: <b>{c_name}</b>\n\n"
            f"💬 Bạn có muốn gửi thêm nội dung/chỉ đạo cho {item_label} không?\n\n"
            f"👉 <b>Nhập nội dung</b> vào ô chat bên dưới\n"
            f"👉 Hoặc bấm nút <b>Bỏ qua</b> để dùng nội dung gốc",
            call.message.chat.id, call.message.message_id,
            reply_markup=skip_markup, parse_mode="HTML"
        )
        
        # Lưu trạng thái chờ content
        pending_content[call.message.chat.id] = {
            "urls": urls,
            "c_id": c_id,
            "c_info": c_info,
            "reply_msg": call.message.reply_to_message,
            "prompt_msg_id": call.message.message_id,
            "kind": link_kind,
            "waiting": True
        }

        # Cho phép gửi link và chỉ đạo trong cùng một tin nhắn. Nếu có phần
        # chữ ngoài URL, không bắt người dùng gửi lại một tin nhắn thứ hai.
        if initial_content:
            pending_content[call.message.chat.id]["waiting"] = False
            pending_content.pop(call.message.chat.id, None)
            bot.edit_message_text(
                f"✅ Đã nhận chỉ đạo thủ công.\n🚀 Đưa {len(urls)} link vào hàng đợi xử lý.",
                call.message.chat.id,
                call.message.message_id,
            )
            for url in urls:
                video_queue.put((link_kind, call.message.reply_to_message, url, c_id, c_info, initial_content))
            bot.answer_callback_query(call.id, "✅ Đã đưa vào hàng đợi!")
            return
        
        # Đăng ký lắng nghe tin nhắn tiếp theo
        bot.register_next_step_handler(call.message, process_extra_content)
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id, "❌ Lỗi: Không tìm thấy link cho phiên này, vui lòng gửi lại link.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('skip_content_'))
def callback_skip_content(call):
    chat_id = call.message.chat.id
    
    if chat_id in pending_content and pending_content[chat_id].get("waiting"):
        ctx = pending_content.pop(chat_id)
        urls = ctx["urls"]
        c_id = ctx["c_id"]
        c_info = ctx["c_info"]
        reply_msg = ctx["reply_msg"]
        link_kind = ctx.get("kind", "video")
        
        # Xóa nút bỏ qua và cập nhật tin nhắn
        bot.edit_message_text(
            f"⏭ Đã bỏ qua phần nhập nội dung.\n🚀 Đưa {len(urls)} link vào hàng đợi xử lý (dùng nội dung gốc).",
            chat_id, call.message.message_id
        )
        
        # Hủy bỏ handler đang chờ text
        bot.clear_step_handler_by_chat_id(chat_id)
        
        for url in urls:
            video_queue.put((link_kind, reply_msg, url, c_id, c_info, ""))
        
        bot.answer_callback_query(call.id, "✅ Đã bỏ qua!")
    else:
        bot.answer_callback_query(call.id, "⚠️ Phiên này đã hết hạn.")

def process_extra_content(message):
    chat_id = message.chat.id
    
    # Kiểm tra xem phiên còn đang chờ hay đã bị skip
    if chat_id not in pending_content or not pending_content[chat_id].get("waiting"):
        return  # Đã bị skip bằng nút, bỏ qua tin nhắn này
    
    ctx = pending_content.pop(chat_id)
    urls = ctx["urls"]
    c_id = ctx["c_id"]
    c_info = ctx["c_info"]
    reply_msg = ctx["reply_msg"]
    prompt_msg_id = ctx.get("prompt_msg_id")
    link_kind = ctx.get("kind", "video")
    
    extra_content = (message.text or "").strip()
    
    # Xóa nút bỏ qua trên tin nhắn cũ
    if prompt_msg_id:
        try:
            bot.edit_message_reply_markup(chat_id, prompt_msg_id, reply_markup=None)
        except:
            pass
    
    if extra_content:
        bot.send_message(chat_id, f"📝 Đã ghi nhận nội dung của bạn!\n🚀 Đưa {len(urls)} link vào hàng đợi xử lý.")
    else:
        bot.send_message(chat_id, f"🚀 Đưa {len(urls)} link vào hàng đợi xử lý (dùng nội dung gốc video).")
    
    for url in urls:
        video_queue.put((link_kind, reply_msg, url, c_id, c_info, extra_content))

if __name__ == '__main__':
    import logging
    telebot.logger.setLevel(logging.ERROR)  # Ẩn các cảnh báo timeout mạng rác

    with _single_instance_lock() as lock_owned:
        if not lock_owned:
            raise SystemExit(1)

        print("🚀 Telegram Bot đang chạy! Chờ tin nhắn...")
        while True:
            try:
                # Dùng polling một vòng thay vì infinity_polling: bản
                # infinity_polling của pyTelegramBotAPI nuốt 409 rồi retry
                # vô hạn, khiến bot spam log và không bao giờ thoát.
                bot.polling(non_stop=False, timeout=60, logger_level=logging.ERROR)
                print("⚠️ Polling đã dừng; thử kết nối lại sau 5 giây...")
                time.sleep(5)
            except KeyboardInterrupt:
                print("Đã dừng Bot.")
                break
            except Exception as error:
                if _is_polling_conflict(error):
                    _print_webhook_diagnostic()
                    print(
                        "❌ Telegram từ chối polling (409 Conflict): token đang "
                        "bị một tiến trình khác hoặc webhook giữ. Hãy dừng bot "
                        "còn lại/tắt webhook rồi khởi động lại."
                    )
                    break
                print(f"⚠️ Lỗi kết nối Telegram: {error}")
                print("⏳ Đang thử kết nối lại sau 5 giây...")
                time.sleep(5)
