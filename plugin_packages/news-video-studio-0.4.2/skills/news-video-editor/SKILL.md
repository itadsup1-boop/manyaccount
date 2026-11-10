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
- Giữ chính xác tên field của schema: `hook`, `script_voice`, `beats[].duration_hint`, `beats[].visual_query`, `on_screen_text`, `motion`, `transition` và `music_*`.
- Tạo 7–9 beat. Tổng `duration_hint` xấp xỉ thời lượng hồ sơ kênh (mặc định 52 giây). Beat đầu là `hook`; beat cuối là `payoff` hoặc `close`.
- Với bài tin kinh tế/đời sống 52 giây, phải có **ít nhất 3 và tối đa 5 beat B-roll**.

### Quy tắc quan trọng về biến hình ảnh: DUY NHẤT 1 BIẾN `visual_query`
Để công cụ tìm kiếm được hình ảnh chân thật, đúng bối cảnh và sát nhất với nội dung bài báo, **mỗi beat chỉ dùng DUY NHẤT 1 biến `visual_query`**. Không tạo thêm các biến phụ làm loãng mô tả (như `asset_search_queries`, `visual_brief`, `visual_fallback`, `required_country`, `country_strict`).

1. **Với beat B-roll (tìm kiếm ảnh/video thực tế đời thường)**:
   - `visual_query` phải là **mô tả chi tiết, cụ thể, chân thật và sát thực tế nhất với nội dung bài báo**.
   - Nêu rõ: **chủ thể thực tế, hành động đời thường, bối cảnh không gian tại Việt Nam** gắn liền với dữ kiện bài báo.
   - **Tuyệt đối tránh** từ khóa ngắn chung chung bằng tiếng Anh dịch máy (như `"apartment building exterior"`, `"people meeting"`, `"signing contract"`) vì sẽ tìm ra ảnh dựng 3D, mô hình kiến trúc hoặc ảnh người nước ngoài không ăn nhập với tin tức Việt Nam.
   - **Ví dụ đúng (chi tiết, chân thực, sát bài báo)**:
     - Beat 1 (Ngoại cảnh): `Tòa nhà chung cư cao tầng hiện đại thực tế tại TP HCM, khu dân cư đô thị Việt Nam ban ngày`
     - Beat 3 (Cư dân): `Cư dân sinh hoạt tại sảnh chung cư và hành lang tòa nhà thực tế tại TP HCM`
     - Beat 4 (Hợp đồng): `Bản hợp đồng quản lý vận hành chung cư và thỏa thuận chi phí dịch vụ thực tế`
     - Beat 6 (Ban quản trị): `Họp ban quản trị và cư dân chung cư thảo luận thỏa thuận mức phí quản lý`
   - Có thể dùng tiếng Việt mô tả chi tiết hoặc tiếng Anh cụ thể gắn liền bối cảnh Việt Nam (`Vietnam apartment building realistic exterior Ho Chi Minh City`).

2. **Với beat Đồ họa (số liệu, so sánh, bản đồ)**:
   - Dùng tiền tố `DATA GRAPHIC:` hoặc `MAP GRAPHIC:` ở đầu `visual_query` kèm theo số liệu, bảng biểu, mốc so sánh cần hiển thị.
   - Ví dụ: `DATA GRAPHIC: Khung giá chung cư có thang máy 1.800 - 13.700 đ/m2 và không thang máy 600 - 8.800 đ/m2`
   - Phân bổ mặc định: hook/data → B-roll → data → B-roll → B-roll → fact/data → B-roll → close.

3. **Chữ trên màn hình & must_show**:
   - `on_screen_text`: Tối đa 7 từ, ngắn gọn, súc tích, tác động mạnh.
   - `must_show`: Mảng chứa số liệu, mốc thời gian hoặc địa danh bắt buộc hiện trên màn hình.

## Bản quyền và tính chính xác

- Không tạo ảnh AI, không dùng ảnh screenshot có chứa logo/watermark của tòa soạn báo hay thương hiệu bên thứ ba.
- Không crop, che, xóa hoặc tái tạo logo/watermark.
- Chỉ dùng dữ kiện có trong bài báo nguồn; không bịa tên người, nguyên nhân, số liệu hay dự báo.

## Quy trình biên tập

1. Lập `fact_sheet` trước khi viết. `confirmed_facts` có ít nhất hai dữ kiện kiểm chứng được; `unknowns` giữ thông tin còn thiếu.
2. Tạo ba hook theo `result`, `conflict`, `impact`; `hook` phải trùng `selected_hook`.
3. Viết `script_voice` nối sau hook, không lặp lại hook; độ dài cùng `hook` khoảng 150–165 từ cho video 52 giây.
4. Tin nhạy cảm: `is_sensitive:true`, `music_mood:"sensitive_empathy"`, `music_energy:1`, `sfx:""`.
5. Nếu bài kém chất liệu hay không đúng kênh: `topic_fit:false`, `should_make_video:false`, nêu lý do trong `skip_reason`.
