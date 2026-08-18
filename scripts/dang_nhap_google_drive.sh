
#!/bin/bash
cd /home/giang-adsup/Documents/mannyAccount

echo "=================================================="
echo "🔑 CÔNG CỤ ĐĂNG NHẬP / CHUYỂN TÀI KHOẢN GOOGLE DRIVE"
echo "=================================================="
echo ""

if [ -f "config/token.pickle" ]; then
    echo "⚠️ Phát hiện máy tính đang lưu một phiên đăng nhập Google cũ."
    read -p "Bạn có muốn xóa tài khoản cũ này để đăng nhập tài khoản mới không? (y/n): " answer
    if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
        rm -f config/token.pickle
        echo "✅ Đã xóa phiên đăng nhập cũ."
    else
        echo "⏭️ Giữ nguyên phiên đăng nhập cũ."
    fi
    echo ""
fi

echo "🚀 Đang bật trình duyệt để kết nối Google Drive..."
echo "Vui lòng chọn tài khoản và bấm 'Cho phép' (Allow) trên trình duyệt."
echo "--------------------------------------------------"

source .venv/bin/activate
python3 shared/modules/upload_drive.py

echo "--------------------------------------------------"
echo "🎉 Quá trình đăng nhập đã hoàn tất!"
echo "LƯU Ý: Nếu bạn upload vào thư mục mới, hãy nhớ mở file .env để sửa lại DRIVE_FOLDER_ID nhé."
echo ""
read -n 1 -s -r -p "Bấm phím bất kỳ để thoát..."
echo ""
