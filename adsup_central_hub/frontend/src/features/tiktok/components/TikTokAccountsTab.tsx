import { KeyRound, MonitorPlay, Plus, RefreshCw, Trash2 } from 'lucide-react';

import type { TikTokController } from '../useTikTokController';

type Props = { controller: TikTokController };

function initials(value: string) {
  return value.replace(/^@/, '').split(/[._-]/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'TK';
}

export default function TikTokAccountsTab({ controller }: Props) {
  return (
    <section className="tiktok-tab-panel" aria-label="Quản lý tài khoản TikTok">
      <div className="panel-actions">
        <button className="tiktok-btn tiktok-btn--outline" type="button" onClick={controller.fetchAccounts}>
          <RefreshCw size={16} aria-hidden="true" /> Làm mới
        </button>
      </div>

      <article className="tiktok-card">
        <div className="tiktok-card__header"><div><h3><Plus size={18} /> Thêm tài khoản mới</h3></div></div>
        <div className="account-create-grid">
          <label><span>TikTok ID</span><input className="tiktok-input" value={controller.newAcc.tiktok_id} onChange={(event) => controller.setNewAcc({ ...controller.newAcc, tiktok_id: event.target.value })} placeholder="@tiktok_id" /></label>
          <label><span>Email</span><input className="tiktok-input" type="email" value={controller.newAcc.email} onChange={(event) => controller.setNewAcc({ ...controller.newAcc, email: event.target.value })} placeholder="email@gmail.com" /></label>
          <label><span>Máy</span><input className="tiktok-input" value={controller.newAcc.machine_id} onChange={(event) => controller.setNewAcc({ ...controller.newAcc, machine_id: event.target.value })} /></label>
          <button className="tiktok-btn tiktok-btn--primary" type="button" onClick={controller.handleAddAccount}>Thêm tài khoản</button>
        </div>
      </article>

      <article className="tiktok-card">
        <div className="tiktok-card__header"><div><h3>Danh sách tài khoản TikTok</h3><p>{controller.accounts.length} tài khoản đã cấu hình</p></div></div>
        <div className="tiktok-table-wrap">
          <table className="tiktok-table">
            <thead><tr><th>Tài khoản</th><th>Profile Chrome</th><th>Max Limit</th><th>Trạng thái</th><th>Hành động</th></tr></thead>
            <tbody>
              {controller.accounts.map((account) => (
                <tr key={account.tiktok_id}>
                  <td><div className="account-cell"><span className="account-avatar">{initials(account.tiktok_id)}</span><div><strong>{account.tiktok_id}</strong><small>{account.email || 'Chưa có email'}</small></div></div></td>
                  <td><code>{account.chrome_profile || '-'}</code></td>
                  <td><input className="table-number-input" type="number" min="1" defaultValue={account.video_limit_per_run || 3} onBlur={(event) => controller.handleUpdateLimit(account.tiktok_id, Number.parseInt(event.target.value) || 3)} aria-label={`Giới hạn video ${account.tiktok_id}`} /></td>
                  <td><label className="tiktok-switch"><input type="checkbox" checked={Boolean(account.active)} onChange={() => controller.handleToggleActive(account.tiktok_id, account.active)} /><span aria-hidden="true" /><b>{account.active ? 'Bật' : 'Tắt'}</b></label></td>
                  <td><div className="table-actions">
                    <button type="button" onClick={() => controller.handleOpenChrome(account.chrome_profile)} aria-label={`Mở Chrome ${account.tiktok_id}`} title="Mở Chrome TikTok"><MonitorPlay size={16} /></button>
                    <button type="button" onClick={() => controller.handleOpenChatGPT(account.tiktok_id)} aria-label={`Mở ChatGPT ${account.tiktok_id}`} title="Mở ChatGPT"><KeyRound size={16} /></button>
                    <button className="is-danger" type="button" onClick={() => controller.handleDeleteAccount(account.tiktok_id)} aria-label={`Xóa ${account.tiktok_id}`} title="Xóa tài khoản"><Trash2 size={16} /></button>
                  </div></td>
                </tr>
              ))}
              {!controller.accounts.length && <tr><td colSpan={5} className="table-empty">Chưa có tài khoản TikTok.</td></tr>}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
