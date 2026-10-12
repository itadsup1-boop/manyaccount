# Nhập dữ liệu hiệu suất TikTok

Đợt 7 lưu metrics trong `data/performance.sqlite3`. File này là runtime state và
đã được `.gitignore`; không đưa dữ liệu tài khoản thật vào Git.

## Mốc đo

Mỗi video nên có snapshot ở `2h`, `24h`, `72h` và `168h` (7 ngày). Cùng một
`channel_id + video_id + measurement_window` sẽ được cập nhật thay vì tạo bản ghi
trùng. Nếu CSV không có `measurement_window`, importer tự suy ra từ
`published_at` và `measured_at`; ngoài các mốc chuẩn sẽ lưu dưới dạng `custom`.

## Chuẩn bị CSV

Dùng header trong `config/tiktok_metrics_template.csv`. Tối thiểu mỗi dòng phải có:

- `video_id`
- `channel_id` hoặc truyền `--channel-id`
- Các metrics hiện lấy được; field thiếu được giữ ở 0/unknown

Tỷ lệ chấp nhận cả `0.35`, `35` và `35%`; hệ thống luôn lưu chuẩn `0.35`.
Views/likes chấp nhận dạng `1,234`, `12.5K` hoặc số thường.

Nếu video thuộc A/B test, giữ thêm `experiment_id`, `experiment_variant`,
`experiment_variable` và `experiment_value`. Các cột `music_energy`,
`subtitle_style` và `cta_mode` giúp truy vết chính xác thuộc tính đã dựng. Không tự
suy luận variant từ tiêu đề hoặc số view.

## Kiểm tra trước khi ghi

~~~bash
.venv/bin/python scripts/import_tiktok_metrics.py \
  --input path/to/metrics.csv \
  --channel-id Adsupnews \
  --measurement-window 24h \
  --dry-run
~~~

## Nhập vào store

~~~bash
.venv/bin/python scripts/import_tiktok_metrics.py \
  --input path/to/metrics.csv \
  --channel-id Adsupnews \
  --measurement-window 24h \
  --report-json data/last_metrics_import.json
~~~

Có thể thay `--input` bằng Google Sheet export CSV:

~~~bash
.venv/bin/python scripts/import_tiktok_metrics.py \
  --sheet-csv-url 'https://docs.google.com/spreadsheets/d/.../export?format=csv' \
  --channel-id Adsupnews \
  --measurement-window 24h
~~~

Dùng `--strict` nếu muốn hủy toàn bộ lần nhập khi chỉ một dòng thiếu `video_id`
hoặc `channel_id`. Mặc định importer giữ các dòng hợp lệ và báo rõ số dòng lỗi.
Report chỉ có trạng thái `ready` khi đạt ngưỡng mặc định 30 video; nhóm ít mẫu vẫn
được hiển thị nhưng có `eligible=false`. Nếu views/like/share của snapshot sau thấp
hơn snapshot trước, report gắn cảnh báo `NON_MONOTONIC_*` để kiểm tra lại CSV.

Chỉ dùng file export thủ công hoặc API chính thức khi tài khoản được cấp quyền;
không crawl trang Analytics và không đưa cookie/token TikTok vào CSV.
