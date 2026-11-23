import React, { useEffect, useRef, useState } from 'react';
import { MediaMTXWebRTCReader } from '../utils/webrtcReader';

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
  const [status, setStatus] = useState('connecting'); // 'connecting' | 'playing' | 'error'
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    const rawPath = streamPath || cameraObj?.webrtc_path || cameraObj?.id;
    if (!rawPath) return;

    // Annotated WebRTC: When hudEnabled is on, stream the 100% frame-locked AI HUD stream ({path}_hud).
    // When hudEnabled is off, stream the clean raw camera feed ({path}).
    const targetPath = hudEnabled ? `${rawPath}_hud` : rawPath;

    setStatus('connecting');
    setErrorMessage('');

    const host = window.location.hostname || 'localhost';
    const isServer = window.location.port === '31017' || window.location.port === '31030' || host === '124.123.89.162';
    const targetPort = cameraObj?.webrtc_port || (isServer ? 32089 : 8889);
    const whepUrl = `http://${host}:${targetPort}/${targetPath}/whep`;

    try {
      readerRef.current = new MediaMTXWebRTCReader({
        url: whepUrl,
        onError: (err) => {
          console.warn(`[WebRTC ${targetPath}] Error:`, err);
          setStatus('error');
          setErrorMessage(String(err || 'Stream disconnected'));
        },
        onTrack: (evt) => {
          if (videoRef.current && evt.streams && evt.streams[0]) {
            videoRef.current.srcObject = evt.streams[0];
            setStatus('playing');
            setErrorMessage('');
          }
        }
      });
    } catch (e) {
      console.error(`[WebRTC ${targetPath}] Initialization error:`, e);
      setStatus('error');
      setErrorMessage(e.message);
    }

    return () => {
      if (readerRef.current) {
        try {
          readerRef.current.close();
        } catch (_) {}
        readerRef.current = null;
      }
    };
  }, [streamPath, cameraObj?.id, cameraObj?.webrtc_path, hudEnabled]);

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
      {/* 100% Hardware GPU Decoded Native WebRTC Video Element */}
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
            {hudEnabled ? 'Connecting Frame-Locked AI WebRTC Stream...' : 'Connecting Ultra-Low Latency WebRTC...'}
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
          <span style={{ color: '#f87171', fontWeight: '600' }}>WebRTC Stream Offline</span>
          <span style={{ fontSize: '11px', color: '#64748b', maxWidth: '80%', textAlign: 'center' }}>
            {errorMessage || 'Waiting for live H.264 camera feed...'}
          </span>
        </div>
      )}
    </div>
  );
}
