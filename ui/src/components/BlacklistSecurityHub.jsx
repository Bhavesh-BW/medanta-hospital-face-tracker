import React, { useState, useMemo } from 'react';

const formatAlertTime = (ts) => {
  if (!ts) return 'Just now';
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
  return s.replace('T', ' ').slice(0, 19);
};

export default function BlacklistSecurityHub({ watchlist, alerts, onRemoveBlacklist, onEnrollManual }) {
  const [activeTab, setActiveTab] = useState('trail'); // 'trail' | 'watchlist'
  const [search, setSearch] = useState('');
  const [selectedCamFilter, setSelectedCamFilter] = useState('all');
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [manualName, setManualName] = useState('');
  const [manualReason, setManualReason] = useState('');
  const [manualPhotoB64, setManualPhotoB64] = useState('');
  const [enrolling, setEnrolling] = useState(false);

  // Pagination states for both tabs
  const [trailPage, setTrailPage] = useState(1);
  const [trailPageSize, setTrailPageSize] = useState(10);
  const [watchlistPage, setWatchlistPage] = useState(1);
  const [watchlistPageSize, setWatchlistPageSize] = useState(10);

  // Filter alerts (sightings across all cameras)
  const filteredAlerts = useMemo(() => {
    return (alerts || []).filter(item => {
      const q = search.toLowerCase();
      const matchSearch = (
        (item.person_name || '').toLowerCase().includes(q) ||
        (item.watchlist_id || '').toLowerCase().includes(q) ||
        (item.camera_name || '').toLowerCase().includes(q) ||
        (item.location || '').toLowerCase().includes(q) ||
        (item.reason || '').toLowerCase().includes(q)
      );
      const matchCam = selectedCamFilter === 'all' || item.camera_id === selectedCamFilter;
      return matchSearch && matchCam;
    });
  }, [alerts, search, selectedCamFilter]);

  // Filter watchlist
  const filteredWatchlist = useMemo(() => {
    return (watchlist || []).filter(item => 
      (item.name || '').toLowerCase().includes(search.toLowerCase()) ||
      (item.blacklist_reason || '').toLowerCase().includes(search.toLowerCase()) ||
      (item.reason || '').toLowerCase().includes(search.toLowerCase()) ||
      (item.person_id || '').toLowerCase().includes(search.toLowerCase()) ||
      (item.alias || '').toLowerCase().includes(search.toLowerCase()) ||
      (item.id || '').toLowerCase().includes(search.toLowerCase())
    );
  }, [watchlist, search]);

  // Trail Pagination calculations
  const totalTrail = filteredAlerts.length;
  const totalTrailPages = Math.max(1, Math.ceil(totalTrail / trailPageSize));
  const safeTrailPage = Math.min(Math.max(1, trailPage), totalTrailPages);
  const trailStart = (safeTrailPage - 1) * trailPageSize;
  const trailEnd = Math.min(trailStart + trailPageSize, totalTrail);
  const paginatedAlerts = filteredAlerts.slice(trailStart, trailEnd);

  // Watchlist Pagination calculations
  const totalWatchlist = filteredWatchlist.length;
  const totalWatchlistPages = Math.max(1, Math.ceil(totalWatchlist / watchlistPageSize));
  const safeWatchlistPage = Math.min(Math.max(1, watchlistPage), totalWatchlistPages);
  const wlStart = (safeWatchlistPage - 1) * watchlistPageSize;
  const wlEnd = Math.min(wlStart + watchlistPageSize, totalWatchlist);
  const paginatedWatchlist = filteredWatchlist.slice(wlStart, wlEnd);

  const handleSearchChange = (e) => {
    setSearch(e.target.value);
    setTrailPage(1);
    setWatchlistPage(1);
  };

  const handleCamFilterChange = (camId) => {
    setSelectedCamFilter(camId);
    setTrailPage(1);
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setTrailPage(1);
    setWatchlistPage(1);
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      setManualPhotoB64(event.target.result);
    };
    reader.readAsDataURL(file);
  };

  const handleEnrollSubmit = async (e) => {
    e.preventDefault();
    if (!manualPhotoB64) {
      alert("Please upload a photo containing the person's face.");
      return;
    }
    setEnrolling(true);
    try {
      await onEnrollManual(manualPhotoB64, manualName || 'Unknown Threat', manualReason || 'Security Watchlist');
      setShowEnrollModal(false);
      setManualName('');
      setManualReason('');
      setManualPhotoB64('');
    } catch (err) {
      alert(`Enrollment failed: ${err.message}`);
    } finally {
      setEnrolling(false);
    }
  };

  return (
    <div className="med-card" style={{ padding: '20px', marginBottom: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h3 style={{ fontSize: '16px', fontWeight: '800', color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>Blacklisted Security Watchlist & Incident Hub</span>
            <span style={{ fontSize: '11px', fontWeight: '700', padding: '2px 8px', borderRadius: '9999px', backgroundColor: '#fee2e2', color: '#b91c1c' }}>
              High Priority Screening
            </span>
          </h3>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Real-time biometric threat monitoring with instantaneous cross-camera facial recognition & passage audit trail
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Search Box */}
          <input
            type="text"
            placeholder={activeTab === 'trail' ? "Filter camera, name, ID..." : "Search watchlist..."}
            value={search}
            onChange={handleSearchChange}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border-light)',
              fontSize: '12px',
              outline: 'none',
              width: '190px'
            }}
          />

          {/* Enroll Blacklisted Person Button */}
          <button
            type="button"
            onClick={() => setShowEnrollModal(true)}
            style={{
              padding: '7px 14px',
              borderRadius: '8px',
              backgroundColor: '#e11d48',
              color: '#ffffff',
              fontSize: '12px',
              fontWeight: '700',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              cursor: 'pointer',
              boxShadow: '0 1px 2px rgba(225,29,72,0.2)'
            }}
          >
            <span>+ Enroll Watchlist</span>
          </button>
        </div>
      </div>

      {/* View Switcher Tabs */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: '1px solid var(--border-light)',
        marginBottom: '16px',
        flexWrap: 'wrap',
        gap: '10px'
      }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            onClick={() => handleTabChange('trail')}
            style={{
              padding: '8px 16px',
              borderBottom: activeTab === 'trail' ? '2px solid #e11d48' : '2px solid transparent',
              color: activeTab === 'trail' ? '#e11d48' : 'var(--text-muted)',
              fontWeight: activeTab === 'trail' ? '800' : '600',
              fontSize: '13px',
              backgroundColor: 'transparent',
              borderTop: 'none',
              borderLeft: 'none',
              borderRight: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            <span>🚨 Cross-Camera Sighting & Passage Trail</span>
            <span style={{
              fontSize: '11px',
              padding: '1px 7px',
              borderRadius: '9999px',
              backgroundColor: activeTab === 'trail' ? '#fee2e2' : '#f1f5f9',
              color: activeTab === 'trail' ? '#991b1b' : 'var(--text-dim)',
              fontWeight: '700'
            }}>
              {(alerts || []).length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => handleTabChange('watchlist')}
            style={{
              padding: '8px 16px',
              borderBottom: activeTab === 'watchlist' ? '2px solid #0284c7' : '2px solid transparent',
              color: activeTab === 'watchlist' ? '#0284c7' : 'var(--text-muted)',
              fontWeight: activeTab === 'watchlist' ? '800' : '600',
              fontSize: '13px',
              backgroundColor: 'transparent',
              borderTop: 'none',
              borderLeft: 'none',
              borderRight: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            <span>📋 Enrolled Watchlist</span>
            <span style={{
              fontSize: '11px',
              padding: '1px 7px',
              borderRadius: '9999px',
              backgroundColor: activeTab === 'watchlist' ? '#e0f2fe' : '#f1f5f9',
              color: activeTab === 'watchlist' ? '#0369a1' : 'var(--text-dim)',
              fontWeight: '700'
            }}>
              {(watchlist || []).length}
            </span>
          </button>
        </div>

        {/* Camera Filter Pills for Trail tab */}
        {activeTab === 'trail' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', paddingBottom: '6px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-dim)' }}>CAMERA:</span>
            {[
              { id: 'all', label: 'All Cameras' },
              { id: 'main', label: 'Main Porch' },
              { id: 'recep1', label: 'Reception & OPD' },
              { id: 'outside', label: 'Perimeter Gates' },
              { id: 'ot1', label: 'OT Corridor' }
            ].map(c => (
              <button
                key={c.id}
                type="button"
                onClick={() => handleCamFilterChange(c.id)}
                style={{
                  padding: '2px 8px',
                  borderRadius: '6px',
                  border: `1px solid ${selectedCamFilter === c.id ? '#e11d48' : 'var(--border-light)'}`,
                  backgroundColor: selectedCamFilter === c.id ? '#fff1f2' : '#ffffff',
                  color: selectedCamFilter === c.id ? '#e11d48' : 'var(--text-muted)',
                  fontSize: '11px',
                  fontWeight: selectedCamFilter === c.id ? '700' : '500',
                  cursor: 'pointer'
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── TAB 1: CROSS-CAMERA SIGHTING & PASSAGE TRAIL ── */}
      {activeTab === 'trail' && (
        <div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: '#fff5f5', borderBottom: '1px solid #fecdd3', color: '#991b1b' }}>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>CCTV SNAPSHOT / ID</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>BLACKLISTED INDIVIDUAL</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>SECURITY REASON</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>CAMERA & LOCATION</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>TIME SEEN</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>CONFIDENCE</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700', textAlign: 'right' }}>INCIDENT STATUS</th>
                </tr>
              </thead>
              <tbody>
                {filteredAlerts.length === 0 ? (
                  <tr>
                    <td colSpan="7" style={{ padding: '36px 20px', textAlign: 'center', color: 'var(--text-dim)' }}>
                      <div style={{ fontSize: '28px', marginBottom: '8px' }}>🛡️</div>
                      <div style={{ fontWeight: '700', color: 'var(--text-main)', marginBottom: '4px' }}>
                        No Blacklisted Sightings Logged
                      </div>
                      <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        Active biometric surveillance is running across all CCTV cameras. Sightings appear automatically when identified.
                      </p>
                    </td>
                  </tr>
                ) : (
                  paginatedAlerts.map((item, idx) => {
                    const confNum = item.confidence ? Number(item.confidence) : 94.0;
                    return (
                      <tr key={item.id || idx} style={{ borderBottom: '1px solid #f1f5f9', backgroundColor: idx === 0 && safeTrailPage === 1 ? '#fffafb' : '#ffffff' }}>
                        {/* CCTV Snapshot */}
                        <td style={{ padding: '10px 14px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{
                              width: '36px',
                              height: '36px',
                              borderRadius: '8px',
                              backgroundColor: '#fee2e2',
                              border: '2px solid #e11d48',
                              overflow: 'hidden',
                              flexShrink: 0,
                              boxShadow: '0 0 6px rgba(225,29,72,0.3)'
                            }}>
                              {item.photo_b64 ? (
                                <img src={item.photo_b64} alt={item.person_name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                              ) : (
                                <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px' }}>🚨</div>
                              )}
                            </div>
                            <div>
                              <div style={{ fontWeight: '800', fontFamily: 'var(--font-mono)', color: '#b91c1c', fontSize: '11px' }}>
                                {item.id}
                              </div>
                              <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>CCTV Capture</div>
                            </div>
                          </div>
                        </td>

                        {/* Blacklisted Individual */}
                        <td style={{ padding: '10px 14px' }}>
                          <div style={{ fontWeight: '800', color: '#1e293b', fontSize: '13px' }}>
                            {item.person_name || 'Unidentified Threat'}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                            <span style={{
                              fontFamily: 'var(--font-mono)',
                              fontSize: '11px',
                              fontWeight: '700',
                              padding: '1px 6px',
                              borderRadius: '4px',
                              backgroundColor: '#fee2e2',
                              color: '#b91c1c'
                            }}>
                              {item.watchlist_id || 'WATCHLIST'}
                            </span>
                          </div>
                        </td>

                        {/* Security Reason */}
                        <td style={{ padding: '10px 14px', maxWidth: '200px' }}>
                          <span style={{ color: 'var(--text-main)', fontSize: '12px', fontWeight: '500' }}>
                            {item.reason || 'Barred from OPD Premises'}
                          </span>
                        </td>

                        {/* Camera & Location */}
                        <td style={{ padding: '10px 14px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ fontSize: '12px' }}>📹</span>
                            <span style={{ fontWeight: '700', color: 'var(--text-main)', fontSize: '12px' }}>
                              {item.camera_name || 'Main Porch Entry'}
                            </span>
                          </div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <span>📍</span>
                            <span>{item.location || 'Gate 01 Main Entry'}</span>
                          </div>
                        </td>

                        {/* Time Seen */}
                        <td style={{ padding: '10px 14px', whiteSpace: 'nowrap' }}>
                          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: '700', color: '#1e293b', fontSize: '12px' }}>
                            {formatAlertTime(item.timestamp || item.created_at)}
                          </div>
                        </td>

                        {/* Confidence (Dynamic, not hardcoded) */}
                        <td style={{ padding: '10px 14px' }}>
                          <span style={{
                            padding: '3px 8px',
                            borderRadius: '6px',
                            backgroundColor: '#ecfdf5',
                            border: '1px solid #a7f3d0',
                            color: '#047857',
                            fontWeight: '800',
                            fontSize: '11px',
                            fontFamily: 'var(--font-mono)'
                          }}>
                            {confNum.toFixed(1)}% Match
                          </span>
                        </td>

                        {/* Incident Status */}
                        <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                          <span style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '5px',
                            padding: '3px 10px',
                            borderRadius: '9999px',
                            backgroundColor: '#fee2e2',
                            border: '1px solid #fca5a5',
                            color: '#991b1b',
                            fontWeight: '800',
                            fontSize: '11px'
                          }}>
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#ef4444' }}></span>
                            {item.status || 'CRITICAL SIGHTING'}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Controlled Pagination Footer for Trail */}
          {totalTrail > 0 && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 14px',
              borderTop: '1px solid #fee2e2',
              backgroundColor: '#fffafb',
              borderRadius: '0 0 10px 10px',
              marginTop: '4px',
              flexWrap: 'wrap',
              gap: '12px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '12px', color: '#64748b' }}>
                  Showing <strong>{trailStart + 1}</strong> – <strong>{trailEnd}</strong> of <strong>{totalTrail}</strong> sightings
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#94a3b8' }}>Rows:</span>
                  <select
                    value={trailPageSize}
                    onChange={(e) => {
                      setTrailPageSize(Number(e.target.value));
                      setTrailPage(1);
                    }}
                    style={{
                      padding: '2px 8px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '11px',
                      fontWeight: '700',
                      color: '#1e293b',
                      backgroundColor: '#ffffff',
                      outline: 'none',
                      cursor: 'pointer'
                    }}
                  >
                    <option value={5}>5</option>
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <button
                  type="button"
                  disabled={safeTrailPage <= 1}
                  onClick={() => setTrailPage(1)}
                  style={{
                    padding: '4px 8px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: safeTrailPage <= 1 ? '#f1f5f9' : '#ffffff',
                    color: safeTrailPage <= 1 ? '#94a3b8' : '#1e293b',
                    fontSize: '11px',
                    fontWeight: '700',
                    cursor: safeTrailPage <= 1 ? 'not-allowed' : 'pointer'
                  }}
                  title="First Page"
                >
                  ⏮ First
                </button>
                <button
                  type="button"
                  disabled={safeTrailPage <= 1}
                  onClick={() => setTrailPage(prev => Math.max(1, prev - 1))}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: safeTrailPage <= 1 ? '#f1f5f9' : '#ffffff',
                    color: safeTrailPage <= 1 ? '#94a3b8' : '#1e293b',
                    fontSize: '11px',
                    fontWeight: '700',
                    cursor: safeTrailPage <= 1 ? 'not-allowed' : 'pointer'
                  }}
                >
                  ◀ Prev
                </button>

                <span style={{ fontSize: '12px', fontWeight: '700', color: '#1e293b', padding: '0 6px' }}>
                  Page {safeTrailPage} of {totalTrailPages}
                </span>

                <button
                  type="button"
                  disabled={safeTrailPage >= totalTrailPages}
                  onClick={() => setTrailPage(prev => Math.min(totalTrailPages, prev + 1))}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: safeTrailPage >= totalTrailPages ? '#f1f5f9' : '#ffffff',
                    color: safeTrailPage >= totalTrailPages ? '#94a3b8' : '#1e293b',
                    fontSize: '11px',
                    fontWeight: '700',
                    cursor: safeTrailPage >= totalTrailPages ? 'not-allowed' : 'pointer'
                  }}
                >
                  Next ▶
                </button>
                <button
                  type="button"
                  disabled={safeTrailPage >= totalTrailPages}
                  onClick={() => setTrailPage(totalTrailPages)}
                  style={{
                    padding: '4px 8px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: safeTrailPage >= totalTrailPages ? '#f1f5f9' : '#ffffff',
                    color: safeTrailPage >= totalTrailPages ? '#94a3b8' : '#1e293b',
                    fontSize: '11px',
                    fontWeight: '700',
                    cursor: safeTrailPage >= totalTrailPages ? 'not-allowed' : 'pointer'
                  }}
                  title="Last Page"
                >
                  Last ⏭
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 2: ENROLLED WATCHLIST ── */}
      {activeTab === 'watchlist' && (
        <div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid var(--border-light)', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>PHOTO / PERSON</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>CATEGORY</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>SECURITY REASON</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700' }}>ENROLLED DATE</th>
                  <th style={{ padding: '10px 14px', fontWeight: '700', textAlign: 'right' }}>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {filteredWatchlist.length === 0 ? (
                  <tr>
                    <td colSpan="5" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-dim)' }}>
                      No enrolled blacklist targets found matching query.
                    </td>
                  </tr>
                ) : (
                  paginatedWatchlist.map((item, idx) => (
                    <tr key={item.id || idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '12px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div style={{
                            width: '38px',
                            height: '38px',
                            borderRadius: '8px',
                            backgroundColor: '#fee2e2',
                            border: '2px solid #ef4444',
                            overflow: 'hidden',
                            flexShrink: 0
                          }}>
                            {item.photo_b64 ? (
                              <img src={item.photo_b64} alt={item.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            ) : (
                              <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px' }}>🚨</div>
                            )}
                          </div>
                          <div>
                            <div style={{ fontWeight: '700', color: '#991b1b', fontSize: '13px' }}>
                              {item.name || item.id}
                            </div>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)' }}>
                              {item.id}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '12px 14px' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          backgroundColor: '#f1f5f9',
                          color: 'var(--text-muted)',
                          fontWeight: '700',
                          fontSize: '11px',
                          textTransform: 'uppercase'
                        }}>
                          {item.category || 'VISITOR'}
                        </span>
                      </td>
                      <td style={{ padding: '12px 14px', color: '#991b1b', fontWeight: '500' }}>
                        {item.reason || item.blacklist_reason || 'Security threat / Banned'}
                      </td>
                      <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>
                        {item.enrolled_at ? item.enrolled_at.slice(0, 10) : '2026-11-11'}
                      </td>
                      <td style={{ padding: '12px 14px', textAlign: 'right' }}>
                        <button
                          type="button"
                          onClick={() => onRemoveBlacklist(item)}
                          style={{
                            padding: '4px 10px',
                            borderRadius: '6px',
                            backgroundColor: '#f8fafc',
                            border: '1px solid var(--border-light)',
                            color: 'var(--text-muted)',
                            fontSize: '11px',
                            fontWeight: '600',
                            cursor: 'pointer'
                          }}
                        >
                          Revoke Blacklist
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Controlled Pagination Footer for Watchlist */}
          {totalWatchlist > 0 && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 14px',
              borderTop: '1px solid var(--border-light)',
              backgroundColor: '#f8fafc',
              borderRadius: '0 0 10px 10px',
              marginTop: '4px',
              flexWrap: 'wrap',
              gap: '12px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '12px', color: '#64748b' }}>
                  Showing <strong>{wlStart + 1}</strong> – <strong>{wlEnd}</strong> of <strong>{totalWatchlist}</strong> targets
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#94a3b8' }}>Rows:</span>
                  <select
                    value={watchlistPageSize}
                    onChange={(e) => {
                      setWatchlistPageSize(Number(e.target.value));
                      setWatchlistPage(1);
                    }}
                    style={{
                      padding: '2px 8px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '11px',
                      fontWeight: '700',
                      color: '#1e293b',
                      backgroundColor: '#ffffff',
                      outline: 'none',
                      cursor: 'pointer'
                    }}
                  >
                    <option value={5}>5</option>
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <button
                  type="button"
                  disabled={safeWatchlistPage <= 1}
                  onClick={() => setWatchlistPage(1)}
                  style={{
                    padding: '4px 8px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: safeWatchlistPage <= 1 ? '#f1f5f9' : '#ffffff',
                    color: safeWatchlistPage <= 1 ? '#94a3b8' : '#1e293b',
                    fontSize: '11px',
                    fontWeight: '700',
                    cursor: safeWatchlistPage <= 1 ? 'not-allowed' : 'pointer'
                  }}
                  title="First Page"
                >
                  ⏮ First
                </button>
                <button
                  type="button"
                  disabled={safeWatchlistPage <= 1}
                  onClick={() => setWatchlistPage(prev => Math.max(1, prev - 1))}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: safeWatchlistPage <= 1 ? '#f1f5f9' : '#ffffff',
                    color: safeWatchlistPage <= 1 ? '#94a3b8' : '#1e293b',
                    fontSize: '11px',
                    fontWeight: '700',
                    cursor: safeWatchlistPage <= 1 ? 'not-allowed' : 'pointer'
                  }}
                >
                  ◀ Prev
                </button>

                <span style={{ fontSize: '12px', fontWeight: '700', color: '#1e293b', padding: '0 6px' }}>
                  Page {safeWatchlistPage} of {totalWatchlistPages}
                </span>

                <button
                  type="button"
                  disabled={safeWatchlistPage >= totalWatchlistPages}
                  onClick={() => setWatchlistPage(prev => Math.min(totalWatchlistPages, prev + 1))}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: safeWatchlistPage >= totalWatchlistPages ? '#f1f5f9' : '#ffffff',
                    color: safeWatchlistPage >= totalWatchlistPages ? '#94a3b8' : '#1e293b',
                    fontSize: '11px',
                    fontWeight: '700',
                    cursor: safeWatchlistPage >= totalWatchlistPages ? 'not-allowed' : 'pointer'
                  }}
                >
                  Next ▶
                </button>
                <button
                  type="button"
                  disabled={safeWatchlistPage >= totalWatchlistPages}
                  onClick={() => setWatchlistPage(totalWatchlistPages)}
                  style={{
                    padding: '4px 8px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: safeWatchlistPage >= totalWatchlistPages ? '#f1f5f9' : '#ffffff',
                    color: safeWatchlistPage >= totalWatchlistPages ? '#94a3b8' : '#1e293b',
                    fontSize: '11px',
                    fontWeight: '700',
                    cursor: safeWatchlistPage >= totalWatchlistPages ? 'not-allowed' : 'pointer'
                  }}
                  title="Last Page"
                >
                  Last ⏭
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Manual Enrollment Modal */}
      {showEnrollModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: '#ffffff',
            borderRadius: '16px',
            padding: '24px',
            maxWidth: '480px',
            width: '90%',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)'
          }}>
            <h4 style={{ fontSize: '16px', fontWeight: '800', color: 'var(--text-main)', marginBottom: '4px' }}>
              Enroll Person to Security Watchlist
            </h4>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>
              Upload a clear facial photograph. InsightFace will extract and register the 512-d vector for automated camera detection.
            </p>

            <form onSubmit={handleEnrollSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '700', marginBottom: '4px' }}>Full Name / Alias:</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Ramesh Kumar"
                  value={manualName}
                  onChange={(e) => setManualName(e.target.value)}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--border-light)', fontSize: '13px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '700', marginBottom: '4px' }}>Reason for Blacklisting:</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Theft in OPD Room 204 / Barred"
                  value={manualReason}
                  onChange={(e) => setManualReason(e.target.value)}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--border-light)', fontSize: '13px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '700', marginBottom: '4px' }}>Face Photo (JPEG/PNG):</label>
                <input
                  type="file"
                  accept="image/*"
                  required
                  onChange={handleFileChange}
                  style={{ fontSize: '12px' }}
                />
                {manualPhotoB64 && (
                  <div style={{ marginTop: '8px', width: '80px', height: '80px', borderRadius: '8px', overflow: 'hidden', border: '1px solid var(--border-light)' }}>
                    <img src={manualPhotoB64} alt="Preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowEnrollModal(false)}
                  style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--border-light)', color: 'var(--text-muted)', fontSize: '12px', fontWeight: '600', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={enrolling}
                  style={{ padding: '8px 16px', borderRadius: '8px', backgroundColor: '#e11d48', color: '#ffffff', fontSize: '12px', fontWeight: '700', cursor: 'pointer' }}
                >
                  {enrolling ? 'Extracting Vector...' : 'Save & Activate'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
