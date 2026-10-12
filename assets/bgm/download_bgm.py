import os
import subprocess

bgm_dir = "/home/giang-adsup/Documents/mannyAccount/assets/bgm"
queries = {
    "Vui_ve": "happy upbeat no copyright background music",
    "Hoi_hop": "suspense dark no copyright background music",
    "Cam_dong": "sad emotional piano no copyright background music",
    "Kich_tinh": "epic action no copyright background music",
    "Nhe_nhang": "chill lofi hiphop no copyright background music",
    "Trung_tinh": "corporate inspiring no copyright background music"
}

for tone, query in queries.items():
    print(f"Downloading {tone}...")
    cmd = [
        "yt-dlp",
        f"ytsearch3:{query}",
        "--match-filter", "duration < 240",
        "-x", "--audio-format", "mp3",
        "-o", f"{bgm_dir}/{tone}_%(id)s.%(ext)s"
    ]
    subprocess.run(cmd)
