"""tool_tk_webhook.py — Gửi video mới từ Tool Media sang dự án tool_tk đăng NGAY.

Dùng direct-upload API của tool_tk: backend nhận (channel, video, title) rồi
tự mở AdsPower đăng ngay không cần warmup. Nếu nick đang bận (GUI đang chạy
trên profile đó), tool_tk tự trả bài về làn ưu tiên của group và warmup đăng
ở chu kỳ kế. Nguyên tắc: TUYỆT ĐỐI KHÔNG RAISE — nếu webhook hỏng, tool_tk
vẫn nhận video qua đường dự phòng quét Sheet chu kỳ 10 phút.
"""
import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHANNELS_CONFIG_PATH = os.path.join(
    PROJECT_ROOT, "apps", "telegram_bot", "channels_config.json"
)


def _get_conf(key: str) -> str:
    """Đọc cấu hình từ os.environ, fallback đọc trực tiếp file .env dự án."""
    val = str(os.environ.get(key, "") or "").strip()
    if val:
        return val
    env_path = os.path.join(PROJECT_ROOT, ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _load_channel_field(channel_id: str, field: str) -> str:
    clean = str(channel_id or "").strip()
    if not clean:
        return ""
    try:
        with open(CHANNELS_CONFIG_PATH, "r", encoding="utf-8") as f:
            channels = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"[TOOLTK WEBHOOK] Không đọc được channels_config.json: {exc}")
        return ""
    info = channels.get(clean)
    if not isinstance(info, dict):
        return ""
    return str(info.get(field, "") or "").strip()


def notify_new_video(channel_id: str, row_index, title: str, drive_link: str) -> bool:
    """POST /api/media-webhooks/direct-upload (đăng ngay, không warmup). Không raise.

    channel_id là key kênh trong channels_config.json; nick tool_tk và group
    được tra từ field tool_tk_channel / upload_group của kênh đó.
    """
    url = _get_conf("TOOLTK_WEBHOOK_URL")
    token = _get_conf("TOOLTK_WEBHOOK_TOKEN")
    channel = _load_channel_field(channel_id, "tool_tk_channel")
    group = _load_channel_field(channel_id, "upload_group")
    if not (url and token and channel and drive_link):
        logger.info(
            "[TOOLTK WEBHOOK] Bỏ qua: thiếu cấu hình hoặc dữ liệu "
            f"(url={bool(url)} token={bool(token)} channel={channel!r} link={bool(drive_link)})."
        )
        return False
    try:
        row_index = int(row_index or 0)
    except (TypeError, ValueError):
        row_index = 0
    payload = json.dumps(
        {
            "channel": channel,
            "group": group,
            "row_index": row_index,
            "title": str(title or ""),
            "drive_link": str(drive_link or ""),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
        logger.info(
            f"[TOOLTK WEBHOOK] [{channel_id} → {channel}] dòng {row_index} → "
            f"{body.get('status')} (task_id={body.get('task_id')})."
        )
        return body.get("status") in ("queued_direct", "duplicate")
    except Exception as exc:
        logger.warning(
            f"[TOOLTK WEBHOOK] [{channel_id}] gọi webhook thất bại, bỏ qua "
            f"(tool_tk còn đường dự phòng quét Sheet): {exc}"
        )
        return False
