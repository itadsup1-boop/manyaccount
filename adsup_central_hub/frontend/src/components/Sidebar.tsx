import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Newspaper, Users, Video } from 'lucide-react';

export default function Sidebar() {
  return (
    <div className="sidebar">
      <h1>Adsup Central Hub</h1>
      <div className="nav-links">
        <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <LayoutDashboard size={20} />
          <span>Dashboard Tổng</span>
        </NavLink>
        <NavLink to="/article" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <Newspaper size={20} />
          <span>Tool Tin Tức</span>
        </NavLink>
        <NavLink to="/facebook" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <Users size={20} />
          <span>Tool Facebook</span>
        </NavLink>
        <NavLink to="/tiktok" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <Video size={20} />
          <span>Tool TikTok</span>
        </NavLink>
      </div>
    </div>
  );
}
