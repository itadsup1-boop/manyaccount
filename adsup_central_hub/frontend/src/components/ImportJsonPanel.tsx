import { useState, useEffect, useRef } from 'react';
import { Upload, RefreshCw, FileJson, CheckCircle2, XCircle, Search, Film, Play, Clapperboard, ShieldCheck } from 'lucide-react';

type Issue = { code: string; message: string; field: string; severity: string };

type ImportResult = {
  ok: boolean;
  evidence_gate?: {
    required: boolean;
    passed: boolean;
    high_risk: boolean;
    reason: string;
    unsupported: string[];
  };
  validation: {
    passed: boolean;
    errors: Issue[];
    warnings: Issue[];
    beat_count: number;
    total_hint_seconds: number;
    target_duration_seconds: number;
    duration_deviation: number | null;
    channel_id: string;
  };
  storyboard: {
    timeline_basis: string;
    beat_count: number;
    total_hint_seconds: number;
    target_duration_seconds: number;
    hook: string;
    script_voice: string;
    title_tiktok: string;
    source_url: string;
    music: { mood: string; energy: number; is_sensitive: boolean };
    beats: {
      beat_number: number;
      start_sec: number;
      end_sec: number;
      duration_hint: number;
      role: string;
      voice_over: string;
      on_screen_text: string;
      visual_query: string;
      asset_search_queries?: string[];
      visual_brief?: string;
      required_country?: string;
      country_strict?: boolean;
      must_show: string[];
      estimated_voice_seconds: number;
    }[];
  };
  job_id: string | null;
  created: boolean;
};

type JobMeta = {
  job_id: string;
  status: string;
  channel_id: string;
  source_url: string;
  beat_count: number;
  passed: boolean;
  operator_approved?: boolean;
  created_at: string;
};

type MediaPlanBeat = {
  beat_number: number;
  kind: string;
  visual_query: string;
  search_query: string;
  media_type: string | null;
  candidates_evaluated: number;
  selected: {
    provider_asset_id: string;
    page_url: string;
    relevance_score: number;
    description?: string;
    width?: number;
    height?: number;
    country?: string | null;
    country_verification?: string;
    city?: string | null;
  } | null;
  reason: string;
  asset_id?: string;
};

type MediaPlan = {
  plan_version: string;
  job_id: string;
  status: string;
  beats: MediaPlanBeat[];
  summary: {
    total_beats: number;
    broll: number;
    data_graphic: number;
    map_graphic: number;
    no_asset_found: number;
    assets_downloaded: number;
  };
};

const PLAN_STATUS_LABEL: Record<string, string> = {
  ready: 'Đủ tư liệu — sẵn sàng dựng',
  partial: 'Thiếu B-roll — cảnh thiếu sẽ dùng graphic fallback',
  graphics_only: 'Không có B-roll — đã chặn dựng để tránh video toàn chữ',
};

const REASON_LABEL: Record<string, string> = {
  empty_visual_query: 'Beat thiếu visual_query',
  no_candidates: 'Pexels không trả kết quả cho query',
  below_threshold: 'Không ứng viên nào đủ liên quan (ngưỡng 0.3)',
  below_technical_requirement: 'Ứng viên không đủ phân giải crop 1080×1920',
  usage_cap_reached: 'Asset đã dùng đủ 2 lần trong video',
  download_failed: 'Tải asset thất bại',
  country_unverified: 'Không xác minh được quốc gia theo yêu cầu',
};

const KIND_STYLE: Record<string, { label: string; color: string }> = {
  broll: { label: 'B-roll', color: 'var(--success)' },
  data_graphic: { label: 'Data graphic', color: '#60a5fa' },
  map_graphic: { label: 'Map graphic', color: '#60a5fa' },
  no_asset_found: { label: 'Không có asset', color: 'var(--danger)' },
};

const SAMPLE_HINT = `{
  "schema_version": 1,
  "id_tiktok": "Adsupnews",
  "hook": "Con số này khiến cả thị trường bất ngờ.",
  "script_voice": "Nội dung voice chính của video...",
  "beats": [
    {
      "beat_number": 1,
      "role": "hook",
      "duration_hint": 2.0,
      "voice_over": "...",
      "visual_query": "...",
      "on_screen_text": "...",
      "must_show": []
    }
  ]
}`;

export default function ImportJsonPanel({ channels }: { channels: string[] }) {
  const [jsonText, setJsonText] = useState('');
  const [channel, setChannel] = useState('');
  const [busy, setBusy] = useState<'' | 'validate' | 'import'>('');
  const [result, setResult] = useState<ImportResult | null>(null);
  const [parseError, setParseError] = useState('');
  const [jobs, setJobs] = useState<JobMeta[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState('');
  const [planBusy, setPlanBusy] = useState('');
  const [planError, setPlanError] = useState('');
  const [mediaPlan, setMediaPlan] = useState<MediaPlan | null>(null);
  const [renderBusy, setRenderBusy] = useState('');
  const [renderError, setRenderError] = useState('');
  const [renderMeta, setRenderMeta] = useState<{
    mode: string;
    segment_count: number;
    total_planned_seconds: number;
    probe: { width: number; height: number; codec: string; fps: number; duration: number; size_bytes: number };
    warnings: string[];
    preview_url: string;
  } | null>(null);
  const [finalBusy, setFinalBusy] = useState('');
  const [finalError, setFinalError] = useState('');
  const [finalMeta, setFinalMeta] = useState<{
    mode: string;
    segment_count: number;
    voice: { hook_duration: number; script_duration: number; total_duration: number };
    bgm: { track_id: string; mood: string; license_status: string } | null;
    subtitle: { engine: string; path: string | null };
    sfx_count: number;
    probe: { width: number; height: number; codec: string; fps: number; duration: number; size_bytes: number };
    video_qa: {
      passed: boolean; blocking_errors: string[]; warnings: string[];
      integrated_lufs: number | null; duration: number;
    } | null;
    warnings: string[];
    final_url: string;
  } | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const loadJobs = () => {
    setJobsLoading(true);
    fetch('/api/article/production-jobs?limit=50')
      .then(res => res.json())
      .then(data => setJobs(data.items || []))
      .catch(console.error)
      .finally(() => setJobsLoading(false));
  };

  useEffect(() => {
    loadJobs();
  }, []);

  const parseDoc = (): any | null => {
    setParseError('');
    if (!jsonText.trim()) {
      setParseError('Chưa dán JSON nào.');
      return null;
    }
    try {
      const doc = JSON.parse(jsonText);
      if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
        setParseError('JSON gốc phải là một object (bắt đầu bằng { ).');
        return null;
      }
      return doc;
    } catch (err: any) {
      setParseError(`JSON không đọc được: ${err.message}`);
      return null;
    }
  };

  const send = (dryRun: boolean) => {
    const doc = parseDoc();
    if (!doc) return;
    setBusy(dryRun ? 'validate' : 'import');
    setPlanError('');
    setMediaPlan(null);
    setRenderError('');
    setRenderMeta(null);
    setFinalError('');
    setFinalMeta(null);
    const params = new URLSearchParams({ dry_run: String(dryRun) });
    if (channel) params.set('channel_id', channel);
    fetch(`/api/article/import-production-json?${params.toString()}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(doc),
    })
      .then(async res => {
        const data = await res.json();
        setResult(data);
        if (!dryRun && res.ok && data.job_id) loadJobs();
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
      })
      .catch(err => setParseError(`Lỗi kết nối API: ${err.message}`))
      .finally(() => setBusy(''));
  };

  const openJob = (jobId: string) => {
    setDetailLoading(jobId);
    setPlanError('');
    setMediaPlan(null);
    setRenderError('');
    setRenderMeta(null);
    setFinalError('');
    setFinalMeta(null);
    fetch(`/api/article/production-jobs/${jobId}`)
      .then(res => res.json())
      .then(data => {
        if (data.job) {
          setResult({
            ok: data.validation?.passed ?? false,
            validation: data.validation || {},
            storyboard: data.storyboard || {},
            job_id: jobId,
            created: false,
          });
          setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
        }
      })
      .catch(console.error)
      .finally(() => setDetailLoading(''));
  };

  const runMediaPlan = (jobId: string) => {
    setPlanBusy(jobId);
    setPlanError('');
    setRenderError('');
    setRenderMeta(null);
    setFinalError('');
    setFinalMeta(null);
    fetch(`/api/article/production-jobs/${jobId}/media-plan`, { method: 'POST' })
      .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          setPlanError(typeof data?.detail === 'string' ? data.detail : `Lỗi API ${res.status}`);
          return;
        }
        setMediaPlan(data.plan || null);
        loadJobs();
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
      })
      .catch(err => setPlanError(`Lỗi kết nối API: ${err.message}`))
      .finally(() => setPlanBusy(''));
  };

  const runRenderPreview = (jobId: string) => {
    setRenderBusy(jobId);
    setRenderError('');
    setRenderMeta(null);
    setFinalError('');
    setFinalMeta(null);
    fetch(`/api/article/production-jobs/${jobId}/render-preview`, { method: 'POST' })
      .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          setRenderError(typeof data?.detail === 'string' ? data.detail : `Lỗi API ${res.status}`);
          return;
        }
        setRenderMeta(data);
        loadJobs();
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
      })
      .catch(err => setRenderError(`Lỗi kết nối API: ${err.message}`))
      .finally(() => setRenderBusy(''));
  };

  const runRenderFinal = (jobId: string) => {
    setFinalBusy(jobId);
    setFinalError('');
    setFinalMeta(null);
    fetch(`/api/article/production-jobs/${jobId}/render-final`, { method: 'POST' })
      .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          setFinalError(typeof data?.detail === 'string' ? data.detail : `Lỗi API ${res.status}`);
          return;
        }
        setFinalMeta(data);
        loadJobs();
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
      })
      .catch(err => setFinalError(`Lỗi kết nối API: ${err.message}`))
      .finally(() => setFinalBusy(''));
  };

  const statusColor = (status: string) => {
    if (status === 'blocked' || status === 'qa_failed') return 'var(--danger)';
    if (status === 'needs_review' || status === 'assets_partial') return '#eab308';
    if (status === 'imported') return 'var(--text-secondary)';
    return 'var(--success)';
  };

  const jobLocked = (job: JobMeta) =>
    !job.passed || (job.status === 'needs_review' && !job.operator_approved);

  const approveJob = (jobId: string) => {
    setDetailLoading(jobId);
    fetch(`/api/article/production-jobs/${jobId}/approve`, { method: 'POST' })
      .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          setFinalError(typeof data?.detail === 'string' ? data.detail : `Lỗi API ${res.status}`);
          return;
        }
        loadJobs();
      })
      .catch(err => setFinalError(`Lỗi kết nối API: ${err.message}`))
      .finally(() => setDetailLoading(''));
  };

  const validation = result?.validation;
  const evidence_gate = result?.evidence_gate;
  const storyboard = result?.storyboard;
  const allIssues = [...(validation?.errors || []), ...(validation?.warnings || [])];
  const planHasNoRealMedia = mediaPlan?.status === 'graphics_only';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <div className="card">
        <h3>📥 Import JSON kịch bản khoá</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem', fontSize: '0.85rem' }}>
          Dán JSON v1 do ChatGPT/Gemini trả về (schema_version: 1, 7-9 beats). JSON sai schema sẽ bị
          chặn trước khi dựng — không có bước gọi lại AI; hãy sửa JSON rồi import lại.
        </p>

        <div className="form-row" style={{ marginTop: '1rem' }}>
          <div className="form-group">
            <label className="form-label">Kênh (để đối chiếu hồ sơ độ dài):</label>
            <select className="form-select" value={channel} onChange={e => setChannel(e.target.value)}>
              <option value="">-- Lấy từ JSON / không chọn --</option>
              {channels.map(ch => <option key={ch} value={ch}>{ch}</option>)}
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Nội dung JSON:</label>
          <textarea
            className="form-input"
            style={{ minHeight: '320px', fontFamily: 'monospace', fontSize: '0.82rem', lineHeight: '1.5', resize: 'vertical' }}
            value={jsonText}
            onChange={e => setJsonText(e.target.value)}
            placeholder={`Dán JSON vào đây...\nVí dụ cấu trúc:\n${SAMPLE_HINT}`}
          />
        </div>

        {parseError && (
          <div style={{ color: 'var(--danger)', marginBottom: '0.75rem', fontSize: '0.85rem' }}>
            {parseError}
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button className="btn btn-ghost" onClick={() => send(true)} disabled={busy !== ''}>
            <Search size={18} /> {busy === 'validate' ? 'Đang kiểm tra...' : 'Chỉ kiểm tra'}
          </button>
          <button className="btn btn-primary" onClick={() => send(false)} disabled={busy !== ''}>
            <Upload size={18} /> {busy === 'import' ? 'Đang nhập...' : 'Nhập & tạo job'}
          </button>
        </div>
      </div>

      {result && (
        <div className="card" ref={resultRef}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
              {result.ok ? (
                <CheckCircle2 size={22} color="var(--success)" />
              ) : (
                <XCircle size={22} color="var(--danger)" />
              )}
              {result.ok ? 'JSON hợp lệ' : 'JSON bị chặn'}
            </h3>
            {result.job_id && (
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Job: <strong>{result.job_id}</strong>
                {result.created ? ' (mới)' : ' (đã tồn tại)'}
              </span>
            )}
          </div>

          {validation && (
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '0.5rem' }}>
              {validation.beat_count} beats · tổng duration_hint{' '}
              <strong>{validation.total_hint_seconds}s</strong> · mục tiêu{' '}
              <strong>{validation.target_duration_seconds}s</strong>
              {validation.duration_deviation !== null &&
                ` · lệch ${(validation.duration_deviation * 100).toFixed(0)}%`}
              {validation.channel_id && ` · kênh ${validation.channel_id}`}
            </p>
          )}

          {allIssues.length > 0 && (
            <div style={{ marginTop: '1rem', overflowX: 'auto' }}>
              <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <th style={{ padding: '0.5rem' }}>Mức</th>
                    <th style={{ padding: '0.5rem' }}>Mã</th>
                    <th style={{ padding: '0.5rem' }}>Trường</th>
                    <th style={{ padding: '0.5rem' }}>Mô tả</th>
                  </tr>
                </thead>
                <tbody>
                  {allIssues.map((issue, idx) => (
                    <tr key={`${issue.code}-${idx}`} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '0.5rem', color: issue.severity === 'error' ? 'var(--danger)' : '#eab308', fontWeight: 700 }}>
                        {issue.severity === 'error' ? 'Lỗi' : 'Cảnh báo'}
                      </td>
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{issue.code}</td>
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace', wordBreak: 'break-all' }}>{issue.field}</td>
                      <td style={{ padding: '0.5rem' }}>{issue.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {evidence_gate && !evidence_gate.passed && (
            <div style={{ marginTop: '0.85rem', border: '1px solid #eab308', borderRadius: 8, padding: '0.75rem 1rem', fontSize: '0.82rem' }}>
              <strong style={{ color: '#eab308' }}>
                ⚠️ Evidence gate: {evidence_gate.reason === 'EVIDENCE_MISSING'
                  ? 'thiếu source_text'
                  : 'số liệu không khớp source_text'}
                {evidence_gate.high_risk ? ' · kênh rủi ro cao' : ''}
              </strong>
              <p style={{ margin: '0.35rem 0 0.35rem', color: 'var(--text-secondary)' }}>
                Job vào hàng chờ duyệt — tự kiểm tra nguồn rồi bấm "Duyệt" ở bảng job bên dưới.
              </p>
              {evidence_gate.unsupported?.length > 0 && (
                <ul style={{ margin: 0, paddingLeft: '1.2rem', color: 'var(--text-secondary)' }}>
                  {evidence_gate.unsupported.slice(0, 4).map((claim, i) => <li key={i}>{claim}</li>)}
                </ul>
              )}
            </div>
          )}
          {evidence_gate && evidence_gate.passed && evidence_gate.required && (
            <p style={{ marginTop: '0.85rem', color: 'var(--success)', fontSize: '0.82rem' }}>
              ✅ Evidence gate: số liệu trong kịch bản khớp source_text.
            </p>
          )}

          {storyboard && storyboard.beats && storyboard.beats.length > 0 && (
            <div style={{ marginTop: '1.25rem' }}>
              <h4 style={{ marginBottom: '0.5rem' }}>🎬 Storyboard preview (timeline từ duration_hint, chưa tính TTS thật)</h4>
              {storyboard.hook && (
                <p style={{ fontSize: '0.85rem', marginBottom: '0.75rem' }}>
                  <strong>Hook:</strong> {storyboard.hook}
                </p>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {storyboard.beats.map(beat => (
                  <div
                    key={beat.beat_number}
                    style={{
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      padding: '0.6rem 0.85rem',
                      display: 'flex',
                      gap: '0.85rem',
                      alignItems: 'flex-start',
                    }}
                  >
                    <div style={{ minWidth: 92, color: 'var(--text-secondary)', fontSize: '0.78rem', fontFamily: 'monospace', paddingTop: 2 }}>
                      #{beat.beat_number}
                      <br />
                      {beat.start_sec}s → {beat.end_sec}s
                    </div>
                    <div style={{ flex: 1, fontSize: '0.85rem' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                        {beat.role && (
                          <span style={{ fontSize: '0.7rem', border: '1px solid var(--border)', borderRadius: 6, padding: '1px 6px', color: 'var(--text-secondary)' }}>
                            {beat.role}
                          </span>
                        )}
                        {beat.on_screen_text && <strong>{beat.on_screen_text}</strong>}
                      </div>
                      {beat.voice_over && (
                        <div style={{ color: 'var(--text-secondary)', marginTop: '0.2rem' }}>🎙️ {beat.voice_over}</div>
                      )}
                      {beat.visual_query && (
                        <div style={{ color: 'var(--text-secondary)', marginTop: '0.2rem', fontStyle: 'italic' }}>
                          🖼️ {beat.visual_query}
                        </div>
                      )}
                      {beat.asset_search_queries && beat.asset_search_queries.length > 0 && (
                        <div style={{ color: 'var(--text-secondary)', marginTop: '0.2rem', fontSize: '0.78rem' }}>
                          🔎 {beat.asset_search_queries.join(' · ')}
                        </div>
                      )}
                      {beat.visual_brief && (
                        <div style={{ color: 'var(--text-secondary)', marginTop: '0.2rem', fontSize: '0.8rem' }}>
                          📐 {beat.visual_brief}
                        </div>
                      )}
                      {beat.required_country && (
                        <div style={{ color: beat.country_strict ? '#eab308' : 'var(--text-secondary)', marginTop: '0.2rem', fontSize: '0.78rem' }}>
                          🌏 {beat.country_strict ? 'Chỉ nhận asset đã xác minh tại' : 'Ưu tiên'}: {beat.required_country}
                        </div>
                      )}
                      {beat.must_show?.length > 0 && (
                        <div style={{ marginTop: '0.25rem', display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                          {beat.must_show.map((item, i) => (
                            <span key={i} style={{ fontSize: '0.72rem', border: '1px solid var(--border)', borderRadius: 6, padding: '1px 6px' }}>
                              {item}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {planError && (
            <div style={{ marginTop: '1rem', color: 'var(--danger)', fontSize: '0.85rem' }}>
              ⚠️ {planError}
            </div>
          )}

          {mediaPlan && (
            <div style={{ marginTop: '1.25rem', border: '1px solid var(--border)', borderRadius: 8, padding: '0.85rem 1rem' }}>
              <h4 style={{ margin: 0, marginBottom: '0.25rem' }}>🎞️ Kết quả tìm tư liệu</h4>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', margin: '0 0 0.75rem' }}>
                {PLAN_STATUS_LABEL[mediaPlan.status] || mediaPlan.status} · {mediaPlan.summary.assets_downloaded} asset đã tải về
                {' '}({mediaPlan.summary.broll} B-roll · {mediaPlan.summary.data_graphic} data · {mediaPlan.summary.map_graphic} map · {mediaPlan.summary.no_asset_found} thiếu)
              </p>
              {planHasNoRealMedia && (
                <div style={{ marginBottom: '0.75rem', border: '1px solid #eab308', borderRadius: 6, padding: '0.6rem 0.75rem', fontSize: '0.8rem', color: '#eab308' }}>
                  ⚠️ Chưa dựng được: JSON đang chỉ định toàn DATA/FACT graphic. Hãy sửa ít nhất 3 `visual_query` thành B-roll tiếng Anh, kiểm tra Pexels, rồi bấm “Tìm tư liệu” lại.
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {mediaPlan.beats.map(beat => {
                  const kindStyle = KIND_STYLE[beat.kind] || { label: beat.kind, color: 'var(--text-secondary)' };
                  const reason =
                    beat.reason && beat.reason !== 'graphic_fallback_per_brief'
                      ? beat.reason.startsWith('search_error:')
                        ? `Lỗi tìm kiếm: ${beat.reason.slice('search_error:'.length).trim()}`
                        : REASON_LABEL[beat.reason] || beat.reason
                      : '';
                  return (
                    <div key={beat.beat_number} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start', fontSize: '0.82rem' }}>
                      <span style={{ fontFamily: 'monospace', color: 'var(--text-secondary)', minWidth: 28, paddingTop: 2 }}>
                        #{beat.beat_number}
                      </span>
                      <span
                        style={{
                          color: kindStyle.color, fontWeight: 700, fontSize: '0.72rem',
                          border: `1px solid ${kindStyle.color}`, borderRadius: 6,
                          padding: '1px 6px', minWidth: 96, textAlign: 'center', alignSelf: 'center',
                        }}
                      >
                        {kindStyle.label}
                      </span>
                      <div style={{ flex: 1 }}>
                        {beat.selected ? (
                          <>
                            <div>
                              <strong>{beat.selected.provider_asset_id}</strong>
                              {' '}· liên quan {(beat.selected.relevance_score * 100).toFixed(0)}%
                              {' '}· {beat.selected.country && beat.selected.country_verification === 'provider_metadata'
                                ? `địa điểm xác minh: ${beat.selected.city ? `${beat.selected.city}, ` : ''}${beat.selected.country}`
                                : 'quốc gia chưa xác minh'}
                              {beat.asset_id && (
                                <span style={{ color: 'var(--text-secondary)' }}> · đã tải về: assets/</span>
                              )}
                            </div>
                            <a
                              href={beat.selected.page_url}
                              target="_blank"
                              rel="noreferrer"
                              style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', wordBreak: 'break-all' }}
                            >
                              {beat.selected.page_url}
                            </a>
                          </>
                        ) : (
                          <div style={{ color: 'var(--text-secondary)' }}>
                            {beat.kind === 'data_graphic' || beat.kind === 'map_graphic' ? (
                              <>Dựng đồ hoạ từ: <em>{beat.search_query}</em></>
                            ) : (
                              reason || 'Không chọn được asset — renderer sẽ dựng graphic fallback'
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {renderError && (
            <div style={{ marginTop: '0.75rem', color: 'var(--danger)', fontSize: '0.85rem' }}>
              ⚠️ {renderError}
            </div>
          )}

          {renderMeta && (
            <div style={{ marginTop: '1rem', border: '1px solid var(--border)', borderRadius: 8, padding: '0.85rem 1rem' }}>
              <h4 style={{ margin: 0, marginBottom: '0.35rem' }}>🎥 Preview đã render (chưa có voice)</h4>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', margin: '0 0 0.6rem' }}>
                {renderMeta.segment_count} cảnh · kế hoạch {renderMeta.total_planned_seconds}s · thật{' '}
                {renderMeta.probe.duration}s · {renderMeta.probe.width}×{renderMeta.probe.height} ·{' '}
                {renderMeta.probe.codec} {renderMeta.probe.fps}fps ·{' '}
                {(renderMeta.probe.size_bytes / 1024 / 1024).toFixed(1)} MB
              </p>
              {renderMeta.warnings?.length > 0 && (
                <ul style={{ color: '#eab308', fontSize: '0.78rem', margin: '0 0 0.6rem', paddingLeft: '1.2rem' }}>
                  {renderMeta.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
              <a
                href={renderMeta.preview_url}
                target="_blank"
                rel="noreferrer"
                className="btn btn-ghost"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', textDecoration: 'none' }}
              >
                <Play size={18} /> ▶ Xem / tải preview.mp4
              </a>
            </div>
          )}

          {finalError && (
            <div style={{ marginTop: '0.75rem', color: 'var(--danger)', fontSize: '0.85rem' }}>
              ⚠️ {finalError}
            </div>
          )}

          {finalMeta && (
            <div style={{ marginTop: '1rem', border: '1px solid var(--border)', borderRadius: 8, padding: '0.85rem 1rem' }}>
              <h4 style={{ margin: 0, marginBottom: '0.35rem' }}>🎬 Video hoàn chỉnh (voice + phụ đề + BGM)</h4>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', margin: '0 0 0.6rem' }}>
                Voice: hook {finalMeta.voice.hook_duration}s + script {finalMeta.voice.script_duration}s ={' '}
                {finalMeta.voice.total_duration}s · phụ đề {finalMeta.subtitle.engine} · BGM{' '}
                {finalMeta.bgm ? `${finalMeta.bgm.track_id} (${finalMeta.bgm.mood}, ${finalMeta.bgm.license_status})` : 'không dùng'} ·{' '}
                {finalMeta.sfx_count} SFX · {finalMeta.segment_count} cảnh ·{' '}
                {finalMeta.probe.width}×{finalMeta.probe.height} · {finalMeta.probe.codec} {finalMeta.probe.fps}fps ·{' '}
                {(finalMeta.probe.size_bytes / 1024 / 1024).toFixed(1)} MB
              </p>
              {finalMeta.video_qa && (
                <p style={{
                  fontSize: '0.8rem', margin: '0 0 0.6rem', fontWeight: 700,
                  color: finalMeta.video_qa.passed ? 'var(--success, #22c55e)' : 'var(--danger)',
                }}>
                  {finalMeta.video_qa.passed ? '✅ VideoQA: ĐẠT' : `❌ VideoQA: KHÔNG ĐẠT — ${finalMeta.video_qa.blocking_errors.join(', ')}`}
                  {finalMeta.video_qa.integrated_lufs != null && ` · ${Math.round(finalMeta.video_qa.integrated_lufs)} LUFS`}
                  {finalMeta.video_qa.warnings.length > 0 && ` · cảnh báo: ${finalMeta.video_qa.warnings.join(', ')}`}
                </p>
              )}
              {finalMeta.warnings?.length > 0 && (
                <ul style={{ color: '#eab308', fontSize: '0.78rem', margin: '0 0 0.6rem', paddingLeft: '1.2rem' }}>
                  {finalMeta.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
              <a
                href={finalMeta.final_url}
                target="_blank"
                rel="noreferrer"
                className="btn btn-ghost"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', textDecoration: 'none' }}
              >
                <Play size={18} /> ▶ Xem / tải final.mp4
              </a>
            </div>
          )}

          {result.job_id && (
            <div style={{ marginTop: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
              <button
                className="btn btn-ghost"
                onClick={() => result.job_id && runMediaPlan(result.job_id)}
                disabled={planBusy !== '' || result.ok === false}
                title={result.ok ? undefined : 'Job bị chặn bởi validation — sửa JSON rồi import lại'}
              >
                <Search size={18} /> {planBusy ? 'Đang tìm tư liệu...' : 'Tìm tư liệu (Pexels)'}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => result.job_id && runRenderPreview(result.job_id)}
                disabled={renderBusy !== '' || finalBusy !== '' || result.ok === false || planHasNoRealMedia}
                title={planHasNoRealMedia ? 'Cần B-roll thật trước khi render' : result.ok ? 'Render preview không voice để xem trước bố cục' : 'Job bị chặn bởi validation — sửa JSON rồi import lại'}
              >
                <Film size={18} /> {renderBusy ? 'Đang render (1-3 phút)...' : 'Render thử (không voice)'}
              </button>
              <button
                className="btn btn-primary"
                onClick={() => result.job_id && runRenderFinal(result.job_id)}
                disabled={finalBusy !== '' || renderBusy !== '' || result.ok === false || planHasNoRealMedia}
                title={planHasNoRealMedia ? 'Cần B-roll thật trước khi dựng video' : 'Sinh voice TTS + phụ đề + BGM rồi dựng final.mp4 (vài phút)'}
              >
                <Clapperboard size={18} /> {finalBusy ? 'Đang dựng video (2-4 phút)...' : 'Dựng video'}
              </button>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                "Dựng video" gọi TTS voice.adsup.vn thật (không rút gọn câu), "Render thử" chỉ xem nhanh bố cục không voice.
              </span>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3>🗂️ Production jobs</h3>
          <button className="btn btn-ghost" onClick={loadJobs}>
            <RefreshCw size={16} /> Làm mới
          </button>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '0.35rem' }}>
          Job do pipeline tự lưu sau khi ChatGPT trả JSON, hoặc do bạn nhập tay ở trên. Cùng một JSON
          + cùng kênh luôn là một job (không trùng).
        </p>
        <div style={{ marginTop: '1rem', overflowX: 'auto' }}>
          <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '0.65rem' }}>Job</th>
                <th style={{ padding: '0.65rem' }}>Kênh</th>
                <th style={{ padding: '0.65rem' }}>Trạng thái</th>
                <th style={{ padding: '0.65rem', width: 70 }}>Beats</th>
                <th style={{ padding: '0.65rem' }}>Nguồn</th>
                <th style={{ padding: '0.65rem', width: 150 }}>Tạo lúc</th>
                <th style={{ padding: '0.65rem', width: 140 }}>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <tr key={job.job_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <td style={{ padding: '0.65rem', fontFamily: 'monospace', fontSize: '0.78rem' }}>{job.job_id}</td>
                  <td style={{ padding: '0.65rem' }}>{job.channel_id || '-'}</td>
                  <td style={{ padding: '0.65rem', color: statusColor(job.status), fontWeight: 600 }}>
                    {job.status}
                  </td>
                  <td style={{ padding: '0.65rem' }}>{job.beat_count}</td>
                  <td style={{ padding: '0.65rem', wordBreak: 'break-all', color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                    {job.source_url || '-'}
                  </td>
                  <td style={{ padding: '0.65rem', color: 'var(--text-secondary)' }}>
                    {job.created_at ? new Date(job.created_at).toLocaleString('vi-VN') : '-'}
                  </td>
                  <td style={{ padding: '0.65rem' }}>
                    <div style={{ display: 'flex', gap: '0.25rem' }}>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: '0.35rem 0.55rem' }}
                        onClick={() => openJob(job.job_id)}
                        disabled={detailLoading === job.job_id}
                        title="Xem storyboard"
                      >
                        <FileJson size={16} />
                      </button>
                      {job.status === 'needs_review' && !job.operator_approved && (
                        <button
                          className="btn btn-ghost"
                          style={{ padding: '0.35rem 0.55rem', color: '#eab308' }}
                          onClick={() => approveJob(job.job_id)}
                          disabled={detailLoading === job.job_id}
                          title="Duyệt job (tự kiểm tra evidence bằng tay xong mới bấm)"
                        >
                          <ShieldCheck size={16} />
                        </button>
                      )}
                      <button
                        className="btn btn-ghost"
                        style={{ padding: '0.35rem 0.55rem' }}
                        onClick={() => runMediaPlan(job.job_id)}
                        disabled={planBusy === job.job_id || jobLocked(job)}
                        title={job.passed ? 'Tìm tư liệu Pexels cho từng beat' : 'Job bị chặn bởi validation'}
                      >
                        <Search size={16} />
                      </button>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: '0.35rem 0.55rem' }}
                        onClick={() => runRenderPreview(job.job_id)}
                        disabled={renderBusy === job.job_id || finalBusy !== '' || jobLocked(job) || job.status === 'graphics_only'}
                        title={job.status === 'graphics_only' ? 'Cần tìm được B-roll thật trước khi render' : job.passed ? 'Render preview không voice' : 'Job bị chặn bởi validation'}
                      >
                        <Film size={16} />
                      </button>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: '0.35rem 0.55rem' }}
                        onClick={() => runRenderFinal(job.job_id)}
                        disabled={finalBusy === job.job_id || renderBusy !== '' || jobLocked(job) || job.status === 'graphics_only'}
                        title={job.status === 'graphics_only' ? 'Cần tìm được B-roll thật trước khi dựng video' : job.passed ? 'Dựng video hoàn chỉnh (TTS + phụ đề + BGM)' : 'Job bị chặn bởi validation'}
                      >
                        <Clapperboard size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!jobsLoading && jobs.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    Chưa có job nào.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
