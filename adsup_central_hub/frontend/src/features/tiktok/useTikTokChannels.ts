import type { Dispatch, SetStateAction } from 'react';

import { DEFAULT_SUBTITLE_SETTINGS, DEFAULT_TITLE_TEXT_SETTINGS } from './contentProfiles';

type ChannelDraft = { url: string; limit: number };

type Params = {
  accounts: any[];
  setAccounts: Dispatch<SetStateAction<any[]>>;
  selectedAccountId: string;
  newChannel: ChannelDraft;
  setNewChannel: Dispatch<SetStateAction<ChannelDraft>>;
  fetchAccounts: () => void;
};

export function useTikTokChannels({
  accounts,
  setAccounts,
  selectedAccountId,
  newChannel,
  setNewChannel,
  fetchAccounts,
}: Params) {
  const handleAddChannel = () => {
    if (!selectedAccountId || !newChannel.url) return;
    const account = accounts.find(a => a.tiktok_id === selectedAccountId);
    if (!account) return;

    const updatedChannels = [...(account.channels || []), {
      url: newChannel.url,
      limit: newChannel.limit,
      render_settings: {
        edit_mode: 'Có Frame Full (Tiktok)',
        title_settings: { source_start: 2.0, source_end: 5.0, zoom_factor: 1.0, manual_x_offset: 0, manual_y_offset: 100 },
        content_settings: { source_start: 10.0, source_end: "auto", zoom_factor: 1.05, manual_x_offset: 0, manual_y_offset: -11 },
        text_overlay_settings: { ...DEFAULT_TITLE_TEXT_SETTINGS },
        text_content_settings: { text_color: "#ffffff", stroke_width: 0, font_size: 45, box_y_start: 0.73, box_y_end: 0.83, box_width_percentage: 0.65, font_filename: "Inter_18pt-Bold.ttf" },
        subtitle_settings: { ...DEFAULT_SUBTITLE_SETTINGS },
        assets: { title_frame_filename: "", content_frame_filename: "", title_logo_filename: "", content_logo_filename: "", title_logo_width_percentage: 0.14, title_logo_x: "main_w-overlay_w-30", title_logo_y: "30", content_logo_width_percentage: 0.14, content_logo_x: "main_w-overlay_w-30", content_logo_y: "30" }
      }
    }];

    fetch(`/api/tiktok/accounts/${selectedAccountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channels: updatedChannels })
    }).then(() => {
      setNewChannel({ url: '', limit: 3 });
      fetchAccounts();
    });
  };

  const handleDeleteChannel = (channelIdx: number) => {
    if (!selectedAccountId) return;
    const account = accounts.find(a => a.tiktok_id === selectedAccountId);
    if (!account) return;

    const updatedChannels = account.channels.filter((_: any, idx: number) => idx !== channelIdx);

    fetch(`/api/tiktok/accounts/${selectedAccountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channels: updatedChannels })
    }).then(() => fetchAccounts());
  };

  const handleChannelSubtitleSettings = (
    channelIdx: number,
    updates: Record<string, number | boolean>
  ) => {
    setAccounts(prev => prev.map(acc => {
      if (acc.tiktok_id !== selectedAccountId) return acc;
      const channels = (acc.channels || []).map((channel: any, idx: number) => {
        if (idx !== channelIdx) return channel;
        const nextMargin = updates.margin_v === undefined
          ? channel.render_settings?.subtitle_settings?.margin_v ?? DEFAULT_SUBTITLE_SETTINGS.margin_v
          : Math.max(60, Math.min(760, Number(updates.margin_v)));
        const nextFontSize = updates.font_size === undefined
          ? channel.render_settings?.subtitle_settings?.font_size ?? DEFAULT_SUBTITLE_SETTINGS.font_size
          : Math.max(46, Math.min(76, Number(updates.font_size)));
        return {
          ...channel,
          render_settings: {
            ...(channel.render_settings || {}),
            subtitle_settings: {
              ...DEFAULT_SUBTITLE_SETTINGS,
              ...(channel.render_settings?.subtitle_settings || {}),
              ...updates,
              margin_v: nextMargin,
              font_size: nextFontSize,
              adaptive_long_caption: false,
              position_mode: 'manual'
            }
          }
        };
      });
      return { ...acc, channels };
    }));
  };

  const handleChannelTitleSettings = (
    channelIdx: number,
    updates: Record<string, number | string>
  ) => {
    setAccounts(prev => prev.map(acc => {
      if (acc.tiktok_id !== selectedAccountId) return acc;
      const channels = (acc.channels || []).map((channel: any, idx: number) => {
        if (idx !== channelIdx) return channel;
        return {
          ...channel,
          render_settings: {
            ...(channel.render_settings || {}),
            text_overlay_settings: {
              ...DEFAULT_TITLE_TEXT_SETTINGS,
              ...(channel.render_settings?.text_overlay_settings || {}),
              ...updates,
              position_mode: 'manual'
            }
          }
        };
      });
      return { ...acc, channels };
    }));
  };

  const handleChannelSubtitlePosition = (channelIdx: number, marginV: number) => {
    handleChannelSubtitleSettings(channelIdx, { margin_v: marginV });
  };

  const handleChannelSubtitleFontSize = (channelIdx: number, fontSize: number) => {
    handleChannelSubtitleSettings(channelIdx, { font_size: fontSize });
  };

  const handleSaveChannelRenderSettings = (channelIdx: number) => {
    const account = accounts.find(acc => acc.tiktok_id === selectedAccountId);
    if (!account) return;
    const sanitizedChannels = (account.channels || []).map((channel: any) => ({
      ...channel,
      render_settings: {
        ...(channel.render_settings || {}),
        subtitle_settings: {
          ...DEFAULT_SUBTITLE_SETTINGS,
          ...(channel.render_settings?.subtitle_settings || {}),
          enabled: false
        }
      }
    }));
    fetch(`/api/tiktok/accounts/${selectedAccountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channels: sanitizedChannels })
    }).then(res => res.json()).then(data => {
      if (data.status === 'success') {
        alert(`Đã lưu bố cục và khóa tắt karaoke cho nguồn #${channelIdx + 1}.`);
        fetchAccounts();
      } else {
        alert('Lỗi lưu bố cục chữ: ' + (data.error || 'Không rõ lỗi'));
      }
    });
  };

  const handleApplySubtitleToAllChannels = (channelIdx: number) => {
    const account = accounts.find(acc => acc.tiktok_id === selectedAccountId);
    if (!account) return;
    const sourceChannel = (account.channels || [])[channelIdx];
    if (!sourceChannel) return;
    const subtitleSettings = {
      ...DEFAULT_SUBTITLE_SETTINGS,
      ...(sourceChannel.render_settings?.subtitle_settings || {}),
      enabled: false,
      adaptive_long_caption: false,
      position_mode: 'manual'
    };
    const updatedChannels = (account.channels || []).map((channel: any) => ({
      ...channel,
      render_settings: {
        ...(channel.render_settings || {}),
        subtitle_settings: { ...subtitleSettings }
      }
    }));

    setAccounts(prev => prev.map(acc => (
      acc.tiktok_id === selectedAccountId
        ? { ...acc, channels: updatedChannels }
        : acc
    )));
    fetch(`/api/tiktok/accounts/${selectedAccountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channels: updatedChannels })
    }).then(res => res.json()).then(data => {
      if (data.status === 'success') {
        alert('Đã áp dụng cùng vị trí và cỡ chữ cho tất cả nguồn của tài khoản.');
        fetchAccounts();
      } else {
        alert('Lỗi áp dụng subtitle: ' + (data.error || 'Không rõ lỗi'));
      }
    });
  };

  const handleApplyTitleToAllChannels = (channelIdx: number) => {
    const account = accounts.find(acc => acc.tiktok_id === selectedAccountId);
    if (!account) return;
    const sourceChannel = (account.channels || [])[channelIdx];
    if (!sourceChannel) return;
    const titleSettings = {
      ...DEFAULT_TITLE_TEXT_SETTINGS,
      ...(sourceChannel.render_settings?.text_overlay_settings || {}),
      position_mode: 'manual'
    };
    const updatedChannels = (account.channels || []).map((channel: any) => ({
      ...channel,
      render_settings: {
        ...(channel.render_settings || {}),
        text_overlay_settings: { ...titleSettings }
      }
    }));

    setAccounts(prev => prev.map(acc => (
      acc.tiktok_id === selectedAccountId
        ? { ...acc, channels: updatedChannels }
        : acc
    )));
    fetch(`/api/tiktok/accounts/${selectedAccountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channels: updatedChannels })
    }).then(res => res.json()).then(data => {
      if (data.status === 'success') {
        alert('Đã áp dụng cùng vị trí title cho tất cả nguồn của tài khoản.');
        fetchAccounts();
      } else {
        alert('Lỗi áp dụng title: ' + (data.error || 'Không rõ lỗi'));
      }
    });
  };


  return {
    handleAddChannel,
    handleDeleteChannel,
    handleChannelSubtitlePosition,
    handleChannelSubtitleFontSize,
    handleChannelTitleSettings,
    handleSaveChannelRenderSettings,
    handleApplySubtitleToAllChannels,
    handleApplyTitleToAllChannels,
  };
}
