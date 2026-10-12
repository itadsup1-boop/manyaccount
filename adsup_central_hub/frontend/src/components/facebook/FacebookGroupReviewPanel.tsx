import { Check, RefreshCw, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

type ReviewItem = {
  id: string;
  ai_title?: string;
  caption?: string;
  original_url?: string;
  status?: string;
  review_error?: string;
  preview_url?: string;
  created_at?: string;
  review_payload?: {
    source_name?: string;
    id_tiktok?: string;
    ai_result?: { hook?: string };
  };
};

async function parseResponse(response: Response) {
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.detail || data.error || 'Thao tác thất bại');
  }
  return data;
}

export default function FacebookGroupReviewPanel() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState('');
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const data = await parseResponse(await fetch('/api/facebook/group-review'));
      setItems(Array.isArray(data) ? data : []);
      setError('');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = window.setInterval(refresh, 5000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const approve = async (item: ReviewItem) => {
    setWorkingId(item.id);
    try {
      await parseResponse(await fetch(`/api/facebook/group-review/${item.id}/approve`, {
        method: 'POST'
      }));
      await refresh();
      alert('Đã duyệt: video đã được upload Drive và ghi Google Sheet.');
    } catch (requestError) {
      alert(`Duyệt thất bại: ${requestError instanceof Error ? requestError.message : requestError}`);
      await refresh();
    } finally {
      setWorkingId('');
    }
  };

  const reject = async (item: ReviewItem) => {
    if (!window.confirm('Từ chối video này? File video đã dựng sẽ bị xóa và không thể khôi phục.')) return;
    setWorkingId(item.id);
    try {
      await parseResponse(await fetch(`/api/facebook/group-review/${item.id}/reject`, {
        method: 'POST'
      }));
      await refresh();
    } catch (requestError) {
      alert(`Từ chối thất bại: ${requestError instanceof Error ? requestError.message : requestError}`);
    } finally {
      setWorkingId('');
    }
  };

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
        <div>
          <h3>Video Group chờ duyệt</h3>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.4rem', fontSize: '0.85rem' }}>
            Video trong danh sách này chưa được upload Google Drive hoặc Google Sheet.
          </p>
        </div>
        <button className="btn" onClick={refresh} disabled={loading}>
          <RefreshCw size={16} /> Làm mới
        </button>
      </div>

      {error && <p style={{ color: 'var(--danger)', marginTop: '1rem' }}>Lỗi: {error}</p>}
      {!loading && !error && items.length === 0 && (
        <p style={{ color: 'var(--text-secondary)', padding: '2rem', textAlign: 'center' }}>
          Chưa có video Group nào chờ duyệt.
        </p>
      )}

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', marginTop: '1rem' }}>
        {items.map(item => {
          const payload = item.review_payload || {};
          const busy = workingId === item.id;
          return (
            <div className="card" key={item.id} style={{ border: '1px solid var(--border)' }}>
              {item.preview_url && (
                <video
                  controls
                  preload="metadata"
                  src={item.preview_url}
                  style={{ width: '100%', maxHeight: '480px', borderRadius: '8px', background: '#000' }}
                />
              )}
              <h4 style={{ marginTop: '1rem' }}>{item.ai_title || item.caption || 'Video Facebook Group'}</h4>
              <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem', fontSize: '0.85rem' }}>
                Group: <strong>{payload.source_name || 'Không rõ'}</strong> · Kênh đích: <strong>{payload.id_tiktok || 'Adsupnews'}</strong>
              </p>
              {payload.ai_result?.hook && <p style={{ marginTop: '0.75rem' }}>Hook: {payload.ai_result.hook}</p>}
              {item.status === 'upload_failed' && (
                <p style={{ color: 'var(--danger)', marginTop: '0.75rem' }}>Upload trước đó lỗi: {item.review_error}</p>
              )}
              {item.original_url && <a href={item.original_url} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: '0.75rem', color: 'var(--info)' }}>Mở bài gốc</a>}
              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
                <button className="btn btn-success" disabled={Boolean(workingId)} onClick={() => approve(item)}>
                  <Check size={18} /> {busy ? 'Đang xử lý...' : item.status === 'upload_failed' ? 'Thử duyệt lại' : 'Duyệt & Upload'}
                </button>
                <button className="btn btn-danger" disabled={Boolean(workingId)} onClick={() => reject(item)}>
                  <Trash2 size={18} /> Từ chối & Xóa
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
