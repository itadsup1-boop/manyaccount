# News Video Studio → HyperFrames

## Luồng vận hành

1. Tool Media tạo file `article_input.txt` chứa bài báo đã làm sạch.
2. Người vận hành đính kèm file đó vào chat có `@News Video Studio`, sau đó
   gửi: `Đọc file đính kèm và chỉ trả News Video Production JSON v2.`
3. Tải JSON trả về và đưa vào renderer này.
4. Dịch vụ asset chỉ tải stock chân thực có license; ghi `local_path`,
   `license_status: licensed_real_stock`, `source_url`, `license_url` vào JSON.
5. Renderer kiểm tra JSON, chỉ copy asset hợp lệ, sinh project HyperFrames,
   tạo voice tiếng Việt hoặc nhận voice đã duyệt, lint và xuất MP4.

## Lệnh chuẩn bị project HyperFrames

```bash
python -m apps.news_hyperframes.render_json production.json \
  --asset-root /duong-dan/thu-vien-stock \
  --voice-path /duong-dan/voice.wav \
  --music-path /duong-dan/nhac-da-duyet.mp3
```

Lệnh trên chỉ tạo job để xem/kiểm tra. Thêm `--render` để lint và render MP4:

```bash
python -m apps.news_hyperframes.render_json production.json \
  --asset-root /duong-dan/thu-vien-stock \
  --voice-path /duong-dan/voice.wav --render
```

Không có `--voice-path` thì dùng `--voice-id <UUID>` để gọi Voicebox. Nhạc chỉ
được đưa vào khi file đã được catalogue đánh dấu license `approved`.

## Bảo vệ bản quyền

Renderer không tải ảnh từ URL, không lấy ảnh bài báo và không dùng DuckDuckGo.
Asset có `publisher_asset: true`, `is_ai_generated: true`, thiếu local path,
hoặc không có `license_status` đúng sẽ bị bỏ qua và beat dùng đồ hoạ dữ liệu.

## Tạo file để upload ChatGPT

```bash
python3 -m apps.news_hyperframes.article_upload_package article.txt \
  --url 'https://example.com/bai-bao' --publisher 'Tên toà soạn' \
  --output article_input.txt
```
