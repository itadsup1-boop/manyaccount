import { KeyRound, Pencil, Plus, RefreshCw, Save, Trash2, X } from 'lucide-react';
import { useState } from 'react';

export const FACEBOOK_GROUP_EDIT_MODE_FULL_AI = 'full_ai_voiceover';
export const FACEBOOK_GROUP_EDIT_MODE_HOOK = 'hook_then_original';

const DEFAULT_CHANNEL = 'Adsupnews';

type GroupSource = {
  id: number;
  id_tiktok?: string;
  source_name?: string;
  source_url?: string;
  edit_mode?: string;
  max_video_age_hours?: number;
  max_videos_per_scan?: number;
  delogo?: string;
};

type GroupSourceForm = {
  id_tiktok: string;
  source_name: string;
  source_url: string;
  edit_mode: string;
  max_video_age_hours: number;
  max_videos_per_scan: number;
  delogo: string;
};

type Props = {
  sources: GroupSource[];
  auth: { logged_in?: boolean; login_running?: boolean };
  onRefresh: () => void;
  onLogin: () => void;
};

function emptyForm(): GroupSourceForm {
  return {
    id_tiktok: DEFAULT_CHANNEL,
    source_name: '',
    source_url: '',
    edit_mode: FACEBOOK_GROUP_EDIT_MODE_HOOK,
    max_video_age_hours: 48,
    max_videos_per_scan: 5,
    delogo: ''
  };
}

async function parseResponse(response: Response) {
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.detail || data.error || 'Không lưu được nguồn Group');
  }
  return data;
}

export default function FacebookGroupSourcesPanel({ sources, auth, onRefresh, onLogin }: Props) {
  const [form, setForm] = useState<GroupSourceForm>(emptyForm());
  const [editingId, setEditingId] = useState<number | null>(null);

  const reset = () => {
    setForm(emptyForm());
    setEditingId(null);
  };

  const submit = async () => {
    if (!form.source_name.trim() || !form.source_url.trim()) {
      alert('Hãy nhập Tên nhóm và URL nhóm.');
      return;
    }
    const endpoint = editingId
      ? `/api/facebook/group-sources/${editingId}`
      : '/api/facebook/group-sources';
    try {
      await parseResponse(await fetch(endpoint, {
        method: editingId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      }));
      reset();
      onRefresh();
    } catch (error) {
      alert(`Lỗi: ${error instanceof Error ? error.message : error}`);
    }
  };

  const edit = (source: GroupSource) => {
    setEditingId(source.id);
    setForm({
      id_tiktok: String(source.id_tiktok || DEFAULT_CHANNEL),
      source_name: String(source.source_name || ''),
      source_url: String(source.source_url || ''),
      edit_mode: String(source.edit_mode || FACEBOOK_GROUP_EDIT_MODE_HOOK),
      max_video_age_hours: source.max_video_age_hours ?? 48,
      max_videos_per_scan: source.max_videos_per_scan ?? 5,
      delogo: String(source.delogo || '')
    });
  };

  const remove = async (id: number) => {
    try {
      await parseResponse(await fetch(`/api/facebook/group-sources/${id}`, {
        method: 'DELETE'
      }));
      onRefresh();
    } catch (error) {
      alert(`Lỗi: ${error instanceof Error ? error.message : error}`);
    }
  };

  return (
    <div className="grid">
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
          <h3>{editingId ? 'Sửa nguồn Group' : 'Thêm nguồn Facebook Group'}</h3>
          <button className="btn" onClick={onLogin} disabled={auth.login_running}>
            <KeyRound size={16} />
            {auth.login_running
              ? 'Đang chờ đăng nhập...'
              : auth.logged_in ? 'Facebook đã đăng nhập' : 'Đăng nhập Facebook'}
          </button>
        </div>
        <p style={{ color: 'var(--text-secondary)', marginTop: '0.75rem', fontSize: '0.85rem' }}>
          Khu vực này chỉ dành cho Group và lưu ở bảng riêng. Bot chỉ nhận bài thuộc đúng nhóm và có video trong bài.
        </p>

        <div className="form-group" style={{ marginTop: '1rem' }}>
          <label className="form-label">ID kênh đích:</label>
          <input className="form-input" value={form.id_tiktok} onChange={event => setForm({ ...form, id_tiktok: event.target.value })} />
        </div>
        <div className="form-group" style={{ marginTop: '1rem' }}>
          <label className="form-label">Tên nhóm:</label>
          <input className="form-input" placeholder="VD: Hội xe Việt Nam" value={form.source_name} onChange={event => setForm({ ...form, source_name: event.target.value })} />
        </div>
        <div className="form-group" style={{ marginTop: '1rem' }}>
          <label className="form-label">URL nhóm:</label>
          <input className="form-input" placeholder="https://www.facebook.com/groups/123456789" value={form.source_url} onChange={event => setForm({ ...form, source_url: event.target.value })} />
        </div>

        <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', marginTop: '1rem', gap: '1rem' }}>
          <div className="form-group">
            <label className="form-label">Chế độ biên tập:</label>
            <select className="form-input" value={form.edit_mode} onChange={event => setForm({ ...form, edit_mode: event.target.value })}>
              <option value={FACEBOOK_GROUP_EDIT_MODE_HOOK}>Đọc Hook + giữ tiếng gốc</option>
              <option value={FACEBOOK_GROUP_EDIT_MODE_FULL_AI}>Full AI Script</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Số bài/video mỗi lượt:</label>
            <input type="number" min={1} max={10} className="form-input" value={form.max_videos_per_scan} onChange={event => setForm({ ...form, max_videos_per_scan: Number(event.target.value) || 1 })} />
          </div>
          <div className="form-group">
            <label className="form-label">Max giờ:</label>
            <input type="number" min={0} max={720} className="form-input" value={form.max_video_age_hours} onChange={event => setForm({ ...form, max_video_age_hours: Number(event.target.value) || 0 })} />
          </div>
          <div className="form-group">
            <label className="form-label">Tọa độ Delogo:</label>
            <input className="form-input" placeholder="x=683:y=231:w=280:h=85" value={form.delogo} onChange={event => setForm({ ...form, delogo: event.target.value })} />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
          <button className="btn btn-primary" style={{ flex: 1, justifyContent: 'center' }} onClick={submit}>
            {editingId ? <Save size={18} /> : <Plus size={18} />}
            {editingId ? 'Lưu Group' : 'Thêm Group'}
          </button>
          {editingId && <button className="btn" onClick={reset}><X size={18} /> Hủy</button>}
        </div>
      </div>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3>Nguồn Group đang theo dõi</h3>
          <button className="btn" style={{ background: 'var(--sidebar-bg)' }} onClick={onRefresh}>
            <RefreshCw size={16} /> Làm mới
          </button>
        </div>
        <div style={{ marginTop: '1rem', overflowX: 'auto' }}>
          <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
            <thead><tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th style={{ padding: '0.5rem' }}>Kênh đích</th>
              <th style={{ padding: '0.5rem' }}>Tên Group</th>
              <th style={{ padding: '0.5rem' }}>Chế độ</th>
              <th style={{ padding: '0.5rem' }}>URL</th>
              <th style={{ padding: '0.5rem' }}>Số bài</th>
              <th style={{ padding: '0.5rem' }}>Max giờ</th>
              <th style={{ padding: '0.5rem' }}>Hành động</th>
            </tr></thead>
            <tbody>
              {sources.map(source => (
                <tr key={source.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <td style={{ padding: '0.5rem', fontWeight: 'bold' }}>{source.id_tiktok || DEFAULT_CHANNEL}</td>
                  <td style={{ padding: '0.5rem' }}>{source.source_name}</td>
                  <td style={{ padding: '0.5rem' }}>{source.edit_mode === FACEBOOK_GROUP_EDIT_MODE_HOOK ? 'Hook + tiếng gốc' : 'Full AI'}</td>
                  <td style={{ padding: '0.5rem', color: 'var(--info)' }}>{source.source_url}</td>
                  <td style={{ padding: '0.5rem' }}>{source.max_videos_per_scan ?? 5}</td>
                  <td style={{ padding: '0.5rem' }}>{source.max_video_age_hours ?? 48}</td>
                  <td style={{ padding: '0.5rem', whiteSpace: 'nowrap' }}>
                    <button className="btn" style={{ background: 'transparent', color: 'var(--info)', padding: '0.25rem' }} onClick={() => edit(source)}><Pencil size={16} /></button>
                    <button className="btn" style={{ background: 'transparent', color: 'var(--danger)', padding: '0.25rem' }} onClick={() => remove(source.id)}><Trash2 size={16} /></button>
                  </td>
                </tr>
              ))}
              {sources.length === 0 && <tr><td colSpan={7} style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Chưa có nguồn Group.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
