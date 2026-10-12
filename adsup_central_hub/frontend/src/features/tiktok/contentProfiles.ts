export const DEFAULT_SUBTITLE_SETTINGS = {
  enabled: false,
  margin_v: 320,
  font_size: 52,
  margin_l: 90,
  margin_r: 150,
  hex_color: '#ffffff',
  highlight_color: '#ffd54a',
  max_words: 7,
  adaptive_long_caption: false,
  position_mode: 'manual'
};
export const DEFAULT_TITLE_TEXT_SETTINGS = {
  text_color: '#ffffff',
  stroke_width: 0,
  font_size: 50,
  box_y_start: 0.7,
  box_y_end: 0.82,
  box_width_percentage: 0.85,
  box_x_offset: 0,
  position_mode: 'manual',
  font_filename: 'Inter_18pt-Bold.ttf'
};

export const emptyContentProfile: Record<string, string> = {
  channel_name: '',
  topic: '',
  audience: '',
  content_promise: '',
  primary_goal: '',
  tone_style: '',
  video_length: '38-42s',
  format_style: '',
  hook_style: '',
  avoid: '',
  winning_examples: '',
  source_preference: '',
  comment_strategy: '',
  custom_instruction: ''
};

export const contentProfileFields = [
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
    video_length: '38-42s',
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
    video_length: '38-42s',
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
    video_length: '38-42s',
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
    video_length: '38-42s',
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
    video_length: '38-42s',
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
    video_length: '38-42s',
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
    video_length: '38-42s',
    format_style: 'Mở bằng rủi ro/chi tiết bất ngờ, giải thích ngắn, đưa 2-3 lưu ý, kết bằng lời nhắc tìm hiểu kỹ.',
    hook_style: 'Hook nên nói thẳng rủi ro hoặc chi tiết người xem dễ bỏ qua: "Trước khi làm đẹp, đừng bỏ qua điểm này...".',
    source_preference: 'Ưu tiên video có tình huống làm đẹp rõ, thông tin cảnh báo, câu chuyện thật hoặc dấu hiệu rủi ro dễ nhận biết.',
    comment_strategy: 'Kết bằng câu hỏi trải nghiệm: "Bạn từng nghe trường hợp này chưa?", "Bạn quan tâm nhất rủi ro nào khi làm đẹp?".',
    avoid: 'Không cam kết kết quả, không kết luận y khoa, không dùng hình ảnh/chi tiết gây sốc quá đà, không công kích cá nhân/cơ sở khi thiếu nguồn.',
    winning_examples: 'Mẫu hook: "Làm đẹp không sai, nhưng chi tiết này rất dễ bị bỏ qua..."; "Nhiều người chỉ quan tâm kết quả, còn rủi ro này mới đáng nói..."; "Trước khi quyết định, hãy nghe kỹ 3 điểm này."',
    custom_instruction: 'Viết theo hướng tin thẩm mỹ có ích, cảnh báo đúng mức, giúp người xem tỉnh táo hơn trước khi làm đẹp.'
  }
};

export function buildSuggestedContentProfile(accountId = ''): Record<string, string> {
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
    video_length: '38-42s',
    format_style: 'Mở bằng hook mạnh trong 3 giây đầu, giải thích bối cảnh ngắn, đưa 2-3 điểm chính, kết bằng câu hỏi hoặc nhận định gây thảo luận.',
    hook_style: 'Hook phải nói thẳng nhân vật/sự việc/lợi ích chính, có conflict hoặc điểm bất ngờ, nhưng không bịa và không giật tít sai sự thật.',
    source_preference: 'Ưu tiên video có hành động rõ, cảm xúc mạnh, câu chuyện dễ hiểu trong 3 giây đầu, có conflict hoặc tình tiết khiến người xem muốn xem tiếp.',
    comment_strategy: 'Kết bằng câu hỏi có hai lựa chọn rõ ràng hoặc hỏi trải nghiệm cá nhân để kéo bình luận tự nhiên.',
    avoid: 'Không bịa chi tiết, không vu khống, không dùng số liệu không có nguồn, không dùng ngôn từ kích động quá mức, không viết chung chung.',
    winning_examples: 'Mẫu hook: "Chi tiết này mới là lý do khiến mọi người tranh cãi..."; "Nhiều người chỉ nhìn phần nổi, nhưng điểm đáng chú ý nằm ở..."; "Nếu bạn thuộc nhóm này thì nên xem kỹ đoạn sau..."',
    custom_instruction: 'Khi phân tích video, hãy ưu tiên giữ chân người xem và viết như nội dung đăng TikTok thật, không viết kiểu báo cáo.'
  };
}

export function normalizeSavedContentProfile(profile?: Record<string, string> | string) {
  if (typeof profile === 'string') {
    return { ...emptyContentProfile, custom_instruction: profile };
  }
  const normalized = { ...emptyContentProfile, ...(profile || {}) };
  if (/38\D+42/.test(String(normalized.video_length || ''))) {
    normalized.video_length = '38-42s';
  }
  return normalized;
}

export function fillMissingProfile(profile: Record<string, string>, accountId = '') {
  const suggested = buildSuggestedContentProfile(accountId);
  const normalized = { ...emptyContentProfile, ...profile };
  return Object.keys(normalized).reduce<Record<string, string>>((acc, key) => {
    const value = String(normalized[key] || '').trim();
    acc[key] = value ? normalized[key] : suggested[key] || '';
    return acc;
  }, {});
}

export function formatContentProfilePreview(profile: Record<string, string>) {
  return contentProfileFields
    .map(([label, key]) => {
      const value = String(profile[key] || '').trim();
      return value ? `${label}: ${value}` : '';
    })
    .filter(Boolean)
    .join('\n\n');
}
