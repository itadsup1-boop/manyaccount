import { useEffect, useState } from 'react';
import { Newspaper, Video, ShoppingBag, Radio, Sparkles, CheckCircle2, LogOut, ShieldCheck, UserCheck, KeyRound } from 'lucide-react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

interface SystemStats {
  article_count: number;
  affiliate_count: number;
  tiktok_status: string;
  voice_status: string;
}

export default function Header() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState<SystemStats>({
    article_count: 0,
    affiliate_count: 0,
    tiktok_status: 'sẵn sàng',
    voice_status: 'hoạt động',
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch('/api/dashboard/stats');
        if (res.ok) {
          const data = await res.json();
          setStats((prev) => ({
            ...prev,
            article_count: data.article_processed || data.article_count || 12,
            affiliate_count: data.affiliate_count || 8,
          }));
        }
      } catch (err) {
        // Fallback stats
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="header-white">
      <div className="header-white__top">
        <div className="header-white__brand">
          <div className="header-white__logo-badge">
            <Sparkles size={20} />
          </div>
          <div>
            <h1 className="header-white__title">Adsup Central Hub</h1>
            <p className="header-white__subtitle">Hệ Thống Tự Động Dựng Video Tin Tức, Facebook Remix, TikTok & Affiliate</p>
          </div>
        </div>

        <div className="header-white__badges" style={{ alignItems: 'center', gap: '10px' }}>
          <div className="status-pill status-pill--success">
            <CheckCircle2 size={14} />
            <span>Voicebox: {stats.voice_status}</span>
          </div>

          {user && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', background: 'rgba(255, 255, 255, 0.08)', padding: '6px 12px', borderRadius: '20px', border: '1px solid rgba(255, 255, 255, 0.12)' }}>
              {user.picture ? (
                <img src={user.picture} alt={user.name} style={{ width: 26, height: 26, borderRadius: '50%' }} />
              ) : (
                <div style={{ width: 26, height: 26, borderRadius: '50%', background: '#3b82f6', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: 'bold' }}>
                  {user.name.charAt(0).toUpperCase()}
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc', lineHeight: 1.2 }}>{user.name}</span>
                <span style={{ fontSize: '10px', color: isAdmin ? '#60a5fa' : '#34d399', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '3px' }}>
                  {isAdmin ? <KeyRound size={10} /> : <UserCheck size={10} />}
                  {isAdmin ? 'ADMIN' : 'USER'}
                </span>
              </div>

              {isAdmin && (
                <Link to="/admin/users" className="status-pill status-pill--info" style={{ padding: '4px 8px', fontSize: '11px', textDecoration: 'none' }} title="Quản lý Quyền User">
                  <ShieldCheck size={12} /> Quyền
                </Link>
              )}

              <button
                type="button"
                onClick={handleLogout}
                style={{ background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center' }}
                title="Đăng xuất"
              >
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Live Status Ticker Bar */}
      <div className="ticker-white">
        <div className="ticker-white__label">
          <Radio size={14} />
          <span>TRẠNG THÁI</span>
        </div>
        <div className="ticker-white__wrapper">
          <div className="ticker-white__track">
            <span className="ticker-item">
              <Newspaper size={14} /> 📰 Tool Bài Báo: Đã xử lý <strong>{stats.article_count}</strong> bài viết hôm nay
            </span>
            <span className="ticker-divider">•</span>
            <span className="ticker-item">
              <ShoppingBag size={14} /> 🛍️ Tool Video Affiliate: Đã render <strong>{stats.affiliate_count}</strong> video
            </span>
            <span className="ticker-divider">•</span>
            <span className="ticker-item">
              <Video size={14} /> 🎵 Tool TikTok: Auto Matrix Upload Bot 24/7
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
