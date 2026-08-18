import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(APP_DIR)) # /home/giang-adsup/Documents/mannyAccount

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, APP_DIR)

import time
import subprocess
from datetime import datetime
import json
from shared.services.tele_reporter import TeleReporter
from shared.services.supabase_api import SupabaseAPI

MAX_CONCURRENT_WORKERS = 2
MAX_CONCURRENT_WORKERS_HARD_LIMIT = 2

def get_max_concurrent_workers(schedule_config=None):
    raw_value = None
    if isinstance(schedule_config, dict):
        raw_value = schedule_config.get("max_concurrent_workers")
    if raw_value is None:
        raw_value = os.getenv("MATRIX_MAX_CONCURRENT_WORKERS", MAX_CONCURRENT_WORKERS)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = MAX_CONCURRENT_WORKERS
    return max(1, min(MAX_CONCURRENT_WORKERS_HARD_LIMIT, value))

def get_active_accounts():
    try:
        local_machine_file = os.path.join(PROJECT_ROOT, "config", "local_machine.json")
        try:
            with open(local_machine_file, "r") as f:
                local_machine_id = json.load(f).get("machine_id", "1")
        except:
            local_machine_id = "1"

        accounts = SupabaseAPI.get_all_active_accounts()
        active_ids = [
            acc["tiktok_id"]
            for acc in accounts
            if acc.get("active") and str(acc.get("machine_id", "1")) == str(local_machine_id)
        ]
        return active_ids
    except Exception as e:
        print(f"❌ Lỗi khi lấy danh sách account: {e}")
        return []

def run_worker_batch(account_ids):
    processes = []
    print(f"   🚀 Đang khởi động {len(account_ids)} luồng song song...")

    for acc_id in account_ids:
        worker_script = os.path.join(PROJECT_ROOT, "shared", "core", "worker.py")
        cmd = [sys.executable, worker_script, acc_id]

        try:
            p = subprocess.Popen(cmd, cwd=PROJECT_ROOT)
            processes.append((acc_id, p))
            print(f"      ▶️  Đã kích hoạt: {acc_id} (PID: {p.pid})")
        except Exception as e:
            print(f"      ❌ Lỗi kích hoạt {acc_id}: {e}")

    print(f"   ⏳ Đang chờ {len(processes)} luồng hoàn tất xử lý...")
    finished_count = 0
    total = len(processes)

    while finished_count < total:
        time.sleep(2)
        finished_count = sum(1 for _, p in processes if p.poll() is not None)

    print(f"   ✅ Đợt chạy này đã hoàn tất (100%).")

def start_schedule_loop():
    print("="*60)
    print(f"🤖 MATRIX SCHEDULER - FULL CLOUD (SUPABASE)")
    print(f"⚡ Max Concurrent Workers: {MAX_CONCURRENT_WORKERS_HARD_LIMIT}")
    print("="*60)

    last_run_time = ""

    while True:
        try:
            now = datetime.now()
            current_hhmm = now.strftime("%H:%M")

            sch_config = SupabaseAPI.get_system_config("schedule_config") or {}
            crawl_times = sch_config.get("crawl_times", [])
            max_workers = get_max_concurrent_workers(sch_config)

            if current_hhmm in crawl_times and current_hhmm != last_run_time:
                sys.stdout.write("\033[K")
                print(f"\n⏰ [TRIGGER] Đã đến giờ chạy theo lịch Supabase: {current_hhmm}")
                last_run_time = current_hhmm

                active_ids = get_active_accounts()

                if not active_ids:
                    print("   ⚠️ Không có tài khoản nào đang Active trên Supabase.")
                else:
                    print(f"   📋 Danh sách chạy: {active_ids}")

                    total_accs = len(active_ids)
                    for i in range(0, total_accs, max_workers):
                        batch = active_ids[i : i + max_workers]
                        total_batches = (total_accs + max_workers - 1) // max_workers
                        print(f"\n   📦 [BATCH] Chạy nhóm {i//max_workers + 1}/{total_batches}: {batch}")
                        run_worker_batch(batch)
                        if i + max_workers < total_accs:
                            print("   💤 Nghỉ 10s trước khi chạy nhóm tiếp theo...")
                            time.sleep(10)

                print(f"\n🏁 [SESSION DONE] Đã chạy xong lịch trình {current_hhmm}\n")
                try:
                    TeleReporter.send_summary_report(current_hhmm)
                except Exception as e:
                    print(f"   ⚠️ Lỗi khi gửi báo cáo Tele: {e}")
            if now.second % 10 == 0:
                print(f"⏳ [{current_hhmm}] Đang chờ lịch (Lịch trên DB: {crawl_times})...", end="\r", flush=True)
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Đã dừng thủ công.")
            break
        except Exception as e:
            print(f"\n❌ Lỗi Scheduler Main Loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    start_schedule_loop()
