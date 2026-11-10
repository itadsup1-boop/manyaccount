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
- Giữ chính xác tên field của schema. Tool Media dùng `hook`, `script_voice`, `beats[].duration_hint`, `beats[].visual_query`, `on_screen_text`, `motion`, `transition` và `music_*` để dựng. Beat B-roll có thể thêm `asset_search_queries`, `visual_brief`, `visual_fallback`, `required_country`, `country_strict`.
- Tạo 7–9 beat. Tổng `duration_hint` xấp xỉ thời lượng hồ sơ kênh (mặc định 52 giây). Beat đầu là `hook`; beat cuối là `payoff` hoặc `close`.
- Với bài tin kinh tế/đời sống 52 giây, phải có **ít nhất 3 và tối đa 5 beat B-roll**. Mỗi beat B-roll phải có đủ ba field:
  - `visual_query`: truy vấn chính tiếng Anh 4–7 từ, ví dụ `modern apartment tower exterior Vietnam`.
  - `asset_search_queries`: mảng 2–3 truy vấn tiếng Anh thay thế, mỗi truy vấn 4–7 từ, từ cụ thể đến gần nghĩa. Ví dụ `["modern apartment tower exterior Vietnam", "high rise residential building tropical city", "urban apartment facade Southeast Asia"]`.
  - `visual_brief`: mô tả tiếng Việt 1–2 câu có **góc máy/khung hình, chủ thể, hành động, bối cảnh, ánh sáng hoặc thời điểm, và vùng trống đặt chữ**. Ví dụ: `Khung dọc 9:16, góc thấp 3/4 nhìn tòa chung cư 20–35 tầng, mặt tiền kính và bê tông sáng, đường nội khu cùng cây xanh ở tiền cảnh, ban ngày nhiều mây; nửa trên khung hình thoáng để đặt tiêu đề.`
- `visual_brief` là tiêu chí chọn ảnh/video thật, tuyệt đối không phải lệnh tạo ảnh AI. Không khẳng định asset là ảnh hiện trường.
- Với bài diễn ra tại Việt Nam và người dùng yêu cầu đúng quốc gia, mỗi beat B-roll phải có `"required_country":"Vietnam"` và `"country_strict":true`. Tool Media chỉ được chọn asset có metadata nhà cung cấp xác minh là Vietnam; metadata thiếu, suy đoán từ ngoại hình hoặc ảnh từ Google đều bị loại. Nếu không tìm được, trả data graphic thay vì lấy ảnh nước khác.
- Chỉ dùng `DATA GRAPHIC:` hoặc `MAP GRAPHIC:` cho số liệu chính xác, so sánh, điều khoản, mốc thời gian, bản đồ hoặc khi B-roll có thể gây hiểu nhầm. Không được đặt tiền tố graphic cho mọi beat. Phân bổ mặc định: hook/data → B-roll → data → B-roll → B-roll → fact/data → B-roll → close.
- Không đưa tên toà soạn, thương hiệu, tên dự án, địa chỉ riêng, từ khoá logo/watermark hay chỉ dẫn phong cách (`stock`, `no logo`, `realistic`, `daylight`) vào truy vấn B-roll. Những từ này làm kết quả tìm ảnh kém liên quan hoặc dễ bị loại. `visual_fallback` của B-roll, nếu có, phải là `DATA GRAPHIC:` với dữ kiện đã xác minh; cấm ghi “minh họa AI nguyên gốc”.
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
