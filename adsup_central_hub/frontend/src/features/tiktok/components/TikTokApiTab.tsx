import { Copy, KeyRound, Save } from 'lucide-react';

import type { TikTokController } from '../useTikTokController';

type Props = { controller: TikTokController };

export default function TikTokApiTab({ controller }: Props) {
  const update = (key: string, value: string) => controller.setApiSettings({ ...controller.apiSettings, [key]: value });

  return (
    <section className="tiktok-tab-panel" aria-label="Cấu hình API TikTok">
      <div className="api-config-grid">
        <article className="tiktok-card">
          <div className="tiktok-card__header"><div><h3>Cấu hình AI</h3><p>Phiên ChatGPT và dịch vụ giọng đọc.</p></div></div>
          <div className="config-fields">
            <label><span>AI Studio URL</span><input className="tiktok-input" value={controller.apiSettings.ai_studio_url} onChange={(event) => update('ai_studio_url', event.target.value)} placeholder="Tạm không dùng khi chạy qua ChatGPT" /></label>
            <label><span>API Key</span><input className="tiktok-input" type="password" value={controller.apiSettings.api_key} onChange={(event) => update('api_key', event.target.value)} placeholder="••••••••" /></label>
            <label><span>Voice ID mặc định</span><input className="tiktok-input" value={controller.apiSettings.voice_id} onChange={(event) => update('voice_id', event.target.value)} placeholder="Voice ID" /></label>
          </div>
          <div className="config-actions">
            <button className="tiktok-btn tiktok-btn--outline" type="button" onClick={() => controller.handleOpenChatGPT()}>
              <KeyRound size={16} /> Mở ChatGPT chung
            </button>
            <button className="tiktok-btn tiktok-btn--outline" type="button" onClick={() => controller.handleOpenGemini()}>
              <KeyRound size={16} /> Mở Gemini chung
            </button>
            <button className="tiktok-btn tiktok-btn--soft" type="button" onClick={controller.handleCloneChatGPTProfiles}>
              <Copy size={16} /> Nhân bản ChatGPT
            </button>
            <button className="tiktok-btn tiktok-btn--soft" type="button" onClick={controller.handleCloneGeminiProfiles}>
              <Copy size={16} /> Nhân bản Gemini
            </button>
          </div>
        </article>

        <article className="tiktok-card">
          <div className="tiktok-card__header"><div><h3>Tích hợp ngoài</h3><p>Google Sheets và thông báo Telegram.</p></div></div>
          <div className="config-fields">
            <label><span>Google Sheet URL</span><input className="tiktok-input" value={controller.apiSettings.sheet_url} onChange={(event) => update('sheet_url', event.target.value)} placeholder="https://docs.google.com/spreadsheets/..." /></label>
            <label><span>Telegram Bot Token</span><input className="tiktok-input" type="password" value={controller.apiSettings.tele_token} onChange={(event) => update('tele_token', event.target.value)} placeholder="Bot token" /></label>
            <label><span>Telegram Chat ID</span><input className="tiktok-input" value={controller.apiSettings.tele_chatid} onChange={(event) => update('tele_chatid', event.target.value)} placeholder="-1001234567" /></label>
          </div>
        </article>
      </div>

      <article className="tiktok-card server-config">
        <div><div className="tiktok-card__header"><div><h3>Máy chủ</h3><p>Máy chịu trách nhiệm chạy các tài khoản này.</p></div></div><label><span>Mã máy (Machine ID)</span><input className="tiktok-input" value={controller.apiSettings.machine_id} onChange={(event) => update('machine_id', event.target.value)} /></label></div>
        <button className="tiktok-btn tiktok-btn--primary" type="button" onClick={controller.handleSaveApiSettings}><Save size={16} /> Lưu cấu hình</button>
      </article>
    </section>
  );
}
