import React, { useEffect, useRef, useState } from 'react';
import { MediaMTXWebRTCReader } from '../utils/webrtcReader';

/** Pure WebRTC player for MediaMTX WHEP endpoints (HUD-burned or raw camera feed). */
export default function WebRTCPlayer({
  streamPath,
  cameraObj,
  cameraId,
  hudEnabled = true,
  onClick,
  title = '',
  style = {}
}) {
  const videoRef = useRef(null);
  const readerRef = useRef(null);
  const [status, setStatus] = useState(hudEnabled ? 'playing' : 'connecting'); // 'connecting' | 'playing' | 'fallback' | 'error'
  const [errorMessage, setErrorMessage] = useState('');

  // Resolve base camera ID for backend MJPEG endpoint
  const baseCamId = String(
    cameraId ||
    cameraObj?.id ||
    (streamPath ? String(streamPath).replace(/^live\//, '').replace(/_hud$/, '') : '') ||
    'main'
  ).replace(/^live\//, '').replace(/_hud$/, '');

  useEffect(() => {
    // When HUD is enabled, use synchronous frame-locked MJPEG directly from backend.
    // Frame and bounding box are baked into the same JPEG buffer: 0ms drift / 100% synchronized.
    if (hudEnabled) {
      if (readerRef.current) {
        try { readerRef.current.close(); } catch (_) {}
        readerRef.current = null;
      }
      setStatus('playing');
      setErrorMessage('');
      return;
    }

    // When HUD is OFF, use ultra-low latency direct clean camera WebRTC from MediaMTX
    const rawPath = streamPath || cameraObj?.webrtc_path || cameraObj?.id || baseCamId;
    if (!rawPath) return;

    setStatus('connecting');
    setErrorMessage('');

    const host = window.location.hostname || 'localhost';
    const isServer = ['31017', '31030', '31021'].includes(window.location.port) || host === '124.123.89.162';
    const targetPort = cameraObj?.webrtc_port || (isServer ? 32089 : 8889);
    const whepUrl = `http://${host}:${targetPort}/${targetPath}/whep`;

    let active = true;

    try {
      readerRef.current = new MediaMTXWebRTCReader({
        url: whepUrl,
        onError: (err) => {
          if (!active) return;
          console.warn(`[WebRTC ${rawPath}] Error:`, err);
          // If WebRTC fails, seamlessly fall back to backend MJPEG stream
          setStatus('fallback');
          setErrorMessage(String(err || 'WebRTC stream unavailable'));
        },
        onTrack: (evt) => {
          if (!active) return;
          if (videoRef.current && evt.streams && evt.streams[0]) {
            videoRef.current.srcObject = evt.streams[0];
            setStatus('playing');
            setErrorMessage('');
          }
        }
      });
    } catch (e) {
      if (!active) return;
      console.error(`[WebRTC ${rawPath}] Init error:`, e);
      setStatus('fallback');
      setErrorMessage(e.message);
    }

    return () => {
      active = false;
      if (readerRef.current) {
        try { readerRef.current.close(); } catch (_) {}
        readerRef.current = null;
      }
    };
  }, [streamPath, cameraObj?.id, cameraObj?.webrtc_path, baseCamId, hudEnabled]);

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
      {/* 1. HUD ON Mode: Synchronous Zero-Lag MJPEG Stream (Option 1 - Identical to Port 31030) */}
      {hudEnabled && (
        <img
          key={`hud-${baseCamId}`}
          src={`/api/stream/feed?camera=${encodeURIComponent(baseCamId)}`}
          alt={title || baseCamId}
          onLoad={() => setStatus('playing')}
          onError={() => {
            setStatus('error');
            setErrorMessage('Unable to connect to live AI HUD feed');
          }}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            display: status === 'error' ? 'none' : 'block',
            pointerEvents: 'none'
          }}
        />
      )}

      {/* 2. HUD OFF Mode: Ultra-Low Latency Direct Clean WebRTC Feed */}
      {!hudEnabled && (
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
      )}

      {/* 3. Fallback MJPEG (if WebRTC is offline when HUD is OFF) */}
      {!hudEnabled && status === 'fallback' && (
        <img
          key={`fallback-${baseCamId}`}
          src={`/api/stream/feed?camera=${encodeURIComponent(baseCamId)}`}
          alt={title || baseCamId}
          onError={() => {
            setStatus('error');
            setErrorMessage('Camera feed offline');
          }}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            display: 'block',
            pointerEvents: 'none'
          }}
        />
      )}

      {/* Connecting Spinner Indicator */}
      {status === 'connecting' && (
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
            {hudEnabled ? 'Connecting Zero-Lag AI HUD Stream...' : 'Connecting Ultra-Low Latency WebRTC...'}
          </span>
        </div>
      )}

      {/* Offline / Error Indicator */}
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
            color: '#94a3b8',
            fontSize: '13px',
            fontWeight: '500',
            zIndex: 15
          }}
        >
          <div style={{ color: '#ef4444', fontSize: '24px' }}>📡</div>
          <span style={{ color: '#f87171', fontWeight: '600' }}>Camera Stream Offline</span>
          <span style={{ fontSize: '11px', color: '#64748b', maxWidth: '80%', textAlign: 'center' }}>
            {errorMessage || 'Waiting for live camera feed...'}
          </span>
        </div>
      )}
    </div>
  );
}
