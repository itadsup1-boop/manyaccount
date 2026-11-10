# Kế hoạch nâng cấp Tool Video Tin Tức

## 1. Mục tiêu đã chốt

Tạo video tin tức dọc chất lượng cao từ bài báo, với đầu vào là **Tool Media Article JSON v1** do plugin `@News Video Studio` tạo ra.

Đầu ra bắt buộc:

- MP4 1080 x 1920, 30 fps.
- Voice-over tiếng Việt, nhạc nền đã xác minh quyền sử dụng và phụ đề.
- 7-9 cảnh có nhịp dựng rõ ràng, bám theo timeline trong JSON.
- Ảnh/video chân thực, sắc nét, liên quan đến từng cảnh.
- Đồ họa dữ liệu, typography và bản đồ tự dựng cho số liệu hoặc khi không có B-roll phù hợp.

Chính sách asset mặc định:

```json
{
  "mode": "facts_and_licensed_real_stock_only",
  "ai_generated_assets_allowed": false,
  "publisher_assets_allowed": false,
  "logos_allowed": false,
  "watermark_removal_allowed": false
}
```

## 2. Điều không được làm

- Không dùng DuckDuckGo Images làm nguồn asset sản xuất.
- Không dùng ảnh hoặc video tạo bởi AI.
- Không tải hoặc ghép ảnh/video nhúng trong bài báo.
- Không dùng ảnh, screenshot, logo hoặc watermark của toà soạn/bên thứ ba.
- Không crop, che, xoá hoặc tái tạo logo/watermark.
- Không gọi ChatGPT/Gemini web automation lần nữa sau khi JSON đã được tạo.

Nếu cần ảnh đúng chính xác sự kiện, nhân vật hoặc hiện trường của bài báo, phải có license/quyền sử dụng trực tiếp. Kho stock chỉ được dùng làm B-roll chân thực, không được trình bày như ảnh hiện trường của sự kiện.

## 3. Luồng vận hành mới

```text
Bài báo được đính kèm vào @News Video Studio
        ↓
Tool Media Article JSON v1
        ↓
Import JSON vào Tool Media
        ↓
Validate JSON + chính sách quyền sử dụng
        ↓
Lập media plan cho từng beat
        ↓
Tìm B-roll chân thực từ Pexels / kho stock đã cấp phép
        ↓
Lọc chất lượng + chấm độ liên quan + ghi asset manifest
        ↓
Renderer hiện có của Tool Media dựng cảnh: real B-roll + typography/biểu đồ khi cần
        ↓
TTS + subtitle + BGM đã duyệt
        ↓
Video QA
        ↓
MP4 1080x1920, 30 fps
```

## 4. Giai đoạn 1 — Chuẩn hoá đầu vào JSON v1

### Việc cần làm

1. Tạo API `POST /api/article/import-production-json` nhận một object JSON v1.
2. Tạo màn hình **Import JSON** trên Tool Article: dán JSON, validate, hiển thị lỗi rõ ràng, bấm dựng video.
3. Lưu bản JSON gốc theo `job_id`; không sửa mất các trường mới.
4. Tạo schema/validator riêng cho JSON v2.
5. Sửa URL nguồn: chỉ nhận URL thuần, không nhận Markdown link trong field `source.url`.
6. Thêm endpoint xem storyboard trước khi render.

### Trường bắt buộc cần kiểm tra

- `schema_version = 1`
- `source_type = "article"`
- `should_make_video = true`
- `target.duration_sec`, `render_spec.width`, `render_spec.height`, `render_spec.fps`
- `rights_policy.mode`
- `source.url`, `fact_sheet`, `full_voice_over`
- 7-9 `beats`, timeline liên tục từ giây 0 đến hết `duration_sec`
- Mỗi beat có `voice_over`, `visual_fallback`, `on_screen_text`, `source_fact_ids`

### Tiêu chí nghiệm thu

- Có thể dán JSON v2 và nhận preview storyboard mà không cần crawler bài báo.
- JSON sai schema, timeline sai, URL lỗi hoặc policy không hợp lệ bị chặn trước render.
- Không còn ép `schema_version` từ v2 về v1.

## 5. Giai đoạn 2 — Media plan và nguồn ảnh/video chân thực

### Nguồn asset

1. **Pexels API**: nguồn mặc định cho B-roll ảnh/video chân thực có license.
2. **Kho stock trả phí**: tuỳ chọn cho kênh premium, chỉ tải sau khi license được xác nhận.
3. **Asset do người dùng sở hữu**: cho phép upload và lưu provenance.

### Quy trình chọn asset cho một beat

1. Đọc `visual_fallback`, `must_show`, `voice_over` và fact ID của beat.
2. Sinh 2-3 truy vấn ngắn bằng tiếng Anh, mô tả đúng bối cảnh chứ không bịa sự kiện.
3. Lấy 10-15 ứng viên ảnh/video chân thực từ provider cho mỗi beat.
4. Lọc kỹ thuật:
   - ảnh/video có độ phân giải đủ cho 1080x1920;
   - không thumbnail, ảnh mờ, banner, ảnh trùng;
   - không logo/watermark có thể nhận diện;
   - không có nhận diện dự án, thương hiệu hoặc sự kiện sai.
5. Chấm độ liên quan giữa asset và beat bằng bộ xếp hạng hình-ảnh/nội dung.
6. Chỉ chấp nhận asset đạt ngưỡng điểm; nếu không đạt, trả `no_asset_found`.
7. Với `no_asset_found`, renderer dùng typography, biểu đồ hoặc bản đồ tự dựng; không quay lại DuckDuckGo.

### Asset manifest bắt buộc

Mỗi asset được dùng phải lưu:

```json
{
  "asset_id": "...",
  "provider": "pexels|premium_stock|owned",
  "provider_asset_id": "...",
  "asset_url": "...",
  "page_url": "...",
  "license_status": "licensed|owned",
  "license_source": "...",
  "downloaded_at": "ISO-8601",
  "beat_number": 1,
  "relevance_score": 0.0,
  "logo_scan": "passed",
  "watermark_scan": "passed"
}
```

### Tiêu chí nghiệm thu

- Không còn import `duckduckgo_search` trong luồng render production.
- Không còn tải `images`/`videos` từ HTML bài báo khi policy mới bật.
- Mọi asset trong MP4 đều truy được provider, asset ID và trạng thái license.

## 6. Giai đoạn 3 — Renderer chất lượng cao theo beat

### Quy tắc dựng hình

- Mỗi beat dài khoảng 4-7 giây, dựa theo thời lượng voice thực tế.
- Ưu tiên video B-roll chân thực; ảnh tĩnh dùng chuyển động Ken Burns nhẹ.
- Không dùng cùng một asset quá hai lần trong một video.
- Mỗi cảnh chỉ truyền tải một ý chính.
- Số liệu quan trọng dùng typography/biểu đồ; không cố diễn đạt bằng ảnh.
- Ảnh chân thực chỉ minh hoạ bối cảnh, không được ngụ ý đó là ảnh sự kiện nếu không có quyền.

### Các layout cần xây dựng

1. Full-screen real B-roll + caption ngắn.
2. B-roll nền + thẻ số liệu lớn.
3. Biểu đồ cột/đường/donut tự dựng.
4. Bản đồ tự dựng + marker địa danh.
5. So sánh hai chỉ số.
6. Cảnh kết: ba chỉ số cần theo dõi hoặc thông điệp trung tính.

### Tiêu chí nghiệm thu

- Renderer đọc `asset_ids` hoặc `visual_fallback` của từng beat.
- Không có cảnh trống khi thiếu asset.
- Không ghép video báo chí vào cuối video.
- Cảnh đầu nêu rõ sự kiện/chỉ số chính trong 2 giây đầu.

## 7. Giai đoạn 4 — Voice, subtitle và âm thanh

### Việc cần làm

1. Sinh TTS từ `full_voice_over`; đo thời lượng âm thanh thật.
2. Điều chỉnh thời điểm beat theo duration TTS thật thay vì chỉ tin `start_sec/end_sec` do AI dự đoán.
3. Sinh phụ đề có timecode theo từ/câu; highlight số liệu và từ khoá quan trọng.
4. Chỉ dùng BGM có `license_status = approved` và `license_source`.
5. Ducking nhạc khi có voice; không dùng SFX giật gân cho tin kinh tế, tai nạn hoặc nội dung nhạy cảm.

### Tiêu chí nghiệm thu

- Không mất câu hook hoặc câu kết khi TTS thất bại.
- Subtitle nằm trong safe area.
- Nhạc không lấn voice.
- Video có âm thanh ổn định, không có đoạn im lặng dài bất thường.

## 8. Giai đoạn 5 — Quality gate và quyền sử dụng

### Việc cần làm

1. Bật EvidenceGuard cho tin tài chính, pháp lý, sức khỏe và nội dung có số liệu.
2. Không ép `topic_fit = true`; chỉ render khi nội dung phù hợp profile kênh hoặc đã được operator duyệt rõ ràng.
3. Kiểm tra logo/watermark thật trên asset, không chỉ dựa vào cờ boolean từ crawler.
4. Chặn render nếu asset không có provenance/license manifest.
5. VideoQA bắt buộc kiểm tra 1080x1920, 30 fps, H.264, AAC, safe-zone, khung đen, freeze, silence và loudness.

### Tiêu chí nghiệm thu

- Bất kỳ asset `unknown`, `unlicensed`, có logo/watermark hoặc thiếu provenance đều bị loại.
- Bài có số liệu không có evidence hợp lệ bị đưa về hàng chờ duyệt.
- Video không đạt QA không được upload.

## 9. Giai đoạn 6 — Thay đổi model và chi phí

### Quyết định

- `@News Video Studio` là nơi sinh JSON và kịch bản.
- Tool Media không dùng ChatGPT/Gemini web automation trong luồng import JSON/render.
- AI, nếu cần, chỉ dùng để xếp hạng mức liên quan của asset; có thể dùng bộ xếp hạng local trước để giảm chi phí.

### Lợi ích

- Không lỗi do đổi giao diện ChatGPT/Gemini, login hoặc rate limit.
- Không tốn token lần thứ hai để viết lại cùng một bài báo.
- Renderer có đầu vào nhất quán và dễ kiểm thử.

## 10. Các file hiện tại cần thay đổi

| File/khu vực | Thay đổi cần làm |
|---|---|
| `adsup_central_hub/frontend/src/pages/ToolArticle.tsx` | Thêm tab Import JSON, storyboard và duyệt asset. |
| `adsup_central_hub/backend/main.py` | Thêm API import JSON, tạo job và gọi renderer mới. |
| `shared/core/content_models.py` | Bổ sung model/schema Production JSON v2. |
| `shared/core/content_normalizer.py` | Không hạ v2 xuống v1; giữ timeline, policy và visual fallback. |
| `apps/creator_article/article_pipeline_core.py` | Tách luồng crawler cũ khỏi chế độ JSON v2; bỏ DuckDuckGo/source media. |
| `apps/creator_article/image_searcher.py` | Thay bằng provider adapter Pexels/kho stock. |
| `apps/creator_article/article_crawler.py` | Chỉ dùng để trích xuất text/fact source nếu cần, không tải media trong policy mới. |
| `apps/news_hyperframes/` | Không dùng trong luồng Tool Media hiện tại. |
| `apps/creator_article/article_ffmpeg.py` | Dựng theo media plan/visual fallback của JSON v1; không nhận appended video nguồn. |
| `shared/core/rights_guard.py` | Thêm chế độ strict cho licensed real stock và bắt buộc asset manifest. |
| `shared/core/evidence_guard.py` | Bật cấu hình theo loại tin thay vì hard-code tắt. |
| `config/prompts/prompt_article.txt` | Đồng bộ với JSON v2; bỏ yêu cầu tìm ảnh web thật. |

## 11. Thứ tự triển khai khuyến nghị

1. Giai đoạn 1: Import + validate JSON v2.
2. Giai đoạn 2: Pexels provider + asset manifest + tắt DuckDuckGo trong mode mới.
3. Giai đoạn 3: Renderer real B-roll/graphic fallback theo beat.
4. Giai đoạn 4: Căn TTS, subtitle, BGM theo timeline thực.
5. Giai đoạn 5: Bật quality/rights/evidence gate nghiêm ngặt.
6. Giai đoạn 6: Loại web automation AI khỏi luồng render JSON.

## 12. Definition of Done

Một video được xem là hoàn thành khi:

- JSON v2 được import và validate thành công.
- Không dùng DuckDuckGo, ảnh AI, asset từ bài báo hoặc asset không rõ quyền.
- Mọi ảnh/video chân thực có asset manifest và license/provenance.
- Video có B-roll liên quan hoặc graphic fallback hợp lý tại mọi beat.
- Voice, subtitle và nhạc khớp nhau.
- MP4 qua VideoQA: 1080x1920, 30 fps, H.264/AAC, safe-zone, không black/freeze/silence bất thường.
- Có file storyboard, JSON nguồn và asset manifest lưu cùng job để kiểm tra lại.
