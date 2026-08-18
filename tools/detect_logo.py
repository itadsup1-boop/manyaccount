#!/usr/bin/env python3
"""
Phát hiện vị trí logo/watermark trong video Facebook.
Phân tích vùng pixel tĩnh (logo không di chuyển giữa các frame) ở 4 góc.

Usage:
    python tools/detect_logo.py <video_path>
    python tools/detect_logo.py <video_path> --frame /path/to/frame.jpg
"""

import sys
import os
import subprocess
import json

# ─── FFmpeg helpers ──────────────────────────────────────────────────────────

def get_duration(path):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def extract_gray_frame(path, timestamp, W=135, H=240):
    """Extract a single grayscale frame as raw bytes (W*H bytes). No deps."""
    cmd = [
        "ffmpeg", "-y", "-ss", str(timestamp), "-i", path,
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=disable",
        "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"
    ]
    r = subprocess.run(cmd, capture_output=True)
    data = r.stdout
    if r.returncode != 0 or len(data) < W * H:
        return None
    return data[:W * H]


# ─── Detection logic ─────────────────────────────────────────────────────────

def find_static_corners(path, scale_w=135, scale_h=240, corner_frac=0.27):
    """
    Extract frames at 6 timestamps, compute per-pixel temporal variance,
    find low-variance (static) regions in each corner.

    Returns list of (corner_name, x, y, w, h) in 1080x1920 space.
    """
    dur = get_duration(path)
    timestamps = [max(0.5, dur * t) for t in [0.05, 0.2, 0.35, 0.5, 0.65, 0.8]]

    frames = []
    for t in timestamps:
        f = extract_gray_frame(path, t, scale_w, scale_h)
        if f:
            frames.append(f)

    if len(frames) < 3:
        print("   ⚠️ Không đủ frame để phân tích.")
        return []

    # Tính tổng độ chênh lệch tuyệt đối giữa các frame liên tiếp
    n = scale_w * scale_h
    variance = bytearray(n)
    for j in range(len(frames) - 1):
        fa, fb = frames[j], frames[j + 1]
        for i in range(n):
            variance[i] = min(255, variance[i] + abs(fa[i] - fb[i]))

    # Ngưỡng: pixel tĩnh nếu tổng diff < threshold (trung bình < 25/pair)
    n_pairs = len(frames) - 1
    THRESHOLD = 25 * n_pairs

    # Xác định 4 góc trong tọa độ scaled
    cw = int(scale_w * corner_frac)
    ch = int(scale_h * corner_frac)
    corners = {
        "top_left":     (0,              0,               cw, ch),
        "top_right":    (scale_w - cw,   0,               cw, ch),
        "bottom_left":  (0,              scale_h - ch,    cw, ch),
        "bottom_right": (scale_w - cw,   scale_h - ch,    cw, ch),
    }

    scale_x = 1080 / scale_w
    scale_y = 1920 / scale_h
    results = []

    for name, (cx, cy, ccw, cch) in corners.items():
        static_xs = []
        static_ys = []
        for row in range(cy, cy + cch):
            for col in range(cx, cx + ccw):
                if variance[row * scale_w + col] < THRESHOLD:
                    static_xs.append(col)
                    static_ys.append(row)

        if len(static_xs) < 15:
            continue

        min_x, max_x = min(static_xs), max(static_xs)
        min_y, max_y = min(static_ys), max(static_ys)

        # Bỏ qua nếu quá nhỏ
        if (max_x - min_x) < 4 or (max_y - min_y) < 4:
            continue

        # Đổi về tọa độ 1080x1920 + thêm padding
        pad = 3
        abs_x = max(0, int((min_x - pad) * scale_x))
        abs_y = max(0, int((min_y - pad) * scale_y))
        abs_w = min(1080 - abs_x, int((max_x - min_x + pad * 2 + 1) * scale_x))
        abs_h = min(1920 - abs_y, int((max_y - min_y + pad * 2 + 1) * scale_y))

        results.append((name, abs_x, abs_y, abs_w, abs_h))
        print(f"   ✅ {name}: {len(static_xs)} pixel tĩnh → x={abs_x} y={abs_y} w={abs_w} h={abs_h}")

    return results


# ─── Save annotated frame ─────────────────────────────────────────────────────

def save_annotated_frame(path, output_jpg, regions):
    """Extract a frame and draw red boxes around detected regions + corner coordinates."""
    vf_parts = [
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    ]
    for _, x, y, w, h in regions:
        vf_parts.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=red@0.9:t=4")

    # Góc tọa độ tham chiếu
    labels = [
        ("0,0",       10,   15),
        ("1080,0",    880,  15),
        ("0,1920",    10,   1890),
        ("1080,1920", 840,  1890),
    ]
    for text, tx, ty in labels:
        safe = text.replace(",", "\\,")
        vf_parts.append(f"drawtext=text='{safe}':x={tx}:y={ty}:fontsize=28:fontcolor=yellow:box=1:boxcolor=black@0.5")

    cmd = [
        "ffmpeg", "-y", "-ss", "2", "-i", path,
        "-vf", ",".join(vf_parts),
        "-frames:v", "1", output_jpg
    ]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    video_path = sys.argv[1]
    if not os.path.exists(video_path):
        print(f"❌ File không tồn tại: {video_path}")
        sys.exit(1)

    # --frame <path>
    custom_frame_out = None
    if "--frame" in sys.argv:
        idx = sys.argv.index("--frame")
        if idx + 1 < len(sys.argv):
            custom_frame_out = sys.argv[idx + 1]

    print(f"🔍 Phân tích logo: {os.path.basename(video_path)}")
    print(f"   Đang trích xuất frames...")

    regions = find_static_corners(video_path)

    print()
    if not regions:
        print("⚠️  Không phát hiện logo rõ ràng trong 4 góc.")
        print("   Thử mở frame ảnh để xem tọa độ thủ công.")
    else:
        print("💡 Cấu hình cho Supabase — cột 'delogo' của source này:")
        for name, x, y, w, h in regions:
            print(f"   [{name}]  x={x}:y={y}:w={w}:h={h}")

        if len(regions) == 1:
            _, x, y, w, h = regions[0]
            print(f"\n   → Nhập vào field 'delogo':  x={x}:y={y}:w={w}:h={h}")
        else:
            parts = ":".join(
                f"x={x}:y={y}:w={w}:h={h}"
                for _, x, y, w, h in regions
            )
            chained = ",delogo=".join(
                f"x={x}:y={y}:w={w}:h={h}"
                for _, x, y, w, h in regions
            )
            print(f"\n   → Nhập vào field 'delogo' (nhiều logo):")
            print(f"     {chained}")

    # Lưu frame có đánh dấu
    frame_out = custom_frame_out or os.path.join(
        os.path.dirname(os.path.abspath(video_path)),
        "logo_detect_" + os.path.splitext(os.path.basename(video_path))[0] + ".jpg"
    )
    print(f"\n🖼  Đang lưu frame có đánh dấu → {frame_out}")
    if save_annotated_frame(video_path, frame_out, regions):
        print(f"   Mở file này để kiểm tra (hình chữ nhật đỏ = vùng phát hiện)")
        print(f"   Góc ảnh có tọa độ tham chiếu (vàng) để đọc x,y thủ công nếu cần")
    else:
        print(f"   ⚠️ Không lưu được frame")


if __name__ == "__main__":
    main()
