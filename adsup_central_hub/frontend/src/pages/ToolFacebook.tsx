import { useState, useEffect } from 'react';
import { Play, Square, Plus, RefreshCw, Save, Trash2 } from 'lucide-react';

const FACEBOOK_DEFAULT_CHANNEL_ID = 'Adsupnews';

const defaultContentProfile: Record<string, string> = {
  channel_name: '',
  topic: '',
  audience: '',
  content_promise: '',
  primary_goal: 'view',
  tone_style: '',
  video_length: '30-45s',
  format_style: '',
  hook_style: '',
  source_preference: '',
  comment_strategy: '',
  avoid: '',
  winning_examples: '',
  custom_instruction: ''
};

function normalizeContentProfile(profile?: Record<string, string>) {
  return { ...defaultContentProfile, ...(profile || {}) };
}

function getFacebookChannelId(source?: any) {
  const channelId = String(source?.id_tiktok || '').trim();
  return channelId || FACEBOOK_DEFAULT_CHANNEL_ID;
}

export default function ToolFacebook() {
  const [activeTab, setActiveTab] = useState('pipeline');
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>(['[Hệ thống] Sẵn sàng khởi động Tool Facebook...']);
  const [sources, setSources] = useState<any[]>([]);
  const [promptContent, setPromptContent] = useState('');
  const [voiceConfig, setVoiceConfig] = useState<any>({
    "Tích cực": "", "Trung tính": "", "Cảnh báo": "", "Đồng cảm": ""
  });

  const [newSource, setNewSource] = useState({
    id_tiktok: FACEBOOK_DEFAULT_CHANNEL_ID,
    source_name: '',
    source_url: '',
    max_video_age_hours: 48,
    delogo: ''
  });
  const [selectedChannel, setSelectedChannel] = useState(FACEBOOK_DEFAULT_CHANNEL_ID);
  const [channelConfig, setChannelConfig] = useState<any>({ content_profile: defaultContentProfile });

  const uniqueChannels = Array.from(new Set([FACEBOOK_DEFAULT_CHANNEL_ID, ...sources.map((source: any) => getFacebookChannelId(source)).filter(Boolean)])) as string[];
  const channelProfile = normalizeContentProfile(channelConfig.content_profile);

  const fetchSources = () => {
    fetch(`/api/facebook/sources`)
      .then(res => res.json())
      .then(data => {
        if (!data.error) {
          setSources(data);
          const channels = Array.from(new Set([FACEBOOK_DEFAULT_CHANNEL_ID, ...data.map((source: any) => getFacebookChannelId(source)).filter(Boolean)])) as string[];
          if (!selectedChannel && channels.length === 1) handleChannelSelect(channels[0]);
        }
      })
      .catch(console.error);
  };

  const fetchVoiceConfig = () => {
    fetch(`/api/facebook/voice`)
      .then(res => res.json())
      .then(data => setVoiceConfig(data))
      .catch(console.error);
  };

  useEffect(() => {
    fetchSources();
    fetchVoiceConfig();
    
    fetch(`/api/system/prompts/facebook`)
      .then(res => res.json())
      .then(data => {
        if (data.content !== undefined) setPromptContent(data.content);
      })
      .catch(console.error);

    const interval = setInterval(() => {
      fetch(`/api/facebook/logs`)
        .then(res => res.json())
        .then(data => {
          if (data.logs) setLogs(data.logs);
          if (data.is_running !== undefined) setIsRunning(data.is_running);
        })
        .catch(() => {});
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleVoiceConfigChange = (field: string, value: string) => {
    setVoiceConfig((prev: any) => ({ ...prev, [field]: value }));
  };

  const handleSaveVoiceConfig = () => {
    fetch(`/api/facebook/voice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(voiceConfig)
    }).then(() => alert('Đã lưu cấu hình voice thành công!'));
  };

  const handleSavePrompt = () => {
    fetch(`/api/system/prompts/facebook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: promptContent })
    }).then(res => res.json()).then(data => {
      if (data.status === 'success') alert('Đã lưu cấu hình Prompt thành công!');
      else alert('Lỗi: ' + data.error);
    });
  };

  const handleAddSource = () => {
    const payload = {
      ...newSource,
      id_tiktok: String(newSource.id_tiktok || '').trim() || FACEBOOK_DEFAULT_CHANNEL_ID
    };
    if (!payload.id_tiktok || !payload.source_name || !payload.source_url) return;
    fetch(`/api/facebook/sources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(res => res.json()).then(data => {
      if (data.status === 'success') {
        setNewSource({ id_tiktok: FACEBOOK_DEFAULT_CHANNEL_ID, source_name: '', source_url: '', max_video_age_hours: 48, delogo: '' });
        fetchSources();
      } else {
        alert('Lỗi: ' + data.error);
      }
    });
  };

  const handleDeleteSource = (id: number) => {
    fetch(`/api/facebook/sources/${id}`, { method: 'DELETE' })
      .then(() => fetchSources());
  };

  const handleChannelSelect = (channel: string) => {
    setSelectedChannel(channel);
    if (!channel) {
      setChannelConfig({ content_profile: defaultContentProfile });
      return;
    }
    fetch(`/api/article/config/${channel}`)
      .then(res => res.json())
      .then(data => setChannelConfig({ ...data, content_profile: normalizeContentProfile(data.content_profile) }))
      .catch(console.error);
  };

  useEffect(() => {
    handleChannelSelect(FACEBOOK_DEFAULT_CHANNEL_ID);
  }, []);

  const handleProfileUpdate = (key: string, value: string) => {
    setChannelConfig((prev: any) => ({
      ...prev,
      content_profile: {
        ...normalizeContentProfile(prev.content_profile),
        [key]: value
      }
    }));
  };

  const handleSaveChannelProfile = () => {
    if (!selectedChannel) return;
    fetch(`/api/article/config/${selectedChannel}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(channelConfig)
    }).then(res => res.json()).then(data => {
      if (data.status === 'success') alert('Đã lưu profile kênh Facebook!');
      else alert('Lỗi: ' + data.error);
    });
  };

  const handleStart = () => {
    setIsRunning(true);
    fetch(`/api/facebook/start`, { method: 'POST' });
  };

  const handleStop = () => {
    setIsRunning(false);
    fetch(`/api/facebook/stop`, { method: 'POST' });
  };

  const handleStartOnce = () => {
    setIsRunning(true);
    fetch(`/api/facebook/start_once`, { method: 'POST' });
  };

  return (
    <div>
      <h2 className="page-title">Tool Facebook News Auto Remix</h2>

      <div className="tab-headers">
        <button className={`tab-header ${activeTab === 'pipeline' ? 'active' : ''}`} onClick={() => setActiveTab('pipeline')}>▶️ Pipeline</button>
        <button className={`tab-header ${activeTab === 'sources' ? 'active' : ''}`} onClick={() => setActiveTab('sources')}>📋 Nguồn theo dõi</button>
        <button className={`tab-header ${activeTab === 'content' ? 'active' : ''}`} onClick={() => setActiveTab('content')}>🎯 Chỉ đạo nội dung</button>
        <button className={`tab-header ${activeTab === 'prompt' ? 'active' : ''}`} onClick={() => setActiveTab('prompt')}>🧠 Prompt</button>
        <button className={`tab-header ${activeTab === 'voice' ? 'active' : ''}`} onClick={() => setActiveTab('voice')}>⚙️ Voice</button>
      </div>

      {activeTab === 'pipeline' && (
        <div className="card" style={{ background: 'var(--bg-color)', border: '1px solid var(--border)' }}>
          <div className="controls-bar" style={{ display: 'flex', justifyContent: 'space-between' }}>
            {!isRunning ? (
              <button className="btn btn-primary" style={{ padding: '1rem 2rem', fontSize: '1.2rem', background: 'var(--success)' }} onClick={handleStart}>
                <Play size={24}/> BẮT ĐẦU CHẠY PIPELINE FB
              </button>
            ) : (
              <button className="btn btn-danger" style={{ padding: '1rem 2rem', fontSize: '1.2rem' }} onClick={handleStop}>
                <Square size={24}/> DỪNG LẠI
              </button>
            )}
            <button className="btn" style={{ background: 'var(--sidebar-bg)' }} onClick={handleStartOnce}><Play size={18}/> Chạy 1 lần</button>
          </div>

          <div className="terminal" style={{ maxHeight: '420px', overflowY: 'auto' }}>
            {logs.map((log, idx) => (
              <p key={idx}>{log}</p>
            ))}
            {isRunning && <p className="animate-pulse">_</p>}
          </div>
        </div>
      )}

      {activeTab === 'sources' && (
        <div className="grid">
          <div className="card">
            <h3>➕ Thêm nguồn Facebook mới</h3>
            <div className="form-group" style={{ marginTop: '1rem' }}>
              <label className="form-label">ID kênh đích:</label>
              <input type="text" className="form-input" placeholder="VD: Adsupnews" value={newSource.id_tiktok} onChange={e => setNewSource({...newSource, id_tiktok: e.target.value})} />
              <p style={{ color: 'var(--text-secondary)', marginTop: '0.35rem', fontSize: '0.8rem' }}>
                Mặc định Facebook tổng hợp về kênh Adsup News: <strong>{FACEBOOK_DEFAULT_CHANNEL_ID}</strong>
              </p>
            </div>
            <div className="form-group" style={{ marginTop: '1rem' }}>
              <label className="form-label">Tên Nguồn:</label>
              <input type="text" className="form-input" placeholder="VD: VTV24 News" value={newSource.source_name} onChange={e => setNewSource({...newSource, source_name: e.target.value})} />
            </div>
            <div className="form-group" style={{ marginTop: '1rem' }}>
              <label className="form-label">URL Trang/Nhóm:</label>
              <input type="text" className="form-input" placeholder="VD: https://facebook.com/vtv24" value={newSource.source_url} onChange={e => setNewSource({...newSource, source_url: e.target.value})} />
            </div>
            <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', marginTop: '1rem', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Max giờ:</label>
                <input type="number" className="form-input" value={newSource.max_video_age_hours} onChange={e => setNewSource({...newSource, max_video_age_hours: parseInt(e.target.value) || 0})} />
              </div>
              <div className="form-group">
                <label className="form-label">Toạ độ Delogo:</label>
                <input type="text" className="form-input" placeholder="x=683:y=231:w=280:h=85" value={newSource.delogo} onChange={e => setNewSource({...newSource, delogo: e.target.value})} />
              </div>
            </div>
            <button className="btn btn-primary" style={{ marginTop: '1.5rem', width: '100%', justifyContent: 'center' }} onClick={handleAddSource}>
              <Plus size={18} /> Thêm Nguồn
            </button>
          </div>

          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3>📋 Nguồn đang theo dõi</h3>
              <button className="btn" style={{ background: 'var(--sidebar-bg)' }} onClick={fetchSources}>
                <RefreshCw size={16} /> Làm mới
              </button>
            </div>

            <div style={{ marginTop: '1rem', overflowX: 'auto' }}>
              <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <th style={{ padding: '0.5rem' }}>ID kênh đích</th>
                    <th style={{ padding: '0.5rem' }}>Tên Nguồn</th>
                    <th style={{ padding: '0.5rem' }}>URL</th>
                    <th style={{ padding: '0.5rem' }}>Max Giờ</th>
                    <th style={{ padding: '0.5rem' }}>Delogo</th>
                    <th style={{ padding: '0.5rem' }}>Hành động</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map(s => (
                    <tr key={s.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '0.5rem', fontWeight: 'bold' }}>{getFacebookChannelId(s)}</td>
                      <td style={{ padding: '0.5rem' }}>{s.source_name}</td>
                      <td style={{ padding: '0.5rem', color: 'var(--info)' }}>{s.source_url}</td>
                      <td style={{ padding: '0.5rem' }}>{s.max_video_age_hours}</td>
                      <td style={{ padding: '0.5rem', color: 'var(--text-secondary)' }}>{s.delogo || 'Không'}</td>
                      <td style={{ padding: '0.5rem' }}>
                        <button className="btn" style={{ background: 'transparent', color: 'var(--danger)', padding: '0.25rem' }} onClick={() => handleDeleteSource(s.id)}>
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {sources.length === 0 && (
                    <tr><td colSpan={6} style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Chưa có nguồn nào.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'content' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>🎯 Chỉ đạo nội dung Facebook theo kênh đích</h3>
            <button className="btn btn-success" onClick={handleSaveChannelProfile} disabled={!selectedChannel}>
              <Save size={18} /> Lưu chỉ đạo
            </button>
          </div>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.85rem' }}>
            Bộ chỉ đạo này dùng chung với kho chỉ đạo của Tool TikTok theo ID kênh đích. Với Facebook hiện tại, các link tổng hợp sẽ mặc định dùng kênh Adsup News: Adsupnews.
          </p>
          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">Chọn ID kênh đích:</label>
            <select className="form-select" value={selectedChannel} onChange={e => handleChannelSelect(e.target.value)}>
              <option value="">-- Chọn kênh --</option>
              {uniqueChannels.map(ch => <option key={ch} value={ch}>{ch}</option>)}
            </select>
          </div>
          {selectedChannel && (
            <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
              <div className="form-group">
                <label className="form-label">Tên/định vị kênh:</label>
                <input className="form-input" value={channelProfile.channel_name} onChange={e => handleProfileUpdate('channel_name', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Chủ đề chính:</label>
                <input className="form-input" value={channelProfile.topic} onChange={e => handleProfileUpdate('topic', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Mục tiêu chính:</label>
                <select className="form-select" value={channelProfile.primary_goal} onChange={e => handleProfileUpdate('primary_goal', e.target.value)}>
                  <option value="view">Tăng view</option>
                  <option value="follow">Tăng follow</option>
                  <option value="comment">Kéo bình luận</option>
                  <option value="share">Kéo chia sẻ</option>
                  <option value="lead">Kéo inbox/lead</option>
                  <option value="traffic">Kéo traffic</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Độ dài video:</label>
                <select className="form-select" value={channelProfile.video_length} onChange={e => handleProfileUpdate('video_length', e.target.value)}>
                  <option value="30-45s">30-45s</option>
                  <option value="45-60s">45-60s</option>
                  <option value="60-90s">60-90s</option>
                  <option value="90-120s">90-120s</option>
                </select>
              </div>
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">Tệp người xem:</label>
                <textarea className="form-input" style={{ minHeight: '80px' }} value={channelProfile.audience} onChange={e => handleProfileUpdate('audience', e.target.value)} />
              </div>
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">Lời hứa nội dung:</label>
                <textarea className="form-input" style={{ minHeight: '80px' }} value={channelProfile.content_promise} onChange={e => handleProfileUpdate('content_promise', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Giọng văn/phong cách:</label>
                <input className="form-input" value={channelProfile.tone_style} onChange={e => handleProfileUpdate('tone_style', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Format lặp lại:</label>
                <input className="form-input" value={channelProfile.format_style} onChange={e => handleProfileUpdate('format_style', e.target.value)} />
              </div>
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">Kiểu hook phù hợp:</label>
                <textarea className="form-input" style={{ minHeight: '80px' }} value={channelProfile.hook_style} onChange={e => handleProfileUpdate('hook_style', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Ưu tiên chọn nguồn/video:</label>
                <input className="form-input" value={channelProfile.source_preference} onChange={e => handleProfileUpdate('source_preference', e.target.value)} placeholder="VD: ưu tiên video có conflict, cảm xúc mạnh, hành động rõ" />
              </div>
              <div className="form-group">
                <label className="form-label">Cách kéo bình luận:</label>
                <input className="form-input" value={channelProfile.comment_strategy} onChange={e => handleProfileUpdate('comment_strategy', e.target.value)} placeholder="VD: kết bằng câu hỏi chọn phe hoặc hỏi trải nghiệm cá nhân" />
              </div>
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">Điều cần tránh:</label>
                <textarea className="form-input" style={{ minHeight: '80px' }} value={channelProfile.avoid} onChange={e => handleProfileUpdate('avoid', e.target.value)} />
              </div>
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">Ví dụ từng hiệu quả:</label>
                <textarea className="form-input" style={{ minHeight: '100px' }} value={channelProfile.winning_examples} onChange={e => handleProfileUpdate('winning_examples', e.target.value)} />
              </div>
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">Chỉ đạo tùy biến thêm:</label>
                <textarea className="form-input" style={{ minHeight: '110px' }} value={channelProfile.custom_instruction} onChange={e => handleProfileUpdate('custom_instruction', e.target.value)} placeholder="Quy tắc riêng: từ cấm dùng, cách xưng hô, cấu trúc câu, tiêu chuẩn chọn video..." />
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'prompt' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>🧠 Chỉnh sửa Prompt Kịch Bản Facebook</h3>
            <button className="btn btn-primary" onClick={handleSavePrompt}>
              <Save size={18} /> Lưu Prompt
            </button>
          </div>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
            Nội dung này sẽ được gửi kèm bài đăng cho ChatGPT để phân tích kịch bản. Lưu ý: Không thay đổi cấu trúc trả về bắt buộc nếu có định nghĩa JSON.
          </p>
          <textarea
            className="form-input"
            style={{ width: '100%', minHeight: '520px', fontFamily: 'monospace', fontSize: '14px', lineHeight: '1.5', padding: '1rem' }}
            value={promptContent}
            onChange={(e) => setPromptContent(e.target.value)}
            placeholder="Đang tải prompt..."
          />
        </div>
      )}

      {activeTab === 'voice' && (
        <div className="card">
          <h3>⚙️ Cài đặt Voice ID mặc định (Toàn cục)</h3>
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', marginTop: '1.5rem', gap: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Tích cực:</label>
              <input className="form-input" value={voiceConfig['Tích cực'] || ''} onChange={e => handleVoiceConfigChange('Tích cực', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Trung tính:</label>
              <input className="form-input" value={voiceConfig['Trung tính'] || ''} onChange={e => handleVoiceConfigChange('Trung tính', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Cảnh báo:</label>
              <input className="form-input" value={voiceConfig['Cảnh báo'] || ''} onChange={e => handleVoiceConfigChange('Cảnh báo', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Đồng cảm:</label>
              <input className="form-input" value={voiceConfig['Đồng cảm'] || ''} onChange={e => handleVoiceConfigChange('Đồng cảm', e.target.value)} />
            </div>
          </div>
          <button className="btn btn-primary" style={{ background: 'var(--success)', marginTop: '1.5rem', width: '100%', justifyContent: 'center' }} onClick={handleSaveVoiceConfig}>
            <Save size={18} /> Lưu Cấu Hình Voice
          </button>
        </div>
      )}
    </div>
  );
}
