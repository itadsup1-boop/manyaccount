import { useState, useEffect } from 'react';
import { Activity, Newspaper, Users, Video } from 'lucide-react';

export default function Dashboard() {
  const [stats, setStats] = useState({ active_tools: 0, articles_processed: 0, facebook_posts: 0, tiktok_uploads: 0, system_health: '' });

  useEffect(() => {
    fetch(`/api/dashboard/stats`)
      .then(res => res.json())
      .then(data => setStats(data))
      .catch(console.error);
  }, []);

  const cards = [
    { label: 'Công cụ đang chạy', value: stats.active_tools, icon: <Activity size={22} />, color: '#6366f1' },
    { label: 'Bài báo đã xử lý', value: stats.articles_processed, icon: <Newspaper size={22} />, color: '#10b981' },
    { label: 'Facebook Posts', value: stats.facebook_posts, icon: <Users size={22} />, color: '#3b82f6' },
    { label: 'TikTok Uploads', value: stats.tiktok_uploads, icon: <Video size={22} />, color: '#f59e0b' },
  ];

  return (
    <div>
      <h2 className="page-title">Dashboard Tổng Quan</h2>
      <div className="grid">
        {cards.map((card, idx) => (
          <div className="card stat-card" key={idx}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
              <div style={{
                width: 40, height: 40, borderRadius: 10,
                background: `${card.color}15`, color: card.color,
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}>
                {card.icon}
              </div>
              <span className="stat-label">{card.label}</span>
            </div>
            <span className="stat-value">{card.value}</span>
          </div>
        ))}
      </div>
      <div className="card">
        <h3 style={{ marginBottom: '0.75rem' }}>⚡ System Health</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{
            width: 10, height: 10, borderRadius: '50%',
            background: stats.system_health === 'Good' ? 'var(--success)' : 'var(--warning)',
            boxShadow: `0 0 8px ${stats.system_health === 'Good' ? 'var(--success-glow)' : 'var(--danger-glow)'}`
          }} />
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            {stats.system_health === 'Good' 
              ? 'Tất cả hệ thống đang hoạt động bình thường. Máy chủ sẵn sàng nhận lệnh.'
              : 'Đang kiểm tra trạng thái hệ thống...'}
          </p>
        </div>
      </div>
    </div>
  );
}
