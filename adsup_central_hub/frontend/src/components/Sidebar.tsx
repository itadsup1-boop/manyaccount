import { useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Newspaper,
  Users,
  Video,
  ShoppingBag,
  ChevronDown,
  ChevronRight,
  Workflow,
  FileText,
  Target,
  Type,
  BrainCircuit,
  Mic,
  UsersRound,
  ClipboardCheck,
  LayoutDashboard,
  Rss,
  Settings,
  FolderOpen,
  Shirt,
  PlayCircle,
  Zap,
} from 'lucide-react';

interface MenuSubItem {
  tabId: string;
  label: string;
  icon: React.ElementType;
}

interface ToolGroup {
  id: string;
  basePath: string;
  title: string;
  icon: React.ElementType;
  color: string;
  subItems: MenuSubItem[];
}

const TOOL_GROUPS: ToolGroup[] = [
  {
    id: 'article',
    basePath: '/article',
    title: 'Tool Bài Báo',
    icon: Newspaper,
    color: '#4f46e5',
    subItems: [
      { tabId: 'pipeline', label: 'Pipeline & Dựng Video', icon: Workflow },
      { tabId: 'sources', label: 'Nguồn Bài Báo', icon: FileText },
      { tabId: 'content', label: 'Chỉ Đạo Nội Dung', icon: Target },
      { tabId: 'display', label: 'Chữ Trên Video', icon: Type },
      { tabId: 'prompt', label: 'Cấu Hình Prompt', icon: BrainCircuit },
      { tabId: 'voice', label: 'Cấu Hình Voice', icon: Mic },
    ],
  },
  {
    id: 'facebook',
    basePath: '/facebook',
    title: 'Tool Facebook',
    icon: Users,
    color: '#2563eb',
    subItems: [
      { tabId: 'pipeline', label: 'Pipeline Remix', icon: Workflow },
      { tabId: 'sources', label: 'Nguồn Page', icon: FileText },
      { tabId: 'groups', label: 'Nguồn Group', icon: UsersRound },
      { tabId: 'group-review', label: 'Chờ Duyệt Group', icon: ClipboardCheck },
      { tabId: 'content', label: 'Chỉ Đạo Nội Dung', icon: Target },
      { tabId: 'display', label: 'Chữ Trên Video', icon: Type },
      { tabId: 'voice', label: 'Cấu Hình Voice', icon: Mic },
    ],
  },
  {
    id: 'tiktok',
    basePath: '/tiktok',
    title: 'Tool TikTok',
    icon: Video,
    color: '#059669',
    subItems: [
      { tabId: 'dashboard', label: 'Dashboard Analytics', icon: LayoutDashboard },
      { tabId: 'accounts', label: 'Quản Lý Tài Khoản', icon: UsersRound },
      { tabId: 'channels', label: 'Danh Sách Kênh', icon: Rss },
      { tabId: 'content', label: 'Chỉ Đạo Nội Dung', icon: Target },
      { tabId: 'api', label: 'Cấu Hình API & Bot', icon: Settings },
    ],
  },
  {
    id: 'affiliate',
    basePath: '/affiliate',
    title: 'Tool Video Affiliate',
    icon: ShoppingBag,
    color: '#d97706',
    subItems: [
      { tabId: 'media', label: 'Quản Lý Kho Media', icon: FolderOpen },
      { tabId: 'grok', label: 'Phân Tích Motion Grok', icon: BrainCircuit },
      { tabId: 'outfit', label: 'Outfit & Prompt Editor', icon: Shirt },
      { tabId: 'queue', label: 'Hàng Chờ Render Queue', icon: PlayCircle },
    ],
  },
];

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const currentPath = location.pathname;
  const searchParams = new URLSearchParams(location.search);
  const currentTab = searchParams.get('tab');

  // Open group state (expand current active tool by default)
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    article: currentPath.includes('/article') || currentPath === '/',
    facebook: currentPath.includes('/facebook'),
    tiktok: currentPath.includes('/tiktok'),
    affiliate: currentPath.includes('/affiliate'),
  });

  const toggleGroup = (groupId: string, basePath: string) => {
    setOpenGroups((prev) => ({
      ...prev,
      [groupId]: !prev[groupId],
    }));
    // If clicking main tool, navigate to its base route if not already there
    if (!currentPath.includes(basePath)) {
      navigate(basePath);
    }
  };

  return (
    <aside className="sidebar-white">
      <div className="sidebar-white__brand">
        <Zap size={22} className="brand-icon" />
        <span className="brand-title">Adsup Central Hub</span>
      </div>

      <nav className="sidebar-white__nav">
        {TOOL_GROUPS.map((group) => {
          const GroupIcon = group.icon;
          const isGroupActive = currentPath.includes(group.basePath);
          const isOpen = !!openGroups[group.id];

          return (
            <div
              key={group.id}
              className={`tool-dropdown-group ${isOpen ? 'is-open' : ''} ${isGroupActive ? 'is-active' : ''}`}
            >
              {/* Main Tool Button (Header) */}
              <div
                className={`tool-dropdown-header ${isGroupActive ? 'active-header' : ''}`}
                onClick={() => toggleGroup(group.id, group.basePath)}
              >
                <div className="tool-dropdown-title">
                  <div
                    className="tool-icon-badge"
                    style={{
                      backgroundColor: isGroupActive ? group.color : `${group.color}15`,
                      color: isGroupActive ? '#ffffff' : group.color,
                    }}
                  >
                    <GroupIcon size={18} />
                  </div>
                  <span className="tool-title-text">{group.title}</span>
                </div>
                <button
                  type="button"
                  className="arrow-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setOpenGroups((prev) => ({ ...prev, [group.id]: !prev[group.id] }));
                  }}
                >
                  {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
              </div>

              {/* Dropdown Sub-Items */}
              {isOpen && (
                <div className="tool-dropdown-subitems">
                  {group.subItems.map((sub) => {
                    const SubIcon = sub.icon;
                    const subUrl = `${group.basePath}?tab=${sub.tabId}`;
                    const isSubActive =
                      isGroupActive &&
                      (currentTab === sub.tabId || (!currentTab && sub.tabId === group.subItems[0].tabId));

                    return (
                      <NavLink
                        key={sub.tabId}
                        to={subUrl}
                        className={`subitem-link ${isSubActive ? 'subitem-active' : ''}`}
                      >
                        <SubIcon size={14} />
                        <span>{sub.label}</span>
                      </NavLink>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="sidebar-white__footer">
        <p>Adsup Hub v3.0 • Clean White UI</p>
      </div>
    </aside>
  );
}
