#!/bin/bash
echo "========================================"
echo " KHỞI ĐỘNG TOOL BÁO MẠNG (ARTICLE)"
echo "========================================"

# Lấy thư mục hiện tại của script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Kiểm tra virtual environment
if [ -d "$DIR/../.venv" ]; then
    source "$DIR/../.venv/bin/activate"
else
    echo "⚠️ Không tìm thấy môi trường ảo ở $DIR/../.venv"
    echo "Vui lòng kiểm tra lại!"
    exit 1
fi

# Chạy giao diện Desktop cho Bài báo
python3 "$DIR/../apps/creator_article/article_desktop_app.py"
