import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  FolderOpen,
  BrainCircuit,
  Shirt,
  PlayCircle,
  Upload,
  Sparkles,
  Trash2,
  Play,
  Pause,
  RefreshCw,
  Image as ImageIcon,
  Video as VideoIcon,
  Mic,
  CheckCircle2,
  Clock,
  AlertCircle,
  Plus,
  Eye,
  X,
  FileVideo,
  MonitorPlay,
  Download,
  Film,
  Save,
} from 'lucide-react';
import ToolPageHeader from '../components/ui/ToolPageHeader';

interface AffiliateMediaFile {
  id: string;
  name: string;
  type: 'image' | 'video' | 'audio';
  size: number;
  url: string;
}

interface RenderQueueItem {
  id: string;
  row_index: number;
  image_file: string;
  video_file: string;
  audio_file: string;
  prompt: string;
  outfit: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  note: string;
  progress: number;
}

interface OutputVideoItem {
  id: string;
  filename: string;
  size: number;
  created_at: string;
  url: string;
}

export default function ToolAffiliate() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'media';

  const setActiveTab = (tab: string) => {
    setSearchParams({ tab });
  };

  // Media files state
  const [images, setImages] = useState<AffiliateMediaFile[]>([]);
  const [videos, setVideos] = useState<AffiliateMediaFile[]>([]);
  const [audios, setAudios] = useState<AffiliateMediaFile[]>([]);

  // Selected for rendering
  const [selectedImage, setSelectedImage] = useState<AffiliateMediaFile | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<AffiliateMediaFile | null>(null);
  const [selectedAudio, setSelectedAudio] = useState<AffiliateMediaFile | null>(null);

  // Preview Modal state
  const [previewMedia, setPreviewMedia] = useState<AffiliateMediaFile | null>(null);

  // Prompts & Outfit state
  const [motionPrompt, setMotionPrompt] = useState<string>(
    'Grok AI Analysis: Analyze subject movement, camera pan, zoom, body posture, lighting dynamics'
  );
  const [outfitDescription, setOutfitDescription] = useState<string>(
    'Trang phục hiện đại, lịch sự, phối màu hài hòa chuẩn phong cách Affiliate'
  );
  const [isSavingPrompt, setIsSavingPrompt] = useState<boolean>(false);
  const [promptNotice, setPromptNotice] = useState<string>('');

  // Render Queue & Output State
  const [queue, setQueue] = useState<RenderQueueItem[]>([]);
  const [outputs, setOutputs] = useState<OutputVideoItem[]>([]);
  const [isRendering, setIsRendering] = useState<boolean>(false);
  const [isGrokAnalyzing, setIsGrokAnalyzing] = useState<boolean>(false);

  // Chrome Launchers status state
  const [chromeNotice, setChromeNotice] = useState<string>('');

  // Load existing media, prompt & status on mount
  useEffect(() => {
    fetchMediaFiles();
    fetchQueueStatus();
    fetchMotionPrompt();
    fetchOutputs();
  }, []);

  const fetchMediaFiles = async () => {
    try {
      const res = await fetch('/api/affiliate/files');
      if (res.ok) {
        const data = await res.json();
        const imgs: AffiliateMediaFile[] = data.images || [];
        const vids: AffiliateMediaFile[] = data.videos || [];
        const auds: AffiliateMediaFile[] = data.audios || [];

        setImages(imgs);
        setVideos(vids);
        setAudios(auds);

        if (imgs.length > 0 && !selectedImage) setSelectedImage(imgs[0]);
        if (vids.length > 0 && !selectedVideo) setSelectedVideo(vids[0]);
        if (auds.length > 0 && !selectedAudio) setSelectedAudio(auds[0]);
      }
    } catch (err) {
      console.warn('API affiliate/files fallback offline');
    }
  };

  const fetchQueueStatus = async () => {
    try {
      const res = await fetch('/api/affiliate/queue-status');
      if (res.ok) {
        const data = await res.json();
        setQueue(data.queue || []);
        setIsRendering(data.is_rendering || false);
      }
    } catch (err) {
      console.warn('API affiliate/queue-status fallback offline');
    }
  };

  const fetchMotionPrompt = async () => {
    try {
      const res = await fetch('/api/affiliate/prompt/motion');
      if (res.ok) {
        const data = await res.json();
        if (data.prompt) setMotionPrompt(data.prompt);
      }
    } catch (err) {
      console.warn('API affiliate/prompt/motion fallback');
    }
  };

  const fetchOutputs = async () => {
    try {
      const res = await fetch('/api/affiliate/outputs');
      if (res.ok) {
        const data = await res.json();
        setOutputs(data.outputs || []);
      }
    } catch (err) {
      console.warn('API affiliate/outputs fallback');
    }
  };

  // Launch Chrome Grok
  const handleOpenGrokChrome = async () => {
    setChromeNotice('Đang khởi động Chrome Grok...');
    try {
      const res = await fetch('/api/affiliate/chrome/grok', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setChromeNotice(data.message || 'Đã mở Chrome Grok thành công');
      }
    } catch (err) {
      setChromeNotice('Lỗi khi mở Chrome Grok');
    } finally {
      setTimeout(() => setChromeNotice(''), 4000);
    }
  };

  // Launch Chrome Nano Banana
  const handleOpenNanoChrome = async () => {
    setChromeNotice('Đang khởi động Chrome Nano Banana...');
    try {
      const res = await fetch('/api/affiliate/chrome/nano', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setChromeNotice(data.message || 'Đã mở Chrome Nano Banana thành công');
      }
    } catch (err) {
      setChromeNotice('Lỗi khi mở Chrome Nano Banana');
    } finally {
      setTimeout(() => setChromeNotice(''), 4000);
    }
  };

  // Save Motion Prompt
  const handleSaveMotionPrompt = async () => {
    setIsSavingPrompt(true);
    setPromptNotice('');
    try {
      const res = await fetch('/api/affiliate/prompt/motion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: motionPrompt }),
      });
      if (res.ok) {
        setPromptNotice('✅ Đã lưu file Prompt thành công!');
      } else {
        setPromptNotice('❌ Lỗi khi lưu file Prompt');
      }
    } catch (err) {
      setPromptNotice('❌ Không thể kết nối Server để lưu Prompt');
    } finally {
      setIsSavingPrompt(false);
      setTimeout(() => setPromptNotice(''), 4000);
    }
  };

  // Media upload handler
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, category: 'image' | 'video' | 'audio') => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    formData.append('category', category);

    try {
      const res = await fetch('/api/affiliate/upload', {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        fetchMediaFiles();
      }
    } catch (err) {
      const file = files[0];
      const newMediaItem: AffiliateMediaFile = {
        id: String(Date.now()),
        name: file.name,
        type: category,
        size: file.size,
        url: URL.createObjectURL(file),
      };
      if (category === 'image') {
        setImages((prev) => [...prev, newMediaItem]);
        setSelectedImage(newMediaItem);
      }
      if (category === 'video') {
        setVideos((prev) => [...prev, newMediaItem]);
        setSelectedVideo(newMediaItem);
      }
      if (category === 'audio') {
        setAudios((prev) => [...prev, newMediaItem]);
        setSelectedAudio(newMediaItem);
      }
    }
  };

  // Grok AI Motion Analysis
  const handleRunGrokAnalysis = async () => {
    if (!selectedVideo) {
      alert('Vui lòng chọn 1 Video mẫu để phân tích chuyển động bằng Grok AI!');
      return;
    }
    setIsGrokAnalyzing(true);
    try {
      const res = await fetch('/api/affiliate/analyze-motion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_file: selectedVideo.name }),
      });
      if (res.ok) {
        const data = await res.json();
        setMotionPrompt(data.prompt || 'Phân tích Grok hoàn tất: Cinematic camera movement with smooth transition.');
      }
    } catch (err) {
      setMotionPrompt(
        `[Grok AI Prompt] Motion analysis for ${selectedVideo.name}: Character walks towards camera, smooth lighting shift, 4k ultra high detail.`
      );
    } finally {
      setIsGrokAnalyzing(false);
    }
  };

  // Add Job to Queue
  const handleAddToQueue = async () => {
    if (!selectedImage && !selectedVideo) {
      alert('Vui lòng chọn ít nhất Ảnh Nhân Vật hoặc Video Mẫu!');
      return;
    }

    const newItem: RenderQueueItem = {
      id: String(Date.now()),
      row_index: queue.length + 1,
      image_file: selectedImage ? selectedImage.name : 'Mặc định',
      video_file: selectedVideo ? selectedVideo.name : 'Mặc định',
      audio_file: selectedAudio ? selectedAudio.name : 'Mặc định',
      prompt: motionPrompt,
      outfit: outfitDescription,
      status: 'pending',
      note: 'Sẵn sàng render',
      progress: 0,
    };

    try {
      await fetch('/api/affiliate/start-render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newItem),
      });
    } catch (err) {
      // Local fallback
    }

    setQueue((prev) => [...prev, newItem]);
    setActiveTab('queue');
  };

  // Toggle Start / Pause Queue
  const handleToggleRenderQueue = async () => {
    const nextState = !isRendering;
    setIsRendering(nextState);
    try {
      await fetch(`/api/affiliate/${nextState ? 'start' : 'stop'}`, {
        method: 'POST',
      });
    } catch (err) {
      // Toggle state fallback
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="affiliate-page-container">
      <ToolPageHeader
        title="Tool Làm Video Affiliate (Veo Auto Hub)"
        description="Tự động phân tích Motion (Grok AI), quản lý Chrome Profile, ghép Video sản phẩm & xuất hàng loạt"
        status={
          <div className="tool-page-header__status" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span className={`status-badge-pill ${isRendering ? 'is-running' : 'is-stopped'}`}>
              <span className="dot-indicator" />
              {isRendering ? 'Đang Render Queue' : 'Hàng Chờ Dừng'}
            </span>
          </div>
        }
      />

      {/* CHROME CONTROL BAR & NOTICES */}
      <div className="clean-white-card" style={{ padding: '12px 18px', marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)' }}>Quản Lý Trình Duyệt AI:</span>
          <button
            type="button"
            className="btn-upload-subtle"
            style={{ backgroundColor: '#2563eb', color: '#ffffff', border: 'none', padding: '6px 14px', borderRadius: '6px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
            onClick={handleOpenGrokChrome}
          >
            <MonitorPlay size={15} /> 🌐 Quản Lý Grok AI
          </button>
          <button
            type="button"
            className="btn-upload-subtle"
            style={{ backgroundColor: '#0284c7', color: '#ffffff', border: 'none', padding: '6px 14px', borderRadius: '6px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
            onClick={handleOpenNanoChrome}
          >
            <MonitorPlay size={15} /> 🌐 Quản Lý Nano Banana
          </button>
        </div>

        {chromeNotice && (
          <span style={{ fontSize: '13px', color: '#d97706', fontWeight: 600, backgroundColor: '#fef3c7', padding: '4px 10px', borderRadius: '6px' }}>
            ⚡ {chromeNotice}
          </span>
        )}
      </div>

      {/* Sub-Tabs */}
      <div className="tool-tabs">
        <button
          type="button"
          className={`tool-tab ${activeTab === 'media' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('media')}
        >
          <FolderOpen size={16} />
          <span>Quản Lý Kho Media</span>
        </button>

        <button
          type="button"
          className={`tool-tab ${activeTab === 'grok' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('grok')}
        >
          <BrainCircuit size={16} />
          <span>Phân Tích Motion (Grok AI)</span>
        </button>

        <button
          type="button"
          className={`tool-tab ${activeTab === 'outfit' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('outfit')}
        >
          <Shirt size={16} />
          <span>Outfit & Prompt Editor</span>
        </button>

        <button
          type="button"
          className={`tool-tab ${activeTab === 'queue' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('queue')}
        >
          <PlayCircle size={16} />
          <span>Hàng Chờ Render ({queue.length})</span>
        </button>

        <button
          type="button"
          className={`tool-tab ${activeTab === 'outputs' ? 'is-active' : ''}`}
          onClick={() => {
            setActiveTab('outputs');
            fetchOutputs();
          }}
        >
          <Film size={16} />
          <span>Video Thành Phẩm ({outputs.length})</span>
        </button>
      </div>

      {/* TAB 1: KHO MEDIA */}
      {activeTab === 'media' && (
        <div className="tab-pane-content">
          <div className="media-grid-layout">
            {/* Cột 1: Ảnh Nhân Vật */}
            <div className="media-card">
              <div className="media-card__head">
                <div className="card-title-group">
                  <ImageIcon size={18} className="title-icon" />
                  <h4>Ảnh Nhân Vật</h4>
                </div>
                <label className="btn-upload-subtle">
                  <Upload size={14} /> Thêm Ảnh
                  <input type="file" accept="image/*" multiple onChange={(e) => handleFileUpload(e, 'image')} />
                </label>
              </div>

              <div className="media-card__body">
                {images.length === 0 ? (
                  <div className="media-dropzone">
                    <Upload size={28} className="dropzone-icon" />
                    <p className="dropzone-text">Kéo thả hoặc click chọn Ảnh Nhân Vật (.jpg, .png)</p>
                  </div>
                ) : (
                  <div className="media-items-stack">
                    {images.map((img) => (
                      <div
                        key={img.id}
                        className={`media-select-row ${selectedImage?.name === img.name ? 'is-selected' : ''}`}
                        onClick={() => setSelectedImage(img)}
                      >
                        <div className="media-item-info">
                          <ImageIcon size={16} />
                          <span>{img.name}</span>
                        </div>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="btn-preview-eye"
                            title="Xem Trước"
                            onClick={(e) => {
                              e.stopPropagation();
                              setPreviewMedia(img);
                            }}
                          >
                            <Eye size={15} />
                          </button>
                          {selectedImage?.name === img.name && <CheckCircle2 size={16} className="icon-checked" />}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Cột 2: Video Mẫu */}
            <div className="media-card">
              <div className="media-card__head">
                <div className="card-title-group">
                  <VideoIcon size={18} className="title-icon" />
                  <h4>Video Mẫu (Lấy Motion)</h4>
                </div>
                <label className="btn-upload-subtle">
                  <Upload size={14} /> Thêm Video
                  <input type="file" accept="video/*" multiple onChange={(e) => handleFileUpload(e, 'video')} />
                </label>
              </div>

              <div className="media-card__body">
                {videos.length === 0 ? (
                  <div className="media-dropzone">
                    <Upload size={28} className="dropzone-icon" />
                    <p className="dropzone-text">Kéo thả hoặc click chọn Video Mẫu (.mp4, .mov)</p>
                  </div>
                ) : (
                  <div className="media-items-stack">
                    {videos.map((vid) => (
                      <div
                        key={vid.id}
                        className={`media-select-row ${selectedVideo?.name === vid.name ? 'is-selected' : ''}`}
                        onClick={() => setSelectedVideo(vid)}
                      >
                        <div className="media-item-info">
                          <VideoIcon size={16} />
                          <span>{vid.name}</span>
                        </div>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="btn-preview-eye"
                            title="Xem Trước Video"
                            onClick={(e) => {
                              e.stopPropagation();
                              setPreviewMedia(vid);
                            }}
                          >
                            <Eye size={15} />
                          </button>
                          {selectedVideo?.name === vid.name && <CheckCircle2 size={16} className="icon-checked" />}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Cột 3: Voice Lồng Tiếng */}
            <div className="media-card">
              <div className="media-card__head">
                <div className="card-title-group">
                  <Mic size={18} className="title-icon" />
                  <h4>Voice Lồng Tiếng</h4>
                </div>
                <label className="btn-upload-subtle">
                  <Upload size={14} /> Thêm Voice
                  <input type="file" accept="audio/*" multiple onChange={(e) => handleFileUpload(e, 'audio')} />
                </label>
              </div>

              <div className="media-card__body">
                {audios.length === 0 ? (
                  <div className="media-dropzone">
                    <Upload size={28} className="dropzone-icon" />
                    <p className="dropzone-text">Kéo thả hoặc click chọn Audio Voice (.mp3, .wav)</p>
                  </div>
                ) : (
                  <div className="media-items-stack">
                    {audios.map((aud) => (
                      <div
                        key={aud.id}
                        className={`media-select-row ${selectedAudio?.name === aud.name ? 'is-selected' : ''}`}
                        onClick={() => setSelectedAudio(aud)}
                      >
                        <div className="media-item-info">
                          <Mic size={16} />
                          <span>{aud.name}</span>
                        </div>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="btn-preview-eye"
                            title="Nghe Thử Audio"
                            onClick={(e) => {
                              e.stopPropagation();
                              setPreviewMedia(aud);
                            }}
                          >
                            <Eye size={15} />
                          </button>
                          {selectedAudio?.name === aud.name && <CheckCircle2 size={16} className="icon-checked" />}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* KHU VỰC LIVE PREVIEW MEDIA ĐÃ CHỌN */}
          <div className="selected-preview-panel margin-top-md">
            <div className="panel-head">
              <h3><Eye size={18} /> Khung Xem Trước Media Đã Chọn (Live Preview)</h3>
              <p>Phần này giúp bạn kiểm tra hình ảnh, xem trước video chuyển động và phát thử audio trước khi thêm vào hàng chờ render.</p>
            </div>

            <div className="preview-grid-3">
              {/* Preview 1: Ảnh */}
              <div className="preview-box">
                <div className="box-title"><ImageIcon size={16} /> Xem Trực Tiếp Ảnh Nhân Vật</div>
                {selectedImage ? (
                  <div className="media-container image">
                    <img src={selectedImage.url} alt={selectedImage.name} />
                    <div className="media-caption">{selectedImage.name}</div>
                  </div>
                ) : (
                  <div className="preview-empty">Chưa chọn Ảnh Nhân Vật</div>
                )}
              </div>

              {/* Preview 2: Video */}
              <div className="preview-box">
                <div className="box-title"><FileVideo size={16} /> Xem Trực Tiếp Video Mẫu</div>
                {selectedVideo ? (
                  <div className="media-container video">
                    <video controls src={selectedVideo.url} key={selectedVideo.url} />
                    <div className="media-caption">{selectedVideo.name}</div>
                  </div>
                ) : (
                  <div className="preview-empty">Chưa chọn Video Mẫu</div>
                )}
              </div>

              {/* Preview 3: Audio */}
              <div className="preview-box">
                <div className="box-title"><Mic size={16} /> Nghe Thử Voice Lồng Tiếng</div>
                {selectedAudio ? (
                  <div className="media-container audio">
                    <audio controls src={selectedAudio.url} key={selectedAudio.url} />
                    <div className="media-caption">{selectedAudio.name}</div>
                  </div>
                ) : (
                  <div className="preview-empty">Chưa chọn Audio Voice</div>
                )}
              </div>
            </div>

            <div className="action-row-footer margin-top-md">
              <button type="button" className="btn-main-accent" onClick={handleAddToQueue}>
                <Plus size={18} /> Thêm Vào Hàng Chờ Render
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: GROK AI MOTION ANALYSIS */}
      {activeTab === 'grok' && (
        <div className="tab-pane-content">
          <div className="clean-white-card">
            <div className="card-section-header">
              <h3><BrainCircuit size={18} /> Phân Tích Prompt & Chuyển Động (Grok AI)</h3>
              <p>Trích xuất mô tả chuyển động camera, cử chỉ nhân vật và ánh sáng từ video mẫu.</p>
            </div>

            <div className="card-section-body">
              <div className="input-field-group">
                <label>Video Mẫu Đang Chọn:</label>
                <div className="selected-badge-box">
                  {selectedVideo ? (
                    <span className="badge-selected">🎬 {selectedVideo.name}</span>
                  ) : (
                    <span className="badge-placeholder">Chưa chọn video (Vui lòng chọn ở tab Kho Media)</span>
                  )}
                </div>
              </div>

              <button
                type="button"
                className="btn-grok-trigger"
                onClick={handleRunGrokAnalysis}
                disabled={isGrokAnalyzing || !selectedVideo}
                style={{ backgroundColor: '#d97706', color: '#ffffff', border: 'none', padding: '10px 20px', borderRadius: '8px', fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px', marginTop: '12px' }}
              >
                {isGrokAnalyzing ? (
                  <>
                    <RefreshCw size={16} className="animate-spin" /> Đang Phân Tích Grok AI...
                  </>
                ) : (
                  <>
                    <Sparkles size={16} /> Kích Hoạt Phân Tích Grok AI
                  </>
                )}
              </button>

              <div className="input-field-group margin-top-md">
                <label>Kết Quả Prompt Chuyển Động (Motion Prompt):</label>
                <textarea
                  className="clean-textarea"
                  rows={5}
                  value={motionPrompt}
                  onChange={(e) => setMotionPrompt(e.target.value)}
                  placeholder="Nội dung prompt phân tích từ Grok AI..."
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '14px' }}>
                <button
                  type="button"
                  className="btn-main-accent"
                  onClick={handleSaveMotionPrompt}
                  disabled={isSavingPrompt}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Save size={16} /> {isSavingPrompt ? 'Đang Lưu...' : 'Lưu File Prompt'}
                </button>
                {promptNotice && <span style={{ fontSize: '13px', fontWeight: 600 }}>{promptNotice}</span>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: OUTFIT & PROMPT EDITOR */}
      {activeTab === 'outfit' && (
        <div className="tab-pane-content">
          <div className="clean-white-card">
            <div className="card-section-header">
              <h3><Shirt size={18} /> Trình Chỉnh Sửa Trang Phục & Prompt Nâng Cao</h3>
              <p>Tùy chỉnh phong cách ăn mặc, phụ kiện và đạo cụ cho nhân vật trong Video Affiliate.</p>
            </div>

            <div className="card-section-body">
              <div className="input-field-group">
                <label>Mô Tả Trang Phục (Outfit Prompt):</label>
                <textarea
                  className="clean-textarea"
                  rows={4}
                  value={outfitDescription}
                  onChange={(e) => setOutfitDescription(e.target.value)}
                  placeholder="Nhập mô tả chi tiết trang phục nhân vật..."
                />
              </div>

              <div className="preset-suggestions margin-top-sm">
                <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '8px' }}>Gợi Ý Mẫu Trang Phục Phổ Biến:</label>
                <div className="preset-chips-list" style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="chip-btn"
                    style={{ padding: '6px 14px', borderRadius: '20px', border: '1px solid var(--border)', background: '#ffffff', cursor: 'pointer', fontSize: '13px' }}
                    onClick={() => setOutfitDescription('Áo phông oversize trẻ trung, quần jogger thể thao, tai nghe bluetooth')}
                  >
                    👕 Thể Thao Trẻ Trung
                  </button>
                  <button
                    type="button"
                    className="chip-btn"
                    style={{ padding: '6px 14px', borderRadius: '20px', border: '1px solid var(--border)', background: '#ffffff', cursor: 'pointer', fontSize: '13px' }}
                    onClick={() => setOutfitDescription('Vest công sở sang trọng, đồng hồ kim loại, phong cách doanh nhân')}
                  >
                    👔 Công Sở Sang Trọng
                  </button>
                  <button
                    type="button"
                    className="chip-btn"
                    style={{ padding: '6px 14px', borderRadius: '20px', border: '1px solid var(--border)', background: '#ffffff', cursor: 'pointer', fontSize: '13px' }}
                    onClick={() => setOutfitDescription('Váy dạ hội lộng lẫy, dây chuyền ngọc trai, trang điểm thanh lịch')}
                  >
                    👗 Dạ Hội Thanh Lịch
                  </button>
                </div>
              </div>

              <div className="input-field-group margin-top-md">
                <label>Chỉnh Sửa File Prompt Chuyển Động (`motion_analysis.txt`):</label>
                <textarea
                  className="clean-textarea"
                  rows={6}
                  value={motionPrompt}
                  onChange={(e) => setMotionPrompt(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '14px' }}>
                <button
                  type="button"
                  className="btn-main-accent"
                  onClick={handleSaveMotionPrompt}
                  disabled={isSavingPrompt}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Save size={16} /> {isSavingPrompt ? 'Đang Lưu...' : 'Cập Nhật Cấu Hình Prompt'}
                </button>
                {promptNotice && <span style={{ fontSize: '13px', fontWeight: 600 }}>{promptNotice}</span>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: RENDER QUEUE */}
      {activeTab === 'queue' && (
        <div className="tab-pane-content">
          <div className="queue-action-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
            <button
              type="button"
              className={`btn-render-toggle ${isRendering ? 'stop' : 'start'}`}
              onClick={handleToggleRenderQueue}
              style={{
                backgroundColor: isRendering ? '#dc2626' : '#16a34a',
                color: '#ffffff',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '8px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              {isRendering ? (
                <>
                  <Pause size={16} /> Tạm Dừng Tiến Trình Render
                </>
              ) : (
                <>
                  <Play size={16} /> Bắt Đầu Render Queue
                </>
              )}
            </button>

            <button type="button" className="btn-refresh-subtle" onClick={fetchQueueStatus} style={{ padding: '8px 14px', borderRadius: '6px', border: '1px solid var(--border)', background: '#ffffff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
              <RefreshCw size={14} /> Làm Mới Trạng Thái
            </button>
          </div>

          <div className="clean-white-card">
            <div className="table-wrapper">
              <table className="clean-table">
                <thead>
                  <tr>
                    <th>STT</th>
                    <th>Ảnh Nhân Vật</th>
                    <th>Video Mẫu</th>
                    <th>Voice</th>
                    <th>Trạng Thái</th>
                    <th>Ghi Chú</th>
                    <th>Thao Tác</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="empty-table-row" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                        Hàng chờ hiện đang trống. Vui lòng thêm media từ tab "Quản Lý Kho Media".
                      </td>
                    </tr>
                  ) : (
                    queue.map((item, index) => (
                      <tr key={item.id}>
                        <td>#{index + 1}</td>
                        <td>📸 {item.image_file}</td>
                        <td>🎬 {item.video_file}</td>
                        <td>🎙️ {item.audio_file}</td>
                        <td>
                          <span className={`status-tag status-${item.status}`}>
                            {item.status === 'completed' && <CheckCircle2 size={12} />}
                            {item.status === 'processing' && <RefreshCw size={12} className="animate-spin" />}
                            {item.status === 'pending' && <Clock size={12} />}
                            {item.status === 'failed' && <AlertCircle size={12} />}
                            {item.status}
                          </span>
                        </td>
                        <td>{item.note}</td>
                        <td>
                          <button
                            type="button"
                            className="btn-trash-icon"
                            onClick={() => setQueue((prev) => prev.filter((q) => q.id !== item.id))}
                            style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#ef4444' }}
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: VIDEO THÀNH PHẨM (OUTPUTS) */}
      {activeTab === 'outputs' && (
        <div className="tab-pane-content">
          <div className="clean-white-card">
            <div className="card-section-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '16px', borderBottom: '1px solid var(--border)' }}>
              <div>
                <h3><Film size={18} /> Kho Video Thành Phẩm (Render Outputs)</h3>
                <p>Danh sách các Video Affiliate đã ghép nối hoàn chỉnh trong thư mục downloads.</p>
              </div>
              <button
                type="button"
                className="btn-refresh-subtle"
                onClick={fetchOutputs}
                style={{ padding: '8px 14px', borderRadius: '6px', border: '1px solid var(--border)', background: '#ffffff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
              >
                <RefreshCw size={14} /> Tải Lại Danh Sách
              </button>
            </div>

            <div className="card-section-body" style={{ marginTop: '20px' }}>
              {outputs.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
                  <Film size={36} style={{ marginBottom: '10px', opacity: 0.5 }} />
                  <p>Chưa có video thành phẩm nào được tạo. Hãy chạy Render Queue để sinh video mới!</p>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
                  {outputs.map((out) => (
                    <div
                      key={out.id}
                      style={{
                        backgroundColor: '#ffffff',
                        borderRadius: '12px',
                        border: '1px solid var(--border)',
                        overflow: 'hidden',
                        boxShadow: 'var(--shadow-sm)',
                        display: 'flex',
                        flexDirection: 'column',
                      }}
                    >
                      <div style={{ backgroundColor: '#0f172a', aspectRatio: '16/9', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <video controls src={out.url} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                      </div>
                      <div style={{ padding: '14px', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                        <div>
                          <h4 style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)', wordBreak: 'break-all', marginBottom: '6px' }}>
                            {out.filename}
                          </h4>
                          <div style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', gap: '12px' }}>
                            <span>💾 {formatFileSize(out.size)}</span>
                            <span>🕒 {out.created_at}</span>
                          </div>
                        </div>

                        <div style={{ marginTop: '14px', display: 'flex', gap: '10px' }}>
                          <a
                            href={out.url}
                            download={out.filename}
                            style={{
                              flex: 1,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '6px',
                              backgroundColor: '#4f46e5',
                              color: '#ffffff',
                              textDecoration: 'none',
                              padding: '8px 12px',
                              borderRadius: '6px',
                              fontWeight: 600,
                              fontSize: '13px',
                            }}
                          >
                            <Download size={14} /> Tải Video MP4
                          </a>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* POPUP MODAL PREVIEW FILE */}
      {previewMedia && (
        <div className="modal-overlay" onClick={() => setPreviewMedia(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Xem Trước Media: {previewMedia.name}</h3>
              <button type="button" className="close-btn" onClick={() => setPreviewMedia(null)}>
                <X size={18} />
              </button>
            </div>
            <div className="modal-body">
              {previewMedia.type === 'image' && (
                <img src={previewMedia.url} alt={previewMedia.name} className="modal-preview-img" />
              )}
              {previewMedia.type === 'video' && (
                <video controls autoPlay src={previewMedia.url} className="modal-preview-video" />
              )}
              {previewMedia.type === 'audio' && (
                <div className="audio-player-modal">
                  <Mic size={36} className="audio-icon-large" />
                  <audio controls autoPlay src={previewMedia.url} className="modal-preview-audio" />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
