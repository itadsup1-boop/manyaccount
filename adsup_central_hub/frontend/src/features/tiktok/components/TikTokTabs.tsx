import { Activity, KeyRound, Target, Users, Video } from 'lucide-react';
import ToolTabs from '../../../components/ui/ToolTabs';

export type TikTokTabId = 'dashboard' | 'accounts' | 'channels' | 'content' | 'api';

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: Activity },
  { id: 'accounts', label: 'Tài khoản', icon: Users },
  { id: 'channels', label: 'Quản lý kênh', icon: Video },
  { id: 'content', label: 'Chỉ đạo nội dung', icon: Target },
  { id: 'api', label: 'Cấu hình API', icon: KeyRound },
] as const;

type Props = {
  activeTab: string;
  onChange: (tab: TikTokTabId) => void;
};

export default function TikTokTabs({ activeTab, onChange }: Props) {
  return (
    <ToolTabs
      activeTab={activeTab as TikTokTabId}
      ariaLabel="Các mục Tool TikTok"
      tabs={TABS}
      onChange={onChange}
    />
  );
}
