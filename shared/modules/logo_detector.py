"""
Auto-detect logo/watermark regions in video frames.
Uses temporal variance analysis — logo pixels are static across frames.
No external dependencies beyond FFmpeg.
"""
import os
import subprocess
import json


def _get_duration(path):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(json.loads(r.stdout)["format"]["duration"])


def _extract_gray_frame(path, timestamp, W=135, H=240):
    """Returns W*H raw grayscale bytes via FFmpeg pipe. No external libs."""
    cmd = [
        "ffmpeg", "-y", "-ss", str(timestamp), "-i", path,
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=disable",
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=15)
    data = r.stdout
    return data[:W * H] if r.returncode == 0 and len(data) >= W * H else None


def detect_logo_regions(video_path: str, scale_w=135, scale_h=240, corner_frac=0.27):
    """
    Detect static watermark/logo regions in the 4 corners of a video.

    Works by extracting frames at multiple timestamps and finding pixels
    that barely change (logo pixels are composited on top, always the same).

    Returns:
        List of (x, y, w, h) tuples in 1080x1920 coordinates.
        Empty list if nothing detected or on error.
    """
    try:
        dur = _get_duration(video_path)
        # Spread 6 samples across the video
        timestamps = [max(0.5, dur * t) for t in [0.05, 0.2, 0.4, 0.6, 0.8, 0.95]]

        frames = []
        for t in timestamps:
            f = _extract_gray_frame(video_path, t, scale_w, scale_h)
            if f:
                frames.append(f)

        if len(frames) < 3:
            return []

        # Sum of absolute differences across consecutive frame pairs
        n = scale_w * scale_h
        variance = bytearray(n)
        for j in range(len(frames) - 1):
            fa, fb = frames[j], frames[j + 1]
            for i in range(n):
                variance[i] = min(255, variance[i] + abs(fa[i] - fb[i]))

        # Pixel is "static" if average diff per pair < 25
        THRESHOLD = 25 * (len(frames) - 1)

        # Corner scan area
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
            sx, sy = [], []
            for row in range(cy, cy + cch):
                for col in range(cx, cx + ccw):
                    if variance[row * scale_w + col] < THRESHOLD:
                        sx.append(col)
                        sy.append(row)

            if len(sx) < 12:
                continue

            min_x, max_x = min(sx), max(sx)
            min_y, max_y = min(sy), max(sy)

            if (max_x - min_x) < 4 or (max_y - min_y) < 4:
                continue

            pad = 4
            abs_x = max(0, int((min_x - pad) * scale_x))
            abs_y = max(0, int((min_y - pad) * scale_y))
            abs_w = min(1080 - abs_x, int((max_x - min_x + pad * 2 + 1) * scale_x))
            abs_h = min(1920 - abs_y, int((max_y - min_y + pad * 2 + 1) * scale_y))

            results.append((abs_x, abs_y, abs_w, abs_h))

        return results

    except Exception as e:
        print(f"   ⚠️ Logo detection lỗi: {e}")
        return []
