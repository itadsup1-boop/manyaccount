import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';

interface SubtitlePositionEditorProps {
  channelId: string;
  frameFilename?: string;
  marginV: number;
  fontSize?: number;
  color?: string;
  onChange: (marginV: number) => void;
  onFontSizeChange: (fontSize: number) => void;
}

const PREVIEW_WIDTH = 216;
const PREVIEW_HEIGHT = 384;
const VIDEO_HEIGHT = 1920;
const SCALE = PREVIEW_HEIGHT / VIDEO_HEIGHT;
const MIN_MARGIN = 60;
const MAX_MARGIN = 760;
const SAFE_MARGIN = 320;
const MIN_FONT_SIZE = 46;
const MAX_FONT_SIZE = 76;

function clampMargin(value: number) {
  return Math.max(MIN_MARGIN, Math.min(MAX_MARGIN, value));
}

function clampFontSize(value: number) {
  return Math.max(MIN_FONT_SIZE, Math.min(MAX_FONT_SIZE, value));
}

export default function SubtitlePositionEditor({
  channelId,
  frameFilename = '',
  marginV,
  fontSize = 64,
  color = '#ffffff',
  onChange,
  onFontSizeChange
}: SubtitlePositionEditorProps) {
  const previewRef = useRef<HTMLDivElement>(null);
  const dragOffsetRef = useRef(0);
  const resizeStartRef = useRef({ x: 0, y: 0, fontSize: 52 });
  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [frameMissing, setFrameMissing] = useState(false);

  useEffect(() => {
    setFrameMissing(false);
  }, [channelId, frameFilename]);

  const safeMargin = clampMargin(Number.isFinite(marginV) ? marginV : MIN_MARGIN);
  const safeFontSize = clampFontSize(Number.isFinite(fontSize) ? fontSize : 52);
  const subtitleHeight = Math.max(28, safeFontSize * 2.25 * SCALE);
  const subtitleTop = PREVIEW_HEIGHT - safeMargin * SCALE - subtitleHeight;
  const frameUrl = frameFilename
    ? `/api/tiktok/frame-image/${encodeURIComponent(frameFilename)}`
    : `/api/article/channel-image/${encodeURIComponent(channelId)}/frame_content.png`;

  const pointerY = (event: PointerEvent<HTMLElement>) => {
    const rect = previewRef.current?.getBoundingClientRect();
    if (!rect) return 0;
    return (event.clientY - rect.top) * (PREVIEW_HEIGHT / rect.height);
  };

  const pointerX = (event: PointerEvent<HTMLElement>) => {
    const rect = previewRef.current?.getBoundingClientRect();
    if (!rect) return 0;
    return (event.clientX - rect.left) * (PREVIEW_WIDTH / rect.width);
  };

  const updateFromTop = (top: number) => {
    const rawMargin = (PREVIEW_HEIGHT - top - subtitleHeight) / SCALE;
    const snappedMargin = Math.round(clampMargin(rawMargin) / 10) * 10;
    onChange(snappedMargin);
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragOffsetRef.current = pointerY(event) - subtitleTop;
    setDragging(true);
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    updateFromTop(pointerY(event) - dragOffsetRef.current);
  };

  const stopDragging = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDragging(false);
  };

  const handleResizePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeStartRef.current = {
      x: pointerX(event),
      y: pointerY(event),
      fontSize: safeFontSize
    };
    setResizing(true);
  };

  const handleResizePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (!resizing) return;
    const deltaX = (pointerX(event) - resizeStartRef.current.x) / SCALE;
    const deltaY = (pointerY(event) - resizeStartRef.current.y) / SCALE;
    const resizeDelta = Math.abs(deltaX) > Math.abs(deltaY) ? deltaX : deltaY;
    const nextFontSize = Math.round(
      clampFontSize(resizeStartRef.current.fontSize + resizeDelta) / 2
    ) * 2;
    onFontSizeChange(nextFontSize);
  };

  const stopResizing = (event: PointerEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setResizing(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      onChange(clampMargin(safeMargin + 10));
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      onChange(clampMargin(safeMargin - 10));
    }
  };

  const positionLabel = safeMargin < SAFE_MARGIN
    ? 'Rất thấp (có thể bị giao diện TikTok che)'
    : safeMargin <= 400
      ? 'Thấp'
    : safeMargin >= 650
      ? 'Cao'
      : 'Ở giữa';
  const fontLabel = safeFontSize <= 48
    ? 'Nhỏ'
    : safeFontSize >= 62
      ? 'Lớn'
      : 'Vừa';

  return (
    <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
      <div
        ref={previewRef}
        style={{
          position: 'relative',
          width: `${PREVIEW_WIDTH}px`,
          height: `${PREVIEW_HEIGHT}px`,
          flex: `0 0 ${PREVIEW_WIDTH}px`,
          overflow: 'hidden',
          borderRadius: '0.75rem',
          border: '1px solid var(--border)',
          background: 'linear-gradient(180deg, #1c2940 0%, #25354a 52%, #151b2b 100%)',
          boxShadow: '0 10px 24px rgba(0,0,0,0.25)',
          userSelect: 'none'
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            opacity: 0.18,
            backgroundImage: 'linear-gradient(rgba(255,255,255,.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.15) 1px, transparent 1px)',
            backgroundSize: '36px 38px'
          }}
        />
        {!frameMissing && channelId && (
          <img
            src={frameUrl}
            alt="Khung nội dung"
            draggable={false}
            onError={() => setFrameMissing(true)}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'fill' }}
          />
        )}

        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 0,
            height: `${SAFE_MARGIN * SCALE}px`,
            background: 'linear-gradient(180deg, rgba(239,68,68,0.03), rgba(239,68,68,0.18))',
            borderTop: '1px dashed rgba(248,113,113,0.7)',
            pointerEvents: 'none'
          }}
        >
          <span style={{ position: 'absolute', left: 7, bottom: 6, color: '#fca5a5', fontSize: '9px' }}>
            Vùng nút TikTok
          </span>
        </div>

        <div
          role="slider"
          aria-label="Kéo để thay đổi vị trí subtitle"
          aria-valuemin={MIN_MARGIN}
          aria-valuemax={MAX_MARGIN}
          aria-valuenow={safeMargin}
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={stopDragging}
          onPointerCancel={stopDragging}
          style={{
            position: 'absolute',
            left: '5%',
            top: `${subtitleTop}px`,
            width: '90%',
            height: `${subtitleHeight}px`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 8px',
            boxSizing: 'border-box',
            color,
            fontSize: `${Math.max(12, safeFontSize * SCALE)}px`,
            fontWeight: 800,
            lineHeight: 1.1,
            textAlign: 'center',
            textShadow: '0 1px 2px #000, 1px 0 2px #000, -1px 0 2px #000',
            background: dragging || resizing ? 'rgba(37,99,235,0.35)' : 'rgba(37,99,235,0.18)',
            border: `2px ${dragging || resizing ? 'solid' : 'dashed'} #60a5fa`,
            borderRadius: '0.4rem',
            cursor: dragging ? 'grabbing' : 'grab',
            touchAction: 'none',
            zIndex: 2
          }}
        >
          <span style={{ pointerEvents: 'none' }}>KÉO SUBTITLE LÊN / XUỐNG</span>
          <div
            role="slider"
            aria-label="Kéo để thay đổi cỡ chữ subtitle"
            aria-valuemin={MIN_FONT_SIZE}
            aria-valuemax={MAX_FONT_SIZE}
            aria-valuenow={safeFontSize}
            onPointerDown={handleResizePointerDown}
            onPointerMove={handleResizePointerMove}
            onPointerUp={stopResizing}
            onPointerCancel={stopResizing}
            style={{
              position: 'absolute',
              right: '-5px',
              bottom: '-5px',
              width: '16px',
              height: '16px',
              display: 'grid',
              placeItems: 'center',
              color: '#1e3a8a',
              fontSize: '11px',
              fontWeight: 900,
              lineHeight: 1,
              background: '#dbeafe',
              border: '2px solid #2563eb',
              borderRadius: '4px',
              boxShadow: '0 1px 4px rgba(0,0,0,.45)',
              cursor: 'nwse-resize',
              touchAction: 'none',
              zIndex: 3
            }}
          >
            ↘
          </div>
        </div>
      </div>

      <div style={{ minWidth: '190px', flex: 1 }}>
        <p style={{ margin: 0, color: 'var(--primary)', fontWeight: 700 }}>
          Vị trí hiện tại: {positionLabel}
        </p>
        <p style={{ margin: '0.75rem 0 0', color: 'var(--text-primary)', fontWeight: 600 }}>
          Cỡ chữ: {fontLabel}
        </p>
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
          {[
            { label: 'Chữ nhỏ', value: 46 },
            { label: 'Chữ vừa', value: 54 },
            { label: 'Chữ lớn', value: 64 }
          ].map(option => (
            <button
              key={option.value}
              type="button"
              className="btn"
              onClick={() => onFontSizeChange(option.value)}
              style={{
                padding: '0.45rem 0.65rem',
                background: safeFontSize === option.value ? 'var(--primary)' : 'var(--bg-color)',
                color: 'white',
                border: '1px solid var(--border)'
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p style={{ margin: '0.5rem 0 0', color: 'var(--text-secondary)', fontSize: '0.85rem', lineHeight: 1.5 }}>
          Kéo phần giữa khung để đổi vị trí. Kéo ô vuông ở góc phải dưới ra ngoài để phóng to, kéo vào trong để thu nhỏ. Vùng đỏ mô phỏng khu vực dễ bị nút TikTok che.
        </p>
      </div>
    </div>
  );
}
