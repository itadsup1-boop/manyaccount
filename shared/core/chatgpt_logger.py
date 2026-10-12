#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  chatgpt_logger.py — Bộ ghi log chi tiết cho các lượt gọi ChatGPT

  Lưu vết toàn bộ:
  - Prompt gửi đi
  - Raw response từ ChatGPT UI
  - JSON result sau khi parse
  - Metadata kênh (id_tiktok), URL bài viết/nguồn, timestamp, status
═══════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from typing import Any, Mapping

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHATGPT_LOG_DIR = os.path.join(PROJECT_ROOT, "data", "chatgpt_logs")
HISTORY_LOG_PATH = os.path.join(CHATGPT_LOG_DIR, "chatgpt_history.jsonl")

_LOG_LOCK = threading.Lock()


def _sanitize_id(id_tiktok: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(id_tiktok or "").replace("@", "").strip()).strip("_") or "general"


def save_chatgpt_log(
    prompt: str,
    raw_response: str,
    parsed_result: Mapping[str, Any] | None = None,
    *,
    id_tiktok: str = "",
    source_url: str = "",
    source_type: str = "article",
    status: str = "SUCCESS",
    error_message: str | None = None,
) -> str:
    """
    Lưu log tương tác ChatGPT vào:
    1. Single JSON file: data/chatgpt_logs/chatgpt_{timestamp}_{clean_id}.json
    2. Stream JSONL file: data/chatgpt_logs/chatgpt_history.jsonl
    3. Trả về đường dẫn file log JSON đơn lẻ.
    """
    os.makedirs(CHATGPT_LOG_DIR, exist_ok=True)

    clean_id = _sanitize_id(id_tiktok)
    now = datetime.now().astimezone()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")
    iso_time = now.isoformat(timespec="seconds")

    log_entry = {
        "timestamp": iso_time,
        "source_type": str(source_type or "article"),
        "id_tiktok": clean_id,
        "source_url": str(source_url or ""),
        "status": str(status or "SUCCESS"),
        "error_message": str(error_message) if error_message else None,
        "prompt": str(prompt or ""),
        "raw_response": str(raw_response or ""),
        "parsed_result": dict(parsed_result) if parsed_result is not None else None,
    }

    # 1. Lưu file JSON riêng cho lượt gọi này
    single_file_name = f"chatgpt_{timestamp_str}_{clean_id}.json"
    single_file_path = os.path.join(CHATGPT_LOG_DIR, single_file_name)

    try:
        with open(single_file_path, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"      ⚠️ Lỗi lưu file ChatGPT log riêng: {e}")

    # 2. Ghi dòng tổng hợp vào chatgpt_history.jsonl
    history_summary = {
        "ts": iso_time,
        "source_type": source_type,
        "id_tiktok": clean_id,
        "source_url": source_url,
        "status": status,
        "error_message": str(error_message) if error_message else None,
        "prompt_len": len(prompt or ""),
        "raw_response_len": len(raw_response or ""),
        "log_file": single_file_name,
        "hook_summary": str(parsed_result.get("hook", ""))[:80] if isinstance(parsed_result, dict) else "",
    }

    with _LOG_LOCK:
        try:
            with open(HISTORY_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(history_summary, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"      ⚠️ Lỗi ghi history ChatGPT log: {e}")

    # 3. Đồng bộ sự kiện vào pipeline_events.jsonl nếu có module quality_log
    try:
        from shared.core.quality_log import append_pipeline_event
        append_pipeline_event(
            pipeline=f"chatgpt_{source_type}",
            item_id=source_url or clean_id,
            stage="ai_script",
            event="chatgpt_logged",
            channel_id=clean_id,
            message=f"ChatGPT [{status}] Log saved: {single_file_name}",
            error_code="" if status == "SUCCESS" else status,
            metadata={
                "log_file": single_file_name,
                "status": status,
                "prompt_len": len(prompt or ""),
                "response_len": len(raw_response or ""),
            },
        )
    except Exception:
        pass

    return single_file_path
