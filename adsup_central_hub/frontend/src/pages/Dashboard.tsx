import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, FormEvent, ReactNode } from 'react';
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock3,
  Eye,
  Filter,
  RefreshCw,
  Save,
  Share2,
  TrendingUp,
  UserPlus,
  Video,
} from 'lucide-react';

import '../features/dashboard/dashboard.css';
import '../features/tiktok/tiktok.css';

type Summary = {
  sample_size: number;
  total_views: number;
  median_views: number;
  median_average_watch_time: number;
  median_watch_percentage: number;
  weighted_average_watch_time: number;
  weighted_watch_percentage: number;
  median_watched_full_rate: number;
  median_retention_2s: number;
  median_retention_6s: number;
  median_retention_drop_2s_to_6s: number;
  likes_per_1000: number;
  comments_per_1000: number;
  shares_per_1000: number;
  saves_per_1000: number;
  follows_per_1000: number;
  engagements_per_1000: number;
  measured_from: string;
  measured_to: string;
  data_quality?: {
    with_duration: number;
    with_watch_time: number;
    watch_time_view_coverage: number;
    with_completion: number;
    with_retention_2s: number;
    with_retention_6s: number;
  };
  eligible?: boolean;
};

type BreakdownRow = Summary & {
  value: string;
  eligible: boolean;
};

type CountRow = {
  value: string;
  count: number;
};

type PipelineFailure = {
  ts: string;
  pipeline: string;
  channel_id: string;
  stage: string;
  error_code: string;
  retryable: boolean;
  message: string;
  item_id: string;
};

type TopVideo = Summary & {
  video_id: string;
  channel_id: string;
  title: string;
  story_type: string;
  hook_type: string;
  duration_bucket: string;
  music_mood: string;
  views: number;
  source_url: string;
};

type TrendRow = Summary & {
  date: string;
};

type DashboardPayload = {
  status: 'ready' | 'insufficient_sample' | 'empty';
  generated_at: string;
  filters: DashboardFilters & { timezone: string };
  available_filters: {
    channels: string[];
    measurement_windows: string[];
  };
  overview: Summary;
  breakdowns: Record<string, BreakdownRow[]>;
  trends: TrendRow[];
  top_videos: TopVideo[];
  data_quality: {
    snapshot_count: number;
    latest_video_count: number;
    anomaly_count: number;
    malformed_quality_lines: number;
  };
  pipeline: {
    total_events: number;
    status_counts: CountRow[];
    stage_counts: CountRow[];
    successful_items_by_pipeline: CountRow[];
    failures: {
      total: number;
      by_stage: CountRow[];
      by_error_code: CountRow[];
      recent: PipelineFailure[];
    };
  };
  system_health: 'healthy' | 'attention' | 'empty';
};

type DashboardFilters = {
  start_date: string;
  end_date: string;
  channel_id: string;
  measurement_window: string;
  min_samples: number;
};

type BreakdownKey = 'channel_id' | 'story_type' | 'hook_type' | 'duration' | 'music_mood';
type MetricKey =
  | 'median_watch_percentage'
  | 'weighted_watch_percentage'
  | 'median_watched_full_rate'
  | 'median_retention_2s'
  | 'median_retention_6s'
  | 'median_retention_drop_2s_to_6s'
  | 'shares_per_1000'
  | 'saves_per_1000'
  | 'follows_per_1000';

const INITIAL_FILTERS: DashboardFilters = {
  start_date: '',
  end_date: '',
  channel_id: '',
  measurement_window: '',
  min_samples: 30,
};

const BREAKDOWN_LABELS: Record<BreakdownKey, string> = {
  channel_id: 'Kênh',
  story_type: 'Kiểu nội dung',
  hook_type: 'Kiểu hook',
  duration: 'Thời lượng',
  music_mood: 'Mood nhạc',
};

const METRIC_LABELS: Record<MetricKey, string> = {
  median_watch_percentage: 'Tỷ lệ thời gian xem',
  weighted_watch_percentage: 'Tỷ lệ xem có trọng số view',
  median_watched_full_rate: 'Tỷ lệ xem hết',
  median_retention_2s: 'Giữ chân 2 giây',
  median_retention_6s: 'Giữ chân 6 giây',
  median_retention_drop_2s_to_6s: 'Rơi retention 2s → 6s',
  shares_per_1000: 'Chia sẻ / 1.000 view',
  saves_per_1000: 'Lưu / 1.000 view',
  follows_per_1000: 'Follow / 1.000 view',
};

const PERCENT_METRICS = new Set<MetricKey>([
  'median_watch_percentage',
  'weighted_watch_percentage',
  'median_watched_full_rate',
  'median_retention_2s',
  'median_retention_6s',
]);
const LOWER_IS_BETTER_METRICS = new Set<MetricKey>([
  'median_retention_drop_2s_to_6s',
]);

const integerFormatter = new Intl.NumberFormat('vi-VN');
const decimalFormatter = new Intl.NumberFormat('vi-VN', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatInteger(value: number) {
  return integerFormatter.format(Number.isFinite(value) ? value : 0);
}

function formatMetric(value: number, metric: MetricKey) {
  const suffix = metric === 'median_retention_drop_2s_to_6s'
    ? ' điểm'
    : PERCENT_METRICS.has(metric) ? '%' : '';
  return `${decimalFormatter.format(Number.isFinite(value) ? value : 0)}${suffix}`;
}

function formatTimestamp(value: string) {
  if (!value) return 'Chưa có';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat('vi-VN', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(parsed);
}

function KpiCard({
  icon,
  label,
  value,
  note,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  note: string;
  tone: string;
}) {
  return (
    <article className={`dashboard-kpi dashboard-kpi--${tone}`}>
      <div className="dashboard-kpi__header">
        <span className="dashboard-kpi__icon" aria-hidden="true">{icon}</span>
        <span className="dashboard-kpi__label">{label}</span>
      </div>
      <strong className="dashboard-kpi__value">{value}</strong>
      <span className="dashboard-kpi__note">{note}</span>
    </article>
  );
}

export default function Dashboard() {
  const [draftFilters, setDraftFilters] = useState<DashboardFilters>(INITIAL_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<DashboardFilters>(INITIAL_FILTERS);
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [breakdownKey, setBreakdownKey] = useState<BreakdownKey>('story_type');
  const [metricKey, setMetricKey] = useState<MetricKey>('median_watch_percentage');

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams();
    Object.entries(appliedFilters).forEach(([key, value]) => {
      if (value !== '') params.set(key, String(value));
    });

    setLoading(true);
    setError('');
    fetch(`/api/dashboard/performance?${params.toString()}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.ok) return response.json() as Promise<DashboardPayload>;
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `HTTP ${response.status}`);
      })
      .then(setData)
      .catch((requestError: Error) => {
        if (requestError.name !== 'AbortError') {
          setError(`Không tải được dữ liệu: ${requestError.message}`);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [appliedFilters, refreshKey]);

  const comparisonRows = useMemo(() => {
    const rows = data?.breakdowns[breakdownKey] || [];
    const direction = LOWER_IS_BETTER_METRICS.has(metricKey) ? 1 : -1;
    return [...rows]
      .sort((left, right) => direction * (left[metricKey] - right[metricKey]))
      .slice(0, 10);
  }, [breakdownKey, data, metricKey]);

  const comparisonMax = Math.max(
    1,
    ...comparisonRows.map((row) => Number(row[metricKey]) || 0),
  );

  const submitFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAppliedFilters({ ...draftFilters });
  };

  const resetFilters = () => {
    setDraftFilters({ ...INITIAL_FILTERS });
    setAppliedFilters({ ...INITIAL_FILTERS });
  };

  const statusText = data?.status === 'ready'
    ? 'Đủ mẫu để tham khảo'
    : data?.status === 'insufficient_sample'
      ? 'Chưa đủ mẫu'
      : 'Chưa có dữ liệu';

  const healthText = data?.system_health === 'healthy'
    ? 'Pipeline ổn định'
    : data?.system_health === 'attention'
      ? 'Có lỗi cần xử lý'
      : 'Chưa có telemetry';

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <div>
          <span className="dashboard-eyebrow">TikTok Performance Intelligence</span>
          <h2 className="page-title dashboard-title">Hiệu suất video</h2>
          <p className="dashboard-subtitle">
            Theo dõi giữ chân, tương tác và lỗi pipeline từ dữ liệu đo thật.
          </p>
        </div>
        <div className="dashboard-header__actions">
          <span className={`dashboard-health dashboard-health--${data?.system_health || 'empty'}`}>
            {data?.system_health === 'attention'
              ? <AlertTriangle size={16} aria-hidden="true" />
              : <CheckCircle2 size={16} aria-hidden="true" />}
            {healthText}
          </span>
          <button
            className="tiktok-btn tiktok-btn--outline"
            type="button"
            onClick={() => setRefreshKey((value) => value + 1)}
            disabled={loading}
            aria-label="Làm mới dữ liệu dashboard"
          >
            <RefreshCw size={17} className={loading ? 'dashboard-spin' : ''} aria-hidden="true" />
            Làm mới
          </button>
        </div>
      </header>

      <form className="dashboard-filters" onSubmit={submitFilters}>
        <div className="dashboard-filters__title">
          <Filter size={18} aria-hidden="true" />
          <span>Bộ lọc dữ liệu</span>
        </div>
        <label className="dashboard-field">
          <span>Từ ngày</span>
          <input
            className="tiktok-input"
            type="date"
            value={draftFilters.start_date}
            max={draftFilters.end_date || undefined}
            onChange={(event) => setDraftFilters({ ...draftFilters, start_date: event.target.value })}
          />
        </label>
        <label className="dashboard-field">
          <span>Đến ngày</span>
          <input
            className="tiktok-input"
            type="date"
            value={draftFilters.end_date}
            min={draftFilters.start_date || undefined}
            onChange={(event) => setDraftFilters({ ...draftFilters, end_date: event.target.value })}
          />
        </label>
        <label className="dashboard-field">
          <span>Kênh</span>
          <select
            className="tiktok-select"
            value={draftFilters.channel_id}
            onChange={(event) => setDraftFilters({ ...draftFilters, channel_id: event.target.value })}
          >
            <option value="">Tất cả kênh</option>
            {(data?.available_filters.channels || []).map((channel) => (
              <option value={channel} key={channel}>@{channel}</option>
            ))}
          </select>
        </label>
        <label className="dashboard-field">
          <span>Mốc đo</span>
          <select
            className="tiktok-select"
            value={draftFilters.measurement_window}
            onChange={(event) => setDraftFilters({ ...draftFilters, measurement_window: event.target.value })}
          >
            <option value="">Snapshot mới nhất</option>
            {(data?.available_filters.measurement_windows || []).map((window) => (
              <option value={window} key={window}>{window}</option>
            ))}
          </select>
        </label>
        <label className="dashboard-field dashboard-field--sample">
          <span>Mẫu tối thiểu</span>
          <input
            className="tiktok-input"
            type="number"
            min="1"
            max="1000"
            value={draftFilters.min_samples}
            onChange={(event) => setDraftFilters({
              ...draftFilters,
              min_samples: Math.min(1000, Math.max(1, Number(event.target.value) || 1)),
            })}
          />
        </label>
        <div className="dashboard-filters__actions">
          <button className="tiktok-btn tiktok-btn--primary" type="submit">Áp dụng</button>
          <button className="tiktok-btn tiktok-btn--outline" type="button" onClick={resetFilters}>Đặt lại</button>
        </div>
      </form>

      {error && (
        <div className="dashboard-state dashboard-state--error" role="alert">
          <AlertTriangle size={20} aria-hidden="true" />
          <span>{error}</span>
          <button className="tiktok-btn tiktok-btn--outline" type="button" onClick={() => setRefreshKey((value) => value + 1)}>
            Thử lại
          </button>
        </div>
      )}

      {loading && !data && (
        <div className="dashboard-loading" role="status" aria-live="polite">
          <RefreshCw size={22} className="dashboard-spin" aria-hidden="true" />
          Đang tổng hợp telemetry…
        </div>
      )}

      {data && (
        <>
          <section className="dashboard-summary" aria-label="Chỉ số hiệu suất chính">
            <div className="dashboard-summary__meta">
              <span className={`dashboard-status dashboard-status--${data.status}`}>{statusText}</span>
              <span>{formatInteger(data.overview.sample_size)} video mới nhất</span>
              <span>Cập nhật {formatTimestamp(data.generated_at)}</span>
            </div>
            <div className="dashboard-kpis">
              <KpiCard
                icon={<Video size={19} />}
                label="Video đã đo"
                value={formatInteger(data.overview.sample_size)}
                note={`${formatInteger(data.data_quality.snapshot_count)} snapshot`}
                tone="indigo"
              />
              <KpiCard
                icon={<Eye size={19} />}
                label="View trung vị"
                value={formatInteger(data.overview.median_views)}
                note={`${formatInteger(data.overview.total_views)} tổng view`}
                tone="blue"
              />
              <KpiCard
                icon={<Clock3 size={19} />}
                label="Thời gian xem"
                value={`${decimalFormatter.format(data.overview.median_watch_percentage)}%`}
                note={`${decimalFormatter.format(data.overview.median_average_watch_time)} giây trung vị · ${decimalFormatter.format(data.overview.weighted_watch_percentage)}% theo view`}
                tone="cyan"
              />
              <KpiCard
                icon={<TrendingUp size={19} />}
                label="Xem hết video"
                value={`${decimalFormatter.format(data.overview.median_watched_full_rate)}%`}
                note={`Giữ chân 2s ${decimalFormatter.format(data.overview.median_retention_2s)}% · 6s ${decimalFormatter.format(data.overview.median_retention_6s)}% · rơi ${decimalFormatter.format(data.overview.median_retention_drop_2s_to_6s)} điểm`}
                tone="green"
              />
              <KpiCard
                icon={<Share2 size={19} />}
                label="Chia sẻ / 1.000"
                value={decimalFormatter.format(data.overview.shares_per_1000)}
                note="Theo tổng lượt xem"
                tone="orange"
              />
              <KpiCard
                icon={<Save size={19} />}
                label="Lưu / 1.000"
                value={decimalFormatter.format(data.overview.saves_per_1000)}
                note="Theo tổng lượt xem"
                tone="pink"
              />
              <KpiCard
                icon={<UserPlus size={19} />}
                label="Follow / 1.000"
                value={decimalFormatter.format(data.overview.follows_per_1000)}
                note="Theo tổng lượt xem"
                tone="purple"
              />
            </div>
          </section>

          {data.status === 'empty' && (
            <section className="dashboard-empty">
              <BarChart3 size={28} aria-hidden="true" />
              <div>
                <h3>Chưa có video phù hợp bộ lọc</h3>
                <p>Nhập dữ liệu đo TikTok ở các mốc 2h, 24h, 72h hoặc 168h để dashboard bắt đầu so sánh.</p>
              </div>
            </section>
          )}

          <div className="dashboard-layout">
            <section className="card dashboard-panel dashboard-panel--comparison">
              <div className="dashboard-panel__header">
                <div>
                  <span className="dashboard-panel__eyebrow">So sánh sáng tạo</span>
                  <h3>Yếu tố nào đang hiệu quả?</h3>
                </div>
                <div className="dashboard-panel__controls">
                  <label>
                    <span className="sr-only">Nhóm so sánh</span>
                    <select
                      className="form-select"
                      value={breakdownKey}
                      onChange={(event) => setBreakdownKey(event.target.value as BreakdownKey)}
                    >
                      {Object.entries(BREAKDOWN_LABELS).map(([value, label]) => (
                        <option value={value} key={value}>{label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span className="sr-only">Chỉ số so sánh</span>
                    <select
                      className="form-select"
                      value={metricKey}
                      onChange={(event) => setMetricKey(event.target.value as MetricKey)}
                    >
                      {Object.entries(METRIC_LABELS).map(([value, label]) => (
                        <option value={value} key={value}>{label}</option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
              <div className="dashboard-bars">
                {comparisonRows.length === 0 && <p className="dashboard-muted">Chưa có nhóm dữ liệu để so sánh.</p>}
                {comparisonRows.map((row) => {
                  const metricValue = Number(row[metricKey]) || 0;
                  const normalizedWidth = LOWER_IS_BETTER_METRICS.has(metricKey)
                    ? (comparisonMax - metricValue) / comparisonMax * 100
                    : metricValue / comparisonMax * 100;
                  const width = Math.max(2, normalizedWidth);
                  return (
                    <div className="dashboard-bar-row" key={row.value}>
                      <div className="dashboard-bar-row__meta">
                        <strong title={row.value}>{row.value}</strong>
                        <span>
                          {formatMetric(Number(row[metricKey]), metricKey)} · {row.sample_size} video
                          {!row.eligible && ' · chưa đủ mẫu'}
                        </span>
                      </div>
                      <div
                        className="dashboard-bar-track"
                        role="meter"
                        aria-label={`${row.value}: ${formatMetric(Number(row[metricKey]), metricKey)}`}
                        aria-valuenow={Number(row[metricKey])}
                        aria-valuemin={0}
                        aria-valuemax={comparisonMax}
                      >
                        <span
                          className={row.eligible ? 'dashboard-bar' : 'dashboard-bar dashboard-bar--pending'}
                          style={{ '--dashboard-bar-width': `${width}%` } as CSSProperties}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="card dashboard-panel dashboard-panel--quality">
              <div className="dashboard-panel__header">
                <div>
                  <span className="dashboard-panel__eyebrow">Chất lượng dữ liệu</span>
                  <h3>Telemetry & pipeline</h3>
                </div>
                <span className={`dashboard-failure-count ${data.pipeline.failures.total ? 'is-alert' : ''}`}>
                  {data.pipeline.failures.total} lỗi
                </span>
              </div>
              <dl className="dashboard-quality-grid">
                <div><dt>Sự kiện pipeline</dt><dd>{formatInteger(data.pipeline.total_events)}</dd></div>
                <div><dt>Video mới nhất</dt><dd>{formatInteger(data.data_quality.latest_video_count)}</dd></div>
                <div><dt>Snapshot bất thường</dt><dd>{formatInteger(data.data_quality.anomaly_count)}</dd></div>
                <div><dt>Dòng log lỗi định dạng</dt><dd>{formatInteger(data.data_quality.malformed_quality_lines)}</dd></div>
                <div><dt>Retention 2s có dữ liệu</dt><dd>{formatInteger(data.overview.data_quality?.with_retention_2s ?? 0)}</dd></div>
                <div><dt>Retention 6s có dữ liệu</dt><dd>{formatInteger(data.overview.data_quality?.with_retention_6s ?? 0)}</dd></div>
                <div><dt>Watch time theo view</dt><dd>{decimalFormatter.format(data.overview.data_quality?.watch_time_view_coverage ?? 0)}%</dd></div>
              </dl>
              <div className="dashboard-stage-list">
                <span className="dashboard-small-title">Lỗi theo stage</span>
                {data.pipeline.failures.by_stage.length === 0
                  ? <p className="dashboard-success-copy"><CheckCircle2 size={16} aria-hidden="true" /> Không ghi nhận lỗi trong phạm vi lọc.</p>
                  : data.pipeline.failures.by_stage.slice(0, 6).map((item) => (
                      <div className="dashboard-stage" key={item.value}>
                        <span>{item.value}</span>
                        <strong>{item.count}</strong>
                      </div>
                    ))}
              </div>
            </section>
          </div>

          <section className="card dashboard-panel">
            <div className="dashboard-panel__header">
              <div>
                <span className="dashboard-panel__eyebrow">Diễn biến theo ngày</span>
                <h3>Giữ chân và hoàn thành</h3>
              </div>
              <span className="dashboard-panel__hint">Snapshot mới nhất · múi giờ Việt Nam</span>
            </div>
            <div className="dashboard-table-wrap">
              <table className="dashboard-table">
                <thead><tr><th>Ngày đo</th><th>Video</th><th>View</th><th>Thời gian xem</th><th>Xem hết</th><th>Giữ chân 6s</th><th>Rơi 2s→6s</th><th>Chia sẻ / 1.000</th></tr></thead>
                <tbody>
                  {data.trends.length === 0 && <tr><td colSpan={8} className="dashboard-table-empty">Chưa có dữ liệu theo ngày.</td></tr>}
                  {data.trends.slice(-14).reverse().map((row) => (
                    <tr key={row.date}>
                      <td>{row.date}</td>
                      <td>{formatInteger(row.sample_size)}</td>
                      <td>{formatInteger(row.total_views)}</td>
                      <td>{decimalFormatter.format(row.median_watch_percentage)}%</td>
                      <td>{decimalFormatter.format(row.median_watched_full_rate)}%</td>
                      <td>{decimalFormatter.format(row.median_retention_6s)}%</td>
                      <td>{decimalFormatter.format(row.median_retention_drop_2s_to_6s)} điểm</td>
                      <td>{decimalFormatter.format(row.shares_per_1000)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card dashboard-panel">
            <div className="dashboard-panel__header">
              <div>
                <span className="dashboard-panel__eyebrow">Video dẫn đầu</span>
                <h3>Top 10 theo lượt xem</h3>
              </div>
              <span className="dashboard-panel__hint">Dùng để tìm pattern, không tự kết luận khi chưa đủ mẫu</span>
            </div>
            <div className="dashboard-table-wrap">
              <table className="dashboard-table dashboard-table--videos">
                <thead><tr><th>Video</th><th>Kênh</th><th>Nội dung</th><th>Hook</th><th>Mood nhạc</th><th>View</th><th>Xem hết</th><th>Chia sẻ / 1.000</th></tr></thead>
                <tbody>
                  {data.top_videos.length === 0 && <tr><td colSpan={8} className="dashboard-table-empty">Chưa có video để xếp hạng.</td></tr>}
                  {data.top_videos.map((video) => (
                    <tr key={`${video.channel_id}-${video.video_id}`}>
                      <td className="dashboard-video-title" title={video.title || video.video_id}>{video.title || video.video_id}</td>
                      <td>@{video.channel_id}</td>
                      <td>{video.story_type}</td>
                      <td>{video.hook_type}</td>
                      <td>{video.music_mood}</td>
                      <td>{formatInteger(video.views)}</td>
                      <td>{decimalFormatter.format(video.median_watched_full_rate)}%</td>
                      <td>{decimalFormatter.format(video.shares_per_1000)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card dashboard-panel">
            <div className="dashboard-panel__header">
              <div>
                <span className="dashboard-panel__eyebrow">Chẩn đoán vận hành</span>
                <h3>Lỗi pipeline gần đây</h3>
              </div>
              <span className="dashboard-panel__hint">Tối đa 20 lỗi mới nhất</span>
            </div>
            <div className="dashboard-table-wrap">
              <table className="dashboard-table dashboard-table--errors">
                <thead><tr><th>Thời gian</th><th>Pipeline</th><th>Kênh</th><th>Stage</th><th>Mã lỗi</th><th>Thử lại</th><th>Thông báo</th></tr></thead>
                <tbody>
                  {data.pipeline.failures.recent.length === 0 && <tr><td colSpan={7} className="dashboard-table-empty">Không có lỗi trong phạm vi lọc.</td></tr>}
                  {data.pipeline.failures.recent.map((failure, index) => (
                    <tr key={`${failure.ts}-${failure.item_id}-${index}`}>
                      <td>{formatTimestamp(failure.ts)}</td>
                      <td>{failure.pipeline}</td>
                      <td>{failure.channel_id || '-'}</td>
                      <td><span className="dashboard-code">{failure.stage}</span></td>
                      <td><span className="dashboard-code dashboard-code--danger">{failure.error_code}</span></td>
                      <td>{failure.retryable ? 'Có' : 'Không'}</td>
                      <td className="dashboard-error-message" title={failure.message}>{failure.message || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
