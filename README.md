# manyaccount

Automation suite for content creation, Facebook processing, Telegram control, and TikTok uploading with Adsup Central Hub.

## Chay tren Windows

1. Cai Python 3.11+ va FFmpeg (`winget install Gyan.FFmpeg.Shared`).
2. Chay `scripts\setup_windows.bat` mot lan de tao `.venv`, cai packages va Chromium cho Playwright.
   Sau do chay `scripts\download_whisper_model.bat` de tai model Faster-Whisper `base` cho phu de karaoke.
3. Dien cac key that trong `.env` (khong commit file nay).
4. Chay `scripts\run_windows.bat` de mo menu, hoac:
   - `scripts\run_hub_windows.bat` (mo giao dien web va tu mo trinh duyet)
   - `scripts\run_windows.bat -App tiktok`
   - `scripts\run_windows.bat -App facebook`
   - `scripts\run_windows.bat -App article`
   - `scripts\run_windows.bat -App chatgpt-login -ProfileId ten_kenh`
   - `scripts\verify_windows.bat`
   - `scripts\watch_pipeline_log.bat` (theo doi tung buoc va loi theo thoi gian thuc)

Web Hub chay frontend tai `http://localhost:5173` va API tai `http://localhost:8000/docs`. Nhan `Ctrl+C` trong cua so launcher de dung ca hai tien trinh.

### Tạo bài viết thủ công qua Telegram

Telegram bot hỗ trợ gửi một URL bài báo để chạy ngay Article pipeline. Gửi
link kèm chỉ đạo biên tập trong cùng tin nhắn (hoặc gửi chỉ đạo ở tin nhắn
tiếp theo), chọn kênh, rồi bot sẽ cào bài, viết kịch bản, dựng video, ghi
Google Sheet/Drive và gửi lại thành phẩm. Ví dụ:

```text
https://example.com/bai-viet
Tập trung vào con số chính, giọng tin tức ngắn gọn.
```

Khởi động giao diện cấu hình và bot bằng `./khoi_dong_tele_bot.sh` (Linux/macOS)
(trên Windows chạy `apps/telegram_bot/tele_desktop_app.py` trong môi trường đã
cài dependencies). Cần khai báo
`TELEGRAM_BOT_TOKEN` trong `.env` và có ít nhất một kênh trong
`apps/telegram_bot/channels_config.json`.

Khi bạn chọn một kênh, bot dùng profile ChatGPT đã đăng nhập của chính kênh đó
ở `data/chrome_profiles/chatgpt/chrome_chatgpt_<channel_id>`. Bot chỉ dùng
`chrome_chatgpt_telebot` khi không có channel ID.

Model Whisper duoc cache tai `%USERPROFILE%\.cache\huggingface\hub`; cac lan chay sau se dung lai model, khong tai lai.

Pipeline ghi log chi tiet vao `data\pipeline_events.jsonl`. Mo them mot cua so PowerShell va chay `scripts\watch_pipeline_log.bat`; moi bai se hien cac buoc `crawl`, `ai_script`, `content_validation`, `evidence_guard`, `visual_grounding`, `quality_gate`, `media_assets`, `voice`, `render`, `video_qa`, `upload`, `sheet` va `done/failed`.

Neu launcher khong tu tim thay Python, dat duong dan thu cong truoc khi chay:

```bat
set MANYACCOUNT_PYTHON=C:\Users\Acer\AppData\Local\Programs\Python\Python311\python.exe
scripts\setup_windows.bat
```

Profile ChatGPT duoc luu trong `data\chrome_profiles\chatgpt`. Sau khi login profile chung, co the clone sang cac kenh bang lenh:

```powershell
& .venv\Scripts\python.exe apps\creator_facebook\chatgpt_automator.py clone id_kenh_1 id_kenh_2
```
