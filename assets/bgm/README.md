# Background music library

The renderer recognizes these mood folders:

- `breaking_tension`
- `serious_warning`
- `neutral_news`
- `positive_upbeat`
- `sensitive_empathy`
- `sports_energy`
- `entertainment_drama`

Put only music that is licensed for the intended publishing platforms in these
folders. Audio files are ignored by Git, so keep the corresponding license proof
outside the repository or add its metadata to `catalog.json`.

Example catalog entry:

```json
{
  "id": "neutral_news_01",
  "file": "neutral_news/neutral_news_01.mp3",
  "moods": ["neutral_news"],
  "energy": 2,
  "cue_start_sec": 8.0,
  "license_status": "approved",
  "license_source": "Invoice, license URL, or internal asset reference",
  "enabled": true
}
```

Legacy files named `Vui_ve_*`, `Hoi_hop_*`, `Cam_dong_*`, `Kich_tinh_*`,
`Nhe_nhang_*`, and `Trung_tinh_*` remain supported. Their license status is
reported as `unverified` until catalog metadata is added.

Do not assume that a YouTube title containing “no copyright” grants commercial
usage rights. For TikTok-only commercial posts, add music from TikTok's
Commercial Music Library during publishing, or verify that the selected license
allows the automated editing workflow. For cross-platform publishing, use a
license that explicitly covers every target platform.
