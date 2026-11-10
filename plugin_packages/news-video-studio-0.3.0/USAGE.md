# Cách dùng News Video Studio 0.3

1. Từ Tool Media, tạo `article_input.txt` có các khối nguồn và toàn văn bài báo.
2. Đính kèm file vào ChatGPT, gọi `@News Video Studio`, gửi: `Đọc file đính kèm và chỉ trả News Video Production JSON v2.`
3. Tải JSON về Tool Media. HyperFrames sẽ chỉ dùng asset thật khi asset service đã bổ sung local path và license hợp lệ; các cảnh khác dùng graphic fallback.

JSON không được gắn ảnh hoặc asset của toà soạn. `stock_requests` chỉ là brief để Tool Media lấy B-roll có licence, không phải asset đã được phép dùng.
