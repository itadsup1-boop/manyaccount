"""Create the single text file an operator uploads to ChatGPT Web."""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_PROFILE = """[HỒ SƠ KÊNH]
Khán giả: Việt Nam, 18-35 tuổi.
Tone: tin kinh tế nhanh, trung tính, không giật gân.
Thời lượng: 52 giây.
Đầu ra: chỉ JSON thuần, không Markdown.

[CHÍNH SÁCH RENDER VÀ QUYỀN SỬ DỤNG]
Video bắt buộc 1080x1920, 30 fps.
Chế độ: facts_and_licensed_real_stock_only.
Chỉ dùng ảnh hoặc video chân thực có license rõ ràng; không dùng ảnh AI.
Không dùng ảnh, video, screenshot, logo hoặc watermark của bài báo, toà soạn
hoặc bất kỳ thương hiệu bên thứ ba nào. Không crop, che, xoá hay tái tạo logo.
Khi không có tư liệu stock phù hợp, hãy ghi visual_fallback là đồ hoạ dữ liệu,
typography hoặc bản đồ tự dựng không có logo.
"""


def make_article_upload_file(
    *,
    article_text: str,
    source_url: str,
    publisher: str,
    output_path: str | Path,
    published_at: str = "",
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Write a clean text attachment for the News Video Studio plugin."""
    clean_text = "\n".join(line.rstrip() for line in article_text.strip().splitlines()).strip()
    if not clean_text:
        raise ValueError("Không thể tạo file upload khi chưa có nội dung bài báo.")
    content = (
        f"{profile.strip()}\n\n"
        "[NGUỒN]\n"
        f"URL: {source_url.strip()}\n"
        f"Toà soạn: {publisher.strip()}\n"
        f"Ngày xuất bản: {published_at.strip() or '[chưa xác định]'}\n\n"
        "[BÀI BÁO]\n"
        f"{clean_text}\n"
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Tạo file bài báo để upload vào News Video Studio.")
    parser.add_argument("article_file", help="File TXT chứa nội dung bài báo đã làm sạch")
    parser.add_argument("--url", required=True, help="URL nguồn thuần")
    parser.add_argument("--publisher", required=True, help="Tên toà soạn")
    parser.add_argument("--published-at", default="", help="Ngày xuất bản nếu biết")
    parser.add_argument("--output", required=True, help="Đường dẫn article_input.txt")
    args = parser.parse_args()
    article_path = Path(args.article_file)
    if not article_path.is_file():
        parser.error(f"Không tìm thấy file bài báo: {article_path}")
    result = make_article_upload_file(
        article_text=article_path.read_text(encoding="utf-8"),
        source_url=args.url,
        publisher=args.publisher,
        published_at=args.published_at,
        output_path=args.output,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
