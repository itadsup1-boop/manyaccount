# Brief cho Agent dựng Video Tin Tức từ JSON Tool Media

## 1. Mục tiêu

Xây dựng luồng dựng video tin tức dọc chất lượng cao từ một JSON do ChatGPT trả về. ChatGPT chỉ đảm nhiệm biên tập nội dung; Tool Media chịu trách nhiệm tìm tư liệu, tạo voice, dựng, kiểm tra và xuất MP4.

Đầu ra bắt buộc:

- Video 1080×1920, 30 fps, MP4 H.264/AAC.
- Khoảng 45–70 giây, mặc định 52 giây.
- Có voice-over tiếng Việt, nhạc nền đã xác minh quyền sử dụng, phụ đề và 7–9 cảnh.
- Mỗi cảnh chỉ truyền đạt một ý; video dễ xem trên điện thoại, không dày chữ.

Không gọi ChatGPT/Gemini lần hai trong Tool Media. JSON đã là “kịch bản khoá” cho một video.

## 2. Hợp đồng đầu vào

Agent nhận **Tool Media Article JSON v1**. Những field quan trọng:

| Field | Tool Media sử dụng để làm gì |
|---|---|
| `source_url` | Lưu provenance, không dùng để lấy ảnh bài báo. |
| `fact_sheet` | Đối chiếu số liệu và tránh dựng sai dữ kiện. |
| `hook` | Voice và hình ảnh 0–2 giây đầu. |
| `script_voice` | Phần voice còn lại. |
| `music_mood`, `music_energy`, `is_sensitive` | Chọn nhạc và giới hạn SFX. |
| `beats[]` | Timeline dựng; thứ tự cảnh không được tự ý đảo. |
| `beats[].duration_hint` | Thời lượng mục tiêu của cảnh. |
| `beats[].voice_over` | Nội dung voice phải khớp cảnh. |
| `beats[].visual_query` | Brief tìm ảnh/video chân thực. |
| `beats[].on_screen_text` | Chữ trọng tâm trên hình. |
| `beats[].must_show` | Tên, con số, địa danh phải hiển thị. |
| `beats[].motion`, `transition` | Nhịp chuyển cảnh. |

JSON sai schema, thiếu `hook`, thiếu `script_voice`, ít hơn 7 hoặc nhiều hơn 9 beats, hoặc tổng thời lượng lệch quá 15% so với hồ sơ kênh phải bị chặn trước render.

## 3. Chính sách quyền sử dụng — không được phá vỡ

Không dùng:

- Ảnh, video, screenshot, ảnh thumbnail, phối cảnh hay nội dung nhúng trong bài báo.
- Logo, watermark hoặc asset của toà soạn, dự án, doanh nghiệp hay bên thứ ba.
- Ảnh/video tạo bởi AI.
- Ảnh từ DuckDuckGo Images làm asset sản xuất.
- Thao tác crop, che, xoá hoặc tái tạo logo/watermark.

Được dùng:

- Video/ảnh chân thực từ Pexels hoặc kho stock khác khi có licence/provenance rõ ràng.
- Asset do người vận hành sở hữu.
- Typography, biểu đồ, bản đồ và icon tự dựng không gắn logo.
- BGM đã có `license_status: approved` và `license_source`.

Không có ảnh thật phù hợp **không phải** là lý do lấy ảnh báo chí. Cảnh đó chuyển sang đồ họa dữ kiện.

## 4. Asset manifest bắt buộc

Mỗi media thực sự được đưa vào video cần có record:

```json
{
  "asset_id": "stock_001",
  "beat_number": 3,
  "provider": "pexels|premium_stock|owned",
  "provider_asset_id": "...",
  "asset_url": "...",
  "page_url": "...",
  "local_path": "...",
  "license_status": "licensed|owned",
  "license_source": "...",
  "downloaded_at": "ISO-8601",
  "relevance_score": 0.0,
  "logo_scan": "passed",
  "watermark_scan": "passed",
  "is_ai_generated": false,
  "publisher_asset": false
}
```

Thiếu một trong các phần: `local_path`, provenance, `license_status`, hoặc scan pass → loại asset. Không được tự coi URL là có licence.

## 5. Cách hiểu `visual_query`

`visual_query` là brief, không phải lệnh bắt buộc tìm đúng ảnh hiện trường.

- Query bình thường: tìm B-roll chân thực đúng ngữ cảnh. Ví dụ: `Vietnamese family reviewing mortgage documents at home daylight`.
- `DATA GRAPHIC:`: dựng số liệu bằng chữ/charts, không gọi image search.
- `MAP GRAPHIC:`: dựng bản đồ tối giản, marker địa danh, không logo.

Không dùng stock để đóng giả một sự kiện, một căn nhà, một nhân vật hay một dự án cụ thể trong bài báo. Nếu cần độ chính xác đó mà không có quyền, chỉ dùng graphic trung tính.

## 6. Quy trình dựng cho mỗi beat

1. Đọc `voice_over`, `must_show`, `visual_query` và fact liên quan.
2. Xác định loại hình phù hợp nhất:
   - số liệu/tỷ lệ/so sánh → data graphic;
   - địa điểm/đường đi/phạm vi → map graphic;
   - hoạt động/bối cảnh phổ quát → B-roll thật;
   - không có B-roll trung thực → typography/graphic fallback.
3. Nếu tìm B-roll, lấy 10–15 ứng viên từ provider đã duyệt; lọc resolution, logo, watermark, độ nét, trùng lặp và mức liên quan.
4. Chọn asset có điểm liên quan cao. Không có asset đạt ngưỡng → graphic fallback.
5. Đặt chữ và phụ đề trong safe area; kiểm tra không che chủ thể.
6. Dựng motion nhẹ, không tạo hiệu ứng để che media yếu.

## 7. Nguyên tắc hình ảnh

### B-roll thật

- Ưu tiên clip video chân thực hơn ảnh tĩnh.
- Một asset không dùng quá hai lần trong một video.
- Ảnh tĩnh chỉ được pan/zoom nhẹ theo Ken Burns; không zoom quá mức làm vỡ hình.
- Không kéo dài một B-roll quá 5–6 giây nếu không có hành động rõ ràng.
- Khi có logo/watermark phát hiện được: bỏ asset, không xử lý ảnh để làm mờ logo.

### Đồ họa dữ kiện

- Chỉ thể hiện một thông điệp hoặc tối đa hai số có quan hệ trực tiếp trong một cảnh.
- Ưu tiên số lớn, nhãn ngắn, đơn vị rõ ràng: `%`, `tỷ đồng`, `căn`, `km`.
- Không dựng biểu đồ phức tạp chỉ để “đẹp”.
- Bản đồ chỉ có vùng, marker, tên địa danh; không nhái bản đồ thương hiệu.

### Chữ trên hình

- `on_screen_text`: 3–7 từ; đây là tiêu đề cảnh, không phải phụ đề.
- Một màn hình không quá hai cấp chữ: tiêu đề và số/nhãn hỗ trợ.
- Không viết IN HOA cả đoạn dài.
- Chữ quan trọng phải nằm trong vùng an toàn: trái/phải 72 px, trên 180 px, dưới 360 px.

## 8. Nhịp dựng 52 giây

| Khoảng | Vai trò | Cách dựng |
|---|---|---|
| 0–2 giây | Hook | Chữ/số/sự kiện lớn xuất hiện ngay; không mở bằng intro logo. |
| 2–10 giây | Bối cảnh | Một B-roll hoặc map/graphic để đặt người xem vào câu chuyện. |
| 10–30 giây | Dữ kiện chính | Luân phiên B-roll thật và đồ họa số liệu; mỗi cảnh một fact. |
| 30–42 giây | Mâu thuẫn hoặc turning point | So sánh hai lực kéo, số liệu ngược chiều, hoặc tác động cụ thể. |
| 42–52 giây | Payoff | Kết luận trung tính, chỉ ra điều cần theo dõi; không CTA sáo rỗng. |

Transition mặc định là `cut`. Chỉ dùng `fade` khi đổi chủ đề hoặc không khí. Không dùng chuyển cảnh phô trương, glitch, rung lắc, zoom giật hoặc SFX dồn dập cho bản tin kinh tế/trung tính.

## 9. Voice, phụ đề và nhạc

### Voice

- Ghép `hook + script_voice`; không được mất câu đầu hoặc câu kết.
- Đo duration voice thật sau khi TTS. Nếu lệch đáng kể, co/giãn cảnh hợp lý thay vì cắt tiếng.
- Nếu TTS lỗi hoặc audio quá ngắn: dừng job; không xuất video thiếu voice.

### Phụ đề

- Sinh timecode từ audio thật, không chia đều theo ước lượng JSON.
- 4–7 từ mỗi cụm; tối đa hai dòng.
- Highlight số liệu/từ khoá vừa phải.
- Đặt phụ đề phía trên vùng UI TikTok, không trùng on-screen text.

### Nhạc

- Nhạc chỉ là nền, duck dưới voice.
- `is_sensitive=true`: energy 1, không whoosh, không bass dồn.
- Tin kinh tế/trung tính: `neutral_news`, energy 2, nhịp tiết chế.
- Không có nhạc đã kiểm chứng license → render voice-only; không dùng nhạc không rõ nguồn.

## 10. Quality gate trước khi xuất

Chặn render hoặc đưa vào hàng duyệt khi có một trong các lỗi:

- JSON không hợp lệ hoặc fact trong voice không có trong `fact_sheet`.
- Asset không có manifest/license, bị gắn AI/publisher/unknown, hoặc có logo/watermark.
- Hình mờ, quá nhỏ cho khung 1080×1920, trùng nhiều lần hoặc không liên quan beat.
- Thiếu voice, voice bị cụt, nhạc che voice, hoặc có khoảng im lặng bất thường.
- Sai 1080×1920, 30 fps, H.264/AAC, subtitle ngoài safe area, black frame/freeze kéo dài.

Sau render, lưu cùng job: JSON gốc, JSON đã normalize, asset manifest, file voice, phụ đề, video final và report QA.

## 11. Điều agent không được tự ý làm

- Không viết lại kịch bản bằng AI khác.
- Không đổi hook/ý chính khi không có lệnh sửa JSON.
- Không tìm ảnh từ bài báo hay dùng DuckDuckGo để “lấp cảnh”.
- Không suy diễn số liệu, xu hướng hoặc dự báo từ fact sheet.
- Không upload video nếu QA hoặc rights gate chưa đạt.

## 12. Definition of Done

Một job hoàn thành khi:

1. JSON v1 hợp lệ và được lưu nguyên bản.
2. Mọi cảnh có B-roll được cấp phép hoặc graphic fallback có ý nghĩa.
3. Voice, subtitle, BGM khớp timeline.
4. Không có ảnh AI, ảnh báo chí, logo, watermark hoặc asset không rõ quyền.
5. MP4 đạt 1080×1920, 30 fps, H.264/AAC và qua VideoQA.
