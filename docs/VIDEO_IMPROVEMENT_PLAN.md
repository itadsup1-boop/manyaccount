# Kế hoạch cải thiện hệ thống sản xuất video TikTok

## 1. Thông tin tài liệu

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái | Đợt 1-9 hoàn thành |
| Cập nhật gần nhất | 2026-08-23 |
| Phạm vi | Article, Facebook, TikTok Matrix, Telegram và Central Hub |
| Mục tiêu | Tăng chất lượng nội dung, khả năng giữ chân, tính nguyên bản và độ ổn định của đầu ra video |
| Nguyên tắc | Tối ưu chất lượng và tuân thủ nền tảng; không sử dụng thủ thuật né nhận diện |
| Cách triển khai | Chia nhỏ theo sprint, có kiểm thử và có thể quay lại phiên bản cũ |

Tài liệu này là nguồn kế hoạch chính cho các thay đổi sắp tới. Khi bắt đầu triển khai, cập nhật trạng thái từng hạng mục ngay trong checklist ở cuối tài liệu.

## 2. Kết quả mong muốn

Hệ thống đích:

~~~text
Thu thập nhiều nguồn
→ lọc trùng và chấm điểm nguồn
→ chọn đúng chủ đề cho từng kênh
→ tạo nhiều hướng hook
→ lập cấu trúc câu chuyện và các beats
→ kiểm định nội dung và bằng chứng
→ tạo voice, hình, phụ đề, nhạc và SFX
→ render một lần với cấu hình chuẩn
→ kiểm tra video tự động
→ upload và ghi đúng trạng thái
→ thu thập hiệu suất
→ học từ video thắng/thua của từng kênh
~~~

Không hứa bảo đảm số view. Hệ thống phải tăng xác suất tạo video tốt hơn và cung cấp dữ liệu để biết thay đổi nào thực sự có hiệu quả.

## 3. Hiện trạng

### 3.1. Thành phần đã có

- Hồ sơ biên tập theo kênh trong config/channel_editorial_profiles.json.
- Prompt có hook, script, quality_score, topic_fit và scenes.
- Quality gate cơ bản trước khi dựng.
- TTS, phụ đề, frame, logo và FFmpeg renderer.
- Nhạc nền theo mood, energy và mức độ nhạy cảm.
- Ducking nhạc khi voice phát.
- Chống lặp bài/video nguồn.
- Upload Drive, ghi Google Sheet và một phần báo cáo Telegram.

### 3.2. Khoảng trống cần xử lý

- AI chỉ tạo một hook và tự chấm điểm cho chính kết quả của nó.
- Chưa có schema và validator dùng chung cho mọi pipeline.
- Chưa kiểm tra chặt sự liên kết giữa hook, bằng chứng và payoff.
- Scenes chưa điều khiển timeline dựng một cách đầy đủ.
- Nhiều profile/prompt đang bị viết lặp ở nhiều file.
- Pipeline thường xử lý nguồn theo thứ tự thay vì xếp hạng nhiều ứng viên.
- Một số renderer còn dùng speed, màu, lens distortion và noise ngẫu nhiên.
- Có đường code nối byte ngẫu nhiên vào cuối MP4.
- Một số video bị encode nhiều lần.
- Chưa có Video QA bắt buộc trước upload.
- Trạng thái done có thể được ghi trước khi render/upload hoàn tất.
- Chưa có vòng phản hồi từ hiệu suất TikTok về prompt và cấu trúc video.

## 4. Nguyên tắc nội dung và thương hiệu

### 4.1. Voice và tone

- Voice là tính cách ổn định của từng kênh.
- Tone thay đổi theo ngữ cảnh của từng tin.
- Tin nghiêm trọng phải bình tĩnh và tôn trọng nạn nhân.
- Tin thể thao có thể nhanh và giàu năng lượng.
- Tin giải trí có thể sinh động nhưng không mỉa mai hoặc kết luận vô căn cứ.
- Tin tài chính phải rõ số liệu, tác động và nguồn chứng minh.

### 4.2. Thông điệp

Mỗi video phải trả lời được:

1. Video dành cho ai?
2. Điều gì khiến họ quan tâm ngay?
3. Người xem nhận được thông tin hoặc cảm xúc gì ở cuối?
4. Có dữ kiện nào chứng minh?
5. Nội dung có đúng lời hứa của kênh không?

### 4.3. Tính nhất quán

- Một nguồn cấu hình duy nhất cho hồ sơ biên tập.
- Font, màu, logo, vị trí chữ và phong cách hình nhất quán theo kênh.
- Không dùng cùng một kiểu câu cho mọi kênh.
- Không thay đổi màu hoặc hiệu ứng ngẫu nhiên giữa các video.

## 5. Roadmap triển khai

## Giai đoạn 1 — Chuẩn hóa dữ liệu nội dung

### 5.1. Tạo content schema

Tạo mới:

- shared/core/content_models.py
- shared/core/content_normalizer.py
- tests/test_content_models.py

Schema đề xuất:

~~~json
{
  "schema_version": 1,
  "content_id": "",
  "channel_id": "",
  "source_type": "article",
  "source_url": "",
  "story_type": "explainer",
  "main_angle": "",
  "audience_payoff": "",
  "hook_variants": [
    {
      "text": "",
      "hook_type": "result",
      "promise": "",
      "score": 0
    }
  ],
  "selected_hook": "",
  "selected_hook_reason": "",
  "script_voice": "",
  "evidence": [
    {
      "claim": "",
      "source_text": "",
      "source_url": "",
      "confidence": "high"
    }
  ],
  "beats": [
    {
      "beat_number": 1,
      "role": "hook",
      "duration_hint": 2.0,
      "voice_over": "",
      "visual_query": "",
      "on_screen_text": "",
      "motion": "slow_push_in",
      "transition": "cut",
      "sfx": "",
      "must_show": []
    }
  ],
  "music_mood": "neutral_news",
  "music_energy": 2,
  "is_sensitive": false,
  "retention_risks": [],
  "risk_flags": []
}
~~~

Yêu cầu tương thích:

- Kết quả AI cũ vẫn phải chạy được qua content_normalizer.
- Field thiếu có giá trị mặc định an toàn.
- Field không hợp lệ được normalize hoặc báo lỗi rõ.
- Không làm hỏng dữ liệu đang có trên Google Sheet.

Kết quả nhận lại:

- Mọi pipeline dùng chung một định dạng.
- Renderer biết ý nghĩa và thời lượng từng đoạn.
- Có dữ liệu để phân tích hiệu suất theo story_type và hook_type.

### 5.2. Bổ sung story type

Các loại ban đầu:

- breaking_update
- warning
- explainer
- conflict
- human_story
- achievement
- comparison
- sports_moment
- entertainment_drama

Mỗi story type có cấu trúc hook, body và close riêng. Không dùng một template chung cho tất cả tin.

### 5.3. Tạo ba hook cho mỗi nội dung

Sửa:

- config/prompts/prompt_article.txt
- config/prompts/prompt_script.txt
- apps/creator_article/article_chatgpt_automator.py
- apps/creator_article/article_ai_script.py
- apps/creator_facebook/chatgpt_automator.py
- apps/creator_facebook/fb_ai_script.py

Ba hướng mặc định:

1. Kết quả hoặc sự kiện chính.
2. Mâu thuẫn hoặc chi tiết bất thường.
3. Tác động trực tiếp tới người xem.

AI phải chọn một hook và trả selected_hook_reason. Không được tạo ba câu gần giống nhau chỉ thay vài từ.

Kết quả nhận lại:

- Giảm phụ thuộc vào hook đầu tiên AI nghĩ ra.
- Có biến số rõ để A/B test.
- Tăng độ cụ thể trong hai đến ba giây đầu.

## Giai đoạn 2 — Kiểm định và sửa nội dung

### 5.4. Tạo ContentValidator

Tạo mới:

- shared/core/content_validator.py
- tests/test_content_validator.py

Validator kiểm tra:

- Độ dài và tính cụ thể của hook.
- Hook có nhân vật, sự kiện, hành động, con số hoặc tác động rõ.
- Hook không bị lặp lại ở đầu script.
- Script không có câu thừa hoặc hai câu truyền cùng một thông tin.
- Hook hứa điều gì thì body/payoff phải trả lời điều đó.
- Tin tức có evidence cho khẳng định quan trọng.
- Tiêu đề, hook, script và payoff cùng một trục.
- Tổng số từ và thời lượng ước tính phù hợp hồ sơ kênh.
- Beat đầu tiên hiển thị đúng chủ thể.
- CTA cụ thể, không dùng câu hỏi chung chung.
- Nội dung nhạy cảm dùng tone và music_mood phù hợp.
- Visual query có tên riêng, địa điểm, mẫu xe, đội bóng, con số hoặc vật thể cụ thể khi cần.

Kết quả validator:

~~~json
{
  "passed": false,
  "content_score": 72,
  "errors": [],
  "warnings": [],
  "score_breakdown": {
    "hook": 16,
    "evidence": 13,
    "retention": 14,
    "clarity": 15,
    "brand_fit": 14
  }
}
~~~

### 5.5. Tự sửa một lần

Tạo mới:

- shared/core/content_repair.py

Luồng:

~~~text
AI tạo nội dung
→ normalize
→ validate
→ nếu lỗi: gửi đúng danh sách lỗi để AI sửa một lần
→ validate lại
→ đạt mới tạo voice
→ vẫn lỗi thì skip có lý do
~~~

Không retry vô hạn.

### 5.6. Tích hợp vào pipeline

Sửa:

- apps/creator_article/article_pipeline_core.py
- apps/creator_facebook/fb_pipeline.py
- shared/core/worker.py

Vị trí bắt buộc: sau khi nhận JSON AI và trước TTS.

Kết quả nhận lại:

- Không tốn TTS/render cho kịch bản lỗi.
- Quality score không còn hoàn toàn do AI tự chấm.
- Giảm lặp hook, thiếu payoff và sai thời lượng.

## Giai đoạn 3 — Hợp nhất hồ sơ kênh và prompt

### 5.7. Một nguồn hồ sơ biên tập

Nguồn duy nhất:

- config/channel_editorial_profiles.json

Mở rộng:

~~~json
{
  "brand_voice": [],
  "tone_by_context": {},
  "audience_pains": [],
  "content_pillars": [],
  "allowed_story_types": [],
  "preferred_hook_types": [],
  "banned_phrases": [],
  "cta_styles": [],
  "evidence_standard": "strict",
  "video_style": {},
  "winning_examples": [],
  "losing_examples": []
}
~~~

Giảm và xóa dần profile viết cứng tại:

- shared/core/worker.py
- apps/creator_facebook/fb_pipeline.py
- adsup_central_hub/backend/main.py

Không ghi đè các config runtime hoặc thay đổi riêng của operator khi chưa có migration rõ ràng.

### 5.8. Tạo PromptBuilder

Tạo mới:

- shared/core/prompt_builder.py
- tests/test_prompt_builder.py

PromptBuilder chịu trách nhiệm:

- Đọc profile kênh.
- Chèn voice, tone, audience, story type và điều cấm.
- Chèn bài học hiệu suất khi đủ dữ liệu.
- Chèn schema output thống nhất.
- Không để mỗi pipeline tự ghép prompt theo một kiểu.

Kết quả nhận lại:

- Kênh tài chính không nói như showbiz.
- Kênh thể thao không dùng nhịp của tin thẩm mỹ.
- Sửa định vị một nơi sẽ cập nhật toàn hệ thống.

## Giai đoạn 4 — Chọn nguồn tốt và bảo vệ bằng chứng

### 5.9. Tạo SourceRanker

Tạo mới:

- shared/core/source_ranker.py
- tests/test_source_ranker.py

Thang điểm khởi tạo:

| Tiêu chí | Điểm tối đa |
|---|---:|
| Đúng chủ đề kênh | 25 |
| Có hook rõ | 20 |
| Có dữ kiện hoặc bằng chứng | 20 |
| Có hình ảnh kể chuyện | 15 |
| Có payoff | 10 |
| Mới hoặc đang được quan tâm | 10 |

Ngưỡng ban đầu:

- Dưới 55: bỏ.
- 55–64: hàng chờ.
- Từ 65: có thể sản xuất.
- Từ 80: ưu tiên cao.

Các ngưỡng là giả thuyết vận hành và phải điều chỉnh bằng dữ liệu thật.

Luồng mới:

~~~text
Thu thập 10–20 ứng viên
→ lọc trùng
→ kiểm tra đúng kênh
→ chấm điểm
→ chọn ứng viên tốt nhất
→ mới gọi AI đầy đủ
~~~

### 5.10. Evidence guard

Tạo mới:

- shared/core/evidence_guard.py
- tests/test_evidence_guard.py

Yêu cầu:

- Claim quan trọng phải liên kết với source_text hoặc source_url.
- Không để hình minh họa mâu thuẫn lời đọc.
- Tin chưa xác nhận phải dùng ngôn ngữ điều kiện.
- Tin sức khỏe, tài chính, pháp lý và sự kiện nghiêm trọng dùng ngưỡng evidence cao hơn.
- Không biến suy đoán thành kết luận.

## Giai đoạn 5 — Dựng theo beats

### 5.11. Timeline theo ý nghĩa

Sửa:

- apps/creator_article/article_ffmpeg.py
- shared/modules/video_remix.py
- apps/creator_facebook/fb_pipeline.py

Không chia đều thời lượng cho mọi ảnh. Timeline mẫu:

| Thời gian | Vai trò |
|---|---|
| 0–2 giây | Hook và hình mạnh nhất |
| 2–5 giây | Bối cảnh hoặc lời hứa |
| 5–16 giây | Dữ kiện và diễn biến |
| 16–23 giây | Tác động hoặc payoff |
| 23–28 giây | Câu chốt cụ thể |

Thời lượng thực tế lấy từ profile kênh và audio, không cố kéo mọi video về 28 giây.

### 5.12. Frame đầu

Quy tắc:

- Chủ thể chính xuất hiện ngay.
- Text hook đầu chỉ khoảng 3–7 từ trên màn hình.
- Không dùng intro logo trước nội dung.
- Không dùng ảnh minh họa chung chung.
- Ưu tiên gương mặt, hành động, con số hoặc vật thể đang được nói tới.
- Các thành phần quan trọng nằm trong safe zone.

### 5.13. Phụ đề

Sửa:

- shared/modules/subtitle_renderer.py

Thêm:

- Chia theo cụm ý.
- Highlight tên riêng, con số và từ khóa.
- Tối đa hai dòng.
- Không che chủ thể.
- Không nằm dưới vùng caption và nút TikTok.
- Preset font, màu, viền và vị trí theo từng kênh.
- Fallback an toàn khi Whisper không tạo được word timestamp.

### 5.14. SFX theo beat

Tạo mới:

- shared/services/audio_director.py
- tests/test_audio_director.py

Quy tắc:

- Không thêm whoosh ngẫu nhiên.
- Chỉ thêm SFX ở reveal, con số, bước ngoặt hoặc cảnh báo.
- Tối đa 2–3 SFX trong video khoảng 30 giây.
- Nội dung bi kịch có thể không dùng SFX.
- SFX không được lấn voice.

## Giai đoạn 6 — Chuẩn hóa đầu ra video

Mục tiêu là tạo file sạch, tương thích và có chất lượng như một sản phẩm được biên tập chuyên nghiệp. Không giả metadata Premiere/CapCut và không dùng thủ thuật né nhận diện.

### 5.15. Cấu hình encode dùng chung

Tạo mới:

- shared/core/video_encoding.py
- tests/test_video_encoding.py

Preset đầu ra đề xuất:

~~~python
FINAL_VIDEO_ARGS = [
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "19",
    "-pix_fmt", "yuv420p",
    "-profile:v", "high",
    "-level:v", "4.1",
    "-r", "30",
    "-fps_mode", "cfr",
    "-g", "60",
    "-keyint_min", "60",
    "-movflags", "+faststart",
]

FINAL_AUDIO_ARGS = [
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "48000",
    "-ac", "2",
]
~~~

Thông số mục tiêu:

| Thuộc tính | Giá trị |
|---|---|
| Container | MP4 |
| Video codec | H.264 |
| Kích thước | 1080×1920 |
| Tỷ lệ | 9:16 |
| Pixel format | yuv420p |
| Frame rate | 30 FPS CFR |
| Preset | medium |
| CRF | 19 |
| Profile | High |
| Level | 4.1 |
| GOP | 60 frame |
| Audio | AAC 192 kbps |
| Sample rate | 48 kHz |
| Channels | Stereo |
| Streaming | faststart |

Không nâng lên 60 FPS nếu nguồn không có chuyển động 60 FPS thật.

### 5.16. Xóa biến đổi né fingerprint

Sửa:

- shared/modules/video_remix.py
- apps/creator_facebook/fb_pipeline.py
- apps/creator_article/article_ffmpeg.py

Loại bỏ:

- Speed ngẫu nhiên.
- Lens distortion ngẫu nhiên.
- Noise ngẫu nhiên phủ toàn video.
- Brightness, contrast và saturation ngẫu nhiên.
- Nối byte ngẫu nhiên bằng os.urandom.
- Metadata giả phần mềm biên tập.
- Random SFX.
- Chuyển cảnh random không liên quan nội dung.

Thay thế:

- Color preset cố định theo kênh và ngữ cảnh.
- Motion/transition lấy từ beats.
- Encode chuẩn và nhất quán.
- Nội dung nguyên bản nhờ lời bình, cấu trúc, bằng chứng và giá trị biên tập.

### 5.17. Color preset

Mở rộng config/channel_editorial_profiles.json:

~~~json
{
  "video_style": {
    "color_preset": "clean_news",
    "contrast": 1.02,
    "saturation": 1.03,
    "brightness": 0.0,
    "sharpen": 0.2
  }
}
~~~

Preset ban đầu:

- clean_news
- serious_news
- warm_positive
- sports_energy
- entertainment_pop
- sensitive_neutral

Thông số phải có giới hạn an toàn để không cháy sáng, bệt màu hoặc tạo màu da bất thường.

### 5.18. Motion preset

Motion hợp lệ:

- static
- slow_push_in
- slow_pull_out
- pan_left
- pan_right
- subject_follow

Quy tắc:

- Hook: cut hoặc push-in nhẹ.
- Bằng chứng: ổn định để nhìn rõ.
- Cao trào: chuyển động rõ hơn nhưng không rung.
- Nội dung nhạy cảm: chuyển động chậm.
- Không dùng lens distortion để thay đổi fingerprint.

### 5.19. Giảm số lần encode

Luồng đích:

~~~text
Chuẩn bị media
→ ghép hình, frame, chữ, logo, voice, BGM và SFX trong filter graph
→ encode một lần thành final.mp4
~~~

Nếu chưa thể chuyển ngay sang một pass:

- Intermediate dùng cấu hình chất lượng cao.
- Concat bằng stream copy khi codec/timebase tương thích.
- Không dùng ultrafast với CRF mặc định cho intermediate.
- Chỉ có tối đa một lần encode lossy cuối.

Kết quả nhận lại:

- Giảm bệt hình và vỡ chữ.
- Chi tiết khuôn mặt tốt hơn.
- Phụ đề sắc hơn.
- Giảm generation loss.
- Đầu ra đồng nhất giữa các pipeline.

### 5.20. Safe zone

Tạo mới:

- config/video_safe_zones.json
- shared/core/safe_zone.py
- tests/test_safe_zone.py

Kiểm soát:

- Hook không sát mép trên.
- Phụ đề không đè caption phía dưới.
- Text/logo không nằm dưới các nút bên phải.
- Tối đa hai dòng phụ đề.
- Có preset dự phòng cho caption dài.

## Giai đoạn 7 — Quyền sử dụng và tính nguyên bản

### 5.21. RightsGuard

Tạo mới:

- shared/core/rights_guard.py
- config/media_source_policy.json
- tests/test_rights_guard.py

Metadata media:

~~~json
{
  "source_url": "",
  "owner": "",
  "license_status": "verified",
  "usage_type": "editorial",
  "watermark_detected": false,
  "requires_ai_label": false
}
~~~

Quy tắc:

- Nhạc unverified chỉ dùng thử nội bộ.
- Không phát hành media không rõ nguồn khi policy yêu cầu xác minh.
- Không đăng video còn watermark của nguồn khác.
- Crop, blur hoặc gắn logo không tự biến video thành nội dung nguyên bản.
- Nội dung phải có lời bình, cấu trúc và giá trị biên tập mới.
- Đánh dấu requires_ai_label khi nội dung AI thuộc trường hợp nền tảng yêu cầu công khai.

Tài liệu nền tảng tham khảo:

- TikTok Creative Best Practices: https://ads.tiktok.com/help/article/creative-best-practices
- TikTok Community Guidelines — Integrity and Authenticity: https://www.tiktok.com/community-guidelines/en/integrity-authenticity/
- TikTok Commercial Music Library: https://ads.tiktok.com/resources/help/article/commercial-music-library

## Giai đoạn 8 — Video QA bắt buộc

### 5.22. Tạo VideoQA

Tạo mới:

- shared/core/video_qa.py
- tests/test_video_qa.py

Kết quả mẫu:

~~~json
{
  "container_valid": true,
  "video_codec": "h264",
  "resolution": "1080x1920",
  "aspect_ratio": "9:16",
  "pixel_format": "yuv420p",
  "fps": 30,
  "audio_codec": "aac",
  "audio_sample_rate": 48000,
  "audio_channels": 2,
  "decode_ok": true,
  "safe_zone_ok": true,
  "black_frame_ok": true,
  "freeze_frame_ok": true,
  "silence_ok": true,
  "loudness_ok": true,
  "watermark_ok": true,
  "passed": true,
  "blocking_errors": [],
  "warnings": []
}
~~~

Chặn upload nếu:

- Không decode hết video.
- Sai tỷ lệ hoặc kích thước.
- Không có audio.
- Voice bị nhạc lấn nghiêm trọng.
- Có màn đen hoặc đứng hình dài.
- Text chính nằm ngoài safe zone.
- Có watermark không được phép.
- File chưa render hoàn chỉnh.

Cảnh báo nhưng có thể cho phép:

- Thời lượng lệch nhẹ so với profile.
- Loudness lệch nhỏ.
- Một visual query không có kết quả tốt nhưng nội dung vẫn đúng.

## Giai đoạn 9 — Trạng thái và quan sát pipeline

### 5.23. Chuẩn hóa vòng đời

Trạng thái:

~~~text
selected
→ scripted
→ validated
→ voiced
→ rendered
→ qa_passed
→ uploaded
→ published
→ measured
~~~

Trạng thái lỗi có error_code và retryable:

~~~json
{
  "status": "failed",
  "stage": "rendered",
  "error_code": "FFMPEG_DECODE_FAILED",
  "retryable": true,
  "message": ""
}
~~~

Sửa:

- apps/creator_article/article_pipeline_core.py
- apps/creator_facebook/fb_pipeline.py
- shared/core/worker.py
- shared/services/sheet_api.py
- apps/creator_article/article_sheet_api.py
- apps/creator_facebook/fb_sheet_api.py
- shared/services/tele_reporter.py

Không ghi done trước khi render, QA và upload hoàn tất.

## Giai đoạn 10 — Đo hiệu suất và tự học

### 5.24. Performance store

Tạo mới:

- shared/services/performance_store.py
- shared/core/performance_analyzer.py
- scripts/import_tiktok_metrics.py
- tests/test_performance_analyzer.py

Dữ liệu:

~~~json
{
  "video_id": "",
  "channel_id": "",
  "source_type": "",
  "source_domain": "",
  "story_type": "",
  "hook_type": "",
  "duration": 0,
  "music_mood": "",
  "visual_beat_count": 0,
  "views": 0,
  "average_watch_time": 0,
  "watched_full_rate": 0,
  "likes": 0,
  "comments": 0,
  "shares": 0,
  "saves": 0,
  "follows": 0,
  "measured_at": ""
}
~~~

Mốc đo đề xuất:

- 2 giờ.
- 24 giờ.
- 72 giờ.
- 7 ngày.

Giai đoạn đầu nhập CSV hoặc Google Sheet. Chỉ kết nối API chính thức khi tài khoản có quyền phù hợp.

### 5.25. Experiment manager

Tạo mới:

- shared/core/experiment_manager.py
- tests/test_experiment_manager.py

Mỗi thử nghiệm chỉ thay một biến:

- Hook kết quả so với hook mâu thuẫn.
- 22 giây so với 28 giây.
- Phụ đề thường so với highlight từ khóa.
- Sáu beats so với tám beats.
- Có CTA cụ thể so với không CTA.
- Music energy 1 so với 2.

Không thay đồng thời hook, voice, nhạc, màu và độ dài.

### 5.26. Channel learning

Runtime data:

- data/channel_learning.json

Mẫu:

~~~json
{
  "Adsupnews": {
    "sample_size": 42,
    "winning_hook_types": ["result", "conflict"],
    "winning_story_types": ["breaking_update", "explainer"],
    "best_duration_range": [22, 25],
    "weak_patterns": [
      "hook mở bằng bối cảnh",
      "câu cuối chung chung"
    ]
  }
}
~~~

Quy tắc:

- Không kết luận khi mẫu quá nhỏ.
- So sánh trong cùng kênh và cùng nhóm nội dung.
- Dùng median và tỷ lệ trên 1.000 view để giảm ảnh hưởng của một video đột biến.
- Bài học được chèn vào prompt qua PromptBuilder.
- Operator có thể tắt hoặc xóa bài học sai.

### 5.27. Central Hub

Sau khi performance store ổn định:

- Thêm API hiệu suất thật vào adsup_central_hub/backend.
- Thay số liệu hardcoded.
- Hiển thị retention, completion, share/save/follow trên 1.000 view.
- So sánh theo kênh, story type, hook type, độ dài và music mood.
- Hiển thị lỗi pipeline theo stage.
- Có bộ lọc thời gian và số mẫu tối thiểu.

## 6. Thứ tự sprint

| Sprint | Phạm vi | Ưu tiên |
|---|---|---|
| 1 | Content schema, story type, ba hook | P0 |
| 2 | ContentValidator, content repair và tích hợp ba pipeline | P0 |
| 3 | Hợp nhất profile và PromptBuilder | P0 |
| 4 | SourceRanker, evidence guard và rights guard cơ bản | P1 |
| 5 | Beat renderer, frame đầu, phụ đề và SFX có chủ đích | P1 |
| 6 | Xóa biến đổi né fingerprint, chuẩn hóa FFmpeg và giảm encode | P0 |
| 7 | VideoQA và trạng thái pipeline chính xác | P0 |
| 8 | Performance store và nhập số liệu | P1 |
| 9 | A/B test, channel learning và Central Hub | P2 |

Giai đoạn 6 và 7 phải hoàn thành trước khi coi renderer mới sẵn sàng production.

## 7. Tiêu chí nghiệm thu tổng

### 7.1. Nội dung

- 100% JSON AI được normalize.
- Không tạo TTS nếu nội dung chưa qua validator.
- Mỗi nội dung có ba hook khác biệt thật sự.
- Hook, body và payoff cùng lời hứa.
- Tin tức có evidence cho claim quan trọng.
- Nội dung nhạy cảm có tone và nhạc phù hợp.
- Profile từng kênh được áp dụng nhất quán.

### 7.2. Hình ảnh

- Frame đầu hiển thị đúng chủ thể.
- Timeline bám beats.
- Không có random noise hoặc lens distortion.
- Không có chữ quan trọng ngoài safe zone.
- Phụ đề tối đa hai dòng và bám voice.
- Không có watermark không được phép.

### 7.3. Âm thanh

- Voice rõ hơn BGM.
- BGM đúng mood và không lặp quá gần.
- Không dùng nhạc production có license_status unverified.
- SFX có chủ đích và không lấn voice.
- Không có khoảng im lặng ngoài chủ đích.

### 7.4. File đầu ra

- MP4 H.264, 1080×1920, yuv420p, 30 FPS CFR.
- AAC 48 kHz stereo.
- Decode hoàn chỉnh bằng FFmpeg.
- Không nối byte ngẫu nhiên.
- Không metadata giả Premiere/CapCut.
- Tối đa một lần encode lossy cuối.
- VideoQA passed trước upload.

### 7.5. Vận hành

- Không ghi done trước upload thành công.
- Mọi lỗi có stage và error_code.
- Có log content score, QA score và trạng thái.
- Không làm thay đổi production channel state trong automated tests.

## 8. Kiểm thử bắt buộc

### 8.1. Unit tests

- Content schema và normalize legacy JSON.
- Content validator.
- Prompt builder theo từng kênh.
- Source ranker.
- Evidence guard.
- Audio director.
- Video encoding preset.
- Video QA.
- Performance analyzer.

### 8.2. Smoke tests

1. Article từ ảnh, hook voice, script voice, subtitle và BGM.
2. Facebook có frame.
3. Facebook không frame, có audio nguồn.
4. TikTok remix có voice mới và BGM.
5. Nội dung nhạy cảm bắt buộc dùng sensitive_empathy.
6. Video không có BGM vẫn render an toàn.
7. Video lỗi decode bị QA chặn.

### 8.3. Lệnh kiểm tra tối thiểu

~~~bash
.venv/bin/python -m compileall apps shared adsup_central_hub/backend
.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
~~~

Frontend, khi có thay đổi:

~~~bash
cd adsup_central_hub/frontend
npm run lint
npm run build
~~~

## 9. Đo kết quả sau triển khai

Chỉ so sánh khi có ít nhất khoảng 30 video cho mỗi kênh hoặc mỗi nhóm thử nghiệm đủ mẫu.

KPI chính:

- Average watch time.
- Average watch percentage.
- Watched full rate.
- Retention ở hai và sáu giây nếu lấy được.
- Share trên 1.000 view.
- Save trên 1.000 view.
- Follow trên 1.000 view.

KPI phụ:

- Comment trên 1.000 view.
- Tỷ lệ video qua validator.
- Tỷ lệ video qua VideoQA.
- Tỷ lệ render/upload thành công.
- Thời gian và chi phí trung bình trên một video hoàn thành.

Đánh giá uplift theo tỷ lệ tương đối so với baseline, không chỉ nhìn tổng view.

## 10. Rủi ro và biện pháp

| Rủi ro | Biện pháp |
|---|---|
| Schema mới làm hỏng JSON cũ | ContentNormalizer và test legacy |
| Validator quá chặt làm giảm sản lượng | Tách error/warning và theo dõi skip rate |
| AI repair làm tăng chi phí | Chỉ repair một lần |
| Renderer một pass quá phức tạp | Triển khai theo mode, giữ feature flag |
| Config kênh bị ghi đè | Migration rõ ràng, không sửa runtime state |
| Media không rõ giấy phép | RightsGuard và catalog license_status |
| Dữ liệu hiệu suất ít | Chỉ học khi đủ mẫu |
| Một video viral làm lệch kết luận | Dùng median và chỉ số trên 1.000 view |
| Chất lượng hình giảm do encode nhiều lần | Một lần encode lossy cuối và VideoQA |

## 11. Chiến lược rollout

- Mỗi thay đổi lớn có feature flag.
- Chạy thử với một kênh và dữ liệu không production.
- So sánh video cũ/mới bằng cùng nguồn.
- Không chuyển tất cả kênh cùng lúc.
- Giữ fallback legacy cho tới khi smoke test ổn định.
- Chỉ bật production sau khi ContentValidator và VideoQA đều hoạt động.

Feature flag dự kiến:

~~~text
CONTENT_SCHEMA_V1
CONTENT_VALIDATOR_ENABLED
CONTENT_REPAIR_ENABLED
BEAT_RENDERER_ENABLED
CLEAN_ENCODING_ENABLED
VIDEO_QA_REQUIRED
CONTENT_EXPERIMENTS_ENABLED
PERFORMANCE_LEARNING_ENABLED
~~~

## 12. Checklist triển khai

Ký hiệu:

- [ ] Chưa làm.
- [~] Đang làm.
- [x] Hoàn thành và đã kiểm thử.

### Nội dung

- [x] Tạo content_models.py.
- [x] Tạo content_normalizer.py.
- [x] Bổ sung story_type.
- [x] Bổ sung ba hook và selected_hook.
- [x] Bổ sung evidence và beats.
- [x] Tạo ContentValidator.
- [x] Tạo content repair một lần.
- [x] Tích hợp Article pipeline.
- [x] Tích hợp Facebook pipeline.
- [x] Tích hợp TikTok Matrix worker.

### Thương hiệu và prompt

- [x] Mở rộng channel_editorial_profiles.json.
- [x] Tạo PromptBuilder.
- [x] Xóa dần profile viết cứng trùng lặp.
- [x] Tạo preset voice/tone theo ngữ cảnh.
- [x] Tạo preset màu, chữ và motion theo kênh.

### Nguồn và bằng chứng

- [x] Tạo SourceRanker.
- [x] Chấm nhiều ứng viên trước khi sản xuất.
- [x] Tạo EvidenceGuard.
- [x] Tạo RightsGuard.
- [ ] Xác minh giấy phép BGM production.

Lưu ý: catalog BGM production hiện chưa có track được xác minh. Hệ thống sẽ
giữ voice-only nếu track chưa có cả `license_status=approved` và
`license_source`; không đánh dấu hoàn thành mục giấy phép khi chưa có hồ sơ thật.

### Renderer

- [x] Chuyển Article sang timeline theo beats.
- [x] Chuyển Facebook sang timeline theo beats.
- [x] Chuyển TikTok Remix sang timeline theo beats.
- [x] Cải thiện frame đầu.
- [x] Cải thiện subtitle theo cụm ý.
- [x] Thay random SFX bằng AudioDirector.

### Encoder

- [x] Tạo video_encoding.py.
- [x] Dùng preset chung ở Article.
- [x] Dùng preset chung ở Facebook.
- [x] Dùng preset chung ở TikTok Remix.
- [x] Xóa random speed.
- [x] Xóa lens distortion ngẫu nhiên.
- [x] Xóa random noise.
- [x] Xóa random color grading.
- [x] Xóa os.urandom nối byte vào MP4.
- [x] Loại bỏ metadata giả nếu có.
- [x] Giảm xuống tối đa một lần encode lossy cuối.
- [x] Chuẩn hóa audio về AAC 48 kHz stereo.

### QA và vận hành

- [x] Tạo safe_zone.py.
- [x] Tạo VideoQA.
- [x] Chặn upload khi QA fail.
- [x] Chuẩn hóa trạng thái pipeline.
- [x] Sửa quality log không ghi done quá sớm.
- [x] Thêm error_code theo stage.
- [x] Viết smoke test cho ba mode render.

### Dữ liệu và học hỏi

- [x] Tạo performance store.
- [x] Tạo script nhập metrics.
- [x] Tạo experiment manager.
- [x] Tạo channel learning.
- [x] Thêm performance API vào Central Hub.
- [x] Thay dashboard hardcoded bằng dữ liệu thật.

## 13. Hạng mục làm đầu tiên

Gói đầu tiên nên triển khai:

~~~text
Content schema
+ ba hook
+ story type
+ ContentValidator
+ content repair một lần
+ tích hợp Article/Facebook/TikTok Matrix
~~~

Sau đó triển khai beat renderer, clean encoding và VideoQA trước khi xây vòng học hiệu suất.

## 14. Nhật ký triển khai

### 2026-08-23 — Hoàn thành Đợt 1

Đã thực hiện:

- Content schema phiên bản 1 và content_id ổn định theo nguồn/kênh.
- Normalizer tương thích JSON cũ, đồng thời chuyển scenes cũ thành beats/scenes dùng tiếp cho renderer hiện tại.
- Chín story type.
- Ba hook bắt buộc theo result, conflict và impact.
- selected_hook, selected_hook_reason, main_angle, audience_payoff, evidence, beats, retention_risks và risk_flags.
- ContentValidator chấm điểm theo hook, evidence, structure, clarity, safety và brand fit.
- Nhận diện thêm nội dung nhạy cảm từ lời đọc để không chỉ tin field AI.
- Sửa kịch bản qua AI tối đa một lần; không sửa nội dung đã bị đánh dấu sai chủ đề/không nên làm.
- Chặn Article, Facebook và TikTok Matrix trước TTS khi validator vẫn không đạt.
- Đồng bộ prompt cho ChatGPT automator và hai Gemini client dự phòng.

Kiểm tra đã chạy:

~~~text
python -m compileall: đạt
unittest: 14/14 đạt
git diff --check: đạt
~~~

### 2026-08-23 — Hoàn thành Đợt 2

Đã thực hiện:

- Chuyển tám hồ sơ kênh về nguồn trung tâm config/channel_editorial_profiles.json.
- Bổ sung brand voice, tone theo story type/ngữ cảnh nhạy cảm, audience pains, content pillars, story type/hook ưu tiên, cụm từ cấm, CTA, chuẩn bằng chứng và mẫu thắng/thua.
- Tạo preset voice có tốc độ và hướng đọc riêng cho tin nóng, cảnh báo, tích cực, nhạy cảm và ngữ cảnh chuyên biệt của từng kênh.
- Tạo preset màu, chữ, motion và first frame riêng cho từng kênh; không dùng hiệu ứng ngẫu nhiên trong preset.
- Tạo shared/core/prompt_builder.py để hợp nhất profile, override operator, tone, voice, output schema và điểm chèn bài học hiệu suất.
- Tích hợp PromptBuilder vào ChatGPT/Gemini của Article, Facebook và TikTok Matrix.
- Xóa profile viết cứng trùng khỏi worker.py, fb_pipeline.py và Central Hub backend.
- Central Hub vẫn giữ override operator cũ, nhưng chỉ lưu field thực sự khác cấu hình trung tâm để không nhân bản profile.
- TTS chọn tốc độ theo story_type, tone và is_sensitive; config voice_speed riêng của operator vẫn có quyền ghi đè sau cùng.

Kiểm tra đã chạy:

~~~text
JSON profile: 8/8 đủ preset Đợt 2
python -m compileall apps shared adsup_central_hub/backend: đạt
unittest: 21/21 đạt
smoke import PromptBuilder + Central Hub: đạt
git diff --check: đạt
~~~

### 2026-08-23 — Hoàn thành Đợt 3

Đã thực hiện:

- Tạo `shared/core/source_ranker.py`, chấm ứng viên theo đúng sáu nhóm điểm trong roadmap và bốn trạng thái reject/queue/ready/priority.
- Ứng viên thiếu metadata được giữ ở trạng thái unscored để crawler lỗi metadata không làm mất nguồn tốt.
- Article lấy title, mô tả và tín hiệu hình ngay tại trang danh mục; Facebook dùng caption; TikTok lấy title, mô tả, thumbnail, thời gian và engagement từ yt-dlp/RapidAPI.
- Xếp hạng nhiều ứng viên trước download và gọi AI; Article, Facebook và TikTok Matrix đều xử lý ứng viên điểm cao trước.
- Tạo `shared/core/evidence_guard.py`: đối chiếu URL/source_text, nâng ngưỡng tin tài chính/sức khỏe/pháp lý/nghiêm trọng, phát hiện tin chưa xác nhận bị nói như sự thật và cảnh báo visual chưa bám nguồn.
- EvidenceGuard chạy sau ContentValidator nhưng trước Sheet, TTS và render ở cả ba pipeline.
- Tạo `shared/core/rights_guard.py` và `config/media_source_policy.json`: chặn nguồn bị cấm, cảnh báo nguồn chưa có hồ sơ quyền ở chế độ cơ bản, hỗ trợ strict mode.
- BGM chưa có `license_status=approved` và `license_source` bị loại ngay trong MusicSelector; khi không còn nhạc hợp lệ renderer tự giữ voice-only.
- Sửa checkpoint Article, Facebook và TikTok Matrix: chỉ tiến mốc mới khi toàn bộ batch đã được xử lý hoặc loại có chủ đích, tránh xếp hạng lại làm bỏ sót nội dung.

Kiểm tra đã chạy:

~~~text
python -m compileall apps shared adsup_central_hub/backend tests: đạt
unittest: 30 đạt, 1 smoke FFmpeg bỏ qua vì catalog production chưa có BGM hợp lệ
smoke SourceRanker với profile thật + media rights policy: đạt
git diff --check: đạt
~~~

### 2026-08-23 — Hoàn thành Đợt 4

Đã thực hiện:

- Tạo `shared/core/beat_timeline.py` để phân bổ đúng tổng thời lượng audio, giữ thời lượng hook thật, ánh xạ media và motion/transition theo vai trò từng beat; dữ liệu cũ không có beats dùng fallback xác định.
- Article dựng ảnh theo beat thay vì chia đều, chọn media theo timeline, đặt transition theo mốc beat và giữ tương thích frame/logo hiện tại.
- Facebook chế độ voice/script dùng timeline cho hook, frame, text từng beat và subtitle; chế độ giữ audio gốc chỉ áp dụng first frame để không ép beat AI lên nội dung nguồn chưa được thay voice.
- TikTok Remix chế độ full chia thân bài thành các đoạn beat, cắt đúng phần audio tương ứng rồi concat; chế độ giữ audio gốc tiếp tục ưu tiên đồng bộ nguồn.
- First frame được rút còn 3–7 từ từ chính hook/beat, không tự bịa thêm nội dung.
- Subtitle ASS chia theo cụm ý 3–9 từ, tối đa hai dòng, đẩy khỏi vùng caption/nút TikTok, highlight con số và `must_show`, có preset theo kênh và fallback từ script khi Whisper lỗi.
- Tạo `shared/services/audio_director.py`; bỏ chọn SFX ngẫu nhiên trong Article, chỉ đặt tối đa 2–3 cue ở cảnh báo, reveal, con số hoặc bước ngoặt, tắt SFX với nội dung nhạy cảm và giới hạn gain để không lấn voice.
- Sửa Facebook không còn cộng thừa 0,5 giây vào hook, nhờ đó hook text, beat và subtitle khớp audio thật.

Kiểm tra đã chạy:

~~~text
python -m compileall apps shared adsup_central_hub/backend tests: đạt
unittest: 40 đạt, 1 smoke FFmpeg BGM bỏ qua vì catalog production chưa có track hợp lệ
smoke FFmpeg Article: đạt, 1080x1920, 30 FPS, 4,50 giây
smoke FFmpeg Facebook: đạt, 1080x1920, 30 FPS, 4,50 giây
smoke FFmpeg TikTok Remix: đạt, 1080x1920, 30 FPS, 4,53 giây
git diff --check: đạt
~~~

### 2026-08-23 — Hoàn thành Đợt 5

Đã thực hiện:

- Tạo `shared/core/video_encoding.py` với preset final thống nhất: H.264 High level 4.1, CRF 19, yuv420p, 30 FPS CFR, GOP 60, faststart và AAC 192 kbps 48 kHz stereo.
- Tạo sáu color grading preset cố định, có clamp an toàn cho contrast, saturation, brightness và sharpen; nội dung nhạy cảm luôn dùng `sensitive_neutral`.
- Mở rộng tám hồ sơ kênh bằng `grading_preset` và thông số màu cố định phù hợp với news, tài chính, xe, giải trí, thẩm mỹ, thể thao, sức khỏe và kể chuyện.
- Article, Facebook và TikTok Remix cùng dùng preset encode/color grade trung tâm; subtitle helper dự phòng cũng dùng cùng chuẩn.
- Xóa speed ngẫu nhiên, lens distortion, noise toàn video, random color grading, preset `ultrafast` và mọi đường nối byte `os.urandom` khỏi ba renderer.
- Không giả metadata Premiere/CapCut; final encode bỏ metadata nguồn và chỉ giữ tag muxer/codec thật do FFmpeg tạo.
- Article và Facebook encode mỗi khung hình tối đa một lần rồi concat bằng stream copy khi cần.
- TikTok Remix render beat thành MKV H.264 CRF 0 + FLAC 48 kHz, concat lossless, sau đó burn subtitle, loudness, BGM và SFX trong đúng một lần encode lossy final.
- Chế độ TikTok giữ audio gốc không còn burn subtitle hoặc đặt SFX theo beat AI lên lời nguồn.
- Renderer không còn âm thầm copy video nguồn chưa chuẩn hóa khi FFmpeg lỗi; pipeline nhận lỗi thay vì upload file ngoài chuẩn.

Kiểm tra đã chạy:

~~~text
python -m compileall apps shared adsup_central_hub/backend tests: đạt
unittest: 46 đạt, 1 smoke FFmpeg BGM bỏ qua vì catalog production chưa có track hợp lệ
smoke Article: đạt
smoke Facebook có frame: đạt
smoke Facebook no-frame: đạt
smoke TikTok Remix full: đạt
smoke TikTok Remix audio gốc: đạt
ffprobe cả năm mode: H.264 High 4.1, 1080x1920, yuv420p, 30 FPS CFR, AAC-LC 48 kHz stereo
git diff --check: đạt
~~~

### 2026-08-23 — Hoàn thành Đợt 6

Đã thực hiện:

- Tạo `config/video_safe_zones.json` và `shared/core/safe_zone.py` làm nguồn
  Safe Zone duy nhất cho canvas TikTok 1080×1920, hook, subtitle, logo, vùng nút
  bên phải và vùng caption phía dưới.
- Thêm text-layout planner dùng chung. Article, Facebook và TikTok Remix tự wrap,
  giới hạn hai dòng và clamp hook/on-screen beat vào vùng an toàn; cấu hình cũ đặt
  chữ quá thấp được tự đưa lên thay vì đè giao diện TikTok.
- Subtitle dùng preset thường và preset caption dài; ASS được kiểm tra font, margin
  và số dòng trước upload.
- Tạo `shared/core/video_qa.py`: ffprobe chuẩn container/codec/resolution/FPS/audio,
  decode toàn file bằng FFmpeg, đo black frame, freeze frame, silence, loudness,
  Safe Zone và cờ watermark; kết quả có blocking errors và warnings rõ ràng.
- Gắn VideoQA bắt buộc trước tất cả bốn điểm upload Drive: Article, Facebook,
  TikTok Matrix và Auto Clone. Video không đạt không thể tới hàm upload.
- Tạo `shared/core/pipeline_state.py` với vòng đời
  `selected → scripted → validated → voiced → rendered → qa_passed → uploaded → published → measured`.
- Tạo `shared/core/quality_log.py`; bỏ ghi `done` ngay sau content score. Log hiện
  chỉ ghi `validated`, `qa_passed`, `uploaded`, hoặc `failed` kèm stage,
  error_code, retryable, message và toàn bộ kết quả QA.
- Sheet payload mang `pipeline_status`/`pipeline_stage`; Facebook lưu record ở
  trạng thái `uploaded` thay cho `completed`. Telegram gom lỗi theo
  `stage:error_code` để đưa vào báo cáo vận hành.
- Xóa token Telegram và chat ID từng bị viết cứng trong mã nguồn; thao tác kiểm tra
  kết nối giờ chỉ nhận thông tin từ cấu hình/runtime.
- Thêm regression test dùng AST để bảo đảm mọi lệnh upload luôn có lệnh VideoQA
  chạy trước trong cùng pipeline; thêm smoke test tùy chọn cho năm mode render.

Kiểm tra đã chạy:

~~~text
python -m compileall apps shared adsup_central_hub/backend tests: đạt
unittest toàn bộ: 68 test, 62 đạt và 6 smoke tùy chọn bỏ qua ở chế độ mặc định
smoke Đợt 6 với output rerender mới: 5/5 đạt VideoQA
Article: đạt, gồm kiểm tra ASS Safe Zone
Facebook có frame: đạt
Facebook no-frame: đạt
TikTok Remix full: đạt
TikTok Remix audio gốc: đạt
gate regression: cả 4/4 điểm upload đều chạy QA trước
git diff --check: đạt
~~~

### 2026-08-23 — Hoàn thành Đợt 7

Đã thực hiện:

- Tạo `shared/services/performance_store.py`, lưu SQLite tại
  `data/performance.sqlite3`; thư mục runtime đã được gitignore và không chứa dữ
  liệu tài khoản trong source.
- Mỗi video lưu được nhiều snapshot tại 2h, 24h, 72h và 168h. Khóa
  `channel_id + video_id + measurement_window` giúp nhập lại cùng mốc chỉ update,
  không sinh bản ghi trùng.
- Schema lưu view, average watch time, completion, retention 2s/6s, like, comment,
  share, save, follow cùng story type, hook type, duration, music mood và beat count.
- Tạo `shared/core/performance_analyzer.py`: chuẩn hóa header Anh/Việt, ngày giờ UTC,
  số thường/K/M/nghìn/triệu và tỷ lệ dạng `0.35`, `35`, `35%` về cùng định dạng.
- Báo cáo dùng median, watch percentage và các chỉ số tương tác trên 1.000 view;
  tự chọn snapshot mới nhất để một video không bị đếm nhiều lần.
- Chỉ đánh dấu nhóm `eligible` khi đạt ngưỡng mặc định 30 video; video viral đơn lẻ
  không được dùng để kết luận. Snapshot sau có metrics tích lũy thấp hơn snapshot
  trước được cảnh báo `NON_MONOTONIC_*` thay vì âm thầm đưa vào học.
- Tạo `scripts/import_tiktok_metrics.py`, hỗ trợ CSV, CSV phân cách chấm phẩy/tab,
  JSON, JSONL và Google Sheet export CSV qua HTTPS; có dry-run, strict mode,
  defaults theo kênh/mốc đo và report JSON đầy đủ.
- Thêm `config/tiktok_metrics_template.csv` và hướng dẫn vận hành tại
  `docs/PERFORMANCE_METRICS_IMPORT.md`.
- Giữ Experiment Manager/Channel Learning cho Đợt 8 và Central Hub cho Đợt 9;
  Đợt 7 chỉ tạo contract dữ liệu ổn định cho hai đợt sau.

Kiểm tra đã chạy:

~~~text
python -m compileall apps shared adsup_central_hub/backend tests: đạt
unittest toàn bộ: 79 test, 73 đạt và 6 smoke tùy chọn bỏ qua
unit test riêng Đợt 7: 11/11 đạt
smoke CLI: 3/3 dòng CSV hợp lệ được nhập, 0 dòng lỗi
upsert idempotent: nhập lại vẫn giữ đúng 3 snapshot
report smoke: median/per-1.000 view/min-sample/anomaly contract đạt
git diff --check: đạt
~~~

### 2026-08-23 — Hoàn thành Đợt 8

Đã thực hiện:

- Tạo `shared/core/experiment_manager.py`: definition A/B bắt buộc đúng hai nhánh,
  mỗi nhánh chỉ đổi cùng một biến; hỗ trợ hook type, 22/28 giây, subtitle thường/
  highlight, số beats, CTA và music energy.
- Assignment dùng hash ổn định theo experiment/kênh/source; chạy lại cùng nguồn
  không bị đổi nhánh. Mỗi kênh chỉ có tối đa một experiment đang chạy nên một video
  không đồng thời đổi nhiều thuộc tính.
- PromptBuilder chèn chỉ đạo experiment và bốn field truy vết; cả bốn AI client
  đóng dấu assignment vào JSON. ContentValidator chặn output lệch hook, duration,
  subtitle, beat count, CTA hoặc music energy đã được gán.
- Renderer Article, Facebook có frame và TikTok Remix áp dụng thật hai kiểu subtitle:
  `normal` không highlight và `keyword_highlight` giữ highlight từ khóa/con số.
- Nâng performance schema lên version 2, tự migration SQLite Đợt 7 và lưu
  experiment ID/variant/variable/value cùng music energy, subtitle style và CTA.
- Evaluation chỉ dùng snapshot mới nhất, chỉ so story type có đủ cả hai variant,
  yêu cầu đủ mẫu mỗi nhánh, báo `leader` nhưng không tự chốt `winner` nếu operator
  chưa review.
- Tạo `shared/core/channel_learning.py`: chỉ học khi đủ mẫu; dùng median và
  share/save/follow trên 1.000 view; hook/duration/music được so với baseline của
  cùng story type để giảm lệch nhóm nội dung.
- Bài học mới mặc định tắt. Chỉ đi vào PromptBuilder khi operator bật riêng kênh và
  bật `PERFORMANCE_LEARNING_ENABLED`; operator có thể disable hoặc delete tức thì.
- Thêm `scripts/manage_experiments.py`, `scripts/build_channel_learning.py`,
  `config/experiment_template.json` và hướng dẫn vận hành tại
  `docs/EXPERIMENTS_AND_CHANNEL_LEARNING.md`.
- `CONTENT_EXPERIMENTS_ENABLED` và `PERFORMANCE_LEARNING_ENABLED` đều mặc định tắt;
  Đợt 8 không tự thay đổi production hoặc tự kết luận từ dữ liệu ít.

Kiểm tra đã chạy:

~~~text
python -m compileall apps shared adsup_central_hub/backend scripts tests: đạt
unittest toàn bộ: 89 test, 83 đạt và 6 smoke tùy chọn bỏ qua
unit test Đợt 8 và các contract liên quan: 34/34 đạt
smoke Experiment CLI trên /tmp: create/draft → running → stable assignment đạt
smoke Channel Learning trên DB tạm rỗng: trả insufficient_sample, không sinh lesson
git diff --check: đạt
~~~

### 2026-08-23 — Hoàn thành Đợt 9

Đã thực hiện:

- Tạo `shared/core/performance_dashboard.py` làm lớp tổng hợp dùng chung cho
  Central Hub. Dữ liệu được đọc từ SQLite Đợt 7 và quality log Đợt 6, không còn
  số KPI giả trong backend.
- Chỉ dùng snapshot mới nhất của mỗi video ở phạm vi đã lọc; tổng quan dùng
  median, tỷ lệ xem, retention 2s/6s và like/comment/share/save/follow trên 1.000
  view. Video viral đơn lẻ không làm sai trung vị.
- Thêm bộ lọc ngày theo múi giờ `Asia/Ho_Chi_Minh`, kênh, mốc đo và số mẫu tối
  thiểu. Ngày sai, khoảng ngày ngược và cỡ mẫu ngoài giới hạn trả HTTP 422.
- Thêm breakdown theo kênh, story type, hook type, thời lượng và music mood;
  mỗi nhóm mang trạng thái `eligible` để giao diện cảnh báo khi chưa đủ mẫu.
- Thêm xu hướng theo ngày, top 10 video theo view, số snapshot bất thường và số
  dòng quality log sai định dạng. GET dashboard không tự tạo database khi chưa
  có dữ liệu.
- Thêm API `/api/dashboard/performance` và `/api/dashboard/pipeline-errors`;
  endpoint tương thích `/api/dashboard/stats` cũng đếm trạng thái `uploaded`
  thật theo Article, Facebook và các pipeline TikTok thay cho `142/45/12`.
- Gom lỗi pipeline theo stage, error code, khả năng retry và danh sách 20 lỗi mới
  nhất; trạng thái hệ thống chuyển sang `attention` khi phạm vi lọc có lỗi.
- Thay Dashboard React cũ bằng màn hình phân tích dữ liệu dày nhưng dễ đọc: bảy
  KPI, bộ lọc có label, biểu đồ thanh CSS có số trực tiếp, trend 14 ngày, top
  video, chất lượng telemetry và bảng lỗi pipeline.
- Giao diện có loading/error/empty state, focus-visible, reduced-motion, bảng cuộn
  cục bộ và layout responsive; không thêm chart dependency hoặc emoji trang trí.
- Thêm 9 regression test cho tổng hợp snapshot, bộ lọc múi giờ, JSONL lỗi, alias
  pipeline, không tạo DB ngoài ý muốn và ba endpoint FastAPI.

Kiểm tra đã chạy:

~~~text
python -m compileall apps shared adsup_central_hub/backend scripts tests: đạt
unittest toàn bộ: 98 test, 92 đạt và 6 smoke tùy chọn bỏ qua
unit/API test riêng Đợt 9: 9/9 đạt
FastAPI smoke trên SQLite/JSONL tạm: HTTP 200/422 đúng contract, không tạo DB thiếu
frontend npm run lint: đạt; còn 1 warning cũ ở ToolFacebook.tsx
frontend npm run build: đạt, TypeScript và Vite production bundle thành công
git diff --check: đạt
Ruff: chưa chạy được vì package ruff không có trong .venv
~~~
