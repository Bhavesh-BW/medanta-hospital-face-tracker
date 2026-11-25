import React, { useEffect, useRef, useState, useCallback } from 'react';
import { MediaMTXWebRTCReader } from '../utils/webrtcReader';

export default function WebRTCPlayer({
  streamPath,
  cameraObj,
  cameraId,
  hudEnabled = false,
  onClick,
  title = '',
  style = {}
}) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const readerRef = useRef(null);
  const [status, setStatus] = useState('connecting'); // 'connecting' | 'playing' | 'fallback' | 'error'
  const [errorMessage, setErrorMessage] = useState('');
  const [useFallbackMjpeg, setUseFallbackMjpeg] = useState(false);

  // Derive normalized clean MediaMTX stream path (e.g. 'live/main', 'live/main_exit')
  const getCleanPath = () => {
    let p = streamPath || cameraObj?.webrtc_path;
    if (!p && cameraObj?.rtsp) {
      if (cameraObj.rtsp.includes('/live/')) {
        p = 'live/' + cameraObj.rtsp.split('/live/')[1].split('?')[0];
      } else if (cameraObj.rtsp.includes(':31554/')) {
        p = cameraObj.rtsp.split(':31554/')[1].split('?')[0];
      } else if (cameraObj.rtsp.includes(':8554/')) {
        p = cameraObj.rtsp.split(':8554/')[1].split('?')[0];
      }
    }
    if (cameraObj?.rtsp && (!p || !p.includes('/'))) {
      if (cameraObj.rtsp.includes('/live/')) {
        p = 'live/' + cameraObj.rtsp.split('/live/')[1].split('?')[0];
      }
    }
    return p || cameraObj?.id || cameraId;
  };

  const rawPath = getCleanPath();
  const activeCamId = cameraId || cameraObj?.id || rawPath;

  // 1. Establish Clean WebRTC Video Stream (Native H.264 stream without burning)
  useEffect(() => {
    if (!rawPath) return;

    setStatus('connecting');
    setErrorMessage('');
    setUseFallbackMjpeg(false);

    const host = window.location.hostname || 'localhost';
    const isServer = window.location.port === '31017' || window.location.port === '31030' || host === '124.123.89.162';
    const targetPort = cameraObj?.webrtc_port || (isServer ? 32089 : 8889);
    const whepUrl = `http://${host}:${targetPort}/${rawPath}/whep`;

    let active = true;

    try {
      readerRef.current = new MediaMTXWebRTCReader({
        url: whepUrl,
        onError: (err) => {
          if (!active) return;
          console.warn(`[WebRTC ${rawPath}] Error:`, err);
          // If WebRTC fails or endpoint offline, fall back to backend MJPEG stream
          setUseFallbackMjpeg(true);
          setStatus('fallback');
          setErrorMessage(String(err || 'WebRTC stream unavailable'));
        },
        onTrack: (evt) => {
          if (!active) return;
          if (videoRef.current && evt.streams && evt.streams[0]) {
            videoRef.current.srcObject = evt.streams[0];
            setStatus('playing');
            setErrorMessage('');
            setUseFallbackMjpeg(false);
          }
        }
      });
    } catch (e) {
      if (!active) return;
      console.error(`[WebRTC ${rawPath}] Init error:`, e);
      setUseFallbackMjpeg(true);
      setStatus('fallback');
      setErrorMessage(e.message);
    }

    return () => {
      active = false;
      if (readerRef.current) {
        try {
          readerRef.current.close();
        } catch (_) {}
        readerRef.current = null;
      }
    };
  }, [rawPath, cameraObj?.webrtc_port]);

  // 2. Client-Side Tactical Canvas Drawing
  const drawBoxes = useCallback((boxes) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    if (canvas.width !== rect.width || canvas.height !== rect.height) {
      canvas.width = rect.width;
      canvas.height = rect.height;
    }

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!boxes || boxes.length === 0) return;

    // Calculate aspect ratio fit (account for letterboxing/pillarboxing)
    const video = videoRef.current;
    const vw = (video && video.videoWidth) ? video.videoWidth : 1280;
    const vh = (video && video.videoHeight) ? video.videoHeight : 720;
    const cw = canvas.width;
    const ch = canvas.height;

    const videoRatio = vw / vh;
    const canvasRatio = cw / ch;

    let renderW = cw;
    let renderH = ch;
    let offsetX = 0;
    let offsetY = 0;

    if (canvasRatio > videoRatio) {
      renderH = ch;
      renderW = ch * videoRatio;
      offsetX = (cw - renderW) / 2;
    } else {
      renderW = cw;
      renderH = cw / videoRatio;
      offsetY = (ch - renderH) / 2;
    }

    boxes.forEach((b) => {
      const bx = offsetX + b.x * renderW;
      const by = offsetY + b.y * renderH;
      const bw = b.w * renderW;
      const bh = b.h * renderH;

      const color = b.color || (b.is_blacklisted ? '#dc2626' : (b.is_transit ? '#10b981' : '#38bdf8'));
      const tag = b.tag || (b.is_blacklisted ? 'BLACKLIST' : (b.is_transit ? 'TRANSIT' : 'DETECTED'));
      const tagBg = b.tag_bg || (b.is_blacklisted ? '#991b1b' : (b.is_transit ? '#065f46' : 'rgba(15, 23, 42, 0.88)'));

      // Corner Brackets
      const dLen = Math.max(6, Math.min(bw, bh) * 0.22);
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.5;

      ctx.beginPath();
      // Top-Left
      ctx.moveTo(bx, by + dLen);
      ctx.lineTo(bx, by);
      ctx.lineTo(bx + dLen, by);

      // Top-Right
      ctx.moveTo(bx + bw - dLen, by);
      ctx.lineTo(bx + bw, by);
      ctx.lineTo(bx + bw, by + dLen);

      // Bottom-Left
      ctx.moveTo(bx, by + bh - dLen);
      ctx.lineTo(bx, by + bh);
      ctx.lineTo(bx + dLen, by + bh);

      // Bottom-Right
      ctx.moveTo(bx + bw - dLen, by + bh);
      ctx.lineTo(bx + bw, by + bh);
      ctx.lineTo(bx + bw, by + bh - dLen);
      ctx.stroke();

      // Tag Header Pill
      if (tag) {
        ctx.font = 'bold 11px sans-serif';
        const textMetrics = ctx.measureText(tag);
        const textW = textMetrics.width;
        const pillH = 17;
        const pillY = Math.max(by - pillH - 4, 4);

        ctx.fillStyle = tagBg;
        if (ctx.roundRect) {
          ctx.beginPath();
          ctx.roundRect(bx, pillY, textW + 12, pillH, 4);
          ctx.fill();
        } else {
          ctx.fillRect(bx, pillY, textW + 12, pillH);
        }

        ctx.fillStyle = '#ffffff';
        ctx.fillText(tag, bx + 6, pillY + 12);
      }
    });
  }, []);

  // 3. Connect to Real-time HUD SSE Stream When HUD Is Enabled
  useEffect(() => {
    if (!hudEnabled || !activeCamId) {
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
      return;
    }

    let es = null;
    let pollTimer = null;
    let active = true;

    // Use SSE for ultra-fast, zero-overhead bbox updates
    try {
      es = new EventSource(`/api/stream/hud/sse?camera=${encodeURIComponent(activeCamId)}`);
      es.onmessage = (evt) => {
        if (!active) return;
        try {
          const data = JSON.parse(evt.data);
          if (data && Array.isArray(data.boxes)) {
            drawBoxes(data.boxes);
          } else if (Array.isArray(data)) {
            drawBoxes(data);
          }
        } catch (_) {}
      };
      es.onerror = () => {
        // Fallback polling if SSE is not supported or disconnected
        if (!pollTimer && active) {
          pollTimer = setInterval(async () => {
            if (!active) return;
            try {
              const res = await fetch(`/api/stream/hud?camera=${encodeURIComponent(activeCamId)}`);
              const data = await res.json();
              if (data && Array.isArray(data.boxes)) {
                drawBoxes(data.boxes);
              }
            } catch (_) {}
          }, 150);
        }
      };
    } catch (_) {}

    return () => {
      active = false;
      if (es) {
        es.close();
      }
      if (pollTimer) {
        clearInterval(pollTimer);
      }
    };
  }, [hudEnabled, activeCamId, drawBoxes]);

  return (
    <div
      onClick={onClick}
      title={title}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        backgroundColor: '#070a13',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        userSelect: 'none',
        ...style
      }}
    >
      {/* 1. Hardware GPU-Decoded Native WebRTC Video Element */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        onPlay={() => setStatus('playing')}
        onLoadedMetadata={() => setStatus('playing')}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          display: status === 'playing' ? 'block' : 'none',
          pointerEvents: 'none'
        }}
      />

      {/* 2. Fallback MJPEG Stream (automatically active if WebRTC is offline or establishing) */}
      {useFallbackMjpeg && (
        <img
          src={`/api/stream/feed?camera=${encodeURIComponent(activeCamId)}&hud=0`}
          alt={title || activeCamId}
          onLoad={() => setStatus('playing')}
          onError={() => setStatus('error')}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            display: status === 'playing' || status === 'fallback' ? 'block' : 'none',
            pointerEvents: 'none'
          }}
        />
      )}

      {/* 3. HTML5 Tactical HUD Canvas Overlay (Active only when HUD is ON) */}
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
          zIndex: 10,
          display: hudEnabled ? 'block' : 'none'
        }}
      />

      {/* 4. Connecting Indicator */}
      {status === 'connecting' && !useFallbackMjpeg && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            backgroundColor: 'rgba(7, 10, 19, 0.75)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            color: '#38bdf8',
            fontSize: '13px',
            fontWeight: '600',
            zIndex: 15
          }}
        >
          <div
            style={{
              width: '32px',
              height: '32px',
              border: '3px solid rgba(56, 189, 248, 0.2)',
              borderTopColor: '#38bdf8',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite'
            }}
          />
          <span style={{ color: '#94a3b8', fontSize: '12px' }}>
            Connecting Ultra-Low Latency Stream...
          </span>
        </div>
      )}

      {/* 5. Offline / Error Indicator */}
      {status === 'error' && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            backgroundColor: '#070a13',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            color: '#ef4444',
            padding: '16px',
            textAlign: 'center',
            zIndex: 15
          }}
        >
          <div style={{ fontSize: '28px' }}>📡</div>
          <div style={{ fontSize: '13px', fontWeight: '700', color: '#f87171' }}>
            Camera Stream Unavailable
          </div>
          <div style={{ fontSize: '11px', color: '#64748b', maxWidth: '260px' }}>
            {errorMessage || 'RTSP signal offline; auto-reconnecting'}
          </div>
        </div>
      )}
    </div>
  );
}
