import TikTokAccountsTab from '../features/tiktok/components/TikTokAccountsTab';
import TikTokApiTab from '../features/tiktok/components/TikTokApiTab';
import TikTokChannelsTab from '../features/tiktok/components/TikTokChannelsTab';
import TikTokContentTab from '../features/tiktok/components/TikTokContentTab';
import TikTokDashboardTab from '../features/tiktok/components/TikTokDashboardTab';
import TikTokTabs from '../features/tiktok/components/TikTokTabs';
import type { TikTokTabId } from '../features/tiktok/components/TikTokTabs';
import { useTikTokController } from '../features/tiktok/useTikTokController';
import ToolPageHeader from '../components/ui/ToolPageHeader';
import '../features/tiktok/tiktok.css';

export default function ToolTikTok() {
  const controller = useTikTokController();

  return (
    <div className="tiktok-page">
      <ToolPageHeader
        title="Tool TikTok"
        description="Matrix Bot"
        status={(
          <span className={`tiktok-page__status ${controller.isRunning ? 'is-running' : ''}`}>
            <span aria-hidden="true" />
            {controller.isRunning ? 'Đang vận hành' : 'Đang dừng'}
          </span>
        )}
      />

      <TikTokTabs
        activeTab={controller.activeTab}
        onChange={(tab: TikTokTabId) => controller.setActiveTab(tab)}
      />

      {controller.activeTab === 'dashboard' && <TikTokDashboardTab controller={controller} />}
      {controller.activeTab === 'accounts' && <TikTokAccountsTab controller={controller} />}
      {controller.activeTab === 'channels' && <TikTokChannelsTab controller={controller} />}
      {controller.activeTab === 'content' && <TikTokContentTab controller={controller} />}
      {controller.activeTab === 'api' && <TikTokApiTab controller={controller} />}
    </div>
  );
}
