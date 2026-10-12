#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

stop_existing_telegram_bot() {
    # Dừng đúng các tiến trình của Telegram bot trong project này. Không dùng
    # pkill python chung vì còn nhiều worker Python khác đang chạy.
    local pids=()
    while read -r pid cmd; do
        case "$cmd" in
            *python*tele_desktop_app.py*|*python*apps/telegram_bot/tele_bot.py*)
                [ "$pid" = "$$" ] || pids+=("$pid")
                ;;
        esac
    done < <(ps -eo pid=,args=)

    # Nếu bot được khởi chạy bằng đường dẫn tương đối hoặc đã đổi tên argv,
    # dùng chính file lock để tìm thêm tiến trình đang giữ polling.
    if command -v fuser >/dev/null 2>&1; then
        for pid in $(fuser "$DIR/data/telegram_bot.polling.lock" 2>/dev/null || true); do
            [ "$pid" = "$$" ] || pids+=("$pid")
        done
    fi

    if [ "${#pids[@]}" -eq 0 ]; then
        return
    fi

    echo "🛑 Đang dừng bot Telegram cũ: ${pids[*]}"
    kill -TERM "${pids[@]}" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
        sleep 1
        local alive=()
        for pid in "${pids[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                alive+=("$pid")
            fi
        done
        [ "${#alive[@]}" -eq 0 ] && break
        pids=("${alive[@]}")
    done
    if [ "${#pids[@]}" -gt 0 ]; then
        echo "⚠️ Bot cũ chưa thoát, buộc dừng: ${pids[*]}"
        kill -KILL "${pids[@]}" 2>/dev/null || true
    fi
}

stop_existing_telegram_bot
source .venv/bin/activate
python3 apps/telegram_bot/tele_desktop_app.py
