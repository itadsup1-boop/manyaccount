# Đo retention và watch time

## Mục tiêu

Mỗi video được nhập nhiều snapshot ở các mốc `2h`, `24h`, `72h` và `168h`. Hệ
thống dùng các snapshot mới nhất của từng video để phân tích, nhưng vẫn giữ toàn
bộ snapshot để phát hiện dữ liệu bất thường.

Các trường cần lấy từ TikTok Analytics hoặc file export được cấp quyền:

| Trường | Ý nghĩa |
| --- | --- |
| `duration` | Độ dài video, tính bằng giây |
| `average_watch_time` | Thời gian xem trung bình, tính bằng giây |
| `retention_2s` | Tỷ lệ người xem còn lại ở giây thứ 2 |
| `retention_6s` | Tỷ lệ người xem còn lại ở giây thứ 6 |
| `watched_full_rate` | Tỷ lệ xem hết video |

Tỷ lệ có thể nhập ở dạng `0.35`, `35` hoặc `35%`; importer chuẩn hóa về khoảng
`0..1`.

## Chỉ số suy ra

- `median_watch_percentage`: watch time trung vị chia cho độ dài video.
- `weighted_watch_percentage`: watch time percentage có trọng số theo lượt xem.
- `median_retention_drop_2s_to_6s`: mức rơi retention từ 2 giây xuống 6 giây,
  tính theo điểm phần trăm.
- `median_retention_2s`, `median_retention_6s`: retention trung vị tại từng mốc.

Snapshot có `retention_6s > retention_2s` được gắn anomaly
`RETENTION_6S_GT_2S` và không nên dùng để kết luận trước khi kiểm tra nguồn.
Dashboard cũng hiển thị coverage của watch time và retention để phân biệt “0%
thật” với “chưa đo”.

## Nhập và học

Kiểm tra trước khi ghi:

```bash
.venv/bin/python scripts/import_tiktok_metrics.py \
  --input path/to/metrics.csv \
  --channel-id Adsupnews \
  --measurement-window 24h \
  --dry-run
```

Tạo bài học theo kênh:

```bash
.venv/bin/python scripts/build_channel_learning.py build \
  --channel-id Adsupnews \
  --minimum-sample-size 30 \
  --minimum-group-size 5 \
  --dry-run
```

Learning không dùng dòng thiếu watch time hoặc thiếu toàn bộ completion/retention.
Điểm học kết hợp watch percentage, completion, retention 2s/6s và engagement trên
1.000 view. Bài học về watch time và mức rơi 2s→6s chỉ được đưa vào prompt khi
operator bật learning cho kênh và `PERFORMANCE_LEARNING_ENABLED=1`.

Không tự động gọi API hoặc thu thập cookie/token TikTok; chỉ dùng export/API chính
thức đã được cấp quyền.
