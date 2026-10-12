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
import shutil
import subprocess
import sys

SUPABASE_PROJECT_REF = "iynwmytfroatvzhbkodf"
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "database", "migrations")

def main():
    print("╔═══════════════════════════════════════════════════╗")
    print("║  🗄️  Setup Database — Facebook News Pipeline      ║")
    print("╚═══════════════════════════════════════════════════╝")
    print()

    migration_files = sorted(
        os.path.join(MIGRATIONS_DIR, name)
        for name in os.listdir(MIGRATIONS_DIR)
        if name.endswith(".sql")
    ) if os.path.isdir(MIGRATIONS_DIR) else []
    if not migration_files:
        print(f"❌ Không tìm thấy migration SQL trong: {MIGRATIONS_DIR}")
        sys.exit(1)

    sql_parts = []
    for migration_file in migration_files:
        with open(migration_file, "r", encoding="utf-8") as f:
            sql_parts.append(f"-- FILE: {os.path.basename(migration_file)}\n{f.read()}")
    sql = "\n\n".join(sql_parts)

    print(f"📋 Đã nạp {len(migration_files)} migration. Làm theo 3 bước sau:\n")
    print("   BƯỚC 1: Trình duyệt sẽ mở Supabase SQL Editor")
    print("   BƯỚC 2: Paste (Ctrl+V) toàn bộ SQL vào editor")
    print("   BƯỚC 3: Nhấn nút [Run] (nút xanh góc phải)\n")

    # Copy SQL vào clipboard (nếu có xclip)
    try:
        if shutil.which("xclip"):
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=sql,
                text=True,
                check=True,
            )
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
