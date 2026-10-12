#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

stop_existing_telegram_bot() {
    local pids=()
    while read -r pid cmd; do
        case "$cmd" in
            *python*tele_desktop_app.py*|*python*apps/telegram_bot/tele_bot.py*)
                [ "$pid" = "$$" ] || pids+=("$pid")
                ;;
        esac
    done < <(ps -eo pid=,args=)

    if command -v fuser >/dev/null 2>&1; then
        for pid in $(fuser "../data/telegram_bot.polling.lock" 2>/dev/null || true); do
            [ "$pid" = "$$" ] || pids+=("$pid")
        done
    fi

    [ "${#pids[@]}" -eq 0 ] && return
    echo "🛑 Đang dừng bot Telegram cũ: ${pids[*]}"
    kill -TERM "${pids[@]}" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
        sleep 1
        local alive=()
        for pid in "${pids[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then alive+=("$pid"); fi
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

mkdir -p "../logs"
LOG_FILE="../logs/tele_bot_$(date +%Y%m%d_%H%M%S).log"

echo "========================================"
echo " KHỞI ĐỘNG TELEGRAM BOT"
echo " Log file: $LOG_FILE"
echo "========================================"

source "../.venv/bin/activate"
python3 -u "../apps/telegram_bot/tele_desktop_app.py" 2>&1 | tee "$LOG_FILE"
