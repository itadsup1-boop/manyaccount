import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "apps", "creator_facebook"))

import telebot
import threading
import queue
from dotenv import load_dotenv
import re
from fb_pipeline import FBNewsPipeline
import uuid

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    print("⚠️ Vui lòng thêm TELEGRAM_BOT_TOKEN vào file .env")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

def extract_video_id(url):
    # Dùng regex đơn giản để bóc ID hoặc trả về uuid ngẫu nhiên nếu không tìm thấy
    match = re.search(r'/video/(\d+)', url) or re.search(r'v=(\d+)', url) or re.search(r'/(?:reel|shorts)/(\d+)', url) or re.search(r'/videos/(\d+)', url)
    if match:
        return match.group(1)
    return uuid.uuid4().hex[:8]

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
                        "ffmpeg", "-y", "-i", final_path,
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

# Queue chứa các link chờ xử lý
video_queue = queue.Queue()
pending_urls = {}

def worker_loop():
    while True:
        task = video_queue.get()
        if task is None:
            break
        
        # task = (message, url, c_id, c_info, extra_content)
        if len(task) == 5:
            message, url, c_id, c_info, extra_content = task
        else: # Tương thích cũ nếu có lỗi
            message, url, c_id, c_info = task
            extra_content = ""
            
        bot.send_message(message.chat.id, f"⚙️ Đến lượt bạn! Hệ thống đang xử lý link cho kênh {c_info.get('name')}...")
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
    text = message.text
    chat_id = message.chat.id
    
    urls = re.findall(r'(https?://[^\s]+)', text)
    if not urls:
        bot.send_message(chat_id, "👋 Chào bạn! Hãy dán 1 link TikTok hoặc Facebook vào đây, tôi sẽ tự động xử lý video cho bạn!\n\n💡 Bạn cũng có thể dùng lệnh /stats để xem tiến độ làm video hôm nay.")
        return
        
    valid_urls = [u for u in urls if 'tiktok.com' in u or 'facebook.com' in u or 'fb.watch' in u]
    
    if not valid_urls:
        bot.send_message(chat_id, "⚠️ Hiện tại tôi chỉ hỗ trợ link TikTok và Facebook.")
        return

    channels = load_channels()
    if not channels:
        bot.send_message(chat_id, "⚠️ Chưa cấu hình kênh nào. Vui lòng mở công cụ quản lý để thêm kênh trước!")
        return

    markup = telebot.types.InlineKeyboardMarkup()
    for c_id, c_info in channels.items():
        btn = telebot.types.InlineKeyboardButton(c_info.get('name', c_id), callback_data=f"chan_{c_id}")
        markup.add(btn)

    pending_urls[message.message_id] = valid_urls
    bot.reply_to(message, f"📥 Đã nhận {len(valid_urls)} link.\nVui lòng chọn kênh để làm video:", reply_markup=markup)

# Dict lưu trạng thái chờ nhập content: { chat_id: { "urls", "c_id", "c_info", "reply_msg", "waiting": True } }
pending_content = {}

@bot.callback_query_handler(func=lambda call: call.data.startswith('chan_'))
def callback_channel(call):
    c_id = call.data.replace('chan_', '', 1)
    msg_id = call.message.reply_to_message.message_id if call.message.reply_to_message else None
    
    if msg_id and msg_id in pending_urls:
        urls = pending_urls.pop(msg_id)
        channels = load_channels()
        c_info = channels.get(c_id, {})
        c_name = c_info.get("name", c_id)
        
        # Tạo nút "Bỏ qua"
        skip_markup = telebot.types.InlineKeyboardMarkup()
        skip_markup.add(telebot.types.InlineKeyboardButton("⏭ Bỏ qua (Dùng nội dung gốc)", callback_data=f"skip_content_{call.message.chat.id}"))
        
        bot.edit_message_text(
            f"✅ Đã chọn kênh: <b>{c_name}</b>\n\n"
            f"💬 Bạn có muốn gửi thêm nội dung/chỉ đạo cho video không?\n\n"
            f"👉 <b>Nhập nội dung</b> vào ô chat bên dưới\n"
            f"👉 Hoặc bấm nút <b>Bỏ qua</b> để dùng nội dung gốc của video",
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
            "waiting": True
        }
        
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
        
        # Xóa nút bỏ qua và cập nhật tin nhắn
        bot.edit_message_text(
            f"⏭ Đã bỏ qua phần nhập nội dung.\n🚀 Đưa {len(urls)} link vào hàng đợi xử lý (dùng nội dung gốc video).",
            chat_id, call.message.message_id
        )
        
        # Hủy bỏ handler đang chờ text
        bot.clear_step_handler_by_chat_id(chat_id)
        
        for url in urls:
            video_queue.put((reply_msg, url, c_id, c_info, ""))
        
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
        video_queue.put((reply_msg, url, c_id, c_info, extra_content))

if __name__ == '__main__':
    print("🚀 Telegram Bot đang chạy! Chờ tin nhắn...")
    import logging
    import time
    telebot.logger.setLevel(logging.ERROR)  # Ẩn các cảnh báo timeout mạng rác
    
    while True:
        try:
            # Tăng timeout lên 60s để chống lỗi mạng
            bot.infinity_polling(timeout=60)
        except KeyboardInterrupt:
            print("Đã dừng Bot.")
            break
        except Exception as e:
            print(f"⚠️ Lỗi đứt kết nối mạng Telegram: {e}")
            print("⏳ Đang thử kết nối lại sau 5 giây...")
            time.sleep(5)
