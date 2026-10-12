#!/bin/bash
echo "Starting Adsup Central Hub..."

# Lấy đường dẫn thư mục hiện tại
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(cd "$DIR/.." && pwd)"

# Dọn dẹp tiến trình cũ để tránh lỗi 'Address already in use'
echo "Cleaning up old processes..."
pkill -9 -f "uvicorn main:app" >/dev/null 2>&1
pkill -9 -f "vite" >/dev/null 2>&1
# Dọn các Matrix scheduler/worker bị tách khỏi tiến trình cha ở phiên trước.
# Telegram bot không dùng worker.py này nên không bị ảnh hưởng.
pkill -TERM -f "$PROJECT_ROOT/apps/uploader_tiktok/scheduler_manager.py" >/dev/null 2>&1
pkill -TERM -f "$PROJECT_ROOT/shared/core/worker.py" >/dev/null 2>&1
sleep 1
pkill -KILL -f "$PROJECT_ROOT/apps/uploader_tiktok/scheduler_manager.py" >/dev/null 2>&1
pkill -KILL -f "$PROJECT_ROOT/shared/core/worker.py" >/dev/null 2>&1
fuser -k -9 8000/tcp >/dev/null 2>&1
fuser -k -9 5173/tcp >/dev/null 2>&1
pkill -9 -f "cloudflared.*tunnel" >/dev/null 2>&1
sleep 1

# Start Backend (chạy ngầm)
echo "Starting FastAPI Backend on port 8000..."
source "$DIR/../.venv/bin/activate"
cd "$DIR/backend"
uvicorn main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# Chờ Backend sẵn sàng trước khi khởi động Frontend
echo "⏳ Chờ FastAPI Backend khởi động (tối đa 30 giây)..."
WAITED=0
until curl -s --max-time 1 http://127.0.0.1:8000/docs > /dev/null 2>&1; do
    if [ $WAITED -ge 30 ]; then
        echo "❌ Backend không khởi động được sau 30 giây. Kiểm tra lỗi bên trên."
        break
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done
if [ $WAITED -lt 30 ]; then
    echo "✅ Backend đã sẵn sàng sau ${WAITED}s!"
fi

# Start Frontend (chạy ngầm)
echo "Starting Vite Frontend..."
cd "$DIR/frontend"
npm run dev &
FRONTEND_PID=$!

# Start Cloudflare Tunnel (chạy ngầm - miễn phí, không giới hạn băng thông)
echo "Starting Cloudflare Tunnel for port 5173..."
pkill -9 -f "cloudflared.*tunnel" >/dev/null 2>&1
rm -f /tmp/cloudflared_adsup_hub.log
cloudflared tunnel --config /dev/null --url http://localhost:5173 > /tmp/cloudflared_adsup_hub.log 2>&1 &
CLOUDFLARED_PID=$!

# Lấy link Cloudflare Tunnel từ log
TUNNEL_URL=""
for i in {1..30}; do
    TUNNEL_URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' /tmp/cloudflared_adsup_hub.log 2>/dev/null | head -n 1)
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
    sleep 1
done

echo "=========================================="
echo -e "✅ HỆ THỐNG ĐÃ KHỞI ĐỘNG THÀNH CÔNG THỐNG NHẤT!"
echo -e "🌐 Truy cập Web Hub (Bài Báo, Facebook, TikTok, Video Affiliate) tại: http://localhost:5173"
echo -e "🛍️ Tool Video Affiliate trực tiếp tại: http://localhost:5173/affiliate"
echo -e "🔧 Backend API chạy tại: http://localhost:8000"
if [ -n "$TUNNEL_URL" ]; then
    echo -e "🚀 Link Cloudflare Tunnel (Remote): \033[0;36m${TUNNEL_URL}\033[0m"
else
    echo -e "❌ Không lấy được link Cloudflare Tunnel. Xem log: /tmp/cloudflared_adsup_hub.log"
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
    pkill -9 -f "cloudflared.*tunnel" >/dev/null 2>&1
    exit 0
}

# Bẫy sự kiện Ctrl+C để kill sạch sẽ
trap cleanup INT TERM EXIT

# Đợi các process chạy
wait
