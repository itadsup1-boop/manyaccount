import { useEffect, useState } from 'react';

import {
  buildSuggestedContentProfile,
  emptyContentProfile,
  fillMissingProfile,
  formatContentProfilePreview,
  normalizeSavedContentProfile,
} from './contentProfiles';
import { useTikTokChannels } from './useTikTokChannels';
import { fetchScheduleConfig, saveScheduleConfig } from './systemConfigApi';

const AUTO_REMIX_ENABLED = false;

export function useTikTokController() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>(['[Matrix Bot] Sẵn sàng hoạt động...']);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [newAcc, setNewAcc] = useState({ tiktok_id: '', email: '', machine_id: '1' });
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [selectedProfileAccountId, setSelectedProfileAccountId] = useState('');
  const [profileDraft, setProfileDraft] = useState<Record<string, string>>(buildSuggestedContentProfile());
  const [savedProfileDraft, setSavedProfileDraft] = useState<Record<string, string>>(emptyContentProfile);
  const [newChannel, setNewChannel] = useState({ url: '', limit: 3 });
  const [cloneLogs, setCloneLogs] = useState<string[]>(['[Hệ thống] Sẵn sàng...']);
  const [isCloneRunning, setIsCloneRunning] = useState(false);
  const [scheduleTimes, setScheduleTimes] = useState<string[]>([]);
  const [scheduleStatus, setScheduleStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [scheduleError, setScheduleError] = useState('');
  const [newTime, setNewTime] = useState('');
  const [apiSettings, setApiSettings] = useState({ ai_studio_url: '', api_key: '', voice_id: '', sheet_url: '', tele_token: '', tele_chatid: '', machine_id: '1' });

  const fetchAccounts = () => {
    fetch(`/api/tiktok/accounts`)
      .then(res => res.json())
      .then(data => {
        if (!data.error) setAccounts(data);
      })
      .catch(console.error);
  };

  const [aiProvider, setAiProvider] = useState<string>('chatgpt');

  const reloadSchedule = async (signal?: AbortSignal) => {
    try {
      const config = await fetchScheduleConfig(signal);
      setScheduleTimes(config.crawl_times);
      setScheduleStatus('ready');
      setScheduleError('');
    } catch (error) {
      if (signal?.aborted) return;
      setScheduleStatus('error');
      setScheduleError(error instanceof Error ? error.message : 'Không kết nối được máy chủ.');
    }
  };

  const loadSystemConfigs = () => {
    void reloadSchedule();

    fetch(`/api/system/config/api_settings`)
      .then(res => res.json())
      .then(data => {
        if (data.ai_studio_url !== undefined) setApiSettings(data);
      });

    fetch(`/api/ai/provider`)
      .then(res => res.json())
      .then(data => {
        if (data.provider) setAiProvider(data.provider);
      })
      .catch(() => {});
  };

  const fetchTikTokLogs = () => {
    fetch(`/api/tiktok/logs`)
      .then(res => res.json())
      .then(data => {
        if (data.logs) setLogs(data.logs);
        if (data.is_running !== undefined) setIsRunning(data.is_running);
      })
      .catch(() => {});
  };

  const fetchCloneLogs = () => {
    fetch(`/api/tiktok/clone/logs`)
      .then(res => res.json())
      .then(data => {
        if (data.logs) setCloneLogs(data.logs);
        if (data.is_running !== undefined) setIsCloneRunning(data.is_running);
      })
      .catch(() => {});
  };

  useEffect(() => {
    if (!AUTO_REMIX_ENABLED && activeTab === 'clone') {
      setActiveTab('dashboard');
    }
  }, [activeTab]);

  useEffect(() => {
    fetchAccounts();
    loadSystemConfigs();
    fetchTikTokLogs();
    fetchCloneLogs();

    // Frontend and backend can start a few seconds apart. Refreshing the
    // schedule prevents one failed first request from leaving the UI empty.
    const scheduleRefresh = window.setInterval(() => {
      void reloadSchedule();
    }, 15_000);
    return () => window.clearInterval(scheduleRefresh);
  }, []);

  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(fetchTikTokLogs, 1000);
    return () => clearInterval(interval);
  }, [isRunning]);

  useEffect(() => {
    if (!isCloneRunning) return;
    const interval = setInterval(fetchCloneLogs, 1000);
    return () => clearInterval(interval);
  }, [isCloneRunning]);

  const handleStart = () => {
    setIsRunning(true);
    fetch(`/api/tiktok/start`, { method: 'POST' });
  };

  const handleStop = () => {
    setIsRunning(false);
    fetch(`/api/tiktok/stop`, { method: 'POST' });
  };

  const handleStartClone = () => {
    if (!AUTO_REMIX_ENABLED) {
      setCloneLogs(prev => [
        "[Hệ thống] Auto Remix đang tạm tắt theo cấu hình hiện tại.",
        ...prev.slice(0, 50)
      ]);
      return;
    }
    setIsCloneRunning(true);
    fetch(`/api/tiktok/clone/start`, { method: 'POST' });
  };

  const handleStopClone = () => {
    setIsCloneRunning(false);
    fetch(`/api/tiktok/clone/stop`, { method: 'POST' });
  };

  const handleOpenChrome = (profile: string) => {
    if (!profile) return;
    fetch(`/api/tiktok/chrome/${profile}`, { method: 'POST' });
  };

  const handleOpenChatGPT = (tiktokId?: string) => {
    const suffix = tiktokId ? `/${encodeURIComponent(tiktokId)}` : '';
    fetch(`/api/chatgpt/chrome${suffix}`, { method: 'POST' });
  };

  const handleOpenGemini = (tiktokId?: string) => {
    const suffix = tiktokId ? `/${encodeURIComponent(tiktokId)}` : '';
    fetch(`/api/gemini/chrome${suffix}`, { method: 'POST' });
  };

  const handleSetAiProvider = (provider: string) => {
    setAiProvider(provider);
    fetch(`/api/ai/provider`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider }),
    });
  };

  const handleCloneChatGPTProfiles = () => {
    fetch(`/api/chatgpt/clone-profiles`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          alert(`Đã nhân bản ChatGPT chung cho ${data.total || 0} TikTok ID.`);
        } else {
          alert(`Lỗi nhân bản ChatGPT: ${data.error || 'Không rõ lỗi'}`);
        }
      })
      .catch(err => alert(`Lỗi nhân bản ChatGPT: ${err}`));
  };

  const handleCloneGeminiProfiles = () => {
    fetch(`/api/gemini/clone-profiles`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          alert(`Đã nhân bản Gemini chung cho ${data.total || 0} TikTok ID.`);
        } else {
          alert(`Lỗi nhân bản Gemini: ${data.error || 'Không rõ lỗi'}`);
        }
      })
      .catch(err => alert(`Lỗi nhân bản Gemini: ${err}`));
  };

  const handleAddAccount = () => {
    if (!newAcc.tiktok_id || !newAcc.email) return;
    const clean_id = newAcc.tiktok_id.replace(/[^a-zA-Z0-9_-]/g, "");
    fetch(`/api/tiktok/accounts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tiktok_id: newAcc.tiktok_id,
        email: newAcc.email,
        password: '',
        chrome_profile: clean_id,
        machine_id: newAcc.machine_id,
        active: true,
        channels: []
      })
    }).then(() => {
      setNewAcc({ tiktok_id: '', email: '', machine_id: '1' });
      fetchAccounts();
    });
  };

  const handleDeleteAccount = (id: string) => {
    fetch(`/api/tiktok/accounts/${id}`, { method: 'DELETE' })
      .then(() => fetchAccounts());
  };

  const handleToggleActive = (id: string, currentStatus: boolean) => {
    fetch(`/api/tiktok/accounts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: !currentStatus })
    }).then(() => fetchAccounts());
  };

  const handleUpdateLimit = (id: string, limit: number) => {
    fetch(`/api/tiktok/accounts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_limit_per_run: limit })
    });
  };

  const handleSelectProfileAccount = (id: string) => {
    setSelectedProfileAccountId(id);
    if (!id) {
      setSavedProfileDraft(emptyContentProfile);
      setProfileDraft(buildSuggestedContentProfile());
      return;
    }
    const account = accounts.find(acc => acc.tiktok_id === id);
    const savedProfile = normalizeSavedContentProfile(account?.content_profile);
    setSavedProfileDraft(savedProfile);
    setProfileDraft(fillMissingProfile(savedProfile, id));
  };

  const handleProfileDraftChange = (key: string, value: string) => {
    setProfileDraft(prev => ({ ...prev, [key]: value }));
  };

  const handleFillMissingProfile = () => {
    setProfileDraft(prev => fillMissingProfile(prev, selectedProfileAccountId));
  };

  const handleRestoreSavedProfile = () => {
    setProfileDraft(fillMissingProfile(savedProfileDraft, selectedProfileAccountId));
  };

  const handleSaveAccountInstruction = () => {
    if (!selectedProfileAccountId) return;
    const account = accounts.find(acc => acc.tiktok_id === selectedProfileAccountId);
    const mergedProfile = {
      ...normalizeSavedContentProfile(account?.content_profile),
      ...profileDraft
    };

    fetch(`/api/tiktok/accounts/${selectedProfileAccountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_profile: mergedProfile })
    }).then(res => res.json()).then(data => {
      if (data.status === 'success') {
        setSavedProfileDraft(normalizeSavedContentProfile(mergedProfile));
        setAccounts(prev => prev.map(acc => acc.tiktok_id === selectedProfileAccountId ? { ...acc, content_profile: mergedProfile } : acc));
        alert('Đã lưu chỉ đạo nội dung cho tài khoản TikTok!');
        fetchAccounts();
      } else {
        alert('Lỗi: ' + data.error);
      }
    });
  };

  const {
    handleAddChannel,
    handleDeleteChannel,
    handleChannelSubtitlePosition,
    handleChannelSubtitleFontSize,
    handleChannelTitleSettings,
    handleSaveChannelRenderSettings,
    handleApplySubtitleToAllChannels,
    handleApplyTitleToAllChannels,
  } = useTikTokChannels({
    accounts,
    setAccounts,
    selectedAccountId,
    newChannel,
    setNewChannel,
    fetchAccounts,
  });
  const handleAddScheduleTime = async () => {
    const timeRegex = /^([01]?[0-9]|2[0-3]):[0-5][0-9]$/;
    if (!timeRegex.test(newTime)) {
      alert("Sai định dạng! Hãy nhập HH:MM (VD: 08:30)");
      return;
    }
    const formatted = newTime.length === 4 ? "0" + newTime : newTime;
    if (scheduleTimes.includes(formatted)) return;

    const newTimes = [...scheduleTimes, formatted].sort();

    try {
      setScheduleStatus('loading');
      const saved = await saveScheduleConfig(newTimes);
      setScheduleTimes(saved.crawl_times);
      setNewTime('');
      setScheduleStatus('ready');
      setScheduleError('');
    } catch (error) {
      setScheduleStatus('error');
      setScheduleError(error instanceof Error ? error.message : 'Không lưu được lịch.');
    }
  };

  const handleDeleteScheduleTime = async (timeVal: string) => {
    const newTimes = scheduleTimes.filter(t => t !== timeVal);
    try {
      setScheduleStatus('loading');
      const saved = await saveScheduleConfig(newTimes);
      setScheduleTimes(saved.crawl_times);
      setScheduleStatus('ready');
      setScheduleError('');
    } catch (error) {
      setScheduleStatus('error');
      setScheduleError(error instanceof Error ? error.message : 'Không xóa được lịch.');
    }
  };

  const handleSaveApiSettings = () => {
    fetch(`/api/system/config/api_settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(apiSettings)
    }).then(() => alert("Đã lưu Cấu hình hệ thống thành công!"));
  };

  const savedProfilePreview = formatContentProfilePreview(savedProfileDraft);


  return {
    activeTab,
    setActiveTab,
    isRunning,
    logs,
    accounts,
    newAcc,
    setNewAcc,
    selectedAccountId,
    setSelectedAccountId,
    selectedProfileAccountId,
    profileDraft,
    newChannel,
    setNewChannel,
    cloneLogs,
    isCloneRunning,
    scheduleTimes,
    scheduleStatus,
    scheduleError,
    reloadSchedule,
    newTime,
    setNewTime,
    apiSettings,
    setApiSettings,
    aiProvider,
    fetchAccounts,
    handleStart,
    handleStop,
    handleStartClone,
    handleStopClone,
    handleOpenChrome,
    handleOpenChatGPT,
    handleOpenGemini,
    handleSetAiProvider,
    handleCloneChatGPTProfiles,
    handleCloneGeminiProfiles,
    handleAddAccount,
    handleDeleteAccount,
    handleToggleActive,
    handleUpdateLimit,
    handleSelectProfileAccount,
    handleProfileDraftChange,
    handleFillMissingProfile,
    handleRestoreSavedProfile,
    handleSaveAccountInstruction,
    handleAddChannel,
    handleDeleteChannel,
    handleChannelSubtitlePosition,
    handleChannelSubtitleFontSize,
    handleChannelTitleSettings,
    handleSaveChannelRenderSettings,
    handleApplySubtitleToAllChannels,
    handleApplyTitleToAllChannels,
    handleAddScheduleTime,
    handleDeleteScheduleTime,
    handleSaveApiSettings,
    savedProfilePreview,
  };
}

export type TikTokController = ReturnType<typeof useTikTokController>;
