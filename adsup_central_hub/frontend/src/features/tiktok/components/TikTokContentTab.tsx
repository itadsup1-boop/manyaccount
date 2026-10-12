import { RotateCcw, Save, Sparkles } from 'lucide-react';

import { contentProfileFields } from '../contentProfiles';
import type { TikTokController } from '../useTikTokController';

type Props = { controller: TikTokController };

const TEXTAREA_FIELDS = new Set([
  'audience', 'content_promise', 'hook_style', 'avoid', 'winning_examples', 'custom_instruction',
]);

export default function TikTokContentTab({ controller }: Props) {
  return (
    <section className="tiktok-tab-panel" aria-label="Chỉ đạo nội dung TikTok">
      <article className="tiktok-card">
        <div className="tiktok-card__header content-header">
          <div><h3>Chỉ đạo nội dung AI</h3><p>Một bộ chỉ đạo áp dụng cho tất cả nguồn của tài khoản được chọn.</p></div>
          <button className="tiktok-btn tiktok-btn--primary" type="button" onClick={controller.handleSaveAccountInstruction} disabled={!controller.selectedProfileAccountId}><Save size={16} /> Lưu chỉ đạo</button>
        </div>

        <label className="content-account-select"><span>Áp dụng cho tài khoản</span><select className="tiktok-select" value={controller.selectedProfileAccountId} onChange={(event) => controller.handleSelectProfileAccount(event.target.value)}><option value="">Chọn tài khoản</option>{controller.accounts.map((item) => <option key={item.tiktok_id} value={item.tiktok_id}>{item.tiktok_id}</option>)}</select></label>

        {controller.selectedProfileAccountId ? (
          <>
            <div className="saved-profile-panel">
              <div><strong>Nội dung đã lưu trước đó</strong><span>{controller.savedProfilePreview ? 'Bạn có thể khôi phục hoặc điền các ô còn thiếu.' : 'Chưa có dữ liệu đã lưu cho tài khoản này.'}</span></div>
              <div>
                <button className="tiktok-btn tiktok-btn--outline" type="button" onClick={controller.handleRestoreSavedProfile}><RotateCcw size={15} /> Khôi phục</button>
                <button className="tiktok-btn tiktok-btn--soft" type="button" onClick={controller.handleFillMissingProfile}><Sparkles size={15} /> Điền ô trống</button>
              </div>
            </div>

            <div className="content-profile-grid">
              {contentProfileFields.map(([label, key]) => {
                if (key === 'primary_goal') {
                  return <label key={key}><span>{label}</span><select className="tiktok-select" value={controller.profileDraft[key]} onChange={(event) => controller.handleProfileDraftChange(key, event.target.value)}><option value="view">Tăng view</option><option value="retention">Tăng giữ chân</option><option value="comment">Kéo bình luận</option><option value="share">Kéo chia sẻ</option><option value="follow">Tăng follow</option><option value="lead">Kéo inbox/lead</option></select></label>;
                }
                if (key === 'video_length') {
                  return <label key={key}><span>{label}</span><select className="tiktok-select" value={controller.profileDraft[key]} onChange={(event) => controller.handleProfileDraftChange(key, event.target.value)}><option value="38-42s">38-42s (khoảng 40s)</option><option value="30-45s">30-45s</option><option value="45-60s">45-60s</option><option value="60-90s">60-90s</option><option value="90-120s">90-120s</option></select></label>;
                }
                return <label className={TEXTAREA_FIELDS.has(key) ? 'is-wide' : ''} key={key}><span>{label}</span>{TEXTAREA_FIELDS.has(key) ? <textarea className="tiktok-textarea" value={controller.profileDraft[key]} onChange={(event) => controller.handleProfileDraftChange(key, event.target.value)} rows={key === 'winning_examples' || key === 'custom_instruction' ? 4 : 3} /> : <input className="tiktok-input" value={controller.profileDraft[key]} onChange={(event) => controller.handleProfileDraftChange(key, event.target.value)} />}</label>;
              })}
            </div>
          </>
        ) : <div className="tiktok-empty-state is-compact"><strong>Chọn tài khoản để bắt đầu</strong><span>Form định hướng sẽ tự điền gợi ý phù hợp với từng kênh.</span></div>}
      </article>
    </section>
  );
}
