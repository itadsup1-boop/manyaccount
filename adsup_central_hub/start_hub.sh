#!/bin/bash
echo "Starting Adsup Central Hub..."

# Lấy đường dẫn thư mục hiện tại
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Dọn dẹp tiến trình cũ để tránh lỗi 'Address already in use'
echo "Cleaning up old processes..."
pkill -9 -f "uvicorn main:app" >/dev/null 2>&1
pkill -9 -f "vite" >/dev/null 2>&1
fuser -k -9 8000/tcp >/dev/null 2>&1
fuser -k -9 5173/tcp >/dev/null 2>&1
pkill -9 -f "cloudflared .*--url http://localhost:5173" >/dev/null 2>&1
sleep 1

# Start Backend (chạy ngầm)
echo "Starting FastAPI Backend on port 8000..."
cd "$DIR/backend"
source venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# Start Frontend (chạy ngầm)
echo "Starting Vite Frontend..."
cd "$DIR/frontend"
npm run dev &
FRONTEND_PID=$!

# Start Cloudflare Tunnel (chạy ngầm)
echo "Starting Cloudflare Tunnel for port 5173..."
# Ignore ~/.cloudflared/config.yml so this quick tunnel is not affected by
# existing named-tunnel ingress rules.
cloudflared --config /dev/null tunnel --url http://localhost:5173 > /tmp/cf_adsup_hub.log 2>&1 &
CF_PID=$!

# Lấy link Cloudflare
CF_URL=""
for i in {1..15}; do
    CF_URL=$(grep -o 'https://[^[:space:]]*\.trycloudflare\.com' /tmp/cf_adsup_hub.log | head -n 1)
    if [ -n "$CF_URL" ]; then
        break
    fi
    sleep 1
done

echo "=========================================="
echo -e "✅ HỆ THỐNG ĐÃ KHỞI ĐỘNG THÀNH CÔNG!"
echo -e "🌐 Truy cập giao diện Web tại: http://localhost:5173"
echo -e "🔧 Backend API chạy tại: http://localhost:8000"
if [ -n "$CF_URL" ]; then
    echo -e "☁️  Link Cloudflare (Remote): \033[0;36m${CF_URL}\033[0m"
else
    echo -e "❌ Không lấy được link Cloudflare. Xem log: /tmp/cf_adsup_hub.log"
fi
echo "=========================================="
echo "Bấm Ctrl+C để tắt toàn bộ hệ thống."

# Hàm dọn dẹp khi thoát
cleanup() {
    echo -e "\nĐang tắt hệ thống..."
    pkill -9 -f "uvicorn main:app" >/dev/null 2>&1
    pkill -9 -f "vite" >/dev/null 2>&1
    fuser -k -9 8000/tcp >/dev/null 2>&1
    fuser -k -9 5173/tcp >/dev/null 2>&1
    pkill -9 -f "cloudflared .*--url http://localhost:5173" >/dev/null 2>&1
    exit 0
}

# Bẫy sự kiện Ctrl+C để kill sạch sẽ
trap cleanup INT TERM EXIT

# Đợi các process chạy
wait
