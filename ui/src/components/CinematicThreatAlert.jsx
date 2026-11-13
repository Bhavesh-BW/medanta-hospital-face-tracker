import React, { useEffect, useState, useRef } from 'react';
import { playTacticalChime, TACTICAL_CHIME_B64, getOrCreateAudioContext } from '../utils/alertSound';

export default function CinematicThreatAlert({ alert, onDismiss, soundEnabled = true }) {
  const [countdown, setCountdown] = useState(12);
  const audioElemRef = useRef(null);

  useEffect(() => {
    if (!alert) return;
    if (soundEnabled) {
      playTacticalChime();
      if (audioElemRef.current) {
        audioElemRef.current.currentTime = 0;
        audioElemRef.current.play().catch(() => {});
      }
    }
    setCountdown(12);

    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          onDismiss(alert);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [alert, soundEnabled, onDismiss]);

  if (!alert) return null;

  return (
    <div className="floating-threat-card" role="alert" aria-live="assertive">
      <audio ref={audioElemRef} src={TACTICAL_CHIME_B64} preload="auto" style={{ display: 'none' }} />
      <div className="cinematic-scanline" />

      {/* Top Header Badge & Close Button */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="threat-badge-flashing" style={{
            padding: '4px 10px',
            borderRadius: '6px',
            fontSize: '11px',
            fontWeight: '800',
            letterSpacing: '0.06em',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px'
          }}>
            <span>⚠️</span>
            <span>BLACKLISTED VISITOR DETECTED</span>
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{
            fontSize: '10px',
            color: '#94a3b8',
            fontFamily: 'var(--font-mono)',
            backgroundColor: 'rgba(255, 255, 255, 0.08)',
            padding: '2px 7px',
            borderRadius: '4px'
          }}>
            {countdown}s
          </span>

          <button
            type="button"
            onClick={() => onDismiss(alert)}
            aria-label="Dismiss Alert"
            title="Dismiss Alert"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              fontSize: '18px',
              fontWeight: '700',
              cursor: 'pointer',
              lineHeight: 1,
              padding: '2px 4px',
              borderRadius: '4px',
              transition: 'color 0.15s'
            }}
            onMouseOver={(e) => (e.currentTarget.style.color = '#ffffff')}
            onMouseOut={(e) => (e.currentTarget.style.color = '#94a3b8')}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Center Target Lock Area */}
      <div style={{ display: 'flex', gap: '14px', alignItems: 'center', marginBottom: '14px' }}>
        {/* Tactical Crosshair Frame & Face Thumbnail */}
        <div style={{
          position: 'relative',
          width: '76px',
          height: '76px',
          borderRadius: '10px',
          backgroundColor: '#020617',
          border: '2px solid #ef4444',
          overflow: 'hidden',
          flexShrink: 0,
          boxShadow: '0 0 16px rgba(239, 68, 68, 0.45)'
        }}>
          {alert.photo_b64 ? (
            <img
              src={alert.photo_b64}
              alt={alert.person_name}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          ) : (
            <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '28px' }}>
              👤
            </div>
          )}

          {/* Tactical Crosshair Reticle Overlay */}
          <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
            <div style={{ position: 'absolute', top: '3px', left: '3px', width: '10px', height: '10px', borderTop: '2px solid #ef4444', borderLeft: '2px solid #ef4444' }} />
            <div style={{ position: 'absolute', top: '3px', right: '3px', width: '10px', height: '10px', borderTop: '2px solid #ef4444', borderRight: '2px solid #ef4444' }} />
            <div style={{ position: 'absolute', bottom: '3px', left: '3px', width: '10px', height: '10px', borderBottom: '2px solid #ef4444', borderLeft: '2px solid #ef4444' }} />
            <div style={{ position: 'absolute', bottom: '3px', right: '3px', width: '10px', height: '10px', borderBottom: '2px solid #ef4444', borderRight: '2px solid #ef4444' }} />
          </div>

          {/* Match Confidence Pill */}
          <div style={{
            position: 'absolute',
            bottom: '0',
            left: '0',
            right: '0',
            backgroundColor: 'rgba(225, 29, 72, 0.95)',
            color: '#ffffff',
            fontSize: '9px',
            fontWeight: '800',
            textAlign: 'center',
            padding: '2px 0',
            fontFamily: 'var(--font-mono)'
          }}>
            MATCH: {alert.confidence || 94.2}%
          </div>
        </div>

        {/* Perpetrator Intelligence Data */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '10px', color: '#f87171', fontWeight: '800', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            WATCHLIST IDENTIFIED
          </div>
          <h3 style={{
            fontSize: '16px',
            fontWeight: '800',
            color: '#ffffff',
            marginTop: '1px',
            marginBottom: '4px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}>
            {alert.person_name || 'Unidentified Threat'}
          </h3>

          <div style={{ fontSize: '11px', color: '#cbd5e1', display: 'flex', flexDirection: 'column', gap: '3px' }}>
            <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span style={{ color: '#94a3b8' }}>Reason: </span>
              <span style={{ color: '#fca5a5', fontWeight: '700' }}>{alert.reason || 'Barred from Premises'}</span>
            </div>
            <div>
              <span style={{ color: '#94a3b8' }}>Camera: </span>
              <span style={{ color: '#ffffff', fontWeight: '600' }}>{alert.camera_name || 'Main Porch Entry'}</span>
            </div>
            <div>
              <span style={{ color: '#94a3b8' }}>Timestamp: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: '#38bdf8' }}>{alert.timestamp || 'Live Detection'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', paddingTop: '10px', borderTop: '1px solid rgba(244, 63, 94, 0.2)' }}>
        <button
          type="button"
          onClick={() => onDismiss(alert)}
          style={{
            padding: '7px 14px',
            borderRadius: '6px',
            backgroundColor: 'rgba(255, 255, 255, 0.08)',
            color: '#cbd5e1',
            fontSize: '11px',
            fontWeight: '600',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            cursor: 'pointer'
          }}
        >
          Dismiss
        </button>

        <button
          type="button"
          onClick={() => {
            window.alert(`🚨 Dispatching security patrol to ${alert.camera_name || 'Main Porch Entry'} immediately.`);
            onDismiss(alert);
          }}
          style={{
            padding: '7px 16px',
            borderRadius: '6px',
            backgroundColor: '#e11d48',
            color: '#ffffff',
            fontSize: '11px',
            fontWeight: '800',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            cursor: 'pointer',
            border: 'none',
            boxShadow: '0 0 16px rgba(225, 29, 72, 0.6)'
          }}
        >
          <span>🚨 Dispatch Security</span>
        </button>
      </div>
    </div>
  );
}
