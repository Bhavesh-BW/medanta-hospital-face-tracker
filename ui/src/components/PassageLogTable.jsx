import React, { useState, useMemo } from 'react';

export default function PassageLogTable({ visitors = [], alerts = [], onOpenJourney }) {
  const [filterMode, setFilterMode] = useState('all'); // 'all' | 'multi' | 'blacklisted'
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10); // default 10 rows per page to prevent long scroll

  // Identify all multi-camera visitors
  const multiCameraVisitors = useMemo(() => {
    return (visitors || []).filter(v => v.is_multi_camera || (v.camera_count && v.camera_count > 1));
  }, [visitors]);

  // Determine base list by filter mode
  const baseList = useMemo(() => {
    if (filterMode === 'blacklisted') return alerts || [];
    if (filterMode === 'multi') return multiCameraVisitors;
    return visitors || [];
  }, [filterMode, alerts, multiCameraVisitors, visitors]);

  // Apply search query filter
  const displayList = useMemo(() => {
    if (!searchQuery.trim()) return baseList;
    const q = searchQuery.toLowerCase().trim();
    return baseList.filter(item => {
      const id = String(item.id || item.watchlist_id || '').toLowerCase();
      const name = String(item.person_name || item.name || '').toLowerCase();
      const cam = String(item.camera_name || '').toLowerCase();
      const loc = String(item.location || '').toLowerCase();
      const route = String(item.route_str || '').toLowerCase();
      return id.includes(q) || name.includes(q) || cam.includes(q) || loc.includes(q) || route.includes(q);
    });
  }, [baseList, searchQuery]);

  // Pagination calculations
  const totalItems = displayList.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const safeCurrentPage = Math.min(Math.max(1, currentPage), totalPages);
  const startIndex = (safeCurrentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, totalItems);
  const paginatedList = displayList.slice(startIndex, endIndex);

  // Format date time helper (IST-enforced)
  const formatTime = (ts) => {
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

  const handleFilterChange = (mode) => {
    setFilterMode(mode);
    setCurrentPage(1);
  };

  const handleSearchChange = (val) => {
    setSearchQuery(val);
    setCurrentPage(1);
  };

  return (
    <div className="med-card" style={{ padding: '20px', marginBottom: '32px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '14px' }}>
        <div>
          <h3 style={{ fontSize: '16px', fontWeight: '800', color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span>Visitor Demographic & Passage Verification Log</span>
            {filterMode === 'multi' && (
              <span style={{ fontSize: '11px', fontWeight: '800', padding: '2px 10px', borderRadius: '9999px', backgroundColor: '#f3e8ff', color: '#7c3aed', border: '1px solid #ddd6fe' }}>
                🟣 Filtering: Multi-Camera Journeys ({displayList.length})
              </span>
            )}
            {filterMode === 'blacklisted' && (
              <span style={{ fontSize: '11px', fontWeight: '800', padding: '2px 10px', borderRadius: '9999px', backgroundColor: '#fee2e2', color: '#b91c1c', border: '1px solid #fecdd3' }}>
                ⚠️ Filtering: Blacklisted Camera Sightings ({displayList.length})
              </span>
            )}
          </h3>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            {filterMode === 'multi'
              ? 'Auditing cross-checkpoint visitor journeys: detected across 2 or more CCTV cameras on hospital campus'
              : 'Full immutable passage audit trail for Medanta The Medicity across all CCTV camera checkpoints'}
          </p>
        </div>

        {/* View Switcher Tabs & Live Search */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Quick Search */}
          <div style={{ position: 'relative' }}>
            <input
              type="text"
              placeholder="Search ID, camera, route..."
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              style={{
                padding: '6px 12px 6px 28px',
                fontSize: '12px',
                borderRadius: '8px',
                border: '1px solid var(--border-light, #cbd5e1)',
                backgroundColor: '#ffffff',
                color: '#1e293b',
                outline: 'none',
                width: '180px'
              }}
            />
            <span style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', fontSize: '12px', color: '#94a3b8' }}>
              🔍
            </span>
            {searchQuery && (
              <button
                type="button"
                onClick={() => handleSearchChange('')}
                style={{
                  position: 'absolute',
                  right: '6px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  fontSize: '11px',
                  color: '#94a3b8',
                  cursor: 'pointer'
                }}
              >
                ✕
              </button>
            )}
          </div>

          {/* View Switcher Tabs */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#f1f5f9', padding: '3px', borderRadius: '8px' }}>
            {/* All Passages */}
            <button
              type="button"
              onClick={() => handleFilterChange('all')}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: filterMode === 'all' ? '#ffffff' : 'transparent',
                color: filterMode === 'all' ? 'var(--text-main)' : 'var(--text-muted)',
                fontSize: '12px',
                fontWeight: filterMode === 'all' ? '800' : '600',
                cursor: 'pointer',
                boxShadow: filterMode === 'all' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              <span>All Passages</span>
              <span style={{
                fontSize: '11px',
                padding: '1px 6px',
                borderRadius: '9999px',
                backgroundColor: filterMode === 'all' ? '#e2e8f0' : '#e2e8f0',
                color: '#334155',
                fontWeight: '700'
              }}>
                {(visitors || []).length}
              </span>
            </button>

            {/* Multi-Camera Journeys */}
            <button
              type="button"
              onClick={() => handleFilterChange('multi')}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                border: 'none',
                background: filterMode === 'multi' ? 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)' : 'transparent',
                color: filterMode === 'multi' ? '#ffffff' : '#6d28d9',
                fontSize: '12px',
                fontWeight: filterMode === 'multi' ? '800' : '700',
                cursor: 'pointer',
                boxShadow: filterMode === 'multi' ? '0 2px 6px rgba(124, 58, 237, 0.35)' : 'none',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
              title="Filter visitors detected across 2 or more cameras to view cross-campus journeys"
            >
              <span>🚶 Multi-Camera Journeys</span>
              <span style={{
                fontSize: '11px',
                padding: '1px 7px',
                borderRadius: '9999px',
                backgroundColor: filterMode === 'multi' ? '#ffffff' : '#ede9fe',
                color: '#7c3aed',
                fontWeight: '800'
              }}>
                {multiCameraVisitors.length}
              </span>
            </button>

            {/* Blacklisted Only */}
            <button
              type="button"
              onClick={() => handleFilterChange('blacklisted')}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: filterMode === 'blacklisted' ? '#e11d48' : 'transparent',
                color: filterMode === 'blacklisted' ? '#ffffff' : '#b91c1c',
                fontSize: '12px',
                fontWeight: filterMode === 'blacklisted' ? '800' : '600',
                cursor: 'pointer',
                boxShadow: filterMode === 'blacklisted' ? '0 1px 3px rgba(225,29,72,0.3)' : 'none',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              <span>⚠️ Blacklisted Only</span>
              <span style={{
                fontSize: '11px',
                padding: '1px 6px',
                borderRadius: '9999px',
                backgroundColor: filterMode === 'blacklisted' ? '#ffffff' : '#fee2e2',
                color: filterMode === 'blacklisted' ? '#e11d48' : '#b91c1c',
                fontWeight: '800'
              }}>
                {(alerts || []).length}
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Table Container */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
          <thead>
            <tr style={{
              backgroundColor: filterMode === 'blacklisted' ? '#fff1f2' : filterMode === 'multi' ? '#f5f3ff' : '#f8fafc',
              borderBottom: `2px solid ${filterMode === 'blacklisted' ? '#fecdd3' : filterMode === 'multi' ? '#ddd6fe' : 'var(--border-light, #e2e8f0)'}`,
              color: filterMode === 'blacklisted' ? '#991b1b' : filterMode === 'multi' ? '#5b21b6' : 'var(--text-muted, #64748b)'
            }}>
              <th style={{ padding: '12px 14px', fontWeight: '800' }}>VISITOR (PHOTO & TRACK ID)</th>
              <th style={{ padding: '12px 14px', fontWeight: '800' }}>
                {filterMode === 'blacklisted' ? 'SECURITY REASON / CATEGORY' : 'DEMOGRAPHIC / GENDER'}
              </th>
              <th style={{ padding: '12px 14px', fontWeight: '800' }}>
                {filterMode === 'multi' ? 'CROSS-CAMERA TRANSIT ROUTE' : 'CCTV CAMERA & GATE LOCATION'}
              </th>
              <th style={{ padding: '12px 14px', fontWeight: '800' }}>
                {filterMode === 'multi' ? 'TRANSIT DURATION & DWELL' : 'PASSAGE TIME'}
              </th>
              <th style={{ padding: '12px 14px', fontWeight: '800' }}>
                {filterMode === 'multi' ? 'CAMERAS CONFIRMED' : 'STATUS'}
              </th>
              <th style={{ padding: '12px 14px', fontWeight: '800', textAlign: 'center' }}>ACTIONS</th>
              <th style={{ padding: '12px 14px', fontWeight: '800', textAlign: 'right' }}>VERIFICATION RATE</th>
            </tr>
          </thead>
          <tbody>
            {(!paginatedList || paginatedList.length === 0) ? (
              <tr>
                <td colSpan="7" style={{ padding: '36px', textAlign: 'center', color: 'var(--text-dim, #64748b)' }}>
                  {filterMode === 'multi' ? (
                    <div>
                      <div style={{ fontSize: '24px', marginBottom: '8px' }}>🚶</div>
                      <div style={{ fontWeight: '700', fontSize: '14px', color: '#475569' }}>No Multi-Camera Journeys Found</div>
                      <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>
                        Visitors who appear in 2 or more CCTV cameras will automatically be compiled here for journey audit.
                      </div>
                    </div>
                  ) : filterMode === 'blacklisted' ? (
                    <div>
                      <div style={{ fontSize: '24px', marginBottom: '8px' }}>🛡️</div>
                      <div style={{ fontWeight: '700', fontSize: '14px', color: '#475569' }}>No Blacklisted Sighting Records</div>
                    </div>
                  ) : (
                    <div>No visitor passage records found in selected view.</div>
                  )}
                </td>
              </tr>
            ) : filterMode === 'blacklisted' ? (
              // Blacklisted Sightings Across All Cameras View
              paginatedList.map((item, idx) => {
                const confScore = item.confidence ? Number(item.confidence) : 94.0;
                return (
                  <tr key={item.id || idx} style={{ borderBottom: '1px solid #fee2e2', backgroundColor: idx % 2 === 0 ? '#fffafb' : '#ffffff' }}>
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{
                          width: '36px',
                          height: '36px',
                          borderRadius: '8px',
                          backgroundColor: '#fee2e2',
                          border: '2px solid #e11d48',
                          overflow: 'hidden',
                          flexShrink: 0
                        }}>
                          {item.photo_b64 ? (
                            <img src={item.photo_b64} alt={item.person_name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px' }}>🚨</div>
                          )}
                        </div>
                        <div>
                          <div style={{ fontWeight: '800', fontFamily: 'var(--font-mono)', color: '#b91c1c' }}>
                            {item.person_name || item.watchlist_id}
                          </div>
                          <div style={{ fontSize: '10px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                            {item.id}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor: '#fee2e2',
                        color: '#b91c1c',
                        fontWeight: '800',
                        fontSize: '11px',
                        display: 'inline-block',
                        marginBottom: '2px'
                      }}>
                        BLACKLISTED
                      </span>
                      <div style={{ fontSize: '11px', color: 'var(--text-main)', fontWeight: '500' }}>
                        {item.reason || 'Barred from Premises'}
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ fontWeight: '700', color: 'var(--text-main)' }}>
                        📹 {item.camera_name || 'Main Porch Entry'}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        📍 {item.location || 'Gate 01 Main Entry'}
                      </div>
                      {item.previous_camera_name && item.previous_camera_name !== (item.camera_name || 'Main Porch Entry') && (
                        <div style={{
                          marginTop: '4px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: '#fef2f2',
                          border: '1px solid #fecdd3',
                          color: '#b91c1c',
                          fontSize: '10px',
                          fontWeight: '700'
                        }}>
                          <span>🔄 Cross-Cam Transit:</span>
                          <span>Seen at {item.previous_camera_name}</span>
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)', fontWeight: '700', color: '#1e293b' }}>
                      {item.timestamp || 'Just now'}
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor: '#fee2e2',
                        color: '#b91c1c',
                        fontWeight: '800',
                        fontSize: '11px'
                      }}>
                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#ef4444' }}></span>
                        {item.status || 'CRITICAL SIGHTING'}
                      </span>
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                      {onOpenJourney && (item.watchlist_id || item.visitor_id || item.id) && (
                        <button
                          type="button"
                          onClick={() => onOpenJourney(item.watchlist_id || item.visitor_id || item.id)}
                          style={{
                            padding: '4px 10px',
                            borderRadius: '6px',
                            backgroundColor: '#fef2f2',
                            color: '#b91c1c',
                            border: '1px solid #fecdd3',
                            fontSize: '11px',
                            fontWeight: '700',
                            cursor: 'pointer'
                          }}
                        >
                          📍 Journey
                        </button>
                      )}
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: '800', color: '#e11d48', fontFamily: 'var(--font-mono)' }}>
                      {confScore.toFixed(1)}%
                    </td>
                  </tr>
                );
              })
            ) : filterMode === 'multi' ? (
              // Dedicated Multi-Camera Cross-Checkpoint Journeys View
              paginatedList.map((item, idx) => {
                const camCount = item.camera_count || (item.cameras_seen ? item.cameras_seen.length : 2);
                const camNames = item.camera_names || [item.camera_name || 'Main Porch Entry'];
                const confScore = item.verification_rate != null ? Number(item.verification_rate) : (item.confidence ? Number(item.confidence) : 86.5);
                const confColor = confScore >= 80 ? '#059669' : confScore >= 70 ? '#0284c7' : '#d97706';

                return (
                  <tr
                    key={item.id || idx}
                    style={{
                      borderBottom: '1px solid #ede9fe',
                      backgroundColor: idx % 2 === 0 ? '#fbfaff' : '#ffffff',
                      transition: 'background-color 0.15s ease'
                    }}
                  >
                    {/* Visitor Photo & Track ID */}
                    <td style={{ padding: '12px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{
                          width: '38px',
                          height: '38px',
                          borderRadius: '8px',
                          backgroundColor: '#ede9fe',
                          border: '2px solid #7c3aed',
                          overflow: 'hidden',
                          flexShrink: 0,
                          position: 'relative'
                        }}>
                          {item.photo_b64 ? (
                            <img src={item.photo_b64} alt={item.id} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px' }}>👤</div>
                          )}
                          <span style={{
                            position: 'absolute',
                            bottom: 0,
                            right: 0,
                            backgroundColor: '#7c3aed',
                            color: '#ffffff',
                            fontSize: '9px',
                            fontWeight: '800',
                            padding: '0 3px',
                            borderRadius: '3px 0 0 0'
                          }}>
                            {camCount}C
                          </span>
                        </div>
                        <div>
                          <div style={{ fontWeight: '800', fontFamily: 'var(--font-mono)', color: '#6d28d9', fontSize: '13px' }}>
                            {item.id}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                            <span style={{
                              padding: '1px 6px',
                              borderRadius: '4px',
                              backgroundColor: '#ede9fe',
                              color: '#6d28d9',
                              fontSize: '10px',
                              fontWeight: '700'
                            }}>
                              🟣 {camCount} CAMERAS DETECTED
                            </span>
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Demographic */}
                    <td style={{ padding: '12px 14px' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor: item.gender === 'female' ? '#ffe4e6' : '#e0f2fe',
                        color: item.gender === 'female' ? '#e11d48' : '#0369a1',
                        fontWeight: '700',
                        textTransform: 'uppercase',
                        fontSize: '11px'
                      }}>
                        {item.gender || 'MALE'}
                      </span>
                      <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                        ~{item.age || 32} yrs
                      </div>
                    </td>

                    {/* Multi-Camera Transit Route */}
                    <td style={{ padding: '12px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                        {camNames.map((cName, cIdx) => (
                          <React.Fragment key={cIdx}>
                            <span style={{
                              padding: '3px 8px',
                              borderRadius: '6px',
                              backgroundColor: cIdx === 0 ? '#ecfdf5' : cIdx === camNames.length - 1 ? '#f5f3ff' : '#eff6ff',
                              color: cIdx === 0 ? '#047857' : cIdx === camNames.length - 1 ? '#6d28d9' : '#1d4ed8',
                              border: `1px solid ${cIdx === 0 ? '#a7f3d0' : cIdx === camNames.length - 1 ? '#ddd6fe' : '#bfdbfe'}`,
                              fontSize: '11px',
                              fontWeight: '700'
                            }}>
                              {cIdx === 0 ? '🟢 ' : cIdx === camNames.length - 1 ? '🟣 ' : '🔵 '}
                              {cName}
                            </span>
                            {cIdx < camNames.length - 1 && (
                              <span style={{ color: '#7c3aed', fontWeight: '800', fontSize: '12px' }}>➔</span>
                            )}
                          </React.Fragment>
                        ))}
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                        📍 Total Recorded Sightings: <strong style={{ color: '#0f172a' }}>{item.total_sightings || item.sightings || 2}</strong>
                      </div>
                    </td>

                    {/* Transit Duration & Dwell */}
                    <td style={{ padding: '12px 14px' }}>
                      <div style={{ fontWeight: '800', color: '#059669', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <span>⏱ Dwell:</span>
                        <span>{item.dwell_str || `${item.dwell_mins || 1}m`}</span>
                      </div>
                      <div style={{ fontSize: '10px', color: '#64748b', marginTop: '3px' }}>
                        First: {formatTime(item.first_seen)}
                      </div>
                      <div style={{ fontSize: '10px', color: '#64748b' }}>
                        Latest: {formatTime(item.last_seen || item.started_at)}
                      </div>
                    </td>

                    {/* Cameras Confirmed Status */}
                    <td style={{ padding: '12px 14px' }}>
                      <span style={{
                        padding: '3px 10px',
                        borderRadius: '6px',
                        backgroundColor: '#f5f3ff',
                        color: '#6d28d9',
                        border: '1px solid #ddd6fe',
                        fontWeight: '800',
                        fontSize: '11px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}>
                        <span style={{ width: '7px', height: '7px', borderRadius: '50%', backgroundColor: '#7c3aed' }}></span>
                        MULTI-CAM CONFIRMED
                      </span>
                    </td>

                    {/* Action: Open Journey Audit */}
                    <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                      {onOpenJourney && (
                        <button
                          type="button"
                          onClick={() => onOpenJourney(item.id)}
                          style={{
                            padding: '6px 14px',
                            borderRadius: '8px',
                            background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                            color: '#ffffff',
                            border: 'none',
                            fontSize: '12px',
                            fontWeight: '800',
                            cursor: 'pointer',
                            boxShadow: '0 2px 6px rgba(124, 58, 237, 0.3)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            whiteSpace: 'nowrap'
                          }}
                          title="Open Interactive Cross-Camera Journey Map"
                        >
                          <span>🗺️ View Journey</span>
                          <span style={{
                            backgroundColor: 'rgba(255,255,255,0.25)',
                            padding: '1px 6px',
                            borderRadius: '9999px',
                            fontSize: '10px'
                          }}>
                            {camCount}
                          </span>
                        </button>
                      )}
                    </td>

                    {/* Verification Rate */}
                    <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: '800', color: confColor, fontFamily: 'var(--font-mono)', fontSize: '13px' }}>
                      {confScore.toFixed(1)}%
                    </td>
                  </tr>
                );
              })
            ) : (
              // All General Passages View (with prominent multi-cam indicators)
              paginatedList.map((item, idx) => {
                const isMulti = item.is_multi_camera || (item.camera_count && item.camera_count > 1);
                const camCount = item.camera_count || 1;
                const confScore = item.verification_rate != null ? Number(item.verification_rate) : (item.confidence ? Number(item.confidence) : 84.5);
                const confColor = item.is_blacklisted ? '#e11d48' : confScore >= 80 ? '#059669' : confScore >= 70 ? '#0284c7' : '#d97706';

                return (
                  <tr
                    key={item.id || idx}
                    style={{
                      borderBottom: '1px solid #f1f5f9',
                      backgroundColor: item.is_blacklisted
                        ? '#fff5f5'
                        : isMulti
                        ? '#fcfaff'
                        : '#ffffff'
                    }}
                  >
                    {/* Visitor Photo & ID */}
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{
                          width: '34px',
                          height: '34px',
                          borderRadius: '8px',
                          backgroundColor: '#e2e8f0',
                          border: item.is_blacklisted
                            ? '2px solid #e11d48'
                            : isMulti
                            ? '2px solid #7c3aed'
                            : '1px solid #cbd5e1',
                          overflow: 'hidden',
                          flexShrink: 0,
                          position: 'relative'
                        }}>
                          {item.photo_b64 ? (
                            <img src={item.photo_b64} alt={item.id} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '15px' }}>👤</div>
                          )}
                          {isMulti && (
                            <span style={{
                              position: 'absolute',
                              bottom: 0,
                              right: 0,
                              backgroundColor: '#7c3aed',
                              color: '#ffffff',
                              fontSize: '8px',
                              fontWeight: '800',
                              padding: '0 3px',
                              borderRadius: '3px 0 0 0'
                            }}>
                              {camCount}C
                            </span>
                          )}
                        </div>
                        <div>
                          <div style={{
                            fontWeight: '800',
                            fontFamily: 'var(--font-mono)',
                            color: item.is_blacklisted ? '#b91c1c' : isMulti ? '#6d28d9' : 'var(--text-main)'
                          }}>
                            {item.id}
                          </div>
                          {isMulti && (
                            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', marginTop: '1px' }}>
                              <span style={{
                                fontSize: '10px',
                                fontWeight: '700',
                                color: '#7c3aed',
                                backgroundColor: '#f5f3ff',
                                padding: '1px 5px',
                                borderRadius: '4px',
                                border: '1px solid #ddd6fe'
                              }}>
                                🟣 {camCount} Cams Transit
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Demographic */}
                    <td style={{ padding: '10px 14px' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor: item.gender === 'female' ? '#ffe4e6' : '#e0f2fe',
                        color: item.gender === 'female' ? '#e11d48' : '#0369a1',
                        fontWeight: '700',
                        textTransform: 'uppercase'
                      }}>
                        {item.gender || 'MALE'}
                      </span>
                    </td>

                    {/* Camera & Gate / Transit Route */}
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ fontWeight: '700', color: 'var(--text-main)' }}>
                        📹 {item.camera_name || 'Main Porch Entry'}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        📍 {item.location || 'Gate 01 Main Entry'}
                      </div>
                      {isMulti && item.route_str && (
                        <div style={{
                          marginTop: '4px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          backgroundColor: '#f5f3ff',
                          border: '1px solid #ddd6fe',
                          color: '#6d28d9',
                          fontSize: '10px',
                          fontWeight: '700'
                        }}>
                          <span>🔄 Route:</span>
                          <span>{item.route_str}</span>
                        </div>
                      )}
                      {!isMulti && item.previous_camera_name && item.previous_camera_name !== item.camera_name && (
                        <div style={{
                          marginTop: '4px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: '#eff6ff',
                          border: '1px solid #bfdbfe',
                          color: '#1d4ed8',
                          fontSize: '10px',
                          fontWeight: '700'
                        }}>
                          <span>🔄 Transit:</span>
                          <span>Seen at {item.previous_camera_name}</span>
                        </div>
                      )}
                    </td>

                    {/* Passage Time & Dwell */}
                    <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)', color: 'var(--text-main)' }}>
                      <div>{formatTime(item.last_seen || item.started_at)}</div>
                      {isMulti && (
                        <div style={{ fontSize: '11px', color: '#059669', fontWeight: '700', marginTop: '2px' }}>
                          ⏱ Dwell: {item.dwell_str || `${item.dwell_mins || 1}m`}
                        </div>
                      )}
                    </td>

                    {/* Status */}
                    <td style={{ padding: '10px 14px' }}>
                      {item.is_blacklisted ? (
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          backgroundColor: '#fee2e2',
                          color: '#b91c1c',
                          fontWeight: '800',
                          fontSize: '11px'
                        }}>
                          BLACKLISTED
                        </span>
                      ) : isMulti ? (
                        <span style={{
                          padding: '3px 8px',
                          borderRadius: '6px',
                          backgroundColor: '#f5f3ff',
                          color: '#6d28d9',
                          border: '1px solid #ddd6fe',
                          fontWeight: '800',
                          fontSize: '11px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '5px'
                        }}>
                          <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#7c3aed' }}></span>
                          MULTI-CAM
                        </span>
                      ) : (
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          backgroundColor: '#ecfdf5',
                          color: '#047857',
                          fontWeight: '700'
                        }}>
                          VERIFIED
                        </span>
                      )}
                    </td>

                    {/* Actions */}
                    <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                      {onOpenJourney && (
                        <button
                          type="button"
                          onClick={() => onOpenJourney(item.id)}
                          style={{
                            padding: isMulti ? '4px 12px' : '3px 8px',
                            borderRadius: '6px',
                            background: isMulti ? 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)' : '#f0fdf4',
                            color: isMulti ? '#ffffff' : '#15803d',
                            border: isMulti ? 'none' : '1px solid #bbf7d0',
                            fontSize: '11px',
                            fontWeight: '800',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            boxShadow: isMulti ? '0 2px 5px rgba(124, 58, 237, 0.25)' : 'none'
                          }}
                          title={isMulti ? `View chronological journey across ${camCount} cameras` : 'View passage journey'}
                        >
                          <span>{isMulti ? '🗺️ View Journey' : '📍 Journey'}</span>
                          {isMulti && (
                            <span style={{
                              backgroundColor: 'rgba(255,255,255,0.25)',
                              padding: '1px 5px',
                              borderRadius: '9999px',
                              fontSize: '10px'
                            }}>
                              {camCount}
                            </span>
                          )}
                        </button>
                      )}
                    </td>

                    {/* Verification Rate */}
                    <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: '800', color: confColor, fontFamily: 'var(--font-mono)' }}>
                      {confScore.toFixed(1)}%
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Controlled Pagination Footer */}
      {totalItems > 0 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderTop: '1px solid var(--border-light, #e2e8f0)',
          marginTop: '4px',
          flexWrap: 'wrap',
          gap: '12px',
          backgroundColor: '#f8fafc',
          borderRadius: '0 0 10px 10px'
        }}>
          {/* Sighting Range & Page Size Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <span style={{ fontSize: '12px', color: '#64748b' }}>
              Showing <strong>{startIndex + 1}</strong> – <strong>{endIndex}</strong> of <strong>{totalItems}</strong> records
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>Rows:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setCurrentPage(1);
                }}
                style={{
                  padding: '3px 8px',
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
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>

          {/* Navigation Buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              type="button"
              disabled={safeCurrentPage <= 1}
              onClick={() => setCurrentPage(1)}
              style={{
                padding: '4px 8px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: safeCurrentPage <= 1 ? '#f1f5f9' : '#ffffff',
                color: safeCurrentPage <= 1 ? '#94a3b8' : '#1e293b',
                fontSize: '11px',
                fontWeight: '700',
                cursor: safeCurrentPage <= 1 ? 'not-allowed' : 'pointer'
              }}
              title="First Page"
            >
              ⏮ First
            </button>
            <button
              type="button"
              disabled={safeCurrentPage <= 1}
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              style={{
                padding: '4px 10px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: safeCurrentPage <= 1 ? '#f1f5f9' : '#ffffff',
                color: safeCurrentPage <= 1 ? '#94a3b8' : '#1e293b',
                fontSize: '11px',
                fontWeight: '700',
                cursor: safeCurrentPage <= 1 ? 'not-allowed' : 'pointer'
              }}
            >
              ◀ Prev
            </button>

            <span style={{ fontSize: '12px', fontWeight: '700', color: '#1e293b', padding: '0 8px' }}>
              Page {safeCurrentPage} of {totalPages}
            </span>

            <button
              type="button"
              disabled={safeCurrentPage >= totalPages}
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              style={{
                padding: '4px 10px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: safeCurrentPage >= totalPages ? '#f1f5f9' : '#ffffff',
                color: safeCurrentPage >= totalPages ? '#94a3b8' : '#1e293b',
                fontSize: '11px',
                fontWeight: '700',
                cursor: safeCurrentPage >= totalPages ? 'not-allowed' : 'pointer'
              }}
            >
              Next ▶
            </button>
            <button
              type="button"
              disabled={safeCurrentPage >= totalPages}
              onClick={() => setCurrentPage(totalPages)}
              style={{
                padding: '4px 8px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: safeCurrentPage >= totalPages ? '#f1f5f9' : '#ffffff',
                color: safeCurrentPage >= totalPages ? '#94a3b8' : '#1e293b',
                fontSize: '11px',
                fontWeight: '700',
                cursor: safeCurrentPage >= totalPages ? 'not-allowed' : 'pointer'
              }}
              title="Last Page"
            >
              Last ⏭
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
