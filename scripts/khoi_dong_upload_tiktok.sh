#!/bin/bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==================================================="
echo "   HỆ THỐNG KHỞI ĐỘNG AUTO TIKTOK + VOICE STUDIO   "
echo "==================================================="

VOICE_STARTED_BY_US=0

# 1. Kiểm tra tiến trình Voice (cổng 8080)
echo "[1/3] Đang kiểm tra trạng thái Voice server..."
PIDS=$(lsof -t -i:8080)
if [ ! -z "$PIDS" ]; then
    echo "-> Đã phát hiện Voice server đang chạy (PID: $PIDS). Bỏ qua bước khởi động Voice và giữ nguyên tiến trình này."
else
    # 2. Bật Voicebox (Chạy ngầm để chờ lệnh) nếu chưa chạy
    echo "[2/3] Đang bật Tool Voice chạy ngầm chờ lệnh (Background)..."
    cd /home/giang-adsup/Documents/voiceHA_Long_Hung
    # Chạy script start_viterbox.sh ngầm và đẩy log vào server_output.log
    nohup ./start_viterbox.sh > server_output.log 2>&1 &
    VOICE_PID=$!
    VOICE_STARTED_BY_US=1
    echo "-> Voicebox đã khởi động (PID: $VOICE_PID). Chờ 5 giây để nạp model..."
    sleep 5
fi

# 3. Bật Tool Tiktok Many Account (Hiển thị Giao diện)
echo "[3/3] Đang khởi động Giao diện Tool Tiktok..."
cd "$DIR/.."
# Kích hoạt môi trường ảo của tool
source .venv/bin/activate
# Chạy giao diện
python3 "$DIR/../apps/uploader_tiktok/desktop_app.py"

# 4. Khi người dùng tắt giao diện Tool Tiktok đi, dọn dẹp nếu cần
echo "==================================================="
echo "Giao diện Tool Tiktok đã đóng."
if [ "$VOICE_STARTED_BY_US" -eq 1 ]; then
    echo "Đang tắt Tool Voice đã khởi động cùng script..."
    kill -9 $VOICE_PID 2>/dev/null
    kill -9 $(lsof -t -i:8080) 2>/dev/null
else
    echo "Giữ nguyên Tool Voice vì đã được khởi động từ trước."
fi
echo "Đã dọn dẹp hệ thống. Tạm biệt!"
echo "==================================================="
