import React, { useEffect, useRef, useState } from 'react';
import { MediaMTXWebRTCReader } from '../utils/webrtcReader';

/** Pure WebRTC player for MediaMTX WHEP endpoints (HUD-burned or raw camera feed). */
export default function WebRTCPlayer({
  streamPath,
  cameraObj,
  cameraId,
  hudEnabled = true,
  refreshKey = 0,
  onClick,
  title = '',
  style = {}
}) {
  const videoRef = useRef(null);
  const readerRef = useRef(null);
  const [status, setStatus] = useState('connecting'); // 'connecting' | 'playing' | 'error'
  const [errorMessage, setErrorMessage] = useState('');

  const getRawPath = () => {
    let p = cameraObj?.webrtc_path || streamPath;
    if (!p && cameraObj?.rtsp) {
      if (cameraObj.rtsp.includes('/live/')) {
        p = 'live/' + cameraObj.rtsp.split('/live/')[1].split('?')[0].replace(/^\/+|\/+$/g, '');
      } else if (cameraObj.rtsp.includes(':31554/')) {
        p = cameraObj.rtsp.split(':31554/')[1].split('?')[0].replace(/^\/+|\/+$/g, '');
      } else if (cameraObj.rtsp.includes(':8554/')) {
        p = cameraObj.rtsp.split(':8554/')[1].split('?')[0].replace(/^\/+|\/+$/g, '');
      }
    }
    return p || cameraObj?.id || cameraId;
  };

  const rawPath = getRawPath();
  const baseId = cameraId || cameraObj?.id || (rawPath ? String(rawPath).replace(/^live\//, '').replace(/_hud$/, '') : '');
  const targetPath = hudEnabled
    ? (cameraObj?.webrtc_hud_path || (baseId ? `${baseId}_hud` : ''))
    : rawPath;

  useEffect(() => {
    if (!targetPath) return;

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
          console.warn(`[WebRTC ${targetPath}] Error:`, err);
          setStatus('error');
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
      console.error(`[WebRTC ${targetPath}] Initialization error:`, e);
      setStatus('error');
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
      if (videoRef.current) {
        try {
          videoRef.current.srcObject = null;
        } catch (_) {}
      }
    };
  }, [targetPath, cameraObj?.webrtc_port, refreshKey]);

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
      {/* Hardware-Accelerated Native WebRTC Video Element */}
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
            {hudEnabled ? 'Connecting AI HUD WebRTC Stream...' : 'Connecting Raw WebRTC Stream...'}
          </span>
        </div>
      )}

      {/* Offline / Auto-Retry Indicator (No heavy MJPEG fallback) */}
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
            WebRTC Stream Initializing
          </div>
          <div style={{ fontSize: '11px', color: '#64748b', maxWidth: '280px' }}>
            {errorMessage.includes('404')
              ? `Waiting for ${targetPath} stream publisher (auto-retrying)...`
              : errorMessage || 'RTSP signal offline; auto-reconnecting'}
          </div>
        </div>
      )}
    </div>
  );
}
