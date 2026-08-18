#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p "../logs"
LOG_FILE="../logs/tele_bot_$(date +%Y%m%d_%H%M%S).log"

echo "========================================"
echo " KHỞI ĐỘNG TELEGRAM BOT"
echo " Log file: $LOG_FILE"
echo "========================================"

source "../.venv/bin/activate"
python3 -u "../apps/telegram_bot/tele_desktop_app.py" 2>&1 | tee "$LOG_FILE"
