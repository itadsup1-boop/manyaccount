#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  THEO DÕI REAL-TIME CHATGPT LOGS (TIKTOK NEWS)
# ═══════════════════════════════════════════════════════════

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$DIR/data/chatgpt_logs/chatgpt_history.jsonl"

echo "==================================================="
echo "   HỆ THỐNG THEO DÕI LOG CHATGPT (REAL-TIME STREAM) "
echo "==================================================="
echo "Tệp log: $LOG_FILE"
echo "Bấm Ctrl+C để thoát."
echo "---------------------------------------------------"

mkdir -p "$DIR/data/chatgpt_logs"
touch "$LOG_FILE"

tail -n 20 -f "$LOG_FILE" | while read -r line; do
    if [ -n "$line" ]; then
        echo "$line"
    fi
done
