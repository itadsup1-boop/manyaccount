# A/B test và học theo từng kênh

Đợt 8 mặc định **không tác động production**. Experiment chỉ chạy khi definition
có `status=running` và biến môi trường `CONTENT_EXPERIMENTS_ENABLED=1`. Bài học
chỉ vào prompt khi bản ghi của kênh có `enabled=true` và
`PERFORMANCE_LEARNING_ENABLED=1`.

Runtime state nằm ở:

- `data/experiments.json`
- `data/channel_learning.json`
- `data/performance.sqlite3`

Ba file này đã được `.gitignore`; không đưa metrics hoặc tên chiến dịch thật vào
Git.

## 1. Tạo một experiment

Sao chép `config/experiment_template.json`, sau đó chỉ đổi đúng một biến trong cả
hai nhánh. Các biến được hỗ trợ:

- `hook_type`: `result`, `conflict`, `impact`
- `target_duration_seconds`: 10–60
- `subtitle_style`: `normal`, `keyword_highlight`
- `visual_beat_count`: 3–12
- `cta_mode`: `none`, `specific`
- `music_energy`: 1–3

Tạo definition ở trạng thái draft:

~~~bash
.venv/bin/python scripts/manage_experiments.py create \
  --config config/experiment_template.json
~~~

Manager từ chối variant thay hơn một field, hai variant dùng hai field khác nhau,
hai giá trị giống nhau, hoặc kênh đã có một experiment đang chạy. Điều này bảo đảm
mỗi video không đồng thời đổi hook, độ dài, nhạc, phụ đề và màu.

Xem trước việc chia nhánh ổn định theo source/content ID:

~~~bash
.venv/bin/python scripts/manage_experiments.py assign \
  --channel-id Adsupnews \
  --source-type article \
  --content-key 'source-test-001'
~~~

Cùng một `experiment_id + channel_id + content_key` luôn nhận cùng variant. Sau
khi smoke test bằng nguồn không production:

~~~bash
.venv/bin/python scripts/manage_experiments.py set-status \
  --experiment-id hook-result-vs-conflict-adsupnews-v1 \
  --status running
export CONTENT_EXPERIMENTS_ENABLED=1
~~~

PromptBuilder ghi `experiment_id`, `experiment_variant`, `experiment_variable` và
`experiment_value` vào output. ContentValidator chặn output không khớp nhánh được
gán. Renderer áp dụng `subtitle_style`; các biến hook, beats, CTA, duration và
music energy đi qua content contract hiện tại.

Không chạy music energy 2/3 với tin nhạy cảm: quy tắc safety luôn buộc energy 1.
Subtitle experiment trên Facebook chỉ hợp lệ ở mode có frame/script voice; mode
no-frame giữ audio gốc và không render subtitle nên ContentValidator sẽ loại khỏi
experiment.
Không đổi prompt/profile/voice/renderer giữa lúc test. Nếu cần đổi một yếu tố khác,
tạm dừng test cũ và tạo experiment mới.

## 2. Nhập metrics có dấu experiment

Khi nhập dữ liệu, giữ các cột sau từ output video:

- `experiment_id`
- `experiment_variant`
- `experiment_variable`
- `experiment_value`

Template đầy đủ nằm tại `config/tiktok_metrics_template.csv`. Store tự migration
schema Đợt 7 và vẫn giữ idempotent theo video/mốc đo.

Chỉ đánh giá sau khi cả hai nhánh đủ mẫu và cùng xuất hiện trong ít nhất một
`story_type`. Ví dụ:

~~~bash
.venv/bin/python scripts/manage_experiments.py evaluate \
  --experiment-id hook-result-vs-conflict-adsupnews-v1 \
  --minimum-group-size 5
~~~

Report chỉ trả `leader`, không tự ghi `winner`; operator phải xem chất lượng nội
dung, lỗi QA và độ chênh trước khi kết luận. Video thuộc story type chỉ có một
variant bị loại khỏi phần so sánh để tránh lệch nhóm nội dung.

Tạm dừng hoặc kết thúc:

~~~bash
.venv/bin/python scripts/manage_experiments.py set-status \
  --experiment-id hook-result-vs-conflict-adsupnews-v1 \
  --status paused
~~~

## 3. Tạo Channel Learning

Xem trước, không ghi runtime:

~~~bash
.venv/bin/python scripts/build_channel_learning.py build \
  --channel-id Adsupnews \
  --minimum-sample-size 30 \
  --minimum-group-size 5 \
  --dry-run
~~~

Ghi bài học nhưng chưa bật:

~~~bash
.venv/bin/python scripts/build_channel_learning.py build \
  --channel-id Adsupnews
~~~

Thuật toán chỉ dùng snapshot mới nhất của mỗi video, median watch/completion,
share/save/follow trên 1.000 view. Hook, duration và music mood được chuẩn hóa so
với baseline của **cùng story type**. Dòng thiếu views hoặc duration không được dùng
để học; video viral đơn lẻ không thể quyết định median.

Sau khi operator đọc `prompt_lessons` và `analysis`, bật riêng kênh rồi bật global
feature flag:

~~~bash
.venv/bin/python scripts/build_channel_learning.py enable \
  --channel-id Adsupnews
export PERFORMANCE_LEARNING_ENABLED=1
~~~

PromptBuilder chỉ chèn danh sách lesson đã đủ mẫu, không chèn metrics thô và không
cho phép lesson thay thế bằng chứng nguồn.

Nếu bài học sai, có thể vô hiệu hóa tức thì hoặc xóa:

~~~bash
.venv/bin/python scripts/build_channel_learning.py disable \
  --channel-id Adsupnews
.venv/bin/python scripts/build_channel_learning.py delete \
  --channel-id Adsupnews
~~~

## 4. Quy trình an toàn đề xuất

1. Import đủ snapshot 24h/72h và kiểm tra anomaly.
2. Chọn một kênh, một source type và đúng một biến.
3. Preview assignment bằng ID giả; render vài video không production.
4. Bật experiment, không đổi cấu hình khác trong thời gian đo.
5. Chờ mỗi variant đủ tối thiểu 30 video và có nhóm story type so sánh được.
6. Operator review `leader`, sau đó pause/complete experiment.
7. Build Channel Learning ở `--dry-run`, đọc lesson và mới bật từng kênh.
8. Theo dõi thêm một chu kỳ; disable ngay nếu chất lượng biên tập giảm.

Hệ thống giúp đo thay đổi có kiểm soát, không bảo đảm số view và không tự tối ưu
production khi chưa có phê duyệt của operator.
