import sys
import os
import time
import json
import requests
import re

# =========================================================================
# 1. THIẾT LẬP ĐƯỜNG DẪN HỆ THỐNG TRƯỚC TIÊN (Để chống lỗi ModuleNotFoundError)
# =========================================================================
SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(SHARED_DIR)
sys.path.insert(0, WORKSPACE_ROOT)
sys.path.insert(0, SHARED_DIR)
PROJECT_ROOT = SHARED_DIR

# Đảm bảo các thư mục assets tồn tại
TEMP_VOICE_DIR = os.path.join(PROJECT_ROOT, "assets", "temp_voice")
FRAME_DIR = os.path.join(PROJECT_ROOT, "assets", "frame")
LOGO_DIR = os.path.join(PROJECT_ROOT, "assets", "logo")
FONT_DIR = os.path.join(PROJECT_ROOT, "assets", "font")
CREDENTIALS_FILE = os.path.join(PROJECT_ROOT,"config",'credentials.json')

for d in [TEMP_VOICE_DIR, FRAME_DIR, LOGO_DIR, FONT_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# =========================================================================
# 2. BÂY GIỜ MỚI IMPORT CÁC MODULE NỘI BỘ
# =========================================================================
try:
    from services.tele_reporter import TeleReporter
    from core.context import AccountContext
    from modules.video_handler import download_tiktok_video, get_channel_videos
    from apps.creator_facebook.chatgpt_automator import analyze_video_with_chatgpt
    from modules.video_remix import create_video_from_source_video
    from modules.upload_drive import upload_video_to_drive
    from services.sheet_api import get_latest_row_by_id, save_to_sheet, update_final_result, update_voice_links, update_source_link
    from services.tts_api import create_voice_default, create_voice_clone, create_voice_full_pipeline
    from services.supabase_api import SupabaseAPI
    from core.channel_editorial import get_channel_voice_speed, load_channel_editorial
except ImportError as e:
    print(f"❌ Lỗi Import thư viện: {e}")
    sys.exit(1)


def is_valid_vietnamese(text):
    if not text: return False
    vn_chars_pattern = re.compile(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]', re.IGNORECASE)
    return bool(vn_chars_pattern.search(text))

def load_credentials():
    if not os.path.exists(CREDENTIALS_FILE): return {}
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def build_suggested_content_profile(tiktok_id):
    clean_id = str(tiktok_id or "").replace("@", "").strip()
    default = {
        "channel_name": f"Kênh {clean_id} - nội dung ngắn tối ưu giữ chân và tăng tương tác" if clean_id else "Kênh TikTok nội dung ngắn tối ưu giữ chân và tăng tương tác",
        "topic": "Ưu tiên chủ đề có tín hiệu viral, có tranh luận, cảm xúc hoặc tình tiết khiến người xem muốn xem tiếp.",
        "audience": "Người xem TikTok muốn hiểu nhanh câu chuyện, thích mở đầu rõ vấn đề, có tình tiết bất ngờ và nội dung dễ bình luận/chia sẻ.",
        "content_promise": "Mỗi video phải giúp người xem biết một điều đáng chú ý, tránh một sai lầm, hoặc có góc nhìn mới trong thời lượng ngắn.",
        "primary_goal": "view",
        "tone_style": "Nhanh, rõ, có nhịp căng ở 3 giây đầu; không dài dòng, không lên gân quá mức.",
        "video_length": "30-45s",
        "format_style": "Mở bằng hook mạnh trong 3 giây đầu, giải thích bối cảnh ngắn, đưa 2-3 điểm chính, kết bằng câu hỏi hoặc nhận định gây thảo luận.",
        "hook_style": "Hook phải nói thẳng nhân vật/sự việc/lợi ích chính, có conflict hoặc điểm bất ngờ, nhưng không bịa và không giật tít sai sự thật.",
        "source_preference": "Ưu tiên video có hành động rõ, cảm xúc mạnh, câu chuyện dễ hiểu trong 3 giây đầu, có conflict hoặc tình tiết khiến người xem muốn xem tiếp.",
        "comment_strategy": "Kết bằng câu hỏi có hai lựa chọn rõ ràng hoặc hỏi trải nghiệm cá nhân để kéo bình luận tự nhiên.",
        "avoid": "Không bịa chi tiết, không vu khống, không dùng số liệu không có nguồn, không dùng ngôn từ kích động quá mức, không viết chung chung.",
        "winning_examples": "Mẫu hook: 'Chi tiết này mới là lý do khiến mọi người tranh cãi...'; 'Nhiều người chỉ nhìn phần nổi, nhưng điểm đáng chú ý nằm ở...'; 'Nếu bạn thuộc nhóm này thì nên xem kỹ đoạn sau...'",
        "custom_instruction": "Khi phân tích video, hãy ưu tiên giữ chân người xem và viết như nội dung đăng TikTok thật, không viết kiểu báo cáo.",
    }
    presets = {
        "24h.vui.v8": {
            "channel_name": "24h.vui.v8 - tin sức khỏe và đời sống ngắn, dễ hiểu",
            "topic": "Sức khỏe, đời sống, cảnh báo thói quen sai và các thông tin hữu ích cho người xem phổ thông.",
            "audience": "Người xem muốn hiểu nhanh một vấn đề sức khỏe/đời sống, thích nội dung cảnh báo nhẹ, thực tế và dễ áp dụng.",
            "content_promise": "Mỗi video giúp người xem nhận ra một rủi ro, một thói quen cần sửa, hoặc một góc nhìn đúng hơn về sức khỏe/đời sống.",
            "primary_goal": "retention",
            "tone_style": "Rõ ràng, bình tĩnh, có tính cảnh báo nhưng không hù dọa; ưu tiên giải thích ngắn và dễ hiểu.",
            "video_length": "30-45s",
            "format_style": "Mở bằng vấn đề nhiều người gặp, giải thích nguyên nhân chính, đưa 2-3 ý cần nhớ, kết bằng câu hỏi về trải nghiệm cá nhân.",
            "hook_style": "Hook nên bắt đầu bằng cảnh báo mềm như 'Nhiều người đang hiểu sai điều này...' hoặc 'Thói quen này tưởng bình thường nhưng...'.",
            "source_preference": "Ưu tiên video có tình huống đời thường, ví dụ rõ, biểu cảm thật hoặc thông tin dễ kiểm chứng.",
            "comment_strategy": "Kết bằng câu hỏi 'Bạn có đang gặp tình trạng này không?' hoặc hỏi thói quen của người xem.",
            "avoid": "Không kết luận y khoa chắc chắn, không hù dọa bệnh tật, không nói quá công dụng, không đưa lời khuyên điều trị thay bác sĩ.",
            "winning_examples": "Mẫu hook: 'Nhiều người làm điều này mỗi ngày mà không biết rủi ro...'; 'Dấu hiệu nhỏ này thường bị bỏ qua...'; 'Nếu bạn hay làm việc này, hãy nghe hết 30 giây.'",
            "custom_instruction": "Viết như video TikTok sức khỏe đại chúng: ngắn, rõ, có cảnh báo vừa đủ, luôn tránh khẳng định y khoa quá mức.",
        },
        "adsup_sport": {
            "channel_name": "adsup_sport - highlight thể thao và tin nóng sân cỏ",
            "topic": "Highlight thể thao, bóng đá, khoảnh khắc gây tranh luận, tin nóng cầu thủ/đội bóng và diễn biến trận đấu.",
            "audience": "Fan thể thao thích nội dung nhanh, cảm xúc mạnh, có tranh luận và có lý do để bình luận về đội/cầu thủ.",
            "content_promise": "Mỗi video làm rõ một khoảnh khắc đáng xem, một pha xử lý gây tranh cãi, hoặc một diễn biến thể thao khiến người xem muốn bàn luận.",
            "primary_goal": "comment",
            "tone_style": "Nhanh, giàu năng lượng, có nhịp cao trào; nói thẳng vào pha bóng/sự kiện, không lan man.",
            "video_length": "30-45s",
            "format_style": "Mở bằng khoảnh khắc nóng, tua nhanh bối cảnh, nêu 2-3 điểm đáng chú ý, kết bằng câu hỏi chọn phe.",
            "hook_style": "Hook phải gọi tên pha bóng/sự kiện chính trong 3 giây đầu, ưu tiên conflict như tranh cãi, lật kèo, sai lầm hoặc màn tỏa sáng.",
            "source_preference": "Ưu tiên video có hành động rõ, cảm xúc khán giả/cầu thủ mạnh, tình huống tranh luận hoặc kết quả bất ngờ.",
            "comment_strategy": "Kết bằng câu hỏi chọn phe: 'Bạn đứng về đội nào?', 'Pha này lỗi ai?', 'Theo bạn quyết định này đúng không?'.",
            "avoid": "Không bịa tỷ số, không vu khống cầu thủ/trọng tài, không dùng ngôn từ kích động fan quá mức.",
            "winning_examples": "Mẫu hook: 'Pha này đang khiến fan tranh cãi dữ dội...'; 'Chỉ một khoảnh khắc này đã đổi cả trận đấu...'; 'Nhìn kỹ pha xử lý này của anh ấy.'",
            "custom_instruction": "Ưu tiên giữ nhịp căng và cảm xúc thể thao, nhưng mọi nhận định phải bám vào hình ảnh/video gốc.",
        },
        "gbn.car.24h": {
            "channel_name": "gbn.car.24h - tin xe, đánh giá xe và kinh nghiệm mua xe",
            "topic": "Tin ô tô, mẫu xe mới, giá xe, đánh giá ưu nhược điểm, kinh nghiệm mua xe và câu chuyện thị trường xe.",
            "audience": "Người quan tâm xe, đang cân nhắc mua xe hoặc thích cập nhật thông tin xe dễ hiểu, thực dụng.",
            "content_promise": "Mỗi video giúp người xem hiểu nhanh một điểm đáng chú ý về xe: giá, lỗi, trang bị, ưu nhược điểm hoặc quyết định mua bán.",
            "primary_goal": "retention",
            "tone_style": "Chuyên gia nhưng dễ hiểu, thẳng vào lợi ích/rủi ro; không nói quá kỹ thuật nếu không cần.",
            "video_length": "45-60s",
            "format_style": "Mở bằng giá/lỗi/điểm gây tranh cãi, giải thích bối cảnh, đưa 2-3 điểm chính, kết bằng gợi ý cân nhắc.",
            "hook_style": "Hook nên đánh vào giá, lỗi phổ biến, điểm đáng tiền hoặc câu hỏi mua xe: 'Mẫu xe này có thật sự đáng tiền?'.",
            "source_preference": "Ưu tiên video có xe xuất hiện rõ, thông tin giá/trang bị, tình huống thực tế hoặc so sánh dễ nhìn.",
            "comment_strategy": "Kết bằng câu hỏi về lựa chọn xe: 'Tầm giá này bạn chọn xe nào?', 'Bạn thấy điểm này đáng tiền không?'.",
            "avoid": "Không khẳng định giá/chất lượng nếu không có nguồn, không bôi xấu hãng, không dùng số liệu không chắc chắn.",
            "winning_examples": "Mẫu hook: 'Điểm này mới là thứ khiến nhiều người phân vân...'; 'Tầm giá này, mẫu xe này có một chi tiết rất đáng chú ý...'; 'Trước khi xuống tiền, hãy nhìn kỹ điểm này.'",
            "custom_instruction": "Viết theo hướng tư vấn thực dụng cho người xem, ưu tiên thông tin giúp ra quyết định thay vì chỉ kể lại video.",
        },
        "phongmokechuyen01": {
            "channel_name": "phongmokechuyen01 - tâm sự và cảnh báo thẩm mỹ",
            "topic": "Câu chuyện thẩm mỹ, phẫu thuật thẩm mỹ, trải nghiệm làm đẹp, sai lầm cần tránh và góc nhìn đồng cảm.",
            "audience": "Người quan tâm làm đẹp/thẩm mỹ, đặc biệt là người đang tìm hiểu rủi ro, kinh nghiệm thật và câu chuyện trước khi quyết định.",
            "content_promise": "Mỗi video giúp người xem hiểu một câu chuyện thẩm mỹ, nhận ra một rủi ro hoặc tránh một quyết định vội vàng.",
            "primary_goal": "retention",
            "tone_style": "Đồng cảm, kể chuyện, cảnh báo nhẹ; không phán xét nhân vật và không làm người xem hoang mang.",
            "video_length": "45-60s",
            "format_style": "Mở bằng chi tiết gây tò mò, kể bối cảnh ngắn, rút ra bài học/rủi ro, kết bằng lời nhắc thận trọng.",
            "hook_style": "Hook nên mang màu kể chuyện: 'Câu chuyện này khiến nhiều người phải nghĩ lại...' hoặc 'Điểm đáng chú ý không nằm ở kết quả, mà ở...'.",
            "source_preference": "Ưu tiên video có câu chuyện rõ, biểu cảm thật, trước-sau hoặc tình huống cho thấy bài học/rủi ro.",
            "comment_strategy": "Kết bằng câu hỏi đồng cảm: 'Bạn nghĩ nên xử lý thế nào?', 'Nếu là bạn, bạn có dám quyết định không?'.",
            "avoid": "Không chê bai ngoại hình, không kết luận y khoa, không hứa hẹn kết quả, không công kích cá nhân/cơ sở khi thiếu nguồn.",
            "winning_examples": "Mẫu hook: 'Không phải ai làm đẹp cũng lường trước điều này...'; 'Điểm khiến câu chuyện này đáng chú ý là...'; 'Trước khi quyết định, có một điều rất dễ bị bỏ qua.'",
            "custom_instruction": "Luôn viết theo hướng câu chuyện có bài học, nhân văn và thận trọng; tránh biến nội dung thẩm mỹ thành drama độc hại.",
        },
        "showbiz124h": {
            "channel_name": "showbiz124h - tin nóng showbiz và câu chuyện giải trí",
            "topic": "Showbiz, drama giải trí, phản ứng cộng đồng, phát ngôn nghệ sĩ và các chi tiết hậu trường đáng chú ý.",
            "audience": "Người thích tin giải trí nhanh, muốn biết điểm nóng của câu chuyện và có góc để bình luận.",
            "content_promise": "Mỗi video tóm đúng điểm gây chú ý của câu chuyện showbiz, giúp người xem hiểu nhanh vì sao cộng đồng đang bàn luận.",
            "primary_goal": "comment",
            "tone_style": "Nhanh, tò mò, có nhịp drama vừa đủ; không bịa thêm chi tiết và không kết luận thay người xem.",
            "video_length": "30-45s",
            "format_style": "Mở bằng chi tiết nóng, nêu bối cảnh cực ngắn, đưa 2-3 điểm khiến cộng đồng tranh luận, kết bằng câu hỏi quan điểm.",
            "hook_style": "Hook cần gọi thẳng nhân vật/sự việc hoặc chi tiết bất ngờ trong 3 giây đầu, nhưng không giật tít sai sự thật.",
            "source_preference": "Ưu tiên video có nhân vật rõ, phát ngôn/biểu cảm gây chú ý, phản ứng cộng đồng hoặc tình tiết mới.",
            "comment_strategy": "Kết bằng câu hỏi chọn phe hoặc hỏi quan điểm: 'Bạn thấy ai đúng?', 'Bạn nghĩ chi tiết này có đáng tranh cãi không?'.",
            "avoid": "Không vu khống, không bịa quan hệ/sự kiện, không dùng từ xúc phạm, không khẳng định tin đồn chưa kiểm chứng.",
            "winning_examples": "Mẫu hook: 'Chi tiết này mới là lý do cư dân mạng tranh cãi...'; 'Nhiều người chỉ nhìn phần nổi, nhưng điểm đáng chú ý là...'; 'Phát ngôn này đang chia cộng đồng thành hai luồng ý kiến.'",
            "custom_instruction": "Viết như tin showbiz TikTok: nhanh, có điểm nóng, có góc tranh luận, nhưng phải giữ ranh giới thông tin đã thấy trong video.",
        },
        "taichinh24444h": {
            "channel_name": "taichinh24444h - tài chính, kinh tế và tác động tới túi tiền",
            "topic": "Tài chính cá nhân, kinh tế, thị trường, biến động giá, chính sách và câu chuyện tiền bạc dễ hiểu.",
            "audience": "Người xem muốn hiểu nhanh một tin tài chính ảnh hưởng thế nào tới túi tiền, công việc hoặc quyết định chi tiêu/đầu tư.",
            "content_promise": "Mỗi video giúp người xem hiểu một biến động tài chính/kinh tế bằng ngôn ngữ đơn giản và biết điều cần cảnh giác.",
            "primary_goal": "retention",
            "tone_style": "Phân tích ngắn gọn, tỉnh táo, có cảnh báo rủi ro; không hô hào và không nói chắc về tương lai.",
            "video_length": "45-60s",
            "format_style": "Mở bằng tác động trực tiếp, giải thích nguyên nhân chính, nêu 2-3 hệ quả, kết bằng điều người xem nên theo dõi.",
            "hook_style": "Hook nên bắt đầu bằng tác động: 'Tin này có thể ảnh hưởng tới túi tiền của bạn...' hoặc 'Vì sao giá/tiền/kinh tế đang đổi hướng?'.",
            "source_preference": "Ưu tiên video có số liệu/tin rõ, bối cảnh kinh tế dễ giải thích, hoặc tác động thực tế tới người dân/doanh nghiệp.",
            "comment_strategy": "Kết bằng câu hỏi về trải nghiệm/tác động: 'Bạn thấy giá thay đổi rõ nhất ở đâu?', 'Bạn đang chọn giữ tiền hay chi tiêu?'.",
            "avoid": "Không đưa lời khuyên đầu tư trực tiếp, không cam kết lời/lỗ, không bịa số liệu, không tạo hoảng loạn tài chính.",
            "winning_examples": "Mẫu hook: 'Điều này nghe xa, nhưng có thể ảnh hưởng thẳng tới ví tiền...'; 'Nhiều người chỉ nhìn con số, nhưng vấn đề nằm ở...'; 'Nếu bạn đang có kế hoạch mua/đầu tư, hãy để ý điểm này.'",
            "custom_instruction": "Luôn biến tin tài chính thành nội dung dễ hiểu cho người bình thường, ưu tiên tác động thực tế và cảnh báo rủi ro.",
        },
        "tintucthammy24h": {
            "channel_name": "tintucthammy24h - tin thẩm mỹ, làm đẹp và cảnh báo sức khỏe",
            "topic": "Tin thẩm mỹ, làm đẹp, sức khỏe liên quan làm đẹp, câu chuyện dao kéo và cảnh báo sai lầm phổ biến.",
            "audience": "Người quan tâm làm đẹp/thẩm mỹ, muốn biết thông tin nhanh, rủi ro cần tránh và góc nhìn thực tế trước khi quyết định.",
            "content_promise": "Mỗi video giúp người xem hiểu một tin thẩm mỹ, tránh một sai lầm hoặc nhận ra rủi ro phía sau quyết định làm đẹp.",
            "primary_goal": "retention",
            "tone_style": "Cảnh báo nhẹ, rõ ràng, có cảm giác chuyên gia nhưng vẫn dễ nghe; không giật gân quá mức.",
            "video_length": "45-60s",
            "format_style": "Mở bằng rủi ro/chi tiết bất ngờ, giải thích ngắn, đưa 2-3 lưu ý, kết bằng lời nhắc tìm hiểu kỹ.",
            "hook_style": "Hook nên nói thẳng rủi ro hoặc chi tiết người xem dễ bỏ qua: 'Trước khi làm đẹp, đừng bỏ qua điểm này...'.",
            "source_preference": "Ưu tiên video có tình huống làm đẹp rõ, thông tin cảnh báo, câu chuyện thật hoặc dấu hiệu rủi ro dễ nhận biết.",
            "comment_strategy": "Kết bằng câu hỏi trải nghiệm: 'Bạn từng nghe trường hợp này chưa?', 'Bạn quan tâm nhất rủi ro nào khi làm đẹp?'.",
            "avoid": "Không cam kết kết quả, không kết luận y khoa, không dùng hình ảnh/chi tiết gây sốc quá đà, không công kích cá nhân/cơ sở khi thiếu nguồn.",
            "winning_examples": "Mẫu hook: 'Làm đẹp không sai, nhưng chi tiết này rất dễ bị bỏ qua...'; 'Nhiều người chỉ quan tâm kết quả, còn rủi ro này mới đáng nói...'; 'Trước khi quyết định, hãy nghe kỹ 3 điểm này.'",
            "custom_instruction": "Viết theo hướng tin thẩm mỹ có ích, cảnh báo đúng mức, giúp người xem tỉnh táo hơn trước khi làm đẹp.",
        },
    }
    return {**default, **presets.get(clean_id, {})}


def resolve_content_profile(tiktok_id, *profiles):
    merged = build_suggested_content_profile(tiktok_id)
    for profile in profiles:
        if not profile:
            continue
        if isinstance(profile, dict):
            for key, value in profile.items():
                if str(value).strip():
                    merged[key] = value
            continue
        if isinstance(profile, str):
            stripped = profile.strip()
            if stripped:
                merged["custom_instruction"] = stripped
            continue
        merged["custom_instruction"] = str(profile).strip()
    return merged


def format_content_instruction(profile):
    if not profile:
        return ""
    if isinstance(profile, str):
        return profile.strip()
    if not isinstance(profile, dict):
        return str(profile).strip()

    fields = [
        ("Tên kênh", "channel_name"),
        ("Chủ đề chính", "topic"),
        ("Tệp người xem", "audience"),
        ("Lời hứa nội dung", "content_promise"),
        ("Mục tiêu chính", "primary_goal"),
        ("Giọng văn/phong cách", "tone_style"),
        ("Độ dài video mong muốn", "video_length"),
        ("Format lặp lại", "format_style"),
        ("Kiểu hook phù hợp", "hook_style"),
        ("Ưu tiên chọn nguồn/video", "source_preference"),
        ("Cách kéo bình luận", "comment_strategy"),
        ("Điều cần tránh", "avoid"),
        ("Ví dụ từng hiệu quả", "winning_examples"),
        ("Chỉ đạo tùy biến thêm", "custom_instruction"),
    ]
    lines = []
    for label, key in fields:
        value = str(profile.get(key, "")).strip()
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines)

def handle_tts_and_update_sheet(
    api_key, text, voice_id, row_idx, sheet_url, is_title=False, save_dir=None, speed=1.05
):
    if not text: return None, None

    label = "Tiêu đề" if is_title else "Nội dung"
    actual_save_dir = save_dir if save_dir else TEMP_VOICE_DIR
    file_name = f"tts_{row_idx}_{int(time.time())}_{'title' if is_title else 'content'}.wav"

    print(f"   🔊 Đang xử lý TTS {label} (Gọi qua VieNeu Server)...")

    try:
        local_path = create_voice_full_pipeline(
            text=text,
            save_dir=actual_save_dir,
            filename=file_name,
            profile_id=voice_id,
            rvc_model=voice_id,
            rvc_pitch=0,
            emotion="binh_thuong",
            speed=speed,
        )

        if local_path and os.path.exists(local_path):
            print(f"   ✅ TTS Server Thành công: {local_path}")

            if sheet_url and row_idx:
                if is_title: update_voice_links(sheet_url, row_idx, title_voice_link="local_file", content_voice_link=None)
                else: update_voice_links(sheet_url, row_idx, title_voice_link=None, content_voice_link="local_file")

            return "local_file", local_path

        return None, None

    except Exception as e:
        print(f"   ❌ Lỗi tạo TTS Local: {e}", flush=True)
        return None, None

def run_worker_process(account_id):
    ctx = AccountContext(account_id)
    ctx.logger.info(f"🚀 WORKER STARTED: {account_id}")

    cfg = ctx.config
    if not cfg:
        ctx.logger.error("❌ Không lấy được config từ Supabase. Dừng worker.")
        return

    tiktok_id = cfg.get("tiktok_id")
    profile_name = cfg.get("chrome_profile")
    acc_email = cfg.get("email")
    acc_password = cfg.get("password")
    setting_folder = load_credentials()
    folder_id = setting_folder.get("id_folder")
    settings = SupabaseAPI.get_system_config("app_settings") or {}
    sheet_url = settings.get("sheet_url") or settings.get("google_sheet_url")
    tts_api_key = settings.get("api_key") or settings.get("everai_api_key")
    # Voice ID: ưu tiên voice_id riêng của từng account, nếu không có thì dùng voice chung
    tts_voice_id = cfg.get("voice_id") or settings.get("voice_id") or settings.get("everai_voice_id", "1")

    if not sheet_url or not tts_api_key:
        ctx.logger.error("❌ Lỗi: Thiếu Sheet URL hoặc API Key.")
        return

    state = ctx.load_state()
    if "crawled_videos" not in state: state["crawled_videos"] = []

    processed_count = 0
    acc_limit = cfg.get("video_limit_per_run", 3)

    for channel in cfg.get("channels", []):
        if processed_count >= acc_limit:
            ctx.logger.info(f"🛑 Đã đạt giới hạn tài khoản ({acc_limit} video). Dừng quét kênh tiếp theo.")
            break

        if not channel.get("active", True): continue

        src_url = channel.get("url") or channel.get("channel_url")
        if not src_url: continue

        limit = channel.get("limit", 3)
        render_settings = channel.get("render_settings", {})
        last_crawled_url = channel.get("last_video_url", "")

        ctx.logger.info(f"🔍 Quét kênh: {src_url} (Lấy tối đa {limit} video)")

        try: all_videos = get_channel_videos(src_url, limit=15)
        except Exception as e:
            ctx.logger.error(f"   ⚠️ Lỗi quét video: {e}")
            continue

        new_videos_batch = []
        for v in all_videos:
            if v == last_crawled_url: break
            if v in state["crawled_videos"]: continue
            new_videos_batch.append(v)

        if not new_videos_batch: continue

        new_videos_batch.reverse()
        videos_to_process = new_videos_batch[:limit]

        for vid_url in videos_to_process:
            if processed_count >= acc_limit:
                ctx.logger.info(f"🛑 Đã đạt giới hạn tài khoản ({acc_limit} video). Ngừng xử lý các video còn lại trong kênh.")
                break

            ctx.logger.info(f"▶️ BẮT ĐẦU VIDEO: {vid_url}")
            clean_tid = tiktok_id.replace("@", "").strip()
            


            try:
                paths = download_tiktok_video(vid_url, ctx.temp_dir)
                if not paths: continue

                # (Đã di chuyển phần update link lên Google Sheet xuống phía dưới, sau khi AI Studio chạy xong)

                clean_tid = tiktok_id.replace("@", "").strip()
                up_path = paths.get('ai_studio') or paths.get('original')

                ctx.logger.info("   🤖 Gửi video cho ChatGPT phân tích, bỏ qua Google AI Studio...")
                content_instruction = format_content_instruction(
                    resolve_content_profile(
                        clean_tid,
                        cfg.get("content_profile"),
                        cfg.get("extra_content"),
                        cfg.get("content_instruction"),
                        cfg.get("profile_instruction"),
                        load_channel_editorial(clean_tid).get("content_profile", {}),
                    )
                )
                caption = f"Nguồn TikTok: {vid_url}"
                ai_result = analyze_video_with_chatgpt(
                    up_path,
                    caption,
                    is_tele_bot=False,
                    extra_content=content_instruction,
                    profile_id=clean_tid,
                )

                if not ai_result:
                    ctx.logger.error("   ❌ ChatGPT không trả về kịch bản hợp lệ. Bỏ qua video này.")
                    continue

                should_make_video = ai_result.get("should_make_video", True)
                if str(should_make_video).lower() == "false" or not should_make_video:
                    ctx.logger.info(f"   ⏭️ ChatGPT đánh giá không nên làm video này: {ai_result.get('skip_reason', '')}")
                    continue

                topic_fit = ai_result.get("topic_fit", True)
                if str(topic_fit).lower() == "false" or not topic_fit:
                    topic_fit_reason = ai_result.get("topic_fit_reason") or ai_result.get("skip_reason", "")
                    ctx.logger.info(f"   ⏭️ Video không đúng định vị kênh: {topic_fit_reason}")
                    continue

                sheet_result = save_to_sheet(
                    script_url=sheet_url,
                    link=vid_url,
                    title=ai_result.get("hook", "") or ai_result.get("title_tiktok", "Video Viral"),
                    script=ai_result.get("script_voice", ""),
                    combined_hints=ai_result.get("hook", ""),
                    original_video=vid_url,
                    title_tiktok=ai_result.get("title_tiktok", ""),
                    tiktok_id=clean_tid,
                    file_path="",
                )
                row_idx = sheet_result.get("row") if isinstance(sheet_result, dict) else None
                if not row_idx:
                    ctx.logger.error(f"   ❌ Không ghi được kịch bản vào Google Sheet: {sheet_result}")
                    continue

                row_data = {
                    "row": row_idx,
                    "title_text": ai_result.get("hook", "") or ai_result.get("title_tiktok", "Video Viral"),
                    "content_text": ai_result.get("script_voice", ""),
                    "tone": ai_result.get("tone", "Trung tính"),
                    "tiktok_id_sheet": clean_tid,
                }

                raw_content = row_data.get("content_text", "")
                raw_title = row_data.get("title_text", "")
                if not is_valid_vietnamese(raw_content) and is_valid_vietnamese(raw_title):
                    ctx.logger.error("   ❌ LỖI AI: Content trả về là tiếng Việt không dấu (hoặc bị rỗng). BỎ QUA video này!")
                    update_final_result(sheet_url, row_data['row'], "LỖI: AI TRẢ TEXT KHÔNG DẤU")
                    continue
                # Lấy tone từ row_data và tra cứu Voice ID
                tone = row_data.get("tone", "Trung tính")
                selected_voice_id = tts_voice_id
                voice_config = {}
                settings_paths = [
                    os.path.join(WORKSPACE_ROOT, "apps", "creator_facebook", "data", "global_voice_settings.json"),
                    os.path.join(WORKSPACE_ROOT, "assets", "channels", clean_tid, "voice_config.json"),
                ]
                for settings_path in settings_paths:
                    if not os.path.exists(settings_path):
                        continue
                    try:
                        with open(settings_path, "r", encoding="utf-8") as fs:
                            loaded_voice_config = json.load(fs)
                        if isinstance(loaded_voice_config, dict):
                            voice_config.update(loaded_voice_config)
                    except Exception:
                        pass

                tone_id = str(voice_config.get(tone, "")).strip()
                neutral_id = str(voice_config.get("Trung tính", "")).strip()
                if tone_id:
                    selected_voice_id = tone_id
                elif neutral_id:
                    selected_voice_id = neutral_id
                channel_voice_speed = get_channel_voice_speed(clean_tid)

                ctx.logger.info(
                    f"   🎵 Tone: {tone} -> Voice ID: {selected_voice_id} | Speed: {channel_voice_speed}"
                )

                link_ct, local_content = handle_tts_and_update_sheet(
                    tts_api_key, raw_content, selected_voice_id, row_data['row'], sheet_url,
                    False, save_dir=ctx.temp_dir, speed=channel_voice_speed
                )
                local_title = None
                if row_data.get("title_text"):
                    _, local_title = handle_tts_and_update_sheet(
                        tts_api_key, row_data["title_text"], selected_voice_id, row_data['row'],
                        sheet_url, True, save_dir=ctx.temp_dir, speed=channel_voice_speed
                    )
                
                if not local_content:
                    ctx.logger.error(f"   ⚠️ Bỏ qua video vì không tạo được Voice Content (local_content is None)")
                    continue

                ctx.logger.info("   🎬 Chuẩn bị Remixing...")

                assets_conf = render_settings.get("assets", {})

                t_frame_name = assets_conf.get("title_frame_filename")
                c_frame_name = assets_conf.get("content_frame_filename")
                logo_name = assets_conf.get("logo_filename")
                font_name = render_settings.get("text_overlay_settings", {}).get("font_filename")

                def download_if_missing(folder_type, local_dir, file_name):
                    if not file_name: return None
                    full_path = os.path.join(local_dir, file_name)
                    if not os.path.exists(full_path):
                        ctx.logger.info(f"   📥 Không có file '{file_name}'. Đang tải từ Supabase...")
                        SupabaseAPI.download_asset("assets", folder_type, local_dir, file_name)
                    else:
                        ctx.logger.info(f"   ✅ Đã có file '{file_name}' trong máy.")
                    return full_path

                title_frame_full_path = download_if_missing("frame", FRAME_DIR, t_frame_name)
                content_frame_full_path = download_if_missing("frame", FRAME_DIR, c_frame_name)
                
                t_logo_name = assets_conf.get("title_logo_filename", assets_conf.get("logo_filename"))
                c_logo_name = assets_conf.get("content_logo_filename", assets_conf.get("logo_filename"))
                title_logo_full_path = download_if_missing("logo", LOGO_DIR, t_logo_name)
                content_logo_full_path = download_if_missing("logo", LOGO_DIR, c_logo_name)
                
                download_if_missing("font", FONT_DIR, font_name)

                final_path = create_video_from_source_video(
                    audio_url=local_content,
                    source_video_url=paths['original'],
                    title_audio_url=local_title,
                    title_tiktok=row_data.get("title_text", "Video Viral"),
                    content_text=row_data.get("title_text", "Video Viral"),
                    script_url=sheet_url,
                    row_index=row_data['row'],
                    tiktok_id=clean_tid,
                    override_config=render_settings,
                    output_filename=f"final_{account_id}_{int(time.time())}.mp4",
                    temp_dir=ctx.temp_dir,
                    title_frame_path=title_frame_full_path,
                    content_frame_path=content_frame_full_path,
                    title_logo_path=title_logo_full_path,
                    content_logo_path=content_logo_full_path,
                    target_channel_url=src_url,
                    tone=tone
                )
                if not final_path: continue

                drv_link = upload_video_to_drive(final_path, folder_id=folder_id)

                if drv_link and update_final_result(sheet_url, row_data['row'], drv_link):
                    ctx.logger.info("   ✅ HOÀN TẤT!")

                    if vid_url not in state["crawled_videos"]:
                        state["crawled_videos"].append(vid_url)
                        ctx.save_state(state)

                    try:
                        new_index = channel.get("video_index", 0) + 1
                        SupabaseAPI.update_channel_tracking(tiktok_id, src_url, vid_url, new_index)
                        ctx.logger.info(f"   ☁️ Đã cập nhật Supabase: last_video_url = {vid_url}")
                        if os.path.exists(final_path): os.remove(final_path)
                    except Exception as e:
                        ctx.logger.error(f"   ⚠️ Lỗi cập nhật lên Supabase: {e}")

                    processed_count += 1

                    try:
                        TeleReporter.log_success_video(tiktok_id, src_url)
                    except Exception as e:
                        ctx.logger.error(f"   ⚠️ Lỗi ghi nháp Telegram: {e}")

            except Exception as e:
                ctx.logger.error(f"   🔥 Lỗi: {e}")
            finally:
                ctx.cleanup_temp()
                time.sleep(5)

    ctx.logger.info(f"🏁 WORKER FINISHED. Tổng video thành công: {processed_count}/{acc_limit}")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    account_id = None

    for arg in args:
        arg = arg.strip()
        if not arg.startswith("--"):
            account_id = arg

    if not account_id:
        print("\n❌ LỖI: Thiếu ID tài khoản! (Ví dụ: @tai_khoan)")
    else:
        try:
            run_worker_process(account_id)
        except Exception as e:
            print(f"🔥 WORKER CRASHED: {e}")
            import traceback
            traceback.print_exc()
