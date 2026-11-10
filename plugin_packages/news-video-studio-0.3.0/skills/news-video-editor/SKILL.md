---
name: news-video-editor
description: Chuyển file hoặc nội dung bài báo tiếng Việt thành News Video Production JSON v2 để dựng video dọc HyperFrames với tư liệu stock chân thực có license và đồ hoạ dữ liệu nguyên gốc. Dùng khi người dùng yêu cầu JSON video tin tức, TikTok/Reels từ bài báo, hoặc gửi file bài báo.
metadata:
  short-description: Biên tập bài báo thành JSON video dọc
---

# News Video Editor

Trả về duy nhất một object JSON hợp lệ theo `references/news-video-schema-v2.json`. Không dùng Markdown, không thêm giải thích, không gọi công cụ render.

## Đầu vào

Đọc các khối `[HỒ SƠ KÊNH]`, `[CHÍNH SÁCH RENDER VÀ QUYỀN SỬ DỤNG]`, `[NGUỒN]`, `[BÀI BÁO]` nếu có.

Nếu có file TXT, Markdown, DOCX hoặc PDF đính kèm chứa các khối này, file là đầu vào chính. Đọc toàn bộ nội dung file; không yêu cầu người dùng dán lại bài báo vào chat. Không suy diễn sự kiện từ URL nếu thiếu nội dung bài báo.

Nếu thiếu `[BÀI BÁO]`, trả `input_status: "missing_article_text"`, `should_make_video: false`, `beats: []`, và nêu rõ lý do trong `skip_reason`.

## Chính sách bắt buộc

- Luôn trả `render_spec` 1080×1920, 30 fps; safe area: 72 trái/phải, 180 trên, 360 dưới.
- Luôn trả `rights_policy.mode: "facts_and_licensed_real_stock_only"`, `publisher_assets_allowed: false`, `logos_allowed: false`, `watermark_removal_allowed: false`, `ai_generated_assets_allowed: false`.
- Không dùng, không mô tả là được phép dùng, và không tạo URL cho ảnh/video/screenshot/phối cảnh/logo/watermark từ bài báo, toà soạn hoặc thương hiệu bên thứ ba.
- Không tạo ảnh AI. Không crop, che, xoá hay tái tạo logo/watermark.
- `source.url` phải là URL thuần bắt đầu bằng `https://` hoặc `http://`, không là Markdown link và không chứa dấu `[]()`.

## Quy trình biên tập

1. Lập `fact_sheet` chỉ từ bài nguồn; giữ dữ kiện chưa rõ trong `unknowns`.
2. Tạo ba hook theo góc `result`, `conflict`, `impact`. `hook` trùng `selected_hook`; `selected_hook` trùng chính xác một `hook_variants[].text`.
3. Viết voice 45–70 giây, giọng trung tính theo hồ sơ kênh. `full_voice_over` là hook và script nối liền, không lặp câu hook.
4. Chia 7–9 beats liên tục từ giây 0 đến đúng `target.duration_sec`. Mỗi beat có một ý chính, `source_fact_ids`, câu voice, chữ ngắn trên màn hình, `visual_query` và `visual_fallback`.
5. Tạo `stock_requests`: 1–2 brief cho mỗi beat thật sự cần B-roll. `search_query_en` phải là 6–14 từ tiếng Anh mô tả bối cảnh chân thực, không nêu tên toà soạn/thương hiệu và không giả định đó là ảnh hiện trường. `asset_kind` là `photo` hoặc `video`, `orientation` là `vertical_preferred`.
6. `stock_requests` chỉ là brief để Tool Media tìm Pexels/kho stock; không phải asset đã được cấp phép. Mỗi request phải có `fallback` là đồ hoạ dữ liệu/typography/bản đồ tự dựng.
7. Với nội dung số liệu, lãi suất, giá, tồn kho hoặc tỷ lệ: ưu tiên original data graphic hơn stock. Với người/địa điểm không thể minh hoạ trung thực: dùng đồ hoạ nguyên gốc, không dùng stock gây hiểu nhầm.

## Cờ chất lượng

- Tin nhạy cảm có `is_sensitive: true`, `music_mood: "sensitive_empathy"`, `music_energy: 1`, không SFX giật gân.
- Nếu nguồn không đủ chất liệu hoặc chất lượng dưới 6: `should_make_video: false`, `beats: []`, `full_voice_over: ""`.
- `claim_register` và `evidence` là mảng trống trừ khi người dùng bật EvidenceGuard.
