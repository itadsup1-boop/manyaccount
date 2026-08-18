import { useState, useEffect } from 'react';
import { Play, Square, Settings, Users, Video, Activity, Key, Save, Trash2, Target } from 'lucide-react';

const AUTO_REMIX_ENABLED = false;

const emptyContentProfile: Record<string, string> = {
  channel_name: '',
  topic: '',
  audience: '',
  content_promise: '',
  primary_goal: '',
  tone_style: '',
  video_length: '',
  format_style: '',
  hook_style: '',
  avoid: '',
  winning_examples: '',
  source_preference: '',
  comment_strategy: '',
  custom_instruction: ''
};

const contentProfileFields = [
  ['Tên/định vị kênh', 'channel_name'],
  ['Chủ đề chính', 'topic'],
  ['Tệp người xem', 'audience'],
  ['Lời hứa nội dung', 'content_promise'],
  ['Mục tiêu ưu tiên', 'primary_goal'],
  ['Độ dài video', 'video_length'],
  ['Giọng văn/phong cách', 'tone_style'],
  ['Format nên dùng', 'format_style'],
  ['Kiểu hook muốn ưu tiên', 'hook_style'],
  ['Ưu tiên chọn nguồn/video', 'source_preference'],
  ['Cách kéo bình luận', 'comment_strategy'],
  ['Điều cần tránh', 'avoid'],
  ['Ví dụ video/hook từng hiệu quả', 'winning_examples'],
  ['Chỉ đạo tùy biến thêm', 'custom_instruction']
] as const;

const accountContentProfilePresets: Record<string, Record<string, string>> = {
  '24h.vui.v8': {
    channel_name: '24h.vui.v8 - tin sức khỏe và đời sống ngắn, dễ hiểu',
    topic: 'Sức khỏe, đời sống, cảnh báo thói quen sai và các thông tin hữu ích cho người xem phổ thông.',
    audience: 'Người xem muốn hiểu nhanh một vấn đề sức khỏe/đời sống, thích nội dung cảnh báo nhẹ, thực tế và dễ áp dụng.',
    content_promise: 'Mỗi video giúp người xem nhận ra một rủi ro, một thói quen cần sửa, hoặc một góc nhìn đúng hơn về sức khỏe/đời sống.',
    primary_goal: 'retention',
    tone_style: 'Rõ ràng, bình tĩnh, có tính cảnh báo nhưng không hù dọa; ưu tiên giải thích ngắn và dễ hiểu.',
    video_length: '30-45s',
    format_style: 'Mở bằng vấn đề nhiều người gặp, giải thích nguyên nhân chính, đưa 2-3 ý cần nhớ, kết bằng câu hỏi về trải nghiệm cá nhân.',
    hook_style: 'Hook nên bắt đầu bằng cảnh báo mềm như "Nhiều người đang hiểu sai điều này..." hoặc "Thói quen này tưởng bình thường nhưng...".',
    source_preference: 'Ưu tiên video có tình huống đời thường, ví dụ rõ, biểu cảm thật hoặc thông tin dễ kiểm chứng.',
    comment_strategy: 'Kết bằng câu hỏi "Bạn có đang gặp tình trạng này không?" hoặc hỏi thói quen của người xem.',
    avoid: 'Không kết luận y khoa chắc chắn, không hù dọa bệnh tật, không nói quá công dụng, không đưa lời khuyên điều trị thay bác sĩ.',
    winning_examples: 'Mẫu hook: "Nhiều người làm điều này mỗi ngày mà không biết rủi ro..."; "Dấu hiệu nhỏ này thường bị bỏ qua..."; "Nếu bạn hay làm việc này, hãy nghe hết 30 giây."',
    custom_instruction: 'Viết như video TikTok sức khỏe đại chúng: ngắn, rõ, có cảnh báo vừa đủ, luôn tránh khẳng định y khoa quá mức.'
  },
  adsup_sport: {
    channel_name: 'adsup_sport - highlight thể thao và tin nóng sân cỏ',
    topic: 'Highlight thể thao, bóng đá, khoảnh khắc gây tranh luận, tin nóng cầu thủ/đội bóng và diễn biến trận đấu.',
    audience: 'Fan thể thao thích nội dung nhanh, cảm xúc mạnh, có tranh luận và có lý do để bình luận về đội/cầu thủ.',
    content_promise: 'Mỗi video làm rõ một khoảnh khắc đáng xem, một pha xử lý gây tranh cãi, hoặc một diễn biến thể thao khiến người xem muốn bàn luận.',
    primary_goal: 'comment',
    tone_style: 'Nhanh, giàu năng lượng, có nhịp cao trào; nói thẳng vào pha bóng/sự kiện, không lan man.',
    video_length: '30-45s',
    format_style: 'Mở bằng khoảnh khắc nóng, tua nhanh bối cảnh, nêu 2-3 điểm đáng chú ý, kết bằng câu hỏi chọn phe.',
    hook_style: 'Hook phải gọi tên pha bóng/sự kiện chính trong 3 giây đầu, ưu tiên conflict như tranh cãi, lật kèo, sai lầm hoặc màn tỏa sáng.',
    source_preference: 'Ưu tiên video có hành động rõ, cảm xúc khán giả/cầu thủ mạnh, tình huống tranh luận hoặc kết quả bất ngờ.',
    comment_strategy: 'Kết bằng câu hỏi chọn phe: "Bạn đứng về đội nào?", "Pha này lỗi ai?", "Theo bạn quyết định này đúng không?".',
    avoid: 'Không bịa tỷ số, không vu khống cầu thủ/trọng tài, không dùng ngôn từ kích động fan quá mức.',
    winning_examples: 'Mẫu hook: "Pha này đang khiến fan tranh cãi dữ dội..."; "Chỉ một khoảnh khắc này đã đổi cả trận đấu..."; "Nhìn kỹ pha xử lý này của anh ấy."',
    custom_instruction: 'Ưu tiên giữ nhịp căng và cảm xúc thể thao, nhưng mọi nhận định phải bám vào hình ảnh/video gốc.'
  },
  'gbn.car.24h': {
    channel_name: 'gbn.car.24h - tin xe, đánh giá xe và kinh nghiệm mua xe',
    topic: 'Tin ô tô, mẫu xe mới, giá xe, đánh giá ưu nhược điểm, kinh nghiệm mua xe và câu chuyện thị trường xe.',
    audience: 'Người quan tâm xe, đang cân nhắc mua xe hoặc thích cập nhật thông tin xe dễ hiểu, thực dụng.',
    content_promise: 'Mỗi video giúp người xem hiểu nhanh một điểm đáng chú ý về xe: giá, lỗi, trang bị, ưu nhược điểm hoặc quyết định mua bán.',
    primary_goal: 'retention',
    tone_style: 'Chuyên gia nhưng dễ hiểu, thẳng vào lợi ích/rủi ro; không nói quá kỹ thuật nếu không cần.',
    video_length: '45-60s',
    format_style: 'Mở bằng giá/lỗi/điểm gây tranh cãi, giải thích bối cảnh, đưa 2-3 điểm chính, kết bằng gợi ý cân nhắc.',
    hook_style: 'Hook nên đánh vào giá, lỗi phổ biến, điểm đáng tiền hoặc câu hỏi mua xe: "Mẫu xe này có thật sự đáng tiền?".',
    source_preference: 'Ưu tiên video có xe xuất hiện rõ, thông tin giá/trang bị, tình huống thực tế hoặc so sánh dễ nhìn.',
    comment_strategy: 'Kết bằng câu hỏi về lựa chọn xe: "Tầm giá này bạn chọn xe nào?", "Bạn thấy điểm này đáng tiền không?".',
    avoid: 'Không khẳng định giá/chất lượng nếu không có nguồn, không bôi xấu hãng, không dùng số liệu không chắc chắn.',
    winning_examples: 'Mẫu hook: "Điểm này mới là thứ khiến nhiều người phân vân..."; "Tầm giá này, mẫu xe này có một chi tiết rất đáng chú ý..."; "Trước khi xuống tiền, hãy nhìn kỹ điểm này."',
    custom_instruction: 'Viết theo hướng tư vấn thực dụng cho người xem, ưu tiên thông tin giúp ra quyết định thay vì chỉ kể lại video.'
  },
  phongmokechuyen01: {
    channel_name: 'phongmokechuyen01 - tâm sự và cảnh báo thẩm mỹ',
    topic: 'Câu chuyện thẩm mỹ, phẫu thuật thẩm mỹ, trải nghiệm làm đẹp, sai lầm cần tránh và góc nhìn đồng cảm.',
    audience: 'Người quan tâm làm đẹp/thẩm mỹ, đặc biệt là người đang tìm hiểu rủi ro, kinh nghiệm thật và câu chuyện trước khi quyết định.',
    content_promise: 'Mỗi video giúp người xem hiểu một câu chuyện thẩm mỹ, nhận ra một rủi ro hoặc tránh một quyết định vội vàng.',
    primary_goal: 'retention',
    tone_style: 'Đồng cảm, kể chuyện, cảnh báo nhẹ; không phán xét nhân vật và không làm người xem hoang mang.',
    video_length: '45-60s',
    format_style: 'Mở bằng chi tiết gây tò mò, kể bối cảnh ngắn, rút ra bài học/rủi ro, kết bằng lời nhắc thận trọng.',
    hook_style: 'Hook nên mang màu kể chuyện: "Câu chuyện này khiến nhiều người phải nghĩ lại..." hoặc "Điểm đáng chú ý không nằm ở kết quả, mà ở...".',
    source_preference: 'Ưu tiên video có câu chuyện rõ, biểu cảm thật, trước-sau hoặc tình huống cho thấy bài học/rủi ro.',
    comment_strategy: 'Kết bằng câu hỏi đồng cảm: "Bạn nghĩ nên xử lý thế nào?", "Nếu là bạn, bạn có dám quyết định không?".',
    avoid: 'Không chê bai ngoại hình, không kết luận y khoa, không hứa hẹn kết quả, không công kích cá nhân/cơ sở khi thiếu nguồn.',
    winning_examples: 'Mẫu hook: "Không phải ai làm đẹp cũng lường trước điều này..."; "Điểm khiến câu chuyện này đáng chú ý là..."; "Trước khi quyết định, có một điều rất dễ bị bỏ qua."',
    custom_instruction: 'Luôn viết theo hướng câu chuyện có bài học, nhân văn và thận trọng; tránh biến nội dung thẩm mỹ thành drama độc hại.'
  },
  showbiz124h: {
    channel_name: 'showbiz124h - tin nóng showbiz và câu chuyện giải trí',
    topic: 'Showbiz, drama giải trí, phản ứng cộng đồng, phát ngôn nghệ sĩ và các chi tiết hậu trường đáng chú ý.',
    audience: 'Người thích tin giải trí nhanh, muốn biết điểm nóng của câu chuyện và có góc để bình luận.',
    content_promise: 'Mỗi video tóm đúng điểm gây chú ý của câu chuyện showbiz, giúp người xem hiểu nhanh vì sao cộng đồng đang bàn luận.',
    primary_goal: 'comment',
    tone_style: 'Nhanh, tò mò, có nhịp drama vừa đủ; không bịa thêm chi tiết và không kết luận thay người xem.',
    video_length: '30-45s',
    format_style: 'Mở bằng chi tiết nóng, nêu bối cảnh cực ngắn, đưa 2-3 điểm khiến cộng đồng tranh luận, kết bằng câu hỏi quan điểm.',
    hook_style: 'Hook cần gọi thẳng nhân vật/sự việc hoặc chi tiết bất ngờ trong 3 giây đầu, nhưng không giật tít sai sự thật.',
    source_preference: 'Ưu tiên video có nhân vật rõ, phát ngôn/biểu cảm gây chú ý, phản ứng cộng đồng hoặc tình tiết mới.',
    comment_strategy: 'Kết bằng câu hỏi chọn phe hoặc hỏi quan điểm: "Bạn thấy ai đúng?", "Bạn nghĩ chi tiết này có đáng tranh cãi không?".',
    avoid: 'Không vu khống, không bịa quan hệ/sự kiện, không dùng từ xúc phạm, không khẳng định tin đồn chưa kiểm chứng.',
    winning_examples: 'Mẫu hook: "Chi tiết này mới là lý do cư dân mạng tranh cãi..."; "Nhiều người chỉ nhìn phần nổi, nhưng điểm đáng chú ý là..."; "Phát ngôn này đang chia cộng đồng thành hai luồng ý kiến."',
    custom_instruction: 'Viết như tin showbiz TikTok: nhanh, có điểm nóng, có góc tranh luận, nhưng phải giữ ranh giới thông tin đã thấy trong video.'
  },
  taichinh24444h: {
    channel_name: 'taichinh24444h - tài chính, kinh tế và tác động tới túi tiền',
    topic: 'Tài chính cá nhân, kinh tế, thị trường, biến động giá, chính sách và câu chuyện tiền bạc dễ hiểu.',
    audience: 'Người xem muốn hiểu nhanh một tin tài chính ảnh hưởng thế nào tới túi tiền, công việc hoặc quyết định chi tiêu/đầu tư.',
    content_promise: 'Mỗi video giúp người xem hiểu một biến động tài chính/kinh tế bằng ngôn ngữ đơn giản và biết điều cần cảnh giác.',
    primary_goal: 'retention',
    tone_style: 'Phân tích ngắn gọn, tỉnh táo, có cảnh báo rủi ro; không hô hào và không nói chắc về tương lai.',
    video_length: '45-60s',
    format_style: 'Mở bằng tác động trực tiếp, giải thích nguyên nhân chính, nêu 2-3 hệ quả, kết bằng điều người xem nên theo dõi.',
    hook_style: 'Hook nên bắt đầu bằng tác động: "Tin này có thể ảnh hưởng tới túi tiền của bạn..." hoặc "Vì sao giá/tiền/kinh tế đang đổi hướng?".',
    source_preference: 'Ưu tiên video có số liệu/tin rõ, bối cảnh kinh tế dễ giải thích, hoặc tác động thực tế tới người dân/doanh nghiệp.',
    comment_strategy: 'Kết bằng câu hỏi về trải nghiệm/tác động: "Bạn thấy giá thay đổi rõ nhất ở đâu?", "Bạn đang chọn giữ tiền hay chi tiêu?".',
    avoid: 'Không đưa lời khuyên đầu tư trực tiếp, không cam kết lời/lỗ, không bịa số liệu, không tạo hoảng loạn tài chính.',
    winning_examples: 'Mẫu hook: "Điều này nghe xa, nhưng có thể ảnh hưởng thẳng tới ví tiền..."; "Nhiều người chỉ nhìn con số, nhưng vấn đề nằm ở..."; "Nếu bạn đang có kế hoạch mua/đầu tư, hãy để ý điểm này."',
    custom_instruction: 'Luôn biến tin tài chính thành nội dung dễ hiểu cho người bình thường, ưu tiên tác động thực tế và cảnh báo rủi ro.'
  },
  tintucthammy24h: {
    channel_name: 'tintucthammy24h - tin thẩm mỹ, làm đẹp và cảnh báo sức khỏe',
    topic: 'Tin thẩm mỹ, làm đẹp, sức khỏe liên quan làm đẹp, câu chuyện dao kéo và cảnh báo sai lầm phổ biến.',
    audience: 'Người quan tâm làm đẹp/thẩm mỹ, muốn biết thông tin nhanh, rủi ro cần tránh và góc nhìn thực tế trước khi quyết định.',
    content_promise: 'Mỗi video giúp người xem hiểu một tin thẩm mỹ, tránh một sai lầm hoặc nhận ra rủi ro phía sau quyết định làm đẹp.',
    primary_goal: 'retention',
    tone_style: 'Cảnh báo nhẹ, rõ ràng, có cảm giác chuyên gia nhưng vẫn dễ nghe; không giật gân quá mức.',
    video_length: '45-60s',
    format_style: 'Mở bằng rủi ro/chi tiết bất ngờ, giải thích ngắn, đưa 2-3 lưu ý, kết bằng lời nhắc tìm hiểu kỹ.',
    hook_style: 'Hook nên nói thẳng rủi ro hoặc chi tiết người xem dễ bỏ qua: "Trước khi làm đẹp, đừng bỏ qua điểm này...".',
    source_preference: 'Ưu tiên video có tình huống làm đẹp rõ, thông tin cảnh báo, câu chuyện thật hoặc dấu hiệu rủi ro dễ nhận biết.',
    comment_strategy: 'Kết bằng câu hỏi trải nghiệm: "Bạn từng nghe trường hợp này chưa?", "Bạn quan tâm nhất rủi ro nào khi làm đẹp?".',
    avoid: 'Không cam kết kết quả, không kết luận y khoa, không dùng hình ảnh/chi tiết gây sốc quá đà, không công kích cá nhân/cơ sở khi thiếu nguồn.',
    winning_examples: 'Mẫu hook: "Làm đẹp không sai, nhưng chi tiết này rất dễ bị bỏ qua..."; "Nhiều người chỉ quan tâm kết quả, còn rủi ro này mới đáng nói..."; "Trước khi quyết định, hãy nghe kỹ 3 điểm này."',
    custom_instruction: 'Viết theo hướng tin thẩm mỹ có ích, cảnh báo đúng mức, giúp người xem tỉnh táo hơn trước khi làm đẹp.'
  }
};

function buildSuggestedContentProfile(accountId = ''): Record<string, string> {
  const cleanId = accountId.replace(/^@/, '').trim();
  const preset = accountContentProfilePresets[cleanId];
  if (preset) return { ...emptyContentProfile, ...preset };

  return {
    channel_name: cleanId ? `Kênh ${cleanId} - nội dung ngắn tối ưu giữ chân và tăng tương tác` : 'Kênh TikTok nội dung ngắn tối ưu giữ chân và tăng tương tác',
    topic: 'Ưu tiên chủ đề có tín hiệu viral, có tranh luận, cảm xúc hoặc tình tiết khiến người xem muốn xem tiếp.',
    audience: 'Người xem TikTok muốn hiểu nhanh câu chuyện, thích mở đầu rõ vấn đề, có tình tiết bất ngờ và nội dung dễ bình luận/chia sẻ.',
    content_promise: 'Mỗi video phải giúp người xem biết một điều đáng chú ý, tránh một sai lầm, hoặc có góc nhìn mới trong thời lượng ngắn.',
    primary_goal: 'view',
    tone_style: 'Nhanh, rõ, có nhịp căng ở 3 giây đầu; không dài dòng, không lên gân quá mức.',
    video_length: '30-45s',
    format_style: 'Mở bằng hook mạnh trong 3 giây đầu, giải thích bối cảnh ngắn, đưa 2-3 điểm chính, kết bằng câu hỏi hoặc nhận định gây thảo luận.',
    hook_style: 'Hook phải nói thẳng nhân vật/sự việc/lợi ích chính, có conflict hoặc điểm bất ngờ, nhưng không bịa và không giật tít sai sự thật.',
    source_preference: 'Ưu tiên video có hành động rõ, cảm xúc mạnh, câu chuyện dễ hiểu trong 3 giây đầu, có conflict hoặc tình tiết khiến người xem muốn xem tiếp.',
    comment_strategy: 'Kết bằng câu hỏi có hai lựa chọn rõ ràng hoặc hỏi trải nghiệm cá nhân để kéo bình luận tự nhiên.',
    avoid: 'Không bịa chi tiết, không vu khống, không dùng số liệu không có nguồn, không dùng ngôn từ kích động quá mức, không viết chung chung.',
    winning_examples: 'Mẫu hook: "Chi tiết này mới là lý do khiến mọi người tranh cãi..."; "Nhiều người chỉ nhìn phần nổi, nhưng điểm đáng chú ý nằm ở..."; "Nếu bạn thuộc nhóm này thì nên xem kỹ đoạn sau..."',
    custom_instruction: 'Khi phân tích video, hãy ưu tiên giữ chân người xem và viết như nội dung đăng TikTok thật, không viết kiểu báo cáo.'
  };
}

function normalizeSavedContentProfile(profile?: Record<string, string> | string) {
  if (typeof profile === 'string') {
    return { ...emptyContentProfile, custom_instruction: profile };
  }
  return { ...emptyContentProfile, ...(profile || {}) };
}

function fillMissingProfile(profile: Record<string, string>, accountId = '') {
  const suggested = buildSuggestedContentProfile(accountId);
  const normalized = { ...emptyContentProfile, ...profile };
  return Object.keys(normalized).reduce<Record<string, string>>((acc, key) => {
    const value = String(normalized[key] || '').trim();
    acc[key] = value ? normalized[key] : suggested[key] || '';
    return acc;
  }, {});
}

function formatContentProfilePreview(profile: Record<string, string>) {
  return contentProfileFields
    .map(([label, key]) => {
      const value = String(profile[key] || '').trim();
      return value ? `${label}: ${value}` : '';
    })
    .filter(Boolean)
    .join('\n\n');
}

export default function ToolTikTok() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>(['[Matrix Bot] Sẵn sàng hoạt động...']);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [newAcc, setNewAcc] = useState({ tiktok_id: '', email: '', machine_id: '1' });
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [selectedProfileAccountId, setSelectedProfileAccountId] = useState('');
  const [profileDraft, setProfileDraft] = useState<Record<string, string>>(buildSuggestedContentProfile());
  const [savedProfileDraft, setSavedProfileDraft] = useState<Record<string, string>>(emptyContentProfile);
  const [newChannel, setNewChannel] = useState({ url: '', limit: 3 });
  const [cloneLogs, setCloneLogs] = useState<string[]>(['[Hệ thống] Sẵn sàng...']);
  const [isCloneRunning, setIsCloneRunning] = useState(false);
  const [scheduleTimes, setScheduleTimes] = useState<string[]>([]);
  const [newTime, setNewTime] = useState('');
  const [apiSettings, setApiSettings] = useState({ ai_studio_url: '', api_key: '', voice_id: '', sheet_url: '', tele_token: '', tele_chatid: '', machine_id: '1' });

  const fetchAccounts = () => {
    fetch(`/api/tiktok/accounts`)
      .then(res => res.json())
      .then(data => {
        if (!data.error) setAccounts(data);
      })
      .catch(console.error);
  };

  const loadSystemConfigs = () => {
    fetch(`/api/system/config/schedule_config`)
      .then(res => res.json())
      .then(data => {
        if (data.crawl_times) setScheduleTimes(data.crawl_times);
      });
      
    fetch(`/api/system/config/api_settings`)
      .then(res => res.json())
      .then(data => {
        if (data.ai_studio_url !== undefined) setApiSettings(data);
      });
  };

  const fetchTikTokLogs = () => {
    fetch(`/api/tiktok/logs`)
      .then(res => res.json())
      .then(data => {
        if (data.logs) setLogs(data.logs);
        if (data.is_running !== undefined) setIsRunning(data.is_running);
      })
      .catch(() => {});
  };

  const fetchCloneLogs = () => {
    fetch(`/api/tiktok/clone/logs`)
      .then(res => res.json())
      .then(data => {
        if (data.logs) setCloneLogs(data.logs);
        if (data.is_running !== undefined) setIsCloneRunning(data.is_running);
      })
      .catch(() => {});
  };

  useEffect(() => {
    if (!AUTO_REMIX_ENABLED && activeTab === 'clone') {
      setActiveTab('dashboard');
    }
  }, [activeTab]);

  useEffect(() => {
    fetchAccounts();
    loadSystemConfigs();
    fetchTikTokLogs();
    fetchCloneLogs();
  }, []);

  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(fetchTikTokLogs, 1000);
    return () => clearInterval(interval);
  }, [isRunning]);

  useEffect(() => {
    if (!isCloneRunning) return;
    const interval = setInterval(fetchCloneLogs, 1000);
    return () => clearInterval(interval);
  }, [isCloneRunning]);

  const handleStart = () => {
    setIsRunning(true);
    fetch(`/api/tiktok/start`, { method: 'POST' });
  };

  const handleStop = () => {
    setIsRunning(false);
    fetch(`/api/tiktok/stop`, { method: 'POST' });
  };

  const handleStartClone = () => {
    if (!AUTO_REMIX_ENABLED) {
      setCloneLogs(prev => [
        "[Hệ thống] Auto Remix đang tạm tắt theo cấu hình hiện tại.",
        ...prev.slice(0, 50)
      ]);
      return;
    }
    setIsCloneRunning(true);
    fetch(`/api/tiktok/clone/start`, { method: 'POST' });
  };

  const handleStopClone = () => {
    setIsCloneRunning(false);
    fetch(`/api/tiktok/clone/stop`, { method: 'POST' });
  };

  const handleOpenChrome = (profile: string) => {
    if (!profile) return;
    fetch(`/api/tiktok/chrome/${profile}`, { method: 'POST' });
  };

  const handleOpenChatGPT = (tiktokId?: string) => {
    const suffix = tiktokId ? `/${encodeURIComponent(tiktokId)}` : '';
    fetch(`/api/chatgpt/chrome${suffix}`, { method: 'POST' });
  };

  const handleCloneChatGPTProfiles = () => {
    fetch(`/api/chatgpt/clone-profiles`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          alert(`Đã nhân bản ChatGPT chung cho ${data.total || 0} TikTok ID.`);
        } else {
          alert(`Lỗi nhân bản ChatGPT: ${data.error || 'Không rõ lỗi'}`);
        }
      })
      .catch(err => alert(`Lỗi nhân bản ChatGPT: ${err}`));
  };

  const handleAddAccount = () => {
    if (!newAcc.tiktok_id || !newAcc.email) return;
    const clean_id = newAcc.tiktok_id.replace(/[^a-zA-Z0-9_-]/g, "");
    fetch(`/api/tiktok/accounts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tiktok_id: newAcc.tiktok_id,
        email: newAcc.email,
        password: '',
        chrome_profile: clean_id,
        machine_id: newAcc.machine_id,
        active: true,
        channels: []
      })
    }).then(() => {
      setNewAcc({ tiktok_id: '', email: '', machine_id: '1' });
      fetchAccounts();
    });
  };

  const handleDeleteAccount = (id: string) => {
    fetch(`/api/tiktok/accounts/${id}`, { method: 'DELETE' })
      .then(() => fetchAccounts());
  };

  const handleToggleActive = (id: string, currentStatus: boolean) => {
    fetch(`/api/tiktok/accounts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: !currentStatus })
    }).then(() => fetchAccounts());
  };

  const handleUpdateLimit = (id: string, limit: number) => {
    fetch(`/api/tiktok/accounts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_limit_per_run: limit })
    });
  };

  const handleSelectProfileAccount = (id: string) => {
    setSelectedProfileAccountId(id);
    if (!id) {
      setSavedProfileDraft(emptyContentProfile);
      setProfileDraft(buildSuggestedContentProfile());
      return;
    }
    const account = accounts.find(acc => acc.tiktok_id === id);
    const savedProfile = normalizeSavedContentProfile(account?.content_profile);
    setSavedProfileDraft(savedProfile);
    setProfileDraft(fillMissingProfile(savedProfile, id));
  };

  const handleProfileDraftChange = (key: string, value: string) => {
    setProfileDraft(prev => ({ ...prev, [key]: value }));
  };

  const handleFillMissingProfile = () => {
    setProfileDraft(prev => fillMissingProfile(prev, selectedProfileAccountId));
  };

  const handleRestoreSavedProfile = () => {
    setProfileDraft(fillMissingProfile(savedProfileDraft, selectedProfileAccountId));
  };

  const handleSaveAccountInstruction = () => {
    if (!selectedProfileAccountId) return;
    const account = accounts.find(acc => acc.tiktok_id === selectedProfileAccountId);
    const mergedProfile = {
      ...normalizeSavedContentProfile(account?.content_profile),
      ...profileDraft
    };

    fetch(`/api/tiktok/accounts/${selectedProfileAccountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_profile: mergedProfile })
    }).then(res => res.json()).then(data => {
      if (data.status === 'success') {
        setSavedProfileDraft(normalizeSavedContentProfile(mergedProfile));
        setAccounts(prev => prev.map(acc => acc.tiktok_id === selectedProfileAccountId ? { ...acc, content_profile: mergedProfile } : acc));
        alert('Đã lưu chỉ đạo nội dung cho tài khoản TikTok!');
        fetchAccounts();
      } else {
        alert('Lỗi: ' + data.error);
      }
    });
  };

  const handleAddChannel = () => {
    if (!selectedAccountId || !newChannel.url) return;
    const account = accounts.find(a => a.tiktok_id === selectedAccountId);
    if (!account) return;
    
    const updatedChannels = [...(account.channels || []), {
      url: newChannel.url,
      limit: newChannel.limit,
      render_settings: {
        edit_mode: 'Có Frame Full (Tiktok)',
        title_settings: { source_start: 2.0, source_end: 5.0, zoom_factor: 1.0, manual_x_offset: 0, manual_y_offset: 100 },
        content_settings: { source_start: 10.0, source_end: "auto", zoom_factor: 1.05, manual_x_offset: 0, manual_y_offset: -11 },
        text_overlay_settings: { text_color: "#ffffff", stroke_width: 0, font_size: 45, box_y_start: 0.73, box_y_end: 0.83, box_width_percentage: 0.65, font_filename: "Inter_18pt-Bold.ttf" },
        text_content_settings: { text_color: "#ffffff", stroke_width: 0, font_size: 45, box_y_start: 0.73, box_y_end: 0.83, box_width_percentage: 0.65, font_filename: "Inter_18pt-Bold.ttf" },
        assets: { title_frame_filename: "", content_frame_filename: "", title_logo_filename: "", content_logo_filename: "", title_logo_width_percentage: 0.14, title_logo_x: "main_w-overlay_w-30", title_logo_y: "30", content_logo_width_percentage: 0.14, content_logo_x: "main_w-overlay_w-30", content_logo_y: "30" }
      }
    }];

    fetch(`/api/tiktok/accounts/${selectedAccountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channels: updatedChannels })
    }).then(() => {
      setNewChannel({ url: '', limit: 3 });
      fetchAccounts();
    });
  };

  const handleDeleteChannel = (channelIdx: number) => {
    if (!selectedAccountId) return;
    const account = accounts.find(a => a.tiktok_id === selectedAccountId);
    if (!account) return;
    
    const updatedChannels = account.channels.filter((_: any, idx: number) => idx !== channelIdx);
    
    fetch(`/api/tiktok/accounts/${selectedAccountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channels: updatedChannels })
    }).then(() => fetchAccounts());
  };

  const handleAddScheduleTime = () => {
    const timeRegex = /^([01]?[0-9]|2[0-3]):[0-5][0-9]$/;
    if (!timeRegex.test(newTime)) {
      alert("Sai định dạng! Hãy nhập HH:MM (VD: 08:30)");
      return;
    }
    const formatted = newTime.length === 4 ? "0" + newTime : newTime;
    if (scheduleTimes.includes(formatted)) return;
    
    const newTimes = [...scheduleTimes, formatted].sort();
    
    fetch(`/api/system/config/schedule_config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crawl_times: newTimes, nurture_windows: [] })
    }).then(() => {
      setScheduleTimes(newTimes);
      setNewTime('');
    });
  };

  const handleDeleteScheduleTime = (timeVal: string) => {
    const newTimes = scheduleTimes.filter(t => t !== timeVal);
    fetch(`/api/system/config/schedule_config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crawl_times: newTimes, nurture_windows: [] })
    }).then(() => setScheduleTimes(newTimes));
  };

  const handleSaveApiSettings = () => {
    fetch(`/api/system/config/api_settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(apiSettings)
    }).then(() => alert("Đã lưu Cấu hình hệ thống thành công!"));
  };

  const savedProfilePreview = formatContentProfilePreview(savedProfileDraft);

  return (
    <div>
      <h2 className="page-title">Tool TikTok (Matrix Bot)</h2>
      
      <div className="tab-headers">
        <button className={`tab-header ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
          <Activity size={18} style={{marginRight: '0.5rem'}}/> Dashboard
        </button>
        <button className={`tab-header ${activeTab === 'accounts' ? 'active' : ''}`} onClick={() => setActiveTab('accounts')}>
          <Users size={18} style={{marginRight: '0.5rem'}}/> Tài khoản
        </button>
        <button className={`tab-header ${activeTab === 'channels' ? 'active' : ''}`} onClick={() => setActiveTab('channels')}>
          <Video size={18} style={{marginRight: '0.5rem'}}/> Quản lý Kênh
        </button>
        <button className={`tab-header ${activeTab === 'content' ? 'active' : ''}`} onClick={() => setActiveTab('content')}>
          <Target size={18} style={{marginRight: '0.5rem'}}/> Chỉ đạo nội dung
        </button>
        <button className={`tab-header ${activeTab === 'api' ? 'active' : ''}`} onClick={() => setActiveTab('api')}>
          <Key size={18} style={{marginRight: '0.5rem'}}/> Cấu hình API
        </button>
      </div>

      <div className="tabs-container">
        {activeTab === 'dashboard' && (
          <div className="grid" style={{ gridTemplateColumns: '1fr' }}>
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0 }}>⏰ Cấu hình Lịch chạy Bot (Giờ:Phút)</h3>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input type="text" className="form-input" placeholder="Ví dụ: 08:30" value={newTime} onChange={e => setNewTime(e.target.value)} style={{ width: '150px' }} />
                  <button className="btn btn-primary" style={{ background: 'var(--success)' }} onClick={handleAddScheduleTime}>➕ Thêm Giờ</button>
                </div>
              </div>
              
              <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                {scheduleTimes.length === 0 ? (
                  <p style={{ color: 'var(--text-secondary)' }}>Chưa có lịch chạy nào. Hãy thêm mốc thời gian!</p>
                ) : (
                  scheduleTimes.map(t => (
                    <div key={t} style={{ display: 'flex', alignItems: 'center', background: 'rgba(255,255,255,0.1)', padding: '0.5rem 1rem', borderRadius: '2rem' }}>
                      <span style={{ fontWeight: 'bold', marginRight: '0.5rem' }}>{t}</span>
                      <button className="btn" style={{ background: 'transparent', padding: 0, color: 'var(--danger)' }} onClick={() => handleDeleteScheduleTime(t)}>
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="card" style={{ background: 'var(--bg-color)', border: '1px solid var(--border)' }}>
              <div className="controls-bar" style={{ display: 'flex', justifyContent: 'space-between' }}>
                {!isRunning ? (
                    <button className="btn btn-primary" style={{ padding: '1rem 2rem', fontSize: '1.2rem', background: 'var(--success)' }} onClick={handleStart}>
                      <Play size={24}/> BẮT ĐẦU CHẠY MATRIX BOT
                    </button>
                ) : (
                    <button className="btn btn-danger" style={{ padding: '1rem 2rem', fontSize: '1.2rem' }} onClick={handleStop}>
                      <Square size={24}/> DỪNG LẠI
                    </button>
                )}
                <button className="btn" style={{ background: 'var(--sidebar-bg)' }}><Settings size={18}/> Tuỳ chỉnh</button>
              </div>
              
              <div className="terminal" style={{ maxHeight: '400px', overflowY: 'auto' }}>
                {logs.map((log, idx) => (
                  <p key={idx}>{log}</p>
                ))}
                {isRunning && <p className="animate-pulse">_</p>}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'accounts' && (
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3>👥 Quản lý Tài khoản TikTok</h3>
              <button className="btn btn-primary" onClick={fetchAccounts}>🔄 Làm mới</button>
            </div>
            
            <div className="form-row" style={{ marginTop: '1.5rem', background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '0.5rem' }}>
              <div className="form-group">
                <label className="form-label">TikTok ID:</label>
                <input type="text" className="form-input" placeholder="@..." value={newAcc.tiktok_id} onChange={e => setNewAcc({...newAcc, tiktok_id: e.target.value})} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label">Email:</label>
                <input type="text" className="form-input" placeholder="email@gmail.com" value={newAcc.email} onChange={e => setNewAcc({...newAcc, email: e.target.value})} />
              </div>
              <div className="form-group">
                <label className="form-label">Máy:</label>
                <input type="text" className="form-input" style={{ width: '80px' }} value={newAcc.machine_id} onChange={e => setNewAcc({...newAcc, machine_id: e.target.value})} />
              </div>
              <div className="form-group">
                <button className="btn btn-primary" onClick={handleAddAccount}>➕ Thêm tài khoản</button>
              </div>
            </div>
            
            <div style={{ marginTop: '1.5rem', overflowX: 'auto' }}>
              <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <th style={{ padding: '0.5rem' }}>TikTok ID</th>
                    <th style={{ padding: '0.5rem' }}>Email</th>
                    <th style={{ padding: '0.5rem' }}>Profile Chrome</th>
                    <th style={{ padding: '0.5rem' }}>Max (Limit)</th>
                    <th style={{ padding: '0.5rem' }}>Chạy Bot</th>
                    <th style={{ padding: '0.5rem' }}>Hành động</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map(acc => (
                    <tr key={acc.tiktok_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '0.5rem', fontWeight: 'bold' }}>{acc.tiktok_id}</td>
                      <td style={{ padding: '0.5rem', color: 'var(--text-secondary)' }}>{acc.email}</td>
                      <td style={{ padding: '0.5rem', color: 'var(--info)' }}>{acc.chrome_profile}</td>
                      <td style={{ padding: '0.5rem' }}>
                        <input type="number" defaultValue={acc.video_limit_per_run || 3} onBlur={e => handleUpdateLimit(acc.tiktok_id, parseInt(e.target.value) || 3)} style={{ width: '60px', padding: '0.25rem', background: 'var(--bg-color)', color: 'white', border: '1px solid var(--border)', borderRadius: '0.25rem' }} />
                      </td>
                      <td style={{ padding: '0.5rem' }}>
                        <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                          <input type="checkbox" checked={acc.active} onChange={() => handleToggleActive(acc.tiktok_id, acc.active)} style={{ marginRight: '0.5rem', width: '1.2rem', height: '1.2rem' }} />
                          <span style={{ color: acc.active ? 'var(--success)' : 'var(--danger)' }}>{acc.active ? 'Bật' : 'Tắt'}</span>
                        </label>
                      </td>
                      <td style={{ padding: '0.5rem' }}>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button className="btn" style={{ background: 'var(--sidebar-bg)', color: 'var(--info)', padding: '0.25rem 0.5rem' }} onClick={() => handleOpenChrome(acc.chrome_profile)} title="Mở Chrome TikTok">
                            <Video size={16} />
                          </button>
                          <button className="btn" style={{ background: 'var(--sidebar-bg)', color: 'var(--warning)', padding: '0.25rem 0.5rem' }} onClick={() => handleOpenChatGPT(acc.tiktok_id)} title={`Mở ChatGPT cho ${acc.tiktok_id}`}>
                            <Key size={16} />
                          </button>
                          <button className="btn" style={{ background: 'var(--sidebar-bg)', color: 'var(--danger)', padding: '0.25rem 0.5rem' }} onClick={() => handleDeleteAccount(acc.tiktok_id)}>
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {accounts.length === 0 && (
                    <tr><td colSpan={6} style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Đang tải hoặc chưa có tài khoản nào...</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'channels' && (
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3>📺 Quản lý Kênh Nguồn</h3>
            </div>
            
            <div className="form-group" style={{ marginTop: '1.5rem', maxWidth: '400px' }}>
              <label className="form-label">Chọn Tài Khoản TikTok (Đích đến):</label>
              <select className="form-select" value={selectedAccountId} onChange={e => setSelectedAccountId(e.target.value)}>
                <option value="">-- Chọn tài khoản --</option>
                {accounts.map(acc => (
                  <option key={acc.tiktok_id} value={acc.tiktok_id}>{acc.tiktok_id}</option>
                ))}
              </select>
            </div>

            {selectedAccountId && (
              <>
                <div className="form-row" style={{ marginTop: '1.5rem', background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '0.5rem' }}>
                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="form-label">URL Kênh Nguồn (TikTok):</label>
                    <input type="text" className="form-input" placeholder="https://tiktok.com/@..." value={newChannel.url} onChange={e => setNewChannel({...newChannel, url: e.target.value})} />
                  </div>
                  <div className="form-group" style={{ width: '100px' }}>
                    <label className="form-label">Limit:</label>
                    <input type="number" className="form-input" value={newChannel.limit} onChange={e => setNewChannel({...newChannel, limit: parseInt(e.target.value) || 0})} />
                  </div>
                  <div className="form-group">
                    <button className="btn btn-primary" onClick={handleAddChannel}>➕ Thêm Kênh</button>
                  </div>
                </div>

                <div style={{ marginTop: '1.5rem' }}>
                  <h4 style={{ marginBottom: '1rem', color: 'var(--primary)' }}>Danh sách Kênh của {selectedAccountId}</h4>
                  {accounts.find(a => a.tiktok_id === selectedAccountId)?.channels?.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {accounts.find(a => a.tiktok_id === selectedAccountId)?.channels.map((ch: any, idx: number) => (
                        <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--sidebar-bg)', padding: '1rem', borderRadius: '0.5rem' }}>
                          <div>
                            <p style={{ fontWeight: 'bold' }}>{ch.url}</p>
                            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Limit: {ch.limit} video | Render mặc định</p>
                          </div>
                          <button className="btn" style={{ background: 'transparent', color: 'var(--danger)', padding: '0.5rem' }} onClick={() => handleDeleteChannel(idx)}>
                            <Trash2 size={18} />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p style={{ color: 'var(--text-secondary)' }}>Chưa có kênh nguồn nào được gắn.</p>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'content' && (
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <h3>🎯 Chỉ đạo nội dung theo tài khoản TikTok</h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '0.35rem' }}>
                  Một bộ chỉ đạo áp dụng cho tất cả link nguồn trong tài khoản này. Điền càng rõ, ChatGPT càng dễ chọn hook, góc khai thác và tệp xem để tăng khả năng giữ chân.
                </p>
              </div>
              <button className="btn btn-success" onClick={handleSaveAccountInstruction} disabled={!selectedProfileAccountId}>
                <Save size={18} /> Lưu chỉ đạo
              </button>
            </div>

            <div className="form-group" style={{ marginBottom: '1rem', maxWidth: '420px' }}>
              <label className="form-label">Chọn tài khoản TikTok:</label>
              <select className="form-select" value={selectedProfileAccountId} onChange={e => handleSelectProfileAccount(e.target.value)}>
                <option value="">-- Chọn tài khoản --</option>
                {accounts.map(acc => <option key={acc.tiktok_id} value={acc.tiktok_id}>{acc.tiktok_id}</option>)}
              </select>
            </div>

            {selectedProfileAccountId && (
              <div style={{ marginBottom: '1.25rem', padding: '1rem', border: '1px solid var(--border)', borderRadius: '0.75rem', background: 'rgba(255,255,255,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <div>
                    <h4 style={{ margin: 0, color: 'var(--primary)' }}>Nội dung đã lưu trước đó</h4>
                    <p style={{ margin: '0.35rem 0 0', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      Bên dưới là bản đã lưu trong database. Form đang sửa sẽ giữ lại các phần này và tự điền gợi ý cho ô còn trống.
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <button className="btn" style={{ background: 'var(--sidebar-bg)', padding: '0.55rem 0.75rem' }} onClick={handleRestoreSavedProfile}>
                      Khôi phục bản đã lưu
                    </button>
                    <button className="btn btn-primary" style={{ padding: '0.55rem 0.75rem' }} onClick={handleFillMissingProfile}>
                      Điền gợi ý ô trống
                    </button>
                  </div>
                </div>

                {savedProfilePreview ? (
                  <pre style={{ whiteSpace: 'pre-wrap', marginTop: '1rem', padding: '1rem', borderRadius: '0.5rem', background: 'rgba(0,0,0,0.25)', color: 'var(--text-primary)', fontFamily: 'inherit', lineHeight: 1.5 }}>{savedProfilePreview}</pre>
                ) : (
                  <p style={{ marginTop: '1rem', color: 'var(--text-secondary)' }}>
                    Tài khoản này chưa có chỉ đạo đã lưu. Form bên dưới đang được điền sẵn bằng template tăng view, bạn chỉ cần sửa các ô quan trọng rồi bấm Lưu.
                  </p>
                )}
              </div>
            )}

            {!selectedProfileAccountId ? (
              <p style={{ color: 'var(--text-secondary)' }}>Chọn một tài khoản để cấu hình nội dung.</p>
            ) : (
              <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Tên/định vị kênh:</label>
                  <input className="form-input" value={profileDraft.channel_name} onChange={e => handleProfileDraftChange('channel_name', e.target.value)} placeholder="VD: Kênh tin nóng showbiz 24h" />
                </div>
                <div className="form-group">
                  <label className="form-label">Chủ đề chính:</label>
                  <input className="form-input" value={profileDraft.topic} onChange={e => handleProfileDraftChange('topic', e.target.value)} placeholder="VD: showbiz, xe, tài chính, làm đẹp" />
                </div>
                <div className="form-group">
                  <label className="form-label">Mục tiêu ưu tiên:</label>
                  <select className="form-select" value={profileDraft.primary_goal} onChange={e => handleProfileDraftChange('primary_goal', e.target.value)}>
                    <option value="view">Tăng view</option>
                    <option value="retention">Tăng giữ chân</option>
                    <option value="comment">Kéo bình luận</option>
                    <option value="share">Kéo chia sẻ</option>
                    <option value="follow">Tăng follow</option>
                    <option value="lead">Kéo inbox/lead</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Độ dài video:</label>
                  <select className="form-select" value={profileDraft.video_length} onChange={e => handleProfileDraftChange('video_length', e.target.value)}>
                    <option value="30-45s">30-45s</option>
                    <option value="45-60s">45-60s</option>
                    <option value="60-90s">60-90s</option>
                    <option value="90-120s">90-120s</option>
                  </select>
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Tệp người xem muốn nhắm tới:</label>
                  <textarea className="form-input" style={{ minHeight: '85px' }} value={profileDraft.audience} onChange={e => handleProfileDraftChange('audience', e.target.value)} placeholder="VD: nữ 25-45 quan tâm làm đẹp, thích cảnh báo sai lầm, muốn nội dung dễ hiểu và có ví dụ thật." />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Lời hứa nội dung của kênh:</label>
                  <textarea className="form-input" style={{ minHeight: '85px' }} value={profileDraft.content_promise} onChange={e => handleProfileDraftChange('content_promise', e.target.value)} placeholder="Kênh này giúp người xem hiểu điều gì, tránh lỗi gì, hoặc ra quyết định gì tốt hơn?" />
                </div>
                <div className="form-group">
                  <label className="form-label">Giọng văn/phong cách:</label>
                  <input className="form-input" value={profileDraft.tone_style} onChange={e => handleProfileDraftChange('tone_style', e.target.value)} placeholder="VD: tin nóng, cảnh báo, chuyên gia, kể chuyện, tranh luận" />
                </div>
                <div className="form-group">
                  <label className="form-label">Format nên dùng:</label>
                  <input className="form-input" value={profileDraft.format_style} onChange={e => handleProfileDraftChange('format_style', e.target.value)} placeholder="VD: mở bằng conflict, 3 ý chính, cao trào, câu hỏi cuối" />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Kiểu hook muốn ưu tiên:</label>
                  <textarea className="form-input" style={{ minHeight: '85px' }} value={profileDraft.hook_style} onChange={e => handleProfileDraftChange('hook_style', e.target.value)} placeholder="VD: Hook phải nói rõ nhân vật/sự việc trong 3 giây đầu, có yếu tố bất ngờ nhưng không giật tít sai." />
                </div>
                <div className="form-group">
                  <label className="form-label">Ưu tiên chọn nguồn/video:</label>
                  <input className="form-input" value={profileDraft.source_preference} onChange={e => handleProfileDraftChange('source_preference', e.target.value)} placeholder="VD: ưu tiên video có hành động rõ, conflict, cảm xúc mạnh" />
                </div>
                <div className="form-group">
                  <label className="form-label">Cách kéo bình luận:</label>
                  <input className="form-input" value={profileDraft.comment_strategy} onChange={e => handleProfileDraftChange('comment_strategy', e.target.value)} placeholder="VD: kết bằng câu hỏi chọn phe, hỏi trải nghiệm cá nhân" />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Điều cần tránh:</label>
                  <textarea className="form-input" style={{ minHeight: '85px' }} value={profileDraft.avoid} onChange={e => handleProfileDraftChange('avoid', e.target.value)} placeholder="VD: không bịa số liệu, không vu khống, không kết luận y khoa, không dùng từ quá kích động." />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Ví dụ video/hook từng hiệu quả:</label>
                  <textarea className="form-input" style={{ minHeight: '110px' }} value={profileDraft.winning_examples} onChange={e => handleProfileDraftChange('winning_examples', e.target.value)} placeholder="Dán 3-5 hook hoặc mô tả video từng lên view tốt để ChatGPT học pattern." />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Chỉ đạo tùy biến thêm:</label>
                  <textarea className="form-input" style={{ minHeight: '120px' }} value={profileDraft.custom_instruction} onChange={e => handleProfileDraftChange('custom_instruction', e.target.value)} placeholder="Bất kỳ quy tắc riêng nào khác: từ cấm dùng, cách xưng hô, cấu trúc câu, tiêu chuẩn chọn video..." />
                </div>
              </div>
            )}
          </div>
        )}

        {AUTO_REMIX_ENABLED && activeTab === 'clone' && (
          <div className="card" style={{ background: 'var(--bg-color)', border: '1px solid var(--border)' }}>
            {!AUTO_REMIX_ENABLED && (
              <div style={{ padding: '1rem', marginBottom: '1rem', borderRadius: '0.5rem', background: 'rgba(245, 158, 11, 0.15)', border: '1px solid rgba(245, 158, 11, 0.35)', color: 'var(--warning)' }}>
                Auto Remix đang được tạm tắt. Matrix Bot chính vẫn chạy bình thường ở tab Dashboard.
              </div>
            )}
            <div className="controls-bar" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                <h3 style={{ margin: 0 }}>⚙️ Tiến trình Treo Auto Remix</h3>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>(Tự động tải, lách bản quyền, đăng định kỳ)</span>
              </div>
              {!isCloneRunning ? (
                 <button
                   className={AUTO_REMIX_ENABLED ? "btn btn-primary" : "btn"}
                   style={{ padding: '0.75rem 1.5rem', fontSize: '1rem', background: AUTO_REMIX_ENABLED ? undefined : 'var(--sidebar-bg)', opacity: AUTO_REMIX_ENABLED ? 1 : 0.6, cursor: AUTO_REMIX_ENABLED ? 'pointer' : 'not-allowed' }}
                   onClick={handleStartClone}
                 >
                   <Play size={20}/> {AUTO_REMIX_ENABLED ? 'BẬT AUTO CLONE WORKER' : 'AUTO REMIX ĐANG TẮT'}
                 </button>
              ) : (
                 <button className="btn btn-danger" style={{ padding: '0.75rem 1.5rem', fontSize: '1rem' }} onClick={handleStopClone}>
                   <Square size={20}/> DỪNG WORKER
                 </button>
              )}
            </div>
            
            <div className="terminal" style={{ maxHeight: '400px', overflowY: 'auto', marginTop: '1rem' }}>
              {cloneLogs.map((log, idx) => (
                <p key={idx} style={{ color: log.includes('Lỗi') ? 'var(--danger)' : log.includes('Đã cào') ? 'var(--success)' : 'inherit' }}>{log}</p>
              ))}
              {isCloneRunning && <p className="animate-pulse">_</p>}
            </div>
          </div>
        )}

        {activeTab === 'api' && (
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              <h3>🔑 Cấu hình Hệ thống (System Configs)</h3>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button className="btn btn-primary" onClick={() => handleOpenChatGPT()}>
                  <Key size={18} /> Mở ChatGPT chung
                </button>
                <button className="btn" style={{ background: 'var(--sidebar-bg)', color: 'var(--warning)' }} onClick={handleCloneChatGPTProfiles}>
                  <Key size={18} /> Nhân bản cho tất cả ID
                </button>
              </div>
            </div>
            <p style={{ color: 'var(--text-secondary)', marginTop: '0.75rem', fontSize: '0.85rem' }}>
              Đăng nhập ChatGPT chung một lần, đóng cửa sổ sau khi lưu phiên, rồi bấm nhân bản để tạo profile riêng cho từng TikTok ID. Scheduler chỉ chạy tối đa 2 Chrome cùng lúc.
            </p>
            <div className="grid" style={{ gridTemplateColumns: '1fr', marginTop: '1.5rem', gap: '1rem', maxWidth: '800px' }}>
              <div className="form-row">
                <label style={{ width: '200px' }}>AI Studio URL:</label>
                <input className="form-input" style={{ flex: 1 }} type="text" value={apiSettings.ai_studio_url} onChange={e => setApiSettings({...apiSettings, ai_studio_url: e.target.value})} placeholder="Tạm không dùng khi Matrix Bot chạy qua ChatGPT" />
              </div>
              <div className="form-row">
                <label style={{ width: '200px' }}>API Key:</label>
                <input className="form-input" style={{ flex: 1 }} type="password" value={apiSettings.api_key} onChange={e => setApiSettings({...apiSettings, api_key: e.target.value})} placeholder="***" />
              </div>
              <div className="form-row">
                <label style={{ width: '200px' }}>Voice ID Mặc định:</label>
                <input className="form-input" style={{ flex: 1 }} type="text" value={apiSettings.voice_id} onChange={e => setApiSettings({...apiSettings, voice_id: e.target.value})} placeholder="11labs_voice_id..." />
              </div>
              <div className="form-row">
                <label style={{ width: '200px' }}>Google Sheet URL:</label>
                <input className="form-input" style={{ flex: 1 }} type="text" value={apiSettings.sheet_url} onChange={e => setApiSettings({...apiSettings, sheet_url: e.target.value})} placeholder="https://docs.google.com/spreadsheets/..." />
              </div>
              <div className="form-row">
                <label style={{ width: '200px' }}>Telegram Bot Token:</label>
                <input className="form-input" style={{ flex: 1 }} type="password" value={apiSettings.tele_token} onChange={e => setApiSettings({...apiSettings, tele_token: e.target.value})} placeholder="bot_token..." />
              </div>
              <div className="form-row">
                <label style={{ width: '200px' }}>Telegram Chat ID:</label>
                <input className="form-input" style={{ flex: 1 }} type="text" value={apiSettings.tele_chatid} onChange={e => setApiSettings({...apiSettings, tele_chatid: e.target.value})} placeholder="VD: -1001234567" />
              </div>
              <div className="form-row">
                <label style={{ width: '200px' }}>Mã Máy (Machine ID):</label>
                <input className="form-input" style={{ flex: 1 }} type="text" value={apiSettings.machine_id} onChange={e => setApiSettings({...apiSettings, machine_id: e.target.value})} placeholder="1, 2, 3..." />
              </div>
            </div>
            <button className="btn btn-primary" style={{ background: 'var(--success)', marginTop: '2rem' }} onClick={handleSaveApiSettings}>
              <Save size={18} /> Lưu cấu hình
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
