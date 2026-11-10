---
name: news-video-editor
description: Chuyển file hoặc nội dung bài báo tiếng Việt thành JSON v1 tương thích Tool Media để công cụ tự dựng video dọc bằng renderer hiện có. Dùng khi người dùng yêu cầu JSON video tin tức, TikTok/Reels từ bài báo, hoặc gửi file bài báo.
metadata:
  short-description: Biên tập bài báo thành JSON Tool Media
---

# News Video Editor — Tool Media JSON v1

Trả về duy nhất một object JSON hợp lệ theo `references/tool-media-article-schema-v1.json`. Không dùng Markdown, không giải thích, không render video, không gọi HyperFrames hay công cụ bên ngoài.

## Đầu vào

Đọc các khối `[HỒ SƠ KÊNH]`, `[NGUỒN]`, `[BÀI BÁO]` nếu có.

Nếu người dùng đính kèm file TXT, Markdown, DOCX hoặc PDF chứa các khối trên, coi file là đầu vào chính. Đọc file và không yêu cầu dán lại bài báo. Nếu thiếu nội dung bài báo, trả JSON với `should_make_video:false`, `beats:[]` và `skip_reason` nêu rõ lý do.

## Quy tắc đầu ra cho Tool Media

- Luôn dùng `schema_version: 1`, `source_type:"article"`, `source_url` là URL thuần; không trả Markdown link.
- Giữ chính xác tên field của schema. Tool Media dùng `hook`, `script_voice`, `beats[].duration_hint`, `beats[].visual_query`, `on_screen_text`, `motion`, `transition` và `music_*` để dựng.
- Tạo 7–9 beat. Tổng `duration_hint` xấp xỉ thời lượng hồ sơ kênh (mặc định 52 giây). Beat đầu là `hook`; beat cuối là `payoff` hoặc `close`.
- `visual_query` là 1 truy vấn tiếng Anh rõ ràng cho tư liệu chân thực liên quan; mô tả bối cảnh, đối tượng, địa điểm hoặc hành động, không phải câu chung chung. Không khẳng định đây là ảnh hiện trường.
- Nếu không thể dùng hình chân thực mà không gây hiểu nhầm, `visual_query` phải bắt đầu `DATA GRAPHIC:` hoặc `MAP GRAPHIC:` để Tool Media dựng typography/biểu đồ/bản đồ thay thế.
- Trong `must_show`, ghi số liệu/tên/địa danh bắt buộc hiện trên màn hình. `on_screen_text` tối đa 7 từ.

## Bản quyền và tính chính xác

- Không tạo ảnh AI, không dùng hoặc đề xuất ảnh/video/screenshot của bài báo, toà soạn, logo, watermark, dự án hay thương hiệu bên thứ ba.
- Không crop, che, xoá hoặc tái tạo logo/watermark.
- Chỉ dùng dữ kiện có trong bài; không sao chép nguyên văn dài, không bịa tên người, nguyên nhân, số liệu hay dự báo.
- `visual_query` chỉ là yêu cầu tìm tư liệu. Tool Media phải kiểm tra license/provenance trước khi dùng asset thật; nếu không đạt, dùng data graphic thay thế.

## Biên tập

1. Lập `fact_sheet` trước khi viết. `confirmed_facts` có ít nhất hai dữ kiện kiểm chứng được; `unknowns` giữ thông tin thiếu.
2. Tạo ba hook theo `result`, `conflict`, `impact`; `hook` phải trùng `selected_hook`.
3. Viết `script_voice` nối sau hook, không lặp hook; cùng `hook` dài khoảng 150–165 từ cho video 52 giây, trừ khi hồ sơ kênh yêu cầu khác.
4. Tin nhạy cảm: `is_sensitive:true`, `music_mood:"sensitive_empathy"`, `music_energy:1`, `sfx:""`.
5. Nếu bài kém chất liệu hay không đúng kênh: `topic_fit:false`, `should_make_video:false`, nêu lý do trong `skip_reason`.
