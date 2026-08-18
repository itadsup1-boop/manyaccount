#!/usr/bin/env python3
"""
Script tạo bảng database cho Facebook News Pipeline.
Chạy: python3 setup_database.py

Vì Supabase anon key không hỗ trợ DDL (CREATE TABLE),
bạn cần paste SQL vào Supabase Dashboard > SQL Editor.
Script này sẽ mở trình duyệt cho bạn.
"""

import webbrowser
import os
import sys

SUPABASE_PROJECT_REF = "iynwmytfroatvzhbkodf"
SQL_FILE = os.path.join(os.path.dirname(__file__), "src", "database", "migrations", "001_create_tables.sql")

def main():
    print("╔═══════════════════════════════════════════════════╗")
    print("║  🗄️  Setup Database — Facebook News Pipeline      ║")
    print("╚═══════════════════════════════════════════════════╝")
    print()

    # Đọc SQL
    if not os.path.exists(SQL_FILE):
        print(f"❌ Không tìm thấy file SQL: {SQL_FILE}")
        sys.exit(1)

    with open(SQL_FILE, "r") as f:
        sql = f.read()

    print("📋 SQL đã được copy. Làm theo 3 bước sau:\n")
    print("   BƯỚC 1: Trình duyệt sẽ mở Supabase SQL Editor")
    print("   BƯỚC 2: Paste (Ctrl+V) toàn bộ SQL vào editor")
    print("   BƯỚC 3: Nhấn nút [Run] (nút xanh góc phải)\n")

    # Copy SQL vào clipboard (nếu có xclip)
    try:
        proc = os.popen("which xclip", "r")
        has_xclip = bool(proc.read().strip())
        proc.close()

        if has_xclip:
            os.popen(f'echo """{sql}""" | xclip -selection clipboard')
            print("✅ SQL đã được copy vào clipboard!")
        else:
            # Fallback: ghi ra file tạm
            tmp_file = "/tmp/fb_migration.sql"
            with open(tmp_file, "w") as f:
                f.write(sql)
            print(f"📄 SQL đã ghi vào: {tmp_file}")
            print(f"   Copy bằng lệnh: cat {tmp_file} | xclip -selection clipboard")
    except:
        pass

    print()
    input("👉 Nhấn ENTER để mở Supabase Dashboard... ")

    # Mở trình duyệt
    url = f"https://supabase.com/dashboard/project/{SUPABASE_PROJECT_REF}/sql/new"
    webbrowser.open(url)

    print()
    print(f"🌐 Đã mở: {url}")
    print()
    print("─" * 55)
    print("Sau khi chạy SQL xong, quay lại app Facebook News")
    print("và nhấn nút 🔄 Refresh để kiểm tra.")
    print("─" * 55)


if __name__ == "__main__":
    main()
