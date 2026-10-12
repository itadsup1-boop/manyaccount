import { useEffect, useRef, useState } from 'react';
import type { PointerEvent } from 'react';

interface TitlePositionEditorProps {
  channelId: string;
  frameFilename?: string;
  frameUrl?: string;
  sampleText?: string;
  yStart: number;
  xOffset: number;
  boxWidth: number;
  fontSize: number;
  color?: string;
  onChange: (updates: Record<string, number | string>) => void;
}

const PREVIEW_WIDTH = 216;
const PREVIEW_HEIGHT = 384;
const VIDEO_WIDTH = 1080;
const SCALE = PREVIEW_WIDTH / VIDEO_WIDTH;

export default function TitlePositionEditor({
  channelId,
  frameFilename = '',
  frameUrl: customFrameUrl = '',
  sampleText = 'KÉO TITLE ĐẾN VỊ TRÍ MUỐN',
  yStart,
  xOffset,
  boxWidth,
  fontSize,
  color = '#ffffff',
  onChange
}: TitlePositionEditorProps) {
  const previewRef = useRef<HTMLDivElement>(null);
  const dragOffsetRef = useRef({ x: 0, y: 0 });
  const resizeStartRef = useRef({ x: 0, y: 0, fontSize: 50 });
  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [frameMissing, setFrameMissing] = useState(false);

  useEffect(() => {
    setFrameMissing(false);
  }, [channelId, frameFilename, customFrameUrl]);

  const safeWidth = Math.max(0.35, Math.min(0.95, boxWidth || 0.85));
  const safeY = Math.max(0, Math.min(0.92, yStart || 0));
  const safeFontSize = Math.max(32, Math.min(80, fontSize || 50));
  const boxW = PREVIEW_WIDTH * safeWidth;
  const boxH = Math.max(30, safeFontSize * 2.4 * SCALE);
  const boxX = Math.max(
    0,
    Math.min(
      PREVIEW_WIDTH - boxW,
      (PREVIEW_WIDTH - boxW) / 2 + xOffset * SCALE
    )
  );
  const boxY = Math.max(0, Math.min(PREVIEW_HEIGHT - boxH, PREVIEW_HEIGHT * safeY));

  const frameUrl = customFrameUrl || (frameFilename
    ? `/api/tiktok/frame-image/${encodeURIComponent(frameFilename)}`
    : `/api/article/channel-image/${encodeURIComponent(channelId)}/frame_intro.png`);

  const getPointer = (event: PointerEvent<HTMLElement>) => {
    const rect = previewRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: (event.clientX - rect.left) * (PREVIEW_WIDTH / rect.width),
      y: (event.clientY - rect.top) * (PREVIEW_HEIGHT / rect.height)
    };
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    const point = getPointer(event);
    dragOffsetRef.current = { x: point.x - boxX, y: point.y - boxY };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    const point = getPointer(event);
    const nextX = Math.max(
      0,
      Math.min(PREVIEW_WIDTH - boxW, point.x - dragOffsetRef.current.x)
    );
    const nextY = Math.max(
      0,
      Math.min(PREVIEW_HEIGHT - boxH, point.y - dragOffsetRef.current.y)
    );
    const centeredX = (PREVIEW_WIDTH - boxW) / 2;
    onChange({
      box_y_start: Number((nextY / PREVIEW_HEIGHT).toFixed(4)),
      box_x_offset: Math.round((nextX - centeredX) / SCALE),
      position_mode: 'manual'
    });
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
    const point = getPointer(event);
    resizeStartRef.current = { x: point.x, y: point.y, fontSize: safeFontSize };
    setResizing(true);
  };

  const handleResizePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (!resizing) return;
    const point = getPointer(event);
    const deltaX = (point.x - resizeStartRef.current.x) / SCALE;
    const deltaY = (point.y - resizeStartRef.current.y) / SCALE;
    const resizeDelta = Math.abs(deltaX) > Math.abs(deltaY) ? deltaX : deltaY;
    const nextFontSize = Math.round(
      Math.max(32, Math.min(80, resizeStartRef.current.fontSize + resizeDelta)) / 2
    ) * 2;
    onChange({ font_size: nextFontSize, position_mode: 'manual' });
  };

  const stopResizing = (event: PointerEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setResizing(false);
  };

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
          background: 'linear-gradient(180deg, #26364c, #121827)',
          boxShadow: '0 10px 24px rgba(0,0,0,0.25)',
          userSelect: 'none'
        }}
      >
        {!frameMissing && (
          <img
            src={frameUrl}
            alt="Khung title"
            draggable={false}
            onError={() => setFrameMissing(true)}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'fill' }}
          />
        )}
        <div
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={stopDragging}
          onPointerCancel={stopDragging}
          style={{
            position: 'absolute',
            left: `${boxX}px`,
            top: `${boxY}px`,
            width: `${boxW}px`,
            height: `${boxH}px`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 7px',
            boxSizing: 'border-box',
            color,
            fontSize: `${Math.max(10, safeFontSize * SCALE)}px`,
            fontWeight: 800,
            lineHeight: 1.1,
            textAlign: 'center',
            textShadow: '0 1px 2px #000, 1px 0 2px #000, -1px 0 2px #000',
            background: dragging || resizing ? 'rgba(14,165,233,0.35)' : 'rgba(14,165,233,0.18)',
            border: `2px ${dragging || resizing ? 'solid' : 'dashed'} #38bdf8`,
            borderRadius: '0.4rem',
            cursor: dragging ? 'grabbing' : 'grab',
            touchAction: 'none'
          }}
        >
          <span style={{ pointerEvents: 'none' }}>{sampleText}</span>
          <div
            role="slider"
            aria-label="Kéo để thay đổi cỡ chữ title"
            aria-valuemin={32}
            aria-valuemax={80}
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
              color: '#0c4a6e',
              fontSize: '11px',
              fontWeight: 900,
              lineHeight: 1,
              background: '#e0f2fe',
              border: '2px solid #0284c7',
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
          Title được khóa theo vị trí bạn kéo
        </p>
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
          {[
            { label: 'Chữ nhỏ', value: 40 },
            { label: 'Chữ vừa', value: 50 },
            { label: 'Chữ lớn', value: 60 }
          ].map(option => (
            <button
              key={option.value}
              type="button"
              className="btn"
              onClick={() => onChange({ font_size: option.value, position_mode: 'manual' })}
              style={{
                padding: '0.45rem 0.75rem',
                borderRadius: '8px',
                fontSize: '0.8rem',
                fontWeight: safeFontSize === option.value ? 600 : 500,
                background: safeFontSize === option.value ? 'var(--tiktok-primary-soft, #eef0ff)' : '#ffffff',
                color: safeFontSize === option.value ? 'var(--tiktok-primary-dark, #4f46e5)' : 'var(--tiktok-text, #1f2430)',
                border: safeFontSize === option.value ? '1px solid var(--tiktok-primary, #6366f1)' : '1px solid var(--tiktok-border, #e5e8f0)',
                cursor: 'pointer'
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p style={{ margin: '0.65rem 0 0', color: 'var(--text-secondary)', fontSize: '0.85rem', lineHeight: 1.5 }}>
          Kéo phần giữa khung để đổi vị trí. Kéo ô vuông ở góc phải dưới ra ngoài để phóng to, kéo vào trong để thu nhỏ. Renderer sẽ giữ nguyên vị trí này dù title có một hay hai dòng.
        </p>
      </div>
    </div>
  );
}
