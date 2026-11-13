import React, { useEffect, useState } from 'react';

// Clean IST 24-hour time formatting (matches card display "20:30:52")
const formatTimeIST = (ts) => {
  if (!ts) return 'N/A';
  const s = String(ts).trim();
  if (s.endsWith('Z') || s.includes('+00:00')) {
    const d = new Date(s);
    if (!isNaN(d.getTime())) {
      return d.toLocaleTimeString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
    }
  }
  if (typeof s === 'string' && s.includes('T')) {
    return s.split('T')[1].slice(0, 8);
  }
  if (typeof s === 'string' && s.includes(' ')) {
    return s.split(' ')[1].slice(0, 8);
  }
  return String(s).slice(-8);
};

const formatDateTimeIST = (ts) => {
  if (!ts) return 'N/A';
  const s = String(ts).trim();
  if (s.endsWith('Z') || s.includes('+00:00')) {
    const d = new Date(s);
    if (!isNaN(d.getTime())) {
      return d.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      }).replace(',', '');
    }
  }
  if (typeof s === 'string' && s.includes('T')) {
    const [d, t] = s.split('T');
    return `${d} ${t.slice(0, 8)}`;
  }
  return String(s).replace('T', ' ').slice(0, 19);
};

export default function JourneyTimelineModal({ visitorId, isOpen, onClose, onBlacklist }) {
  const [journey, setJourney] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen || !visitorId) {
      setJourney(null);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    fetch(`/api/visitors/journey?visitor_id=${encodeURIComponent(visitorId)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (isMounted) {
          setJourney(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Failed to load journey audit');
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, visitorId]);

  if (!isOpen) return null;

  const isBlk = journey?.is_blacklisted;
  const isFemale = journey?.gender === 'female';
  const checkpoints = journey?.checkpoints || [];

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.72)',
        backdropFilter: 'blur(5px)',
        zIndex: 99999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        animation: 'fadeIn 0.15s ease-out'
      }}
      onClick={onClose}
    >
      <div
        className="med-card"
        style={{
          width: '100%',
          maxWidth: '680px',
          maxHeight: '90vh',
          backgroundColor: '#ffffff',
          borderRadius: '16px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          border: isBlk ? '2px solid #ef4444' : '1px solid #e2e8f0'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 24px',
            borderBottom: '1px solid #f1f5f9',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: isBlk ? 'linear-gradient(135deg, #fef2f2 0%, #fff 100%)' : 'linear-gradient(135deg, #f8fafc 0%, #fff 100%)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                backgroundColor: isBlk ? '#fee2e2' : '#e0f2fe',
                color: isBlk ? '#dc2626' : '#0284c7',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '18px',
                fontWeight: '800'
              }}
            >
              📍
            </span>
            <div>
              <h2 style={{ fontSize: '18px', fontWeight: '800', color: '#0f172a', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>Visitor Cross-Camera Journey Audit</span>
                {isBlk && (
                  <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '9999px', backgroundColor: '#fee2e2', color: '#dc2626', fontWeight: '800' }}>
                    BLACKLISTED
                  </span>
                )}
              </h2>
              <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0 0' }}>
                Multi-camera tracking & transit checkpoints across Entry, Exit & Interior Relays
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: '#f1f5f9',
              border: 'none',
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '16px',
              fontWeight: '700',
              color: '#64748b',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            ✕
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>
              <div style={{ fontSize: '24px', marginBottom: '8px' }}>⏳</div>
              <p style={{ fontWeight: '600', fontSize: '14px' }}>Compiling multi-camera checkpoints...</p>
            </div>
          )}

          {error && (
            <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: '#fef2f2', border: '1px solid #fecdd3', color: '#b91c1c', fontSize: '13px' }}>
              <strong>Error:</strong> {error}
            </div>
          )}

          {!loading && journey && (
            <div>
              {/* Visitor Profile Summary Card */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '16px',
                  padding: '16px',
                  borderRadius: '12px',
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  marginBottom: '24px'
                }}
              >
                {/* Photo Thumbnail */}
                <div
                  style={{
                    width: '64px',
                    height: '64px',
                    borderRadius: '12px',
                    overflow: 'hidden',
                    backgroundColor: '#e2e8f0',
                    flexShrink: 0,
                    border: `2px solid ${isBlk ? '#ef4444' : isFemale ? '#ec4899' : '#3b82f6'}`
                  }}
                >
                  {journey.photo_b64 ? (
                    <img src={journey.photo_b64} alt={journey.visitor_id} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  ) : (
                    <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '24px' }}>
                      👤
                    </div>
                  )}
                </div>

                {/* Details */}
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '16px', fontWeight: '800', color: '#0f172a', fontFamily: 'monospace' }}>
                      {journey.visitor_id}
                    </span>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: '9999px',
                        fontSize: '11px',
                        fontWeight: '700',
                        backgroundColor: isFemale ? '#fdf2f8' : '#eff6ff',
                        color: isFemale ? '#db2777' : '#2563eb'
                      }}
                    >
                      {journey.gender?.toUpperCase()} ~{journey.age}y
                    </span>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: '9999px',
                        fontSize: '11px',
                        fontWeight: '700',
                        backgroundColor: '#f0fdf4',
                        color: '#15803d'
                      }}
                    >
                      ⏱ {journey.total_dwell_mins || 1} mins on premises
                    </span>
                  </div>

                  <div style={{ fontSize: '12px', color: '#64748b', marginTop: '6px', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                    <span>
                      Latest Sighting (Card Time):{' '}
                      <strong style={{ color: '#0284c7', fontSize: '13px' }}>
                        {formatTimeIST(journey.last_seen || journey.last_seen_time || journey.first_seen)}
                      </strong>
                    </span>
                    <span>
                      First Inbound Entry:{' '}
                      <strong style={{ color: '#0f172a' }}>
                        {formatTimeIST(journey.first_seen || journey.first_seen_time)}
                      </strong>
                    </span>
                    <span>
                      Last Checkpoint:{' '}
                      <strong style={{ color: '#0f172a' }}>
                        {checkpoints[checkpoints.length - 1]?.camera_name || journey.last_camera || 'Main Porch'}
                      </strong>
                    </span>
                    <span>
                      Total Sightings:{' '}
                      <strong style={{ color: '#0f172a' }}>
                        {checkpoints.length}
                      </strong>
                    </span>
                  </div>
                </div>
              </div>

              {/* Checkpoints Timeline */}
              <div style={{ position: 'relative', paddingLeft: '28px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: '800', color: '#334155', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '16px' }}>
                  Camera Sightings Timeline ({checkpoints.length} Checkpoints)
                </h3>

                {/* Vertical Timeline Track Line */}
                <div
                  style={{
                    position: 'absolute',
                    top: '40px',
                    bottom: '20px',
                    left: '11px',
                    width: '2px',
                    backgroundColor: '#cbd5e1'
                  }}
                />

                {checkpoints.map((cp, idx) => {
                  const isFirst = idx === 0;
                  const isLast = idx === checkpoints.length - 1;
                  const isExit = cp.camera_id?.includes('exit') || cp.camera_name?.toLowerCase().includes('exit');

                  let dotColor = '#3b82f6';
                  let badgeBg = '#eff6ff';
                  let badgeText = '#1d4ed8';
                  let typeLabel = 'INTERMEDIATE SIGHTING';

                  if (isFirst) {
                    dotColor = '#10b981';
                    badgeBg = '#ecfdf5';
                    badgeText = '#047857';
                    typeLabel = 'INBOUND ENTRY';
                  } else if (isExit) {
                    dotColor = '#8b5cf6';
                    badgeBg = '#f5f3ff';
                    badgeText = '#6d28d9';
                    typeLabel = 'OUTBOUND EXIT';
                  } else if (isLast) {
                    dotColor = '#0284c7';
                    badgeBg = '#e0f2fe';
                    badgeText = '#0369a1';
                    typeLabel = 'LATEST PASSAGE (CARD)';
                  } else {
                    dotColor = '#3b82f6';
                    badgeBg = '#eff6ff';
                    badgeText = '#1d4ed8';
                    typeLabel = 'INTERMEDIATE SIGHTING';
                  }

                  return (
                    <div
                      key={idx}
                      style={{
                        position: 'relative',
                        marginBottom: idx === checkpoints.length - 1 ? 0 : '20px'
                      }}
                    >
                      {/* Timeline Dot */}
                      <div
                        style={{
                          position: 'absolute',
                          left: '-28px',
                          top: '4px',
                          width: '22px',
                          height: '22px',
                          borderRadius: '50%',
                          backgroundColor: '#ffffff',
                          border: `3px solid ${dotColor}`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '10px',
                          fontWeight: '800',
                          color: dotColor,
                          boxShadow: '0 0 0 2px #fff'
                        }}
                      >
                        {idx + 1}
                      </div>

                      {/* Checkpoint Card */}
                      <div
                        style={{
                          padding: '14px 16px',
                          borderRadius: '10px',
                          backgroundColor: '#ffffff',
                          border: '1px solid #e2e8f0',
                          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '12px',
                          flexWrap: 'wrap'
                        }}
                      >
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                            <span
                              style={{
                                padding: '2px 8px',
                                borderRadius: '4px',
                                fontSize: '10px',
                                fontWeight: '800',
                                backgroundColor: badgeBg,
                                color: badgeText
                              }}
                            >
                              {typeLabel}
                            </span>
                            <span style={{ fontSize: '14px', fontWeight: '800', color: '#0f172a' }}>
                              {cp.camera_name || cp.camera_id}
                            </span>
                          </div>

                          <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                            <span>📍 Location: <strong>{cp.location || 'Hospital Zone'}</strong></span>
                            <span>🕒 Time (IST): <strong>{formatDateTimeIST(cp.timestamp || cp.time_display)}</strong></span>
                            {cp.dwell_mins_since_prev > 0 && (
                              <span style={{ color: '#059669', fontWeight: '700' }}>
                                ⏱ +{cp.dwell_mins_since_prev} min transit duration
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Snapshot Crop */}
                        {cp.photo_b64 && (
                          <div
                            style={{
                              width: '48px',
                              height: '48px',
                              borderRadius: '8px',
                              overflow: 'hidden',
                              backgroundColor: '#f1f5f9',
                              border: '1px solid #cbd5e1',
                              flexShrink: 0
                            }}
                          >
                            <img src={cp.photo_b64} alt="Crop" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid #f1f5f9',
            backgroundColor: '#f8fafc',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px'
          }}
        >
          <div style={{ fontSize: '12px', color: '#64748b' }}>
            Multi-Camera Re-ID Algorithm: <strong>512-d Cosine Metric (Threshold: 0.65)</strong>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            {onBlacklist && !isBlk && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onBlacklist(journey.visitor_id);
                }}
                style={{
                  padding: '8px 14px',
                  borderRadius: '8px',
                  border: '1px solid #fecdd3',
                  backgroundColor: '#fff1f2',
                  color: '#e11d48',
                  fontSize: '12px',
                  fontWeight: '700',
                  cursor: 'pointer'
                }}
              >
                🚫 Blacklist Person
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                color: '#334155',
                fontSize: '12px',
                fontWeight: '700',
                cursor: 'pointer'
              }}
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

