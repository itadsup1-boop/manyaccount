import { Save, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import TitlePositionEditor from '../../../components/TitlePositionEditor';
import { DEFAULT_TITLE_TEXT_SETTINGS } from '../contentProfiles';
import type { TikTokController } from '../useTikTokController';

type Props = { controller: TikTokController };

function channelLabel(url: string) {
  const match = String(url || '').match(/@([^/?]+)/);
  return match ? `@${match[1]}` : url || 'Kênh chưa đặt tên';
}

export default function TikTokChannelsTab({ controller }: Props) {
  const [selectedChannelIndex, setSelectedChannelIndex] = useState(0);
  const account = useMemo(
    () => controller.accounts.find((item) => item.tiktok_id === controller.selectedAccountId),
    [controller.accounts, controller.selectedAccountId],
  );
  const channels = account?.channels || [];
  const channel = channels[selectedChannelIndex];

  useEffect(() => setSelectedChannelIndex(0), [controller.selectedAccountId]);
  useEffect(() => {
    if (selectedChannelIndex >= channels.length) setSelectedChannelIndex(Math.max(0, channels.length - 1));
  }, [channels.length, selectedChannelIndex]);

  const titleSettings = {
    ...DEFAULT_TITLE_TEXT_SETTINGS,
    ...(channel?.render_settings?.text_overlay_settings || {}),
  };

  return (
    <section className="tiktok-tab-panel" aria-label="Quản lý kênh nguồn TikTok">
      <article className="tiktok-card">
        <div className="tiktok-card__header"><div><h3>Chọn tài khoản đích và kênh nguồn</h3><p>Mỗi tài khoản có danh sách nguồn và bố cục title riêng.</p></div></div>
        <div className="channel-create-grid">
          <label><span>Tài khoản TikTok đích</span><select className="tiktok-select" value={controller.selectedAccountId} onChange={(event) => controller.setSelectedAccountId(event.target.value)}><option value="">Chọn tài khoản</option>{controller.accounts.map((item) => <option value={item.tiktok_id} key={item.tiktok_id}>{item.tiktok_id}</option>)}</select></label>
          <label className="channel-url-field"><span>URL kênh nguồn</span><input className="tiktok-input" value={controller.newChannel.url} onChange={(event) => controller.setNewChannel({ ...controller.newChannel, url: event.target.value })} placeholder="https://tiktok.com/@..." /></label>
          <label><span>Limit</span><input className="tiktok-input" type="number" min="1" value={controller.newChannel.limit} onChange={(event) => controller.setNewChannel({ ...controller.newChannel, limit: Number.parseInt(event.target.value) || 0 })} /></label>
          <button className="tiktok-btn tiktok-btn--primary" type="button" onClick={controller.handleAddChannel} disabled={!controller.selectedAccountId}>Thêm kênh</button>
        </div>
      </article>

      {!controller.selectedAccountId ? (
        <div className="tiktok-empty-state"><strong>Chưa chọn tài khoản</strong><span>Chọn một tài khoản TikTok để xem và chỉnh các kênh nguồn.</span></div>
      ) : (
        <div className="channel-workspace">
          <aside className="tiktok-card channel-list" aria-label={`Kênh của ${controller.selectedAccountId}`}>
            <div className="tiktok-card__header"><div><h3>Kênh của {controller.selectedAccountId}</h3><p>{channels.length} nguồn</p></div></div>
            <div className="channel-list__items">
              {channels.map((item: any, index: number) => (
                <button className={`channel-list-item ${selectedChannelIndex === index ? 'is-active' : ''}`} type="button" key={`${item.url}-${index}`} onClick={() => setSelectedChannelIndex(index)}>
                  <strong>{channelLabel(item.url)}</strong><span>Limit: {item.limit} video</span>
                </button>
              ))}
              {!channels.length && <span className="tiktok-empty-inline">Tài khoản chưa có kênh nguồn.</span>}
            </div>
          </aside>

          {channel && (
            <article className="tiktok-card channel-editor">
              <div className="tiktok-card__header channel-editor__header">
                <div><h3>Chỉnh title mở đầu</h3><p>{channelLabel(channel.url)}</p></div>
                <button className="icon-action is-danger" type="button" onClick={() => controller.handleDeleteChannel(selectedChannelIndex)} aria-label="Xóa kênh đang chọn"><Trash2 size={17} /></button>
              </div>

              <TitlePositionEditor
                channelId={controller.selectedAccountId}
                frameFilename={channel.render_settings?.assets?.title_frame_filename ?? ''}
                yStart={Number(titleSettings.box_y_start)}
                xOffset={Number(titleSettings.box_x_offset)}
                boxWidth={Number(titleSettings.box_width_percentage)}
                fontSize={Number(titleSettings.font_size)}
                color={String(titleSettings.text_color || '#ffffff')}
                onChange={(updates) => controller.handleChannelTitleSettings(selectedChannelIndex, updates)}
              />

              <div className="subtitle-lock">
                <div><strong>Subtitle karaoke nguồn TikTok</strong><span>Đang khóa tắt. Video vẫn có title và lời đọc.</span></div>
                <span className="lock-badge">Đang tắt</span>
              </div>

              <div className="channel-editor__actions">
                <button className="tiktok-btn tiktok-btn--outline" type="button" onClick={() => controller.handleApplyTitleToAllChannels(selectedChannelIndex)}>Áp dụng cho tất cả nguồn</button>
                <button className="tiktok-btn tiktok-btn--primary" type="button" onClick={() => controller.handleSaveChannelRenderSettings(selectedChannelIndex)}><Save size={16} /> Lưu title</button>
              </div>
            </article>
          )}
        </div>
      )}
    </section>
  );
}
