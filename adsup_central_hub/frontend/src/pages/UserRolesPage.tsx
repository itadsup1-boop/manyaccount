import { useState, useEffect } from 'react';
import { ShieldCheck, UserCheck, RefreshCw, KeyRound, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { UserProfile } from '../context/AuthContext';
import ToolPageHeader from '../components/ui/ToolPageHeader';
import '../features/tiktok/tiktok.css';

export default function UserRolesPage() {
  const { user, isAdmin, updateRole } = useAuth();
  const navigate = useNavigate();
  const [usersList, setUsersList] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/auth/users');
      if (res.ok) {
        const data = await res.json();
        setUsersList(data.users || []);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleRoleToggle = async (targetEmail: string, currentRole: 'admin' | 'user') => {
    const newRole = currentRole === 'admin' ? 'user' : 'admin';
    await updateRole(targetEmail, newRole);
    fetchUsers();
  };

  if (!isAdmin) {
    return (
      <div className="card" style={{ padding: '3rem', textAlign: 'center' }}>
        <ShieldCheck size={48} color="var(--danger)" style={{ margin: '0 auto 1rem' }} />
        <h2>Quyền truy cập bị từ chối</h2>
        <p style={{ color: 'var(--text-secondary)', margin: '1rem 0' }}>
          Bạn cần quyền <strong>Admin</strong> để xem và quản lý danh sách phân quyền người dùng.
        </p>
        <button className="btn btn-primary" onClick={() => navigate('/article')}>
          Quay lại Trang chính
        </button>
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ marginBottom: '1rem' }}>
        <button className="btn btn-ghost" onClick={() => navigate('/article')} style={{ gap: '6px' }}>
          <ArrowLeft size={16} /> Quay lại Tool
        </button>
      </div>

      <ToolPageHeader
        title="Quản Lý Quyền Hệ Thống (RBAC)"
        description="Chỉ những người dùng được gán quyền Admin mới xem và thao tác được toàn bộ giao diện điều khiển"
        status={(
          <span className="status-pill status-pill--success">
            👑 Admin: {user?.email}
          </span>
        )}
      />

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <div>
            <h3>Danh sách Tài khoản đã Đăng nhập</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
              Bấm nút "Đổi quyền" để nâng cấp một người dùng thành Admin hoặc hạ quyền thành User thông thường.
            </p>
          </div>
          <button className="btn btn-ghost" onClick={fetchUsers} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Làm mới
          </button>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '0.75rem' }}>Người dùng</th>
                <th style={{ padding: '0.75rem' }}>Email</th>
                <th style={{ padding: '0.75rem' }}>Role Hiện tại</th>
                <th style={{ padding: '0.75rem', width: '160px' }}>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {usersList.map((u) => (
                <tr key={u.email} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <td style={{ padding: '0.75rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {u.picture ? (
                      <img src={u.picture} alt={u.name} style={{ width: 32, height: 32, borderRadius: '50%' }} />
                    ) : (
                      <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#3b82f6', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}>
                        {u.name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <span style={{ fontWeight: 600 }}>{u.name}</span>
                  </td>
                  <td style={{ padding: '0.75rem', color: 'var(--info)' }}>{u.email}</td>
                  <td style={{ padding: '0.75rem' }}>
                    {u.role === 'admin' ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 10px', background: 'rgba(59, 130, 246, 0.2)', border: '1px solid #3b82f6', borderRadius: '12px', color: '#60a5fa', fontSize: '0.8rem', fontWeight: 700 }}>
                        <KeyRound size={13} /> ADMIN (Toàn quyền)
                      </span>
                    ) : (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 10px', background: 'rgba(16, 185, 129, 0.2)', border: '1px solid #10b981', borderRadius: '12px', color: '#34d399', fontSize: '0.8rem', fontWeight: 600 }}>
                        <UserCheck size={13} /> USER (Chỉ xem)
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '0.75rem' }}>
                    <button
                      className={`btn ${u.role === 'admin' ? 'btn-ghost' : 'btn-primary'}`}
                      style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
                      onClick={() => handleRoleToggle(u.email, u.role)}
                    >
                      {u.role === 'admin' ? 'Hạ xuống User' : 'Nâng lên Admin'}
                    </button>
                  </td>
                </tr>
              ))}
              {usersList.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    Chưa có danh sách user hoặc đang tải...
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
