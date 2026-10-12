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
try:
    WORKER_TIMEOUT_SECONDS = max(
        300,
        int(os.getenv("MATRIX_WORKER_TIMEOUT_SECONDS", "2400")),
    )
except (TypeError, ValueError):
    WORKER_TIMEOUT_SECONDS = 2400

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
    print(f"   🚀 Đang khởi động {len(account_ids)} luồng song song...", flush=True)

    for acc_id in account_ids:
        worker_script = os.path.join(PROJECT_ROOT, "shared", "core", "worker.py")
        # -u is important here: stdout is redirected to a per-account log and
        # otherwise Python buffers prints until the worker exits, making a live
        # run look frozen in both the scheduler terminal and worker log.
        cmd = [sys.executable, "-u", worker_script, acc_id]

        try:
            # Worker không được kế thừa stdout pipe của Hub. Giữ cả các
            # print() của TTS/Drive trong file riêng để tra cứu link khi cần.
            console_dir = os.path.join(PROJECT_ROOT, "shared", "data", acc_id)
            os.makedirs(console_dir, exist_ok=True)
            console_path = os.path.join(console_dir, "worker_console.log")
            with open(console_path, "a", encoding="utf-8") as console_file:
                p = subprocess.Popen(
                    cmd,
                    cwd=PROJECT_ROOT,
                    stdout=console_file,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                )
            processes.append((acc_id, p))
            print(f"      ▶️  Đã kích hoạt: {acc_id} (PID: {p.pid})", flush=True)
        except Exception as e:
            print(f"      ❌ Lỗi kích hoạt {acc_id}: {e}", flush=True)

    print(f"   ⏳ Đang chờ {len(processes)} luồng hoàn tất xử lý...", flush=True)
    finished_count = 0
    total = len(processes)
    started_at = time.monotonic()
    reported_finished = set()
    last_heartbeat = started_at

    while finished_count < total:
        time.sleep(2)
        now = time.monotonic()
        for acc_id, process in processes:
            return_code = process.poll()
            if return_code is not None and acc_id not in reported_finished:
                reported_finished.add(acc_id)
                if return_code == 0:
                    print(f"      ✅ Worker hoàn tất: {acc_id} (PID: {process.pid})", flush=True)
                else:
                    print(
                        f"      ⚠️ Worker kết thúc lỗi: {acc_id} "
                        f"(PID: {process.pid}, exit={return_code}); xem worker_console.log",
                        flush=True,
                    )
        finished_count = len(reported_finished)
        if finished_count < total and now - last_heartbeat >= 30:
            running = [acc_id for acc_id, process in processes if process.poll() is None]
            elapsed = int(now - started_at)
            print(
                f"   🔄 Batch vẫn đang chạy ({elapsed}s): {running}; "
                "log chi tiết nằm trong shared/data/<account>/worker_console.log",
                flush=True,
            )
            last_heartbeat = now
        if finished_count < total and time.monotonic() - started_at >= WORKER_TIMEOUT_SECONDS:
            print(
                f"   ⚠️ Batch quá thời gian cho phép ({WORKER_TIMEOUT_SECONDS}s); "
                "dừng worker còn treo để không khóa các batch sau.",
                flush=True,
            )
            for acc_id, process in processes:
                if process.poll() is None:
                    try:
                        process.terminate()
                        print(f"      🛑 Đã yêu cầu dừng worker treo: {acc_id} (PID: {process.pid})", flush=True)
                    except Exception as error:
                        print(f"      ⚠️ Không dừng được worker {acc_id}: {error}", flush=True)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and any(
                process.poll() is None for _, process in processes
            ):
                time.sleep(1)
            for acc_id, process in processes:
                if process.poll() is None:
                    try:
                        process.kill()
                        print(f"      🛑 Đã kill worker vẫn còn treo: {acc_id} (PID: {process.pid})", flush=True)
                    except Exception:
                        pass
            break

    print(f"   ✅ Đợt chạy này đã hoàn tất ({finished_count}/{total} worker kết thúc).", flush=True)

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
