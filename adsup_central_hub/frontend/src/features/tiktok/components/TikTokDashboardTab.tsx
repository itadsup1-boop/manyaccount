import { Bot, Clock3, Play, Square, Trash2, TriangleAlert } from 'lucide-react';

import type { TikTokController } from '../useTikTokController';

type Props = { controller: TikTokController };

function getNextRun(times: string[]) {
  if (!times.length) return 'Chưa đặt lịch';
  const now = new Date();
  const current = now.getHours() * 60 + now.getMinutes();
  const next = times.find((time) => {
    const [hour, minute] = time.split(':').map(Number);
    return hour * 60 + minute > current;
  });
  return next ? `${next} hôm nay` : `${times[0]} ngày mai`;
}

export default function TikTokDashboardTab({ controller }: Props) {
  const successCount = controller.logs.filter((line) => /thành công|hoàn tất/i.test(line)).length;
  const errorCount = controller.logs.filter((line) => /lỗi|failed|error/i.test(line)).length;

  return (
    <section className="tiktok-tab-panel" aria-label="Dashboard Matrix Bot">
      <article className="tiktok-card">
        <div className="tiktok-card__header">
          <div>
            <h3><Clock3 size={18} aria-hidden="true" /> Lịch chạy Bot</h3>
            <p>Bot tự động chạy vào các mốc giờ bên dưới.</p>
          </div>
        </div>

        <div className="schedule-chips" aria-label="Danh sách giờ chạy">
          {controller.scheduleTimes.length ? controller.scheduleTimes.map((time) => (
            <span className="schedule-chip" key={time}>
              {time}
              <button
                type="button"
                onClick={() => controller.handleDeleteScheduleTime(time)}
                aria-label={`Xóa lịch ${time}`}
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </span>
          )) : controller.scheduleStatus === 'loading' ? (
            <span className="tiktok-empty-inline">Đang tải lịch chạy...</span>
          ) : controller.scheduleStatus === 'error' ? (
            <span className="tiktok-empty-inline" role="alert">
              Không tải được lịch.{' '}
              <button className="tiktok-link-button" type="button" onClick={() => controller.reloadSchedule()}>
                Thử lại
              </button>
            </span>
          ) : <span className="tiktok-empty-inline">Chưa có lịch chạy.</span>}
        </div>

        {controller.scheduleError && (
          <p className="tiktok-form-error" role="alert">Lỗi tải lịch: {controller.scheduleError}</p>
        )}

        <div className="schedule-add">
          <label className="sr-only" htmlFor="new-schedule-time">Giờ mới</label>
          <input
            id="new-schedule-time"
            className="tiktok-input"
            value={controller.newTime}
            onChange={(event) => controller.setNewTime(event.target.value)}
            placeholder="Ví dụ: 08:30"
          />
          <button className="tiktok-btn tiktok-btn--primary" type="button" onClick={controller.handleAddScheduleTime}>
            Thêm giờ
          </button>
        </div>
      </article>

      <article className="tiktok-card">
        <div className="bot-status-row">
          <div className="bot-status-copy">
            <span className={`status-indicator ${controller.isRunning ? 'is-running' : ''}`} aria-hidden="true" />
            <div>
              <span>Trạng thái</span>
              <strong>{controller.isRunning ? 'Bot đang chạy' : 'Bot đang dừng'}</strong>
              <small>Lần chạy kế tiếp: {getNextRun(controller.scheduleTimes)}</small>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: 'auto', marginRight: '16px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted, #666)' }}>🤖 AI Engine:</span>
            <div style={{ display: 'inline-flex', background: '#f1f5f9', borderRadius: '8px', padding: '3px' }}>
              <button
                type="button"
                className={`tiktok-btn ${controller.aiProvider === 'chatgpt' ? 'tiktok-btn--primary' : 'tiktok-btn--outline'}`}
                style={{ padding: '4px 12px', fontSize: '13px', borderRadius: '6px' }}
                onClick={() => controller.handleSetAiProvider('chatgpt')}
              >
                ChatGPT
              </button>
              <button
                type="button"
                className={`tiktok-btn ${controller.aiProvider === 'gemini' ? 'tiktok-btn--primary' : 'tiktok-btn--outline'}`}
                style={{ padding: '4px 12px', fontSize: '13px', borderRadius: '6px' }}
                onClick={() => controller.handleSetAiProvider('gemini')}
              >
                Gemini (Web)
              </button>
            </div>
          </div>
          {controller.isRunning ? (
            <button className="tiktok-btn tiktok-btn--danger" type="button" onClick={controller.handleStop}>
              <Square size={16} aria-hidden="true" /> Dừng lại
            </button>
          ) : (
            <button className="tiktok-btn tiktok-btn--primary" type="button" onClick={controller.handleStart}>
              <Play size={16} aria-hidden="true" /> Bắt đầu chạy
            </button>
          )}
        </div>

        <dl className="bot-stat-grid">
          <div><dt>Tài khoản đang bật</dt><dd>{controller.accounts.filter((item) => item.active).length}</dd></div>
          <div><dt>Sự kiện hoàn tất</dt><dd>{successCount}</dd></div>
          <div className={errorCount ? 'has-error' : ''}><dt>Lỗi trong log</dt><dd>{errorCount}</dd></div>
        </dl>
      </article>

      <article className="tiktok-card">
        <div className="tiktok-card__header">
          <div>
            <h3><Bot size={18} aria-hidden="true" /> Nhật ký hoạt động</h3>
            <p>Cập nhật tự động khi Matrix Bot đang chạy.</p>
          </div>
          {errorCount > 0 && <span className="log-alert"><TriangleAlert size={15} /> {errorCount} lỗi</span>}
        </div>
        <div className="tiktok-log" role="log" aria-live="polite">
          {controller.logs.map((line, index) => (
            <div className={/lỗi|failed|error/i.test(line) ? 'is-error' : ''} key={`${index}-${line}`}>
              {line}
            </div>
          ))}
          {controller.isRunning && <span className="log-cursor" aria-hidden="true">_</span>}
        </div>
      </article>
    </section>
  );
}
