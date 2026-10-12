import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles,
  ShieldCheck,
  Newspaper,
  Video,
  ShoppingBag,
  Layers,
  Cpu,
  TrendingUp,
  Zap,
  CheckCircle2,
  X,
  Play
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import './LoginPage.css';

export default function LoginPage() {
  const { loginWithGoogle, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [selectedEngine, setSelectedEngine] = useState<'article' | 'facebook' | 'tiktok' | 'affiliate'>('article');
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/article');
    }
  }, [isAuthenticated, navigate]);

  const handleGoogleDirectClick = async () => {
    try {
      setLoading(true);
      setErrorMsg('');
      await loginWithGoogle(
        'admin@adsup.vn',
        'Quản trị viên Adsup',
        'https://ui-avatars.com/api/?name=Admin+Adsup&background=2563eb&color=fff'
      );
      navigate('/article');
    } catch (err: any) {
      setErrorMsg(err.message || 'Đăng nhập Google thất bại');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="hub-login-page">
      {/* NAVBAR */}
      <nav className="hub-navbar">
        <div className="hub-navbar__brand">
          <div className="hub-navbar__logo">
            <Sparkles size={24} />
          </div>
          <div className="hub-navbar__title-group">
            <h1>
              Adsup <span>Central Hub</span>
            </h1>
            <p>Hệ Thống Tự Động Dựng Video Tin Tức & Social Media Automation</p>
          </div>
        </div>

        <div className="hub-navbar__right-actions">
          <div className="hub-navbar__status-pill">
            <div className="hub-navbar__dot"></div>
            <span>Hệ thống AI Pipeline: Sẵn sàng 24/7</span>
          </div>

          {/* TOP RIGHT LOGIN BUTTON */}
          <button
            type="button"
            className="hub-nav-login-btn"
            onClick={() => setIsLoginModalOpen(true)}
          >
            <Zap size={16} /> Đăng nhập
          </button>
        </div>
      </nav>

      {/* MAIN HERO SHOWCASE */}
      <main className="hub-hero-container">
        <section className="hub-showcase">
          <div className="hub-badge">
            <Cpu size={14} /> AI MEDIA AUTOMATION ENGINE V3.5
          </div>

          <h1 className="hub-hero-title">
            Hệ thống quản lý & sản xuất <br />
            <span className="highlight">Video Ngắn AI Tự Động</span>
          </h1>

          <p className="hub-hero-subtitle">
            Giải pháp toàn diện giúp tự động hóa quy trình viết kịch bản AI, dựng video tin tức bài báo,
            remix Facebook Reels, uploader TikTok Matrix và render video Affiliate bán hàng.
          </p>

          <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              className="hub-nav-login-btn"
              onClick={() => setIsLoginModalOpen(true)}
              style={{ padding: '0.8rem 1.75rem', fontSize: '0.95rem' }}
            >
              <Play size={18} fill="#ffffff" /> Bắt đầu trải nghiệm ngay
            </button>
          </div>

          {/* Core Engines 4 Grid */}
          <div className="hub-engines-grid">
            {/* Engine 1: Bài báo AI */}
            <div
              className={`hub-engine-card ${selectedEngine === 'article' ? 'active' : ''}`}
              onClick={() => setSelectedEngine('article')}
            >
              <div className="hub-engine-icon article">
                <Newspaper size={22} />
              </div>
              <h3>
                Bài Báo AI <span className="hub-engine-tag">Báo chí</span>
              </h3>
              <p>Tự động quét link tin tức, tổng hợp bằng Gemini AI & tạo video đọc bài tự động.</p>
            </div>

            {/* Engine 2: Facebook Remix */}
            <div
              className={`hub-engine-card ${selectedEngine === 'facebook' ? 'active' : ''}`}
              onClick={() => setSelectedEngine('facebook')}
            >
              <div className="hub-engine-icon facebook">
                <Video size={22} />
              </div>
              <h3>
                Facebook Remix <span className="hub-engine-tag">Reels Bot</span>
              </h3>
              <p>Theo dõi Group & Fanpage, tự động Remix Reels, ghép nhạc & đăng bài đa kênh.</p>
            </div>

            {/* Engine 3: TikTok Matrix */}
            <div
              className={`hub-engine-card ${selectedEngine === 'tiktok' ? 'active' : ''}`}
              onClick={() => setSelectedEngine('tiktok')}
            >
              <div className="hub-engine-icon tiktok">
                <Layers size={22} />
              </div>
              <h3>
                TikTok Matrix <span className="hub-engine-tag">Upload 24/7</span>
              </h3>
              <p>Quản lý ma trận tài khoản TikTok, tự động phân lịch uploader không gõ captcha.</p>
            </div>

            {/* Engine 4: Affiliate Video */}
            <div
              className={`hub-engine-card ${selectedEngine === 'affiliate' ? 'active' : ''}`}
              onClick={() => setSelectedEngine('affiliate')}
            >
              <div className="hub-engine-icon affiliate">
                <ShoppingBag size={22} />
              </div>
              <h3>
                Affiliate Video <span className="hub-engine-tag">Grok Motion</span>
              </h3>
              <p>Tạo video sản phẩm Affiliate hàng loạt với Grok AI motion prompts & canvas chuẩn.</p>
            </div>
          </div>

          {/* Engine Live Stats Preview */}
          <div className="hub-preview-box">
            <div className="hub-preview-header">
              <h4>
                <TrendingUp size={16} color="#2563eb" /> Trạng thái hoạt động hôm nay
              </h4>
              <span style={{ fontSize: '0.75rem', color: '#10b981', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                <CheckCircle2 size={13} /> Gemini Automator Active
              </span>
            </div>

            <div className="hub-metrics-row">
              <div className="hub-metric-item">
                <div className="hub-metric-num">150+</div>
                <div className="hub-metric-label">Bài Báo Đã Dựng</div>
              </div>
              <div className="hub-metric-item">
                <div className="hub-metric-num">24</div>
                <div className="hub-metric-label">Kênh TikTok Active</div>
              </div>
              <div className="hub-metric-item">
                <div className="hub-metric-num">99.8%</div>
                <div className="hub-metric-label">Tỷ lệ Thành Công</div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* CENTERED POPUP LOGIN MODAL */}
      <div
        className={`hub-modal-overlay ${isLoginModalOpen ? 'active' : ''}`}
        onClick={(e) => {
          if ((e.target as HTMLElement).classList.contains('hub-modal-overlay')) {
            setIsLoginModalOpen(false);
          }
        }}
      >
        <section className="hub-auth-panel">
          <button
            type="button"
            className="hub-modal-close-btn"
            onClick={() => setIsLoginModalOpen(false)}
            title="Đóng"
          >
            <X size={18} />
          </button>

          <div className="hub-auth-header">
            <div className="hub-auth-icon">
              <Zap size={26} />
            </div>
            <h2>Đăng nhập Adsup Hub</h2>
            <p>Bấm nút bên dưới để vào trực tiếp giao diện chính</p>
          </div>

          {errorMsg && (
            <div
              style={{
                padding: '0.75rem 1rem',
                background: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: '10px',
                color: '#b91c1c',
                fontSize: '0.85rem',
                marginBottom: '1.25rem',
                textAlign: 'center'
              }}
            >
              {errorMsg}
            </div>
          )}

          {/* EXACTLY 1 Google Login Button */}
          <div className="hub-g-wrapper">
            <button
              type="button"
              className="hub-g-btn"
              onClick={handleGoogleDirectClick}
              disabled={loading}
              style={{
                padding: '0.9rem 1.25rem',
                fontSize: '0.95rem',
                fontWeight: 700,
                borderRadius: '14px',
                background: '#ffffff',
                border: '1.5px solid #cbd5e1',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.05)'
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
              </svg>
              {loading ? 'Đang vào hệ thống...' : 'Đăng nhập với Google / Gmail'}
            </button>
          </div>

          <div className="hub-auth-footer">
            <ShieldCheck size={14} /> Chuyển hướng tức thì vào giao diện chính khi click
          </div>
        </section>
      </div>

      {/* FOOTER */}
      <footer className="hub-footer">
        © 2026 Adsup Central Hub — AI Media Automation Platform. All Rights Reserved.
      </footer>
    </div>
  );
}
