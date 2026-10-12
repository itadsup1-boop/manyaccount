import { useState, useEffect, useRef } from 'react';
import {
  AudioLines,
  BrainCircuit,
  ClipboardCheck,
  Files,
  LogIn,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Save,
  Square,
  Target,
  Trash2,
  Type,
  UsersRound,
  Workflow,
  X,
  ShieldAlert,
} from 'lucide-react';
import FacebookGroupSourcesPanel from '../components/facebook/FacebookGroupSourcesPanel';
import FacebookGroupReviewPanel from '../components/facebook/FacebookGroupReviewPanel';
import TitlePositionEditor from '../components/TitlePositionEditor';
import ToolPageHeader from '../components/ui/ToolPageHeader';
import ToolTabs from '../components/ui/ToolTabs';
import { useAuth } from '../context/AuthContext';
import '../features/facebook/facebook.css';
import '../features/tiktok/tiktok.css';

const FACEBOOK_DEFAULT_CHANNEL_ID = 'Adsupnews';

type FacebookTab = 'pipeline' | 'sources' | 'groups' | 'group-review' | 'content' | 'display' | 'prompt' | 'voice';

const FACEBOOK_TABS = [
  { id: 'pipeline', label: 'Pipeline', icon: Workflow },
  { id: 'sources', label: 'Nguồn Page', icon: Files },
  { id: 'groups', label: 'Nguồn Group', icon: UsersRound },
  { id: 'group-review', label: 'Chờ duyệt Group', icon: ClipboardCheck },
  { id: 'content', label: 'Chỉ đạo nội dung', icon: Target },
  { id: 'display', label: 'Chữ trên video', icon: Type },
  { id: 'prompt', label: 'Prompt', icon: BrainCircuit },
  { id: 'voice', label: 'Voice', icon: AudioLines },
] as const;

const defaultContentProfile: Record<string, string> = {
  channel_name: '',
  topic: '',
  audience: '',
  content_promise: '',
  primary_goal: 'view',
  tone_style: '',
  video_length: '38-42s',
  format_style: '',
  hook_style: '',
  source_preference: '',
  comment_strategy: '',
  avoid: '',
  winning_examples: '',
  custom_instruction: ''
};

function normalizeContentProfile(profile?: Record<string, string>) {
  const normalized = { ...defaultContentProfile, ...(profile || {}) };
  if (/38\D+42/.test(String(normalized.video_length || ''))) {
    normalized.video_length = '38-42s';
  }
  return normalized;
}

function getFacebookChannelId(source?: any) {
  const channelId = String(source?.id_tiktok || '').trim();
  return channelId || FACEBOOK_DEFAULT_CHANNEL_ID;
}

export default function ToolFacebook() {
  const { isAdmin } = useAuth();
  const [activeTab, setActiveTab] = useState<FacebookTab>('pipeline');
  const pageLogRef = useRef<HTMLDivElement>(null);
  const groupLogRef = useRef<HTMLDivElement>(null);

  const [pageStatus, setPageStatus] = useState<{ is_running: boolean; logs: string[] }>({
    is_running: false,
    logs: ['[Hệ thống] Sẵn sàng khởi động Tool Facebook Page...']
  });
  const [groupStatus, setGroupStatus] = useState<{ is_running: boolean; logs: string[] }>({
    is_running: false,
    logs: ['[Hệ thống] Sẵn sàng khởi động Tool Facebook Group...']
  });
  const [sources, setSources] = useState<any[]>([]);
  const [groupSources, setGroupSources] = useState<any[]>([]);
  const [promptContent, setPromptContent] = useState('');
  const [voiceConfig, setVoiceConfig] = useState<any>({
    "Tích cực": "", "Trung tính": "", "Cảnh báo": "", "Đồng cảm": ""
  });
  const [facebookAuth, setFacebookAuth] = useState<any>({ logged_in: false, login_running: false });
  const [editingSourceId, setEditingSourceId] = useState<number | null>(null);
  const [aiProvider, setAiProvider] = useState<string>('chatgpt');
  const [titlePreviewMode, setTitlePreviewMode] = useState<'intro' | 'content'>('intro');

  useEffect(() => {
    fetch('/api/ai/provider')
      .then(res => res.json())
      .then(data => { if (data.provider) setAiProvider(data.provider); })
      .catch(() => {});
  }, []);

  const handleSetAiProvider = (provider: string) => {
    setAiProvider(provider);
    fetch('/api/ai/provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider }),
    });
  };

  const handleOpenGeminiChrome = () => {
    fetch('/api/gemini/chrome', { method: 'POST' });
  };

  const [newSource, setNewSource] = useState({
    id_tiktok: FACEBOOK_DEFAULT_CHANNEL_ID,
    source_name: '',
    source_url: '',
    max_video_age_hours: 48,
    delogo: ''
  });
  const [selectedChannel, setSelectedChannel] = useState(FACEBOOK_DEFAULT_CHANNEL_ID);
  const [channelConfig, setChannelConfig] = useState<any>({ content_profile: defaultContentProfile });

  const uniqueChannels = Array.from(new Set([
    FACEBOOK_DEFAULT_CHANNEL_ID,
    ...sources.map((source: any) => getFacebookChannelId(source)).filter(Boolean),
    ...groupSources.map((source: any) => getFacebookChannelId(source)).filter(Boolean)
  ])) as string[];
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

  const fetchGroupSources = () => {
    fetch(`/api/facebook/group-sources`)
      .then(res => res.json())
      .then(data => {
        if (!data.error) setGroupSources(data);
      })
      .catch(console.error);
  };

  const fetchVoiceConfig = () => {
    fetch(`/api/facebook/voice`)
      .then(res => res.json())
      .then(data => setVoiceConfig(data))
      .catch(console.error);
  };

  const fetchFacebookAuth = () => {
    fetch(`/api/facebook/auth/status`)
      .then(res => res.json())
      .then(data => setFacebookAuth(data))
      .catch(console.error);
  };

  const handleFacebookLogin = () => {
    fetch(`/api/facebook/auth/login`, { method: 'POST' })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Không mở được cửa sổ đăng nhập');
        return data;
      })
      .then(() => {
        setFacebookAuth((current: any) => ({ ...current, login_running: true }));
        alert('Đã mở cửa sổ Facebook trên máy chạy Hub. Hãy đăng nhập trong cửa sổ đó.');
      })
      .catch(error => alert(`Không mở được Facebook: ${error}`));
  };

  useEffect(() => {
    fetchSources();
    fetchGroupSources();
    fetchVoiceConfig();
    fetchFacebookAuth();

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
          if (data.page) {
            setPageStatus({
              is_running: !!data.page.is_running,
              logs: data.page.logs || ['[Hệ thống] Sẵn sàng khởi động Tool Facebook Page...']
            });
          }
          if (data.group) {
            setGroupStatus({
              is_running: !!data.group.is_running,
              logs: data.group.logs || ['[Hệ thống] Sẵn sàng khởi động Tool Facebook Group...']
            });
          }
        })
        .catch(() => {});
      fetchFacebookAuth();
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (pageLogRef.current) {
      pageLogRef.current.scrollTop = pageLogRef.current.scrollHeight;
    }
  }, [pageStatus.logs]);

  useEffect(() => {
    if (groupLogRef.current) {
      groupLogRef.current.scrollTop = groupLogRef.current.scrollHeight;
    }
  }, [groupStatus.logs]);

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
    fetch(editingSourceId ? `/api/facebook/sources/${editingSourceId}` : `/api/facebook/sources`, {
      method: editingSourceId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(async res => {
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Dữ liệu nguồn không hợp lệ');
      return data;
    }).then(data => {
      if (data.status === 'success') {
        setNewSource({
          id_tiktok: FACEBOOK_DEFAULT_CHANNEL_ID,
          source_name: '',
          source_url: '',
          max_video_age_hours: 48,
          delogo: ''
        });
        setEditingSourceId(null);
        fetchSources();
      } else {
        alert('Lỗi: ' + data.error);
      }
    }).catch(error => alert('Lỗi: ' + error.message));
  };

  const handleEditSource = (source: any) => {
    setEditingSourceId(source.id);
    setNewSource({
      id_tiktok: getFacebookChannelId(source),
      source_name: source.source_name || '',
      source_url: source.source_url || '',
      max_video_age_hours: source.max_video_age_hours ?? 48,
      delogo: source.delogo || ''
    });
  };

  const cancelEditSource = () => {
    setEditingSourceId(null);
    setNewSource({
      id_tiktok: FACEBOOK_DEFAULT_CHANNEL_ID,
      source_name: '',
      source_url: '',
      max_video_age_hours: 48,
      delogo: ''
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

  const handleConfigField = (key: string, value: string | number) => {
    setChannelConfig((prev: any) => ({ ...prev, [key]: value }));
  };

  const handleFacebookTitleEditorChange = (
    updates: Record<string, number | string>,
    mode: 'intro' | 'content'
  ) => {
    setChannelConfig((prev: any) => {
      const next = { ...prev, text_position_mode: 'manual' };
      const widthRatio = Math.max(0.35, Math.min(0.95, Number(prev.text_w ?? 0.85)));
      const centeredLeft = (1080 - 1080 * widthRatio) / 2;

      if (updates.box_y_start !== undefined) {
        const y = Math.max(0, Math.min(0.92, Number(updates.box_y_start)));
        if (mode === 'intro') next.text_y1 = y;
        else next.text_y_content = y;
      }
      if (updates.box_x_offset !== undefined) {
        // TitlePositionEditor emits an offset from the centered text box,
        // while the Facebook renderer stores the absolute left X coordinate.
        next.text_x = Math.round(centeredLeft + Number(updates.box_x_offset));
      }
      if (updates.box_width_percentage !== undefined) {
        next.text_w = Number(updates.box_width_percentage);
      }
      if (updates.font_size !== undefined) {
        next.text_size = Number(updates.font_size);
      }
      if (updates.text_color !== undefined) {
        next.text_color = String(updates.text_color);
      }
      return next;
    });
  };

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

  const handleStart = (sourceScope: 'page' | 'group') => {
    if (sourceScope === 'page') setPageStatus(prev => ({ ...prev, is_running: true }));
    else setGroupStatus(prev => ({ ...prev, is_running: true }));
    fetch(`/api/facebook/start?source_scope=${sourceScope}`, { method: 'POST' });
  };

  const handleStop = (sourceScope: 'page' | 'group' | 'all' = 'all') => {
    if (sourceScope === 'page') setPageStatus(prev => ({ ...prev, is_running: false }));
    else if (sourceScope === 'group') setGroupStatus(prev => ({ ...prev, is_running: false }));
    else {
      setPageStatus(prev => ({ ...prev, is_running: false }));
      setGroupStatus(prev => ({ ...prev, is_running: false }));
    }
    fetch(`/api/facebook/stop?source_scope=${sourceScope}`, { method: 'POST' });
  };

  const handleStartOnce = (sourceScope: 'page' | 'group') => {
    if (sourceScope === 'page') setPageStatus(prev => ({ ...prev, is_running: true }));
    else setGroupStatus(prev => ({ ...prev, is_running: true }));
    fetch(`/api/facebook/start_once?source_scope=${sourceScope}`, { method: 'POST' });
  };

  const rawTitleWidth = Number(channelConfig.text_w ?? 0.85);
  const facebookTitleWidth = Number.isFinite(rawTitleWidth)
    ? Math.max(0.35, Math.min(0.95, rawTitleWidth))
    : 0.85;
  const rawIntroY = Number(channelConfig.text_y1 ?? 0.73);
  const facebookIntroY = Number.isFinite(rawIntroY)
    ? Math.max(0, Math.min(0.92, rawIntroY))
    : 0.73;
  const rawContentY = Number(channelConfig.text_y_content ?? 0);
  const facebookContentY = Number.isFinite(rawContentY) && rawContentY > 0
    ? Math.max(0, Math.min(0.92, rawContentY))
    : Math.min(0.92, facebookIntroY + 220 / 1920);
  const titleCenteredLeft = (1080 - 1080 * facebookTitleWidth) / 2;
  const rawTitleX = Number(channelConfig.text_x ?? 0);
  const facebookTitleXOffset = (Number.isFinite(rawTitleX) ? rawTitleX : 0) - titleCenteredLeft;
  const rawTitleSize = Number(channelConfig.text_size ?? 50);
  const facebookTitleSize = Number.isFinite(rawTitleSize) ? rawTitleSize : 50;

  return (
    <div className="facebook-page">
      <ToolPageHeader
        title="Tool Facebook"
        description="Tự động cào tin bài Facebook Page và Group độc lập"
        status={(
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(255,255,255,0.06)', borderRadius: '8px', padding: '4px 8px' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>🤖 AI Engine:</span>
              <button
                type="button"
                className={`tiktok-btn ${aiProvider === 'chatgpt' ? 'tiktok-btn--primary' : 'tiktok-btn--outline'}`}
                style={{ padding: '3px 10px', fontSize: '12px', borderRadius: '6px' }}
                onClick={() => handleSetAiProvider('chatgpt')}
              >
                ChatGPT
              </button>
              <button
                type="button"
                className={`tiktok-btn ${aiProvider === 'gemini' ? 'tiktok-btn--primary' : 'tiktok-btn--outline'}`}
                style={{ padding: '3px 10px', fontSize: '12px', borderRadius: '6px' }}
                onClick={() => handleSetAiProvider('gemini')}
              >
                Gemini (Web)
              </button>
            </div>
            <button className="tiktok-btn tiktok-btn--outline" onClick={handleOpenGeminiChrome} title="Đăng nhập Gemini Web">
              🌐 Gemini Web
            </button>
            <span className={`facebook-auth-badge ${facebookAuth.logged_in ? 'is-logged-in' : 'is-logged-out'}`}>
              {facebookAuth.logged_in ? 'Đã đăng nhập Facebook' : 'Chưa đăng nhập Facebook'}
            </span>
            <button className="tiktok-btn tiktok-btn--outline" onClick={handleFacebookLogin}>
              <LogIn size={16} aria-hidden="true" /> Trình duyệt Facebook
            </button>
          </div>
        )}
      />

      {!isAdmin && (
        <div style={{ background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.3)', margin: '1rem 0', padding: '0.75rem 1rem', borderRadius: '10px', color: '#93c5fd', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShieldAlert size={18} />
          <span>Bạn đang ở chế độ <strong>Người dùng (User Role)</strong>. Các thao tác điều khiển bot, đổi AI Engine hoặc sửa cấu hình chỉ dành cho Admin.</span>
        </div>
      )}

      <ToolTabs
        activeTab={activeTab}
        ariaLabel="Các mục Tool Facebook"
        tabs={FACEBOOK_TABS}
        onChange={(tab) => setActiveTab(tab)}
      />

      {activeTab === 'pipeline' && (
        <div className="tiktok-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
          {/* PIPELINE PAGE CARD */}
          <article className="tiktok-card">
            <div className="tiktok-card__header" style={{ justifyContent: 'space-between' }}>
              <div>
                <h3>📄 Pipeline Facebook Page</h3>
                <p style={{ color: 'var(--tiktok-subtle)', fontSize: '0.82rem', margin: '0.2rem 0 0' }}>
                  Cào và xử lý các trang Facebook Fanpage
                </p>
              </div>
              <span className={`article-status ${pageStatus.is_running ? 'is-running' : ''}`}>
                <span aria-hidden="true" />
                {pageStatus.is_running ? 'Đang chạy' : 'Đang dừng'}
              </span>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', margin: '1rem 0' }}>
              {pageStatus.is_running ? (
                <button className="tiktok-btn tiktok-btn--danger" onClick={() => handleStop('page')}>
                  <Square size={16}/> Dừng Pipeline Page
                </button>
              ) : (
                <>
                  <button className="tiktok-btn tiktok-btn--primary" onClick={() => handleStart('page')}>
                    <Play size={16}/> Chạy liên tục Page
                  </button>
                  <button className="tiktok-btn tiktok-btn--outline" onClick={() => handleStartOnce('page')}>
                    <Play size={16}/> Page 1 lần
                  </button>
                </>
              )}
            </div>

            <div ref={pageLogRef} className="tiktok-log" style={{ height: '320px', overflowY: 'auto' }}>
              {pageStatus.logs.map((log, idx) => (
                <p key={idx}>{log}</p>
              ))}
              {pageStatus.is_running && <p className="animate-pulse">_</p>}
            </div>
          </article>

          {/* PIPELINE GROUP CARD */}
          <article className="tiktok-card">
            <div className="tiktok-card__header" style={{ justifyContent: 'space-between' }}>
              <div>
                <h3>👥 Pipeline Facebook Group</h3>
                <p style={{ color: 'var(--tiktok-subtle)', fontSize: '0.82rem', margin: '0.2rem 0 0' }}>
                  Cào và xử lý bài viết trong Facebook Group
                </p>
              </div>
              <span className={`article-status ${groupStatus.is_running ? 'is-running' : ''}`}>
                <span aria-hidden="true" />
                {groupStatus.is_running ? 'Đang chạy' : 'Đang dừng'}
              </span>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', margin: '1rem 0' }}>
              {groupStatus.is_running ? (
                <button className="tiktok-btn tiktok-btn--danger" onClick={() => handleStop('group')}>
                  <Square size={16}/> Dừng Pipeline Group
                </button>
              ) : (
                <>
                  <button className="tiktok-btn tiktok-btn--primary" onClick={() => handleStart('group')}>
                    <Play size={16}/> Chạy liên tục Group
                  </button>
                  <button className="tiktok-btn tiktok-btn--outline" onClick={() => handleStartOnce('group')}>
                    <Play size={16}/> Group 1 lần
                  </button>
                </>
              )}
            </div>

            <div ref={groupLogRef} className="tiktok-log" style={{ height: '320px', overflowY: 'auto' }}>
              {groupStatus.logs.map((log, idx) => (
                <p key={idx}>{log}</p>
              ))}
              {groupStatus.is_running && <p className="animate-pulse">_</p>}
            </div>
          </article>
        </div>
      )}

      {activeTab === 'sources' && (
        <div className="grid">
          <div className="card">
            <h3>{editingSourceId ? 'Sửa nguồn Page' : 'Thêm nguồn Facebook Page'}</h3>
            <p style={{ color: 'var(--text-secondary)', marginTop: '0.75rem', fontSize: '0.85rem' }}>
              Đây là khu vực Page cũ. URL Group sẽ không được lưu vào danh sách này.
            </p>
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
              <label className="form-label">URL Page:</label>
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
            <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
              <button className="btn btn-primary" style={{ flex: 1, justifyContent: 'center' }} onClick={handleAddSource}>
                {editingSourceId ? <Save size={18} /> : <Plus size={18} />}
                {editingSourceId ? 'Lưu Page' : 'Thêm Page'}
              </button>
              {editingSourceId && (
                <button className="btn" onClick={cancelEditSource}><X size={18} /> Hủy</button>
              )}
            </div>
          </div>

          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3>Nguồn Page đang theo dõi</h3>
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
                        <button className="btn" style={{ background: 'transparent', color: 'var(--info)', padding: '0.25rem' }} onClick={() => handleEditSource(s)}>
                          <Pencil size={16} />
                        </button>
                        <button className="btn" style={{ background: 'transparent', color: 'var(--danger)', padding: '0.25rem' }} onClick={() => handleDeleteSource(s.id)}>
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {sources.length === 0 && (
                    <tr><td colSpan={6} style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Chưa có nguồn Page.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'groups' && (
        <FacebookGroupSourcesPanel
          sources={groupSources}
          auth={facebookAuth}
          onRefresh={fetchGroupSources}
          onLogin={handleFacebookLogin}
        />
      )}

      {activeTab === 'group-review' && <FacebookGroupReviewPanel />}

      {activeTab === 'content' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>Chỉ đạo nội dung Facebook theo kênh đích</h3>
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
                  <option value="38-42s">38-42s (khoảng 40s)</option>
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

      {activeTab === 'display' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>Chữ tiêu đề trên video Facebook</h3>
            <button className="btn btn-success" onClick={handleSaveChannelProfile} disabled={!selectedChannel}>
              <Save size={18} /> Lưu cấu hình
            </button>
          </div>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.85rem' }}>
            Tiêu đề hiển thị xuyên suốt video. Ở đoạn có Frame Title nó dùng "Vị trí Y
            trên Frame Title"; khi video chuyển sang Frame Content nó tự chuyển xuống
            "Vị trí Y trên Frame Content". Chữ dài sẽ tự xuống dòng và tự thu nhỏ, không
            bị cắt bằng dấu ba chấm.
          </p>

          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">Chọn ID kênh đích:</label>
            <select className="form-select" value={selectedChannel} onChange={e => handleChannelSelect(e.target.value)}>
              <option value="">-- Chọn kênh --</option>
              {uniqueChannels.map(ch => <option key={ch} value={ch}>{ch}</option>)}
            </select>
          </div>

          {!selectedChannel ? (
            <p style={{ color: 'var(--text-secondary)' }}>Hãy chọn kênh để cấu hình chữ.</p>
          ) : (
            <>
              <div
                style={{
                  marginBottom: '1.25rem',
                  padding: '1rem',
                  border: '1px solid var(--border)',
                  borderRadius: '12px',
                  background: 'rgba(15, 23, 42, 0.28)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '1rem' }}>
                  <div>
                    <strong style={{ display: 'block' }}>Xem trước và kéo title trực tiếp</strong>
                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                      Kéo khung chữ để đổi vị trí; kéo ô vuông góc phải dưới để phóng to hoặc thu nhỏ.
                    </span>
                  </div>
                  <div role="tablist" aria-label="Chọn khung xem trước title Facebook" style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={titlePreviewMode === 'intro'}
                      className={`tiktok-btn ${titlePreviewMode === 'intro' ? 'tiktok-btn--primary' : 'tiktok-btn--outline'}`}
                      onClick={() => setTitlePreviewMode('intro')}
                    >
                      Frame Title
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={titlePreviewMode === 'content'}
                      className={`tiktok-btn ${titlePreviewMode === 'content' ? 'tiktok-btn--primary' : 'tiktok-btn--outline'}`}
                      onClick={() => setTitlePreviewMode('content')}
                    >
                      Frame Content
                    </button>
                  </div>
                </div>

                <TitlePositionEditor
                  channelId={selectedChannel}
                  frameUrl={`/api/article/channel-image/${encodeURIComponent(selectedChannel)}/${titlePreviewMode === 'intro' ? 'frame_intro.png' : 'frame_content.png'}`}
                  sampleText={titlePreviewMode === 'intro' ? 'TITLE FACEBOOK - KHUNG MỞ ĐẦU' : 'TITLE FACEBOOK - KHUNG NỘI DUNG'}
                  yStart={titlePreviewMode === 'intro' ? facebookIntroY : facebookContentY}
                  xOffset={facebookTitleXOffset}
                  boxWidth={facebookTitleWidth}
                  fontSize={facebookTitleSize}
                  color={String(channelConfig.text_color || '#ffffff')}
                  onChange={(updates) => handleFacebookTitleEditorChange(updates, titlePreviewMode)}
                />

                {titlePreviewMode === 'content' && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.9rem', flexWrap: 'wrap' }}>
                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                      {rawContentY > 0
                        ? 'Frame Content đang dùng vị trí riêng đã khóa.'
                        : 'Frame Content đang dùng vị trí tự động thấp hơn Frame Title.'}
                    </span>
                    {rawContentY > 0 && (
                      <button
                        type="button"
                        className="tiktok-btn tiktok-btn--outline"
                        onClick={() => handleConfigField('text_y_content', 0)}
                      >
                        Dùng lại vị trí tự động
                      </button>
                    )}
                  </div>
                )}
              </div>

              <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
              <div className="form-group">
                <label className="form-label">Vị trí Y trên Frame Title (0 - 1):</label>
                <input
                  type="number" className="form-input" step="0.01" min="0" max="1"
                  value={channelConfig.text_y1 ?? 0.73}
                  onChange={e => handleConfigField('text_y1', parseFloat(e.target.value) || 0)}
                />
                <small style={{ color: 'var(--text-secondary)' }}>0.73 = 73% chiều cao khung.</small>
              </div>

              <div className="form-group">
                <label className="form-label">Vị trí Y trên Frame Content (0 - 1):</label>
                <input
                  type="number" className="form-input" step="0.01" min="0" max="1"
                  value={channelConfig.text_y_content ?? 0}
                  onChange={e => handleConfigField('text_y_content', parseFloat(e.target.value) || 0)}
                />
                <small style={{ color: 'var(--text-secondary)' }}>
                  Để 0 = tự đặt thấp hơn Frame Title một khoảng.
                </small>
              </div>

              <div className="form-group">
                <label className="form-label">Vị trí X từ mép trái (px):</label>
                <input
                  type="number" className="form-input" step="1"
                  value={channelConfig.text_x ?? 0}
                  onChange={e => handleConfigField('text_x', parseInt(e.target.value) || 0)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Cỡ chữ:</label>
                <input
                  type="number" className="form-input" step="1" min="20" max="120"
                  value={channelConfig.text_size ?? 50}
                  onChange={e => handleConfigField('text_size', parseInt(e.target.value) || 50)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Màu chữ:</label>
                <input
                  type="color" className="form-input" style={{ height: '42px', padding: '4px' }}
                  value={channelConfig.text_color ?? '#ffffff'}
                  onChange={e => handleConfigField('text_color', e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Bề rộng vùng chữ (0 - 1):</label>
                <input
                  type="number" className="form-input" step="0.01" min="0.2" max="1"
                  value={channelConfig.text_w ?? 0.85}
                  onChange={e => handleConfigField('text_w', parseFloat(e.target.value) || 0.85)}
                />
              </div>
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === 'prompt' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>Chỉnh sửa Prompt Kịch Bản Facebook</h3>
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
          <h3>Cài đặt Voice ID mặc định (Toàn cục)</h3>
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
