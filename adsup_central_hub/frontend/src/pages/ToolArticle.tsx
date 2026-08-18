import { useState, useEffect } from 'react';
import { Play, Square, Plus, RefreshCw, Key, Upload, Trash2, Save, Search, ExternalLink } from 'lucide-react';
import VisualTextEditor from '../components/VisualTextEditor';

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

export default function ToolArticle() {
  const [activeTab, setActiveTab] = useState('pipeline');
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>(['[Hệ thống] Sẵn sàng khởi động Tool Tin Tức...']);
  const [promptContent, setPromptContent] = useState('');
  const [processedLinks, setProcessedLinks] = useState<any[]>([]);
  const [processedCount, setProcessedCount] = useState(0);
  const [processedSearch, setProcessedSearch] = useState('');
  const [processedLoading, setProcessedLoading] = useState(false);
  const [processedDuplicates, setProcessedDuplicates] = useState<any[]>([]);
  
  // Data state
  const [sources, setSources] = useState<any[]>([]);
  const [uniqueChannels, setUniqueChannels] = useState<string[]>([]);
  const [newSource, setNewSource] = useState({ id_tiktok: '-- Chọn kênh --', category_url: '' });

  // Config state (unified for visual editor)
  const [selectedChannel, setSelectedChannel] = useState('-- Chọn kênh --');
  const [config, setConfig] = useState<any>({
    text_y1: 0.73, text_y2: 0.83, text_w: 0.65, text_x: 0,
    text_size: 45, text_color: '#ffffff', text_stroke: 0,
    text_font: 'RobotoCondensed-Bold.ttf',
    sub_margin_v: 150, sub_font_size: 70, sub_color: '#00ffff',
    has_frame_intro: false, has_frame_content: false, has_logo: false,
    frame_intro_name: 'Chưa có', frame_content_name: 'Chưa có', logo_name: 'Chưa có',
    content_profile: defaultContentProfile
  });
  
  const [library, setLibrary] = useState<{frames: string[], logos: string[]}>({ frames: [], logos: [] });

  const fetchSources = () => {
    fetch(`/api/article/sources`)
      .then(res => res.json())
      .then(data => {
        if (!data.error) {
          setSources(data);
          const channels = Array.from(new Set(data.map((item: any) => item.id_tiktok).filter(Boolean)));
          setUniqueChannels(channels as string[]);
        }
      })
      .catch(console.error);
      
    fetch(`/api/article/library`)
      .then(res => res.json())
      .then(data => {
        if (!data.error) setLibrary(data);
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchSources();
  }, []);

  // Channel selection for visual editor
  const handleChannelChange = (e: any) => {
    const channel = e.target.value;
    setSelectedChannel(channel);
    
    if (channel !== '-- Chọn kênh --') {
      fetch(`/api/article/config/${channel}`)
        .then(res => res.json())
        .then(data => {
          setConfig({ ...data, content_profile: normalizeContentProfile(data.content_profile) });
        })
        .catch(console.error);
    }
  };

  const handleConfigUpdate = (updates: Record<string, any>) => {
    setConfig((prev: any) => ({ ...prev, ...updates }));
  };

  const handleProfileUpdate = (key: string, value: string) => {
    setConfig((prev: any) => ({
      ...prev,
      content_profile: {
        ...normalizeContentProfile(prev.content_profile),
        [key]: value
      }
    }));
  };

  const handleSaveConfig = () => {
    if (selectedChannel === '-- Chọn kênh --') return;
    fetch(`/api/article/config/${selectedChannel}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    }).then(() => alert('✅ Đã lưu cấu hình thành công!'));
  };

  const handleOpenChrome = () => {
    const channel = (document.getElementById("chromeChannelSelect") as HTMLSelectElement)?.value;
    if (!channel || channel === '-- Chọn kênh để đăng nhập ChatGPT --') return;
    fetch(`/api/article/chrome/${channel}`, { method: 'POST' });
  };

  const fetchArticleLogs = () => {
    fetch(`/api/article/logs`)
      .then(res => res.json())
      .then(data => {
        if (data.logs) setLogs(data.logs);
        if (data.is_running !== undefined) setIsRunning(data.is_running);
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchArticleLogs();
  }, []);

  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(fetchArticleLogs, 1000);
    return () => clearInterval(interval);
  }, [isRunning]);

  const handleStart = () => {
    setIsRunning(true);
    fetch(`/api/article/start`, { method: 'POST' });
  };

  const handleStop = () => {
    setIsRunning(false);
    fetch(`/api/article/stop`, { method: 'POST' });
  };

  const handleStartOnce = () => {
    setIsRunning(true);
    fetch(`/api/article/start_once`, { method: 'POST' });
  };

  const handleAddSource = () => {
    if (newSource.id_tiktok === '-- Chọn kênh --' || !newSource.category_url) return;
    fetch(`/api/article/sources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id_tiktok: newSource.id_tiktok,
        category_url: newSource.category_url,
        video_limit: 3,
        video_style: 'Chữ chạy Full màn hình',
        is_active: true
      })
    })
    .then(() => {
      setNewSource({ id_tiktok: '-- Chọn kênh --', category_url: '' });
      fetchSources();
    });
  };

  const handleDeleteSource = (id: number) => {
    fetch(`/api/article/sources/${id}`, { method: 'DELETE' })
      .then(() => fetchSources());
  };

  const fetchProcessedLinks = (query = processedSearch) => {
    setProcessedLoading(true);
    const params = new URLSearchParams({ limit: '300' });
    const cleanQuery = query.trim();
    if (cleanQuery) params.set('search', cleanQuery);
    fetch(`/api/article/processed-links?${params.toString()}`)
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          console.error(data.error);
          setProcessedLinks([]);
          setProcessedCount(0);
          setProcessedDuplicates([]);
          return;
        }
        setProcessedLinks(data.items || []);
        setProcessedCount(data.count || 0);
        setProcessedDuplicates(data.duplicates || []);
      })
      .catch(console.error)
      .finally(() => setProcessedLoading(false));
  };

  const handleToggleSourceActive = (id: number, currentStatus: boolean) => {
    fetch(`/api/article/sources/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: !currentStatus })
    }).then(() => fetchSources());
  };

  useEffect(() => {
    if (activeTab === 'history') {
      fetchProcessedLinks();
    }
    if (activeTab === 'prompt') {
      fetch(`/api/system/prompts/article`)
        .then(res => res.json())
        .then(data => {
          if (data.content !== undefined) setPromptContent(data.content);
        })
        .catch(console.error);
    }
  }, [activeTab]);

  const handleSavePrompt = () => {
    fetch(`/api/system/prompts/article`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: promptContent })
    }).then(res => res.json()).then(data => {
      if (data.status === 'success') alert('✅ Đã lưu Prompt thành công!');
      else alert('Lỗi: ' + data.error);
    });
  };

  const contentProfile = normalizeContentProfile(config.content_profile);

  return (
    <div>
      <h2 className="page-title">Tool Video Tin Tức Tự Động</h2>
      
      <div className="tab-headers">
        <button className={`tab-header ${activeTab === 'pipeline' ? 'active' : ''}`} onClick={() => setActiveTab('pipeline')}>📰 Pipeline</button>
        <button className={`tab-header ${activeTab === 'chrome' ? 'active' : ''}`} onClick={() => setActiveTab('chrome')}>🌐 Trình duyệt</button>
        <button className={`tab-header ${activeTab === 'history' ? 'active' : ''}`} onClick={() => setActiveTab('history')}>🔎 Bài đã làm</button>
        <button className={`tab-header ${activeTab === 'visual' ? 'active' : ''}`} onClick={() => setActiveTab('visual')}>🎨 Căn chỉnh Text</button>
        <button className={`tab-header ${activeTab === 'profile' ? 'active' : ''}`} onClick={() => setActiveTab('profile')}>🎯 Chỉ đạo nội dung</button>
        <button className={`tab-header ${activeTab === 'assets' ? 'active' : ''}`} onClick={() => setActiveTab('assets')}>🖼️ Frame & Logo</button>
        <button className={`tab-header ${activeTab === 'prompt' ? 'active' : ''}`} onClick={() => setActiveTab('prompt')}>🧠 Prompt</button>
      </div>

      <div className="tabs-container">
        {/* ═══ TAB 1: PIPELINE ═══ */}
        {activeTab === 'pipeline' && (
          <div className="grid" style={{ gridTemplateColumns: '1fr' }}>
            <div className="card">
              <h3>➕ Thêm danh mục Tin Tức mới</h3>
              <div className="form-row" style={{ marginTop: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">ID TikTok:</label>
                  <select className="form-select" value={newSource.id_tiktok} onChange={e => setNewSource({...newSource, id_tiktok: e.target.value})}>
                    <option>-- Chọn kênh --</option>
                    {uniqueChannels.map(ch => <option key={ch} value={ch}>{ch}</option>)}
                  </select>
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label className="form-label">URL Danh mục:</label>
                  <input type="text" className="form-input" placeholder="VD: https://kenh14.vn/doi-song.chn" value={newSource.category_url} onChange={e => setNewSource({...newSource, category_url: e.target.value})} />
                </div>
                <div className="form-group">
                  <button className="btn btn-primary" onClick={handleAddSource}><Plus size={18} /> Thêm</button>
                </div>
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3>📋 Quản lý Kênh & Nguồn Tin</h3>
                <button className="btn btn-ghost" onClick={fetchSources}>
                  <RefreshCw size={16} /> Làm mới
                </button>
              </div>
              
              <div style={{ marginTop: '1rem' }}>
                {uniqueChannels.length === 0 ? (
                  <p style={{ color: 'var(--text-secondary)' }}>(Chưa có dữ liệu. Hãy đảm bảo Database đã kết nối.)</p>
                ) : (
                  uniqueChannels.map(channel => (
                    <div key={channel} className="channel-group">
                      <h4>Kênh: {channel}</h4>
                      {sources.filter(s => s.id_tiktok === channel).map(source => (
                        <div key={source.id} className="source-item">
                          <label>
                            <input type="checkbox" checked={source.is_active} onChange={() => handleToggleSourceActive(source.id, source.is_active)} />
                            <span>📄 {source.category_url}</span>
                          </label>
                          <button className="btn" style={{ background: 'transparent', color: 'var(--danger)', padding: '0.25rem' }} onClick={() => handleDeleteSource(source.id)}>
                            <Trash2 size={16} />
                          </button>
                        </div>
                      ))}
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="card">
              <div className="controls-bar" style={{ justifyContent: 'space-between' }}>
                {!isRunning ? (
                   <button className="btn btn-primary" style={{ padding: '0.85rem 1.75rem', fontSize: '1rem' }} onClick={handleStart}>
                     <Play size={22}/> BẮT ĐẦU TỰ ĐỘNG
                   </button>
                ) : (
                   <button className="btn btn-danger" style={{ padding: '0.85rem 1.75rem', fontSize: '1rem' }} onClick={handleStop}>
                     <Square size={22}/> DỪNG LẠI
                   </button>
                )}
                <button className="btn btn-ghost" onClick={handleStartOnce}>
                  <Play size={18}/> Chạy 1 lần
                </button>
              </div>
              
              <div className="terminal" style={{ maxHeight: '300px', overflowY: 'auto' }}>
                {logs.map((log, idx) => (
                  <p key={idx}>{log}</p>
                ))}
                {isRunning && <p className="animate-pulse">_</p>}
              </div>
            </div>
          </div>
        )}


        {/* ═══ TAB: BÀI ĐÃ LÀM ═══ */}
        {activeTab === 'history' && (
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <h3>🔎 Danh sách bài báo đã làm</h3>
                <p style={{ color: 'var(--text-secondary)', marginTop: '0.35rem', fontSize: '0.85rem' }}>
                  Dữ liệu lấy từ bảng processed_links. Pipeline dùng chính bảng này để bỏ qua link đã xử lý.
                </p>
              </div>
              <button className="btn btn-ghost" onClick={() => fetchProcessedLinks()}>
                <RefreshCw size={16} /> Làm mới
              </button>
            </div>

            <div className="form-row" style={{ marginTop: '1rem' }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label">Dán link hoặc nhập từ khóa để kiểm tra trùng:</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="VD: https://vnexpress.net/..."
                  value={processedSearch}
                  onChange={e => setProcessedSearch(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') fetchProcessedLinks(); }}
                />
              </div>
              <div className="form-group">
                <button className="btn btn-primary" onClick={() => fetchProcessedLinks()}>
                  <Search size={18} /> Kiểm tra
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              <span>{processedLoading ? 'Đang tải...' : `Hiển thị ${processedCount} link gần nhất/tìm thấy`}</span>
              {processedSearch.trim() && !processedLoading && (
                <span style={{ color: processedCount > 0 ? 'var(--danger)' : 'var(--success)', fontWeight: 700 }}>
                  {processedCount > 0 ? 'Link/từ khóa này đã có trong danh sách' : 'Chưa thấy link trùng'}
                </span>
              )}
            </div>

            {processedDuplicates.length > 0 && (
              <div style={{ marginTop: '1rem', padding: '0.75rem', border: '1px solid var(--danger)', borderRadius: 8, color: 'var(--danger)' }}>
                Có {processedDuplicates.length} link bị lặp trong dữ liệu đang hiển thị.
              </div>
            )}

            <div style={{ marginTop: '1rem', overflowX: 'auto' }}>
              <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <th style={{ padding: '0.65rem' }}>Link bài báo</th>
                    <th style={{ padding: '0.65rem', width: 180 }}>Thời gian lưu</th>
                    <th style={{ padding: '0.65rem', width: 80 }}>Mở</th>
                  </tr>
                </thead>
                <tbody>
                  {processedLinks.map((item, idx) => (
                    <tr key={`${item.url || idx}-${idx}`} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '0.65rem', wordBreak: 'break-all' }}>{item.url}</td>
                      <td style={{ padding: '0.65rem', color: 'var(--text-secondary)' }}>
                        {item.created_at ? new Date(item.created_at).toLocaleString('vi-VN') : '-'}
                      </td>
                      <td style={{ padding: '0.65rem' }}>
                        {item.url && (
                          <a className="btn btn-ghost" style={{ padding: '0.35rem 0.55rem' }} href={item.url} target="_blank" rel="noreferrer">
                            <ExternalLink size={16} />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!processedLoading && processedLinks.length === 0 && (
                    <tr>
                      <td colSpan={3} style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                        Chưa có link nào hoặc không tìm thấy kết quả.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ═══ TAB 2: CHROME ═══ */}
        {activeTab === 'chrome' && (
          <div className="card">
            <h3>🌐 Quản lý Trình duyệt ChatGPT</h3>
            <div className="form-row" style={{ marginTop: '1.5rem' }}>
              <div className="form-group" style={{ flex: 1 }}>
                <select id="chromeChannelSelect" className="form-select" defaultValue="-- Chọn kênh để đăng nhập ChatGPT --">
                  <option>-- Chọn kênh để đăng nhập ChatGPT --</option>
                  {uniqueChannels.map(ch => <option key={ch} value={ch}>{ch}</option>)}
                </select>
              </div>
              <div className="form-group">
                <button className="btn btn-success" onClick={handleOpenChrome}><Key size={18} /> Mở Chrome Đăng Nhập</button>
              </div>
            </div>
          </div>
        )}

        {/* ═══ TAB 3: VISUAL TEXT EDITOR ═══ */}
        {activeTab === 'visual' && (
          <div>
            {/* Channel selector */}
            <div className="channel-select-bar">
              <label>🎯 Chọn kênh:</label>
              <select className="form-select" value={selectedChannel} onChange={handleChannelChange}>
                <option>-- Chọn kênh --</option>
                {uniqueChannels.map(ch => <option key={ch} value={ch}>{ch}</option>)}
              </select>
              <button className="btn btn-success" onClick={handleSaveConfig} disabled={selectedChannel === '-- Chọn kênh --'}>
                <Save size={18} /> Lưu Cấu Hình
              </button>
            </div>

            {/* Two visual editors side by side */}
            <div className="visual-editors-grid">
              <VisualTextEditor
                channelId={selectedChannel}
                frameType="intro"
                config={config}
                hasFrame={config.has_frame_intro}
                onConfigChange={handleConfigUpdate}
                label="🎬 Frame Intro — Căn text Tiêu đề (Hook)"
              />
              <VisualTextEditor
                channelId={selectedChannel}
                frameType="content"
                config={config}
                hasFrame={config.has_frame_content}
                onConfigChange={handleConfigUpdate}
                label="📝 Frame Content — Căn text Phụ đề (Nội dung)"
              />
            </div>
          </div>
        )}

        {/* ═══ TAB 4: CHỈ ĐẠO NỘI DUNG ═══ */}
        {activeTab === 'profile' && (
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3>🎯 Chỉ đạo nội dung theo ID TikTok</h3>
              <button className="btn btn-success" onClick={handleSaveConfig} disabled={selectedChannel === '-- Chọn kênh --'}>
                <Save size={18} /> Lưu chỉ đạo
              </button>
            </div>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.85rem' }}>
              Chỉ đạo này được đồng bộ với Tool TikTok theo cùng ID. Tool Tin tức sẽ gửi bộ chỉ đạo này cho ChatGPT để chọn đúng hook, giọng văn, format và tệp người xem của từng kênh.
            </p>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Chọn ID kênh/TikTok:</label>
              <select className="form-select" value={selectedChannel} onChange={handleChannelChange}>
                <option>-- Chọn kênh --</option>
                {uniqueChannels.map(ch => <option key={ch} value={ch}>{ch}</option>)}
              </select>
            </div>

            {selectedChannel === '-- Chọn kênh --' ? (
              <p style={{ color: 'var(--text-secondary)' }}>Chọn một kênh để xem hoặc chỉnh chỉ đạo nội dung đã đồng bộ từ Tool TikTok.</p>
            ) : (
              <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
                <div className="form-group">
                  <label className="form-label">Tên/định vị kênh:</label>
                  <input className="form-input" value={contentProfile.channel_name} onChange={e => handleProfileUpdate('channel_name', e.target.value)} placeholder="VD: Showbiz124h" />
                </div>
                <div className="form-group">
                  <label className="form-label">Chủ đề chính:</label>
                  <input className="form-input" value={contentProfile.topic} onChange={e => handleProfileUpdate('topic', e.target.value)} placeholder="VD: showbiz, thẩm mỹ, xe, tài chính" />
                </div>
                <div className="form-group">
                  <label className="form-label">Mục tiêu chính:</label>
                  <select className="form-select" value={contentProfile.primary_goal} onChange={e => handleProfileUpdate('primary_goal', e.target.value)}>
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
                  <select className="form-select" value={contentProfile.video_length} onChange={e => handleProfileUpdate('video_length', e.target.value)}>
                    <option value="30-45s">30-45s</option>
                    <option value="45-60s">45-60s</option>
                    <option value="60-90s">60-90s</option>
                    <option value="90-120s">90-120s</option>
                  </select>
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Tệp người xem:</label>
                  <textarea className="form-input" style={{ minHeight: '80px' }} value={contentProfile.audience} onChange={e => handleProfileUpdate('audience', e.target.value)} placeholder="VD: nữ 25-45 quan tâm làm đẹp, sợ chọn sai dịch vụ thẩm mỹ" />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Lời hứa nội dung:</label>
                  <textarea className="form-input" style={{ minHeight: '80px' }} value={contentProfile.content_promise} onChange={e => handleProfileUpdate('content_promise', e.target.value)} placeholder="Kênh này giúp người xem hiểu/chọn/cảnh giác về điều gì?" />
                </div>
                <div className="form-group">
                  <label className="form-label">Giọng văn/phong cách:</label>
                  <input className="form-input" value={contentProfile.tone_style} onChange={e => handleProfileUpdate('tone_style', e.target.value)} placeholder="VD: tin nóng, cảnh báo, chuyên gia, kể chuyện" />
                </div>
                <div className="form-group">
                  <label className="form-label">Format lặp lại:</label>
                  <input className="form-input" value={contentProfile.format_style} onChange={e => handleProfileUpdate('format_style', e.target.value)} placeholder="VD: tin nhanh, review, so sánh, cảnh báo, storytelling" />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Kiểu hook phù hợp:</label>
                  <textarea className="form-input" style={{ minHeight: '80px' }} value={contentProfile.hook_style} onChange={e => handleProfileUpdate('hook_style', e.target.value)} placeholder="VD: Chi tiết này mới đáng chú ý..., Nhiều người đang hiểu sai..., Mẫu xe này có đáng mua không?" />
                </div>
                <div className="form-group">
                  <label className="form-label">Ưu tiên chọn nguồn/bài:</label>
                  <input className="form-input" value={contentProfile.source_preference} onChange={e => handleProfileUpdate('source_preference', e.target.value)} placeholder="VD: ưu tiên bài có tranh luận, số liệu mới, nhân vật cụ thể" />
                </div>
                <div className="form-group">
                  <label className="form-label">Cách kéo bình luận:</label>
                  <input className="form-input" value={contentProfile.comment_strategy} onChange={e => handleProfileUpdate('comment_strategy', e.target.value)} placeholder="VD: kết bằng câu hỏi chọn phe hoặc hỏi trải nghiệm cá nhân" />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Điều cần tránh:</label>
                  <textarea className="form-input" style={{ minHeight: '80px' }} value={contentProfile.avoid} onChange={e => handleProfileUpdate('avoid', e.target.value)} placeholder="VD: không khẳng định y khoa quá mức, không bịa số liệu, không vu khống" />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Ví dụ video từng hiệu quả:</label>
                  <textarea className="form-input" style={{ minHeight: '100px' }} value={contentProfile.winning_examples} onChange={e => handleProfileUpdate('winning_examples', e.target.value)} placeholder="Dán 3-5 hook hoặc mô tả video từng lên view tốt để AI học pattern." />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Chỉ đạo tùy biến thêm:</label>
                  <textarea className="form-input" style={{ minHeight: '110px' }} value={contentProfile.custom_instruction} onChange={e => handleProfileUpdate('custom_instruction', e.target.value)} placeholder="Quy tắc riêng: từ cấm dùng, cách xưng hô, cấu trúc câu, tiêu chuẩn chọn bài/video..." />
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══ TAB 5: ASSETS ═══ */}
        {activeTab === 'assets' && (
          <div className="grid">
            <div className="card">
              <h3>🖼️ Quản lý Frame & Logo</h3>
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Chọn ID kênh/TikTok:</label>
                <select className="form-select" value={selectedChannel} onChange={handleChannelChange}>
                  <option>-- Chọn kênh --</option>
                  {uniqueChannels.map(ch => <option key={ch} value={ch}>{ch}</option>)}
                </select>
              </div>

              <div className="asset-section">
                <p className="asset-label">Khung Intro:</p>
                <p style={{ color: config.has_frame_intro ? 'var(--success)' : 'var(--danger)', fontSize: '0.85rem' }}>
                  {config.has_frame_intro ? `✅ Có file (${config.frame_intro_name})` : '❌ Chưa có / Đã tắt'}
                </p>
                <div className="asset-controls">
                  <select className="form-select" style={{ flex: 1, padding: '0.5rem' }}>
                    <option>-- Chọn từ thư viện --</option>
                    {library.frames.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                  <button className="btn btn-primary" style={{ padding: '0.5rem 0.75rem' }}><Upload size={16} /></button>
                  <button className="btn btn-danger" style={{ padding: '0.5rem 0.75rem' }}><Trash2 size={16} /></button>
                </div>
              </div>

              <div className="asset-section">
                <p className="asset-label">Khung Content:</p>
                <p style={{ color: config.has_frame_content ? 'var(--success)' : 'var(--danger)', fontSize: '0.85rem' }}>
                  {config.has_frame_content ? `✅ Có file (${config.frame_content_name})` : '❌ Chưa có / Đã tắt'}
                </p>
                <div className="asset-controls">
                  <select className="form-select" style={{ flex: 1, padding: '0.5rem' }}>
                    <option>-- Chọn từ thư viện --</option>
                    {library.frames.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                  <button className="btn btn-primary" style={{ padding: '0.5rem 0.75rem' }}><Upload size={16} /></button>
                  <button className="btn btn-danger" style={{ padding: '0.5rem 0.75rem' }}><Trash2 size={16} /></button>
                </div>
              </div>

              <div className="asset-section">
                <p className="asset-label">Logo:</p>
                <p style={{ color: config.has_logo ? 'var(--success)' : 'var(--danger)', fontSize: '0.85rem' }}>
                  {config.has_logo ? `✅ Có file (${config.logo_name})` : '❌ Chưa có / Đã tắt'}
                </p>
                <div className="asset-controls">
                  <select className="form-select" style={{ flex: 1, padding: '0.5rem' }}>
                    <option>-- Chọn từ thư viện --</option>
                    {library.logos.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                  <button className="btn btn-primary" style={{ padding: '0.5rem 0.75rem' }}><Upload size={16} /></button>
                  <button className="btn btn-danger" style={{ padding: '0.5rem 0.75rem' }}><Trash2 size={16} /></button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ═══ TAB 6: PROMPT ═══ */}
        {activeTab === 'prompt' && (
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3>🧠 Chỉnh sửa Prompt Bài Báo</h3>
              <button className="btn btn-success" onClick={handleSavePrompt}>
                <Save size={18} /> Lưu Prompt
              </button>
            </div>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.85rem' }}>
              Nội dung này sẽ được gửi kèm bài báo cho ChatGPT để phân tích hình ảnh và bóc tách kịch bản.
            </p>
            <textarea
              className="form-input"
              style={{ width: '100%', minHeight: '500px', fontFamily: 'monospace', fontSize: '0.82rem', lineHeight: '1.6', padding: '1rem', resize: 'vertical' }}
              value={promptContent}
              onChange={(e) => setPromptContent(e.target.value)}
              placeholder="Đang tải prompt..."
            />
          </div>
        )}
      </div>
    </div>
  );
}
