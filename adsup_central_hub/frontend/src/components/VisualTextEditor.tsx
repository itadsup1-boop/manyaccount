import { useState, useRef, useEffect, useCallback } from 'react';

interface VisualTextEditorProps {
  channelId: string;
  frameType: 'intro' | 'content'; // intro = frame_intro.png, content = frame_content.png
  config: {
    text_y1: number;
    text_y2: number;
    text_w: number;
    text_x: number;
    text_size: number;
    text_color: string;
    text_stroke: number;
    text_font: string;
    // Content subtitle config (separate)
    sub_margin_v?: number;
    sub_font_size?: number;
    sub_color?: string;
  };
  hasFrame: boolean;
  onConfigChange: (updates: Record<string, any>) => void;
  label: string;
}

// Canvas dimensions (preview scale of 1080x1920)
const CANVAS_W = 270;
const CANVAS_H = 480;
const REAL_W = 1080;
const SCALE = CANVAS_W / REAL_W;

export default function VisualTextEditor({ channelId, frameType, config, hasFrame, onConfigChange, label }: VisualTextEditorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [frameImg, setFrameImg] = useState<HTMLImageElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  // Convert config to pixel positions on canvas
  const getBoxFromConfig = useCallback(() => {
    if (frameType === 'intro') {
      const x = ((REAL_W - REAL_W * config.text_w) / 2 + (config.text_x || 0)) * SCALE;
      const y = config.text_y1 * CANVAS_H;
      const w = config.text_w * CANVAS_W;
      const h = (config.text_y2 - config.text_y1) * CANVAS_H;
      return { x, y, w, h };
    } else {
      // Content subtitle: positioned by margin from bottom
      const marginV = config.sub_margin_v ?? 150;
      const fontSize = config.sub_font_size ?? 70;
      const textH = fontSize * 2.5 * SCALE; // approximate 2 lines
      const textW = CANVAS_W * 0.9;
      const x = (CANVAS_W - textW) / 2;
      const y = CANVAS_H - (marginV * SCALE) - textH;
      return { x, y, w: textW, h: textH };
    }
  }, [config, frameType]);

  const [box, setBox] = useState(getBoxFromConfig);

  useEffect(() => {
    setBox(getBoxFromConfig());
  }, [getBoxFromConfig]);

  // Load frame image
  useEffect(() => {
    if (!channelId || channelId === '-- Chọn kênh --') {
      setFrameImg(null);
      return;
    }
    const imgName = frameType === 'intro' ? 'frame_intro.png' : 'frame_content.png';
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => setFrameImg(img);
    img.onerror = () => setFrameImg(null);
    img.src = `/api/article/channel-image/${channelId}/${imgName}?t=${Date.now()}`;
  }, [channelId, frameType]);

  // Draw canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Background
    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    // Draw grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    for (let i = 0; i < CANVAS_H; i += CANVAS_H / 10) {
      ctx.beginPath();
      ctx.moveTo(0, i);
      ctx.lineTo(CANVAS_W, i);
      ctx.stroke();
    }
    for (let i = 0; i < CANVAS_W; i += CANVAS_W / 6) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i, CANVAS_H);
      ctx.stroke();
    }

    // Draw frame image
    if (frameImg) {
      ctx.drawImage(frameImg, 0, 0, CANVAS_W, CANVAS_H);
    }

    // Draw text box
    const b = box;
    
    // Box fill (semi-transparent)
    ctx.fillStyle = 'rgba(59, 130, 246, 0.15)';
    ctx.fillRect(b.x, b.y, b.w, b.h);

    // Box border
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 3]);
    ctx.strokeRect(b.x, b.y, b.w, b.h);
    ctx.setLineDash([]);

    // Sample text
    const sampleText = frameType === 'intro' ? 'TIÊU ĐỀ VIDEO MẪU' : 'Phụ đề nội dung mẫu';
    const fontSize = frameType === 'intro'
      ? Math.max(8, (config.text_size || 45) * SCALE)
      : Math.max(8, (config.sub_font_size || 70) * SCALE);
    const textColor = frameType === 'intro'
      ? (config.text_color || '#ffffff')
      : (config.sub_color || '#00FFFF');

    ctx.font = `bold ${fontSize}px sans-serif`;
    ctx.fillStyle = textColor;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    // Draw text with stroke
    const stroke = frameType === 'intro' ? (config.text_stroke || 0) : 4;
    if (stroke > 0) {
      ctx.strokeStyle = '#000000';
      ctx.lineWidth = stroke * SCALE;
      ctx.strokeText(sampleText, b.x + b.w / 2, b.y + b.h / 2, b.w - 10);
    }
    ctx.fillText(sampleText, b.x + b.w / 2, b.y + b.h / 2, b.w - 10);

    // Resize handle (bottom-right corner)
    const handleSize = 10;
    ctx.fillStyle = '#3b82f6';
    ctx.fillRect(b.x + b.w - handleSize, b.y + b.h - handleSize, handleSize, handleSize);

    // Corner indicators
    ctx.fillStyle = '#3b82f6';
    const dotSize = 5;
    // Top-left
    ctx.fillRect(b.x - dotSize/2, b.y - dotSize/2, dotSize, dotSize);
    // Top-right
    ctx.fillRect(b.x + b.w - dotSize/2, b.y - dotSize/2, dotSize, dotSize);
    // Bottom-left
    ctx.fillRect(b.x - dotSize/2, b.y + b.h - dotSize/2, dotSize, dotSize);

  }, [box, frameImg, config, frameType]);

  // Mouse handlers
  const getCanvasPos = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (CANVAS_W / rect.width),
      y: (e.clientY - rect.top) * (CANVAS_H / rect.height)
    };
  };

  const isInResizeHandle = (mx: number, my: number) => {
    const handleSize = 14;
    return mx >= box.x + box.w - handleSize && mx <= box.x + box.w + 4 &&
           my >= box.y + box.h - handleSize && my <= box.y + box.h + 4;
  };

  const isInBox = (mx: number, my: number) => {
    return mx >= box.x && mx <= box.x + box.w && my >= box.y && my <= box.y + box.h;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    const pos = getCanvasPos(e);
    if (isInResizeHandle(pos.x, pos.y)) {
      setResizing(true);
    } else if (isInBox(pos.x, pos.y)) {
      setDragging(true);
      setDragOffset({ x: pos.x - box.x, y: pos.y - box.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const pos = getCanvasPos(e);
    
    // Change cursor
    const canvas = canvasRef.current;
    if (canvas) {
      if (isInResizeHandle(pos.x, pos.y)) {
        canvas.style.cursor = 'nwse-resize';
      } else if (isInBox(pos.x, pos.y)) {
        canvas.style.cursor = 'move';
      } else {
        canvas.style.cursor = 'default';
      }
    }

    if (dragging) {
      const newX = Math.max(0, Math.min(pos.x - dragOffset.x, CANVAS_W - box.w));
      const newY = Math.max(0, Math.min(pos.y - dragOffset.y, CANVAS_H - box.h));
      setBox(prev => ({ ...prev, x: newX, y: newY }));
    } else if (resizing) {
      const newW = Math.max(40, Math.min(pos.x - box.x, CANVAS_W - box.x));
      const newH = Math.max(20, Math.min(pos.y - box.y, CANVAS_H - box.y));
      setBox(prev => ({ ...prev, w: newW, h: newH }));
    }
  };

  const handleMouseUp = () => {
    if (dragging || resizing) {
      // Convert canvas pixels back to config values
      if (frameType === 'intro') {
        const text_w = box.w / CANVAS_W;
        const text_y1 = parseFloat((box.y / CANVAS_H).toFixed(4));
        const text_y2 = parseFloat(((box.y + box.h) / CANVAS_H).toFixed(4));
        const center_x = box.x + box.w / 2;
        const canvas_center = CANVAS_W / 2;
        const text_x = Math.round((center_x - canvas_center) / SCALE);
        
        onConfigChange({
          text_w: parseFloat(text_w.toFixed(4)),
          text_y1,
          text_y2,
          text_x
        });
      } else {
        // Content subtitle: compute margin from bottom
        const marginV = Math.round((CANVAS_H - box.y - box.h) / SCALE);
        onConfigChange({
          sub_margin_v: Math.max(0, marginV)
        });
      }
    }
    setDragging(false);
    setResizing(false);
  };

  return (
    <div className="visual-editor-card">
      <div className="visual-editor-header">
        <h4>{label}</h4>
        <span className={`status-badge ${hasFrame ? 'active' : 'inactive'}`}>
          {hasFrame ? '✅ Có Frame' : '❌ Chưa có'}
        </span>
      </div>

      <div className="visual-editor-body">
        {/* Canvas */}
        <div className="canvas-wrapper" ref={containerRef}>
          <canvas
            ref={canvasRef}
            width={CANVAS_W}
            height={CANVAS_H}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
          />
          {!channelId || channelId === '-- Chọn kênh --' ? (
            <div className="canvas-overlay">
              <p>👆 Vui lòng chọn kênh</p>
            </div>
          ) : !frameImg ? (
            <div className="canvas-overlay">
              <p>📷 Không tìm thấy frame</p>
              <p className="sub">Kênh này chưa có file {frameType === 'intro' ? 'frame_intro.png' : 'frame_content.png'}</p>
            </div>
          ) : null}
        </div>

        {/* Controls */}
        <div className="editor-controls">
          {frameType === 'intro' ? (
            <>
              <div className="control-group">
                <label>Cỡ chữ</label>
                <div className="slider-row">
                  <input
                    type="range"
                    min="20"
                    max="120"
                    value={config.text_size || 45}
                    onChange={e => onConfigChange({ text_size: parseInt(e.target.value) })}
                  />
                  <span className="slider-value">{config.text_size || 45}px</span>
                </div>
              </div>
              <div className="control-group">
                <label>Viền chữ</label>
                <div className="slider-row">
                  <input
                    type="range"
                    min="0"
                    max="10"
                    value={config.text_stroke || 0}
                    onChange={e => onConfigChange({ text_stroke: parseInt(e.target.value) })}
                  />
                  <span className="slider-value">{config.text_stroke || 0}px</span>
                </div>
              </div>
              <div className="control-group">
                <label>Màu chữ</label>
                <div className="color-picker-row">
                  <input
                    type="color"
                    value={config.text_color || '#ffffff'}
                    onChange={e => onConfigChange({ text_color: e.target.value })}
                  />
                  <span>{config.text_color || '#ffffff'}</span>
                </div>
              </div>
              <div className="control-group">
                <label>Font</label>
                <input
                  type="text"
                  className="form-input compact"
                  value={config.text_font || 'RobotoCondensed-Bold.ttf'}
                  onChange={e => onConfigChange({ text_font: e.target.value })}
                />
              </div>
            </>
          ) : (
            <>
              <div className="control-group">
                <label>Cỡ phụ đề</label>
                <div className="slider-row">
                  <input
                    type="range"
                    min="30"
                    max="120"
                    value={config.sub_font_size || 70}
                    onChange={e => onConfigChange({ sub_font_size: parseInt(e.target.value) })}
                  />
                  <span className="slider-value">{config.sub_font_size || 70}px</span>
                </div>
              </div>
              <div className="control-group">
                <label>Màu phụ đề</label>
                <div className="color-picker-row">
                  <input
                    type="color"
                    value={config.sub_color || '#00ffff'}
                    onChange={e => onConfigChange({ sub_color: e.target.value })}
                  />
                  <span>{config.sub_color || '#00ffff'}</span>
                </div>
              </div>
              <div className="control-group">
                <label>Khoảng cách từ đáy</label>
                <div className="slider-row">
                  <input
                    type="range"
                    min="50"
                    max="600"
                    value={config.sub_margin_v || 150}
                    onChange={e => onConfigChange({ sub_margin_v: parseInt(e.target.value) })}
                  />
                  <span className="slider-value">{config.sub_margin_v || 150}px</span>
                </div>
              </div>
            </>
          )}
          
          {/* Live values readout */}
          <div className="config-readout">
            <p className="readout-title">📐 Thông số hiện tại</p>
            {frameType === 'intro' ? (
              <>
                <div className="readout-row"><span>Y Start:</span><span>{config.text_y1}</span></div>
                <div className="readout-row"><span>Y End:</span><span>{config.text_y2}</span></div>
                <div className="readout-row"><span>Width:</span><span>{(config.text_w * 100).toFixed(0)}%</span></div>
                <div className="readout-row"><span>X Offset (lệch tâm):</span><span>{config.text_x}px</span></div>
              </>
            ) : (
              <>
                <div className="readout-row"><span>MarginV:</span><span>{config.sub_margin_v || 150}px</span></div>
                <div className="readout-row"><span>Font Size:</span><span>{config.sub_font_size || 70}px</span></div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
