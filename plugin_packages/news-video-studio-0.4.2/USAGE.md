# News Video Studio 0.5 — Tool Media (1 biến visual_query chi tiết)

Đính kèm file bài báo vào ChatGPT và gửi:

```text
@News Video Studio
Đọc file đính kèm và chỉ trả Tool Media Article JSON v1.
```

## Lưu ý về hình ảnh trong JSON:
Mỗi beat chỉ dùng **duy nhất 1 biến `visual_query`** mô tả chi tiết, chân thực, sát đúng nội dung bài báo:
- Beat B-roll: Nêu rõ người/vật/hành động đời thường/bối cảnh thực tế gắn với tin tức Việt Nam để công cụ tìm ảnh thực tế từ Google Images / kho ảnh.
- Beat Đồ họa: Bắt đầu bằng tiền tố `DATA GRAPHIC:` hoặc `MAP GRAPHIC:`.
- Không tạo các biến phụ rườm rà (`asset_search_queries`, `visual_brief`, `visual_fallback`, `required_country`, `country_strict`).

Tải JSON về Tool Media để hệ thống tự động tải ảnh/video thực tế, tạo TTS, phụ đề, nhạc nền và dựng video hoàn chỉnh.
