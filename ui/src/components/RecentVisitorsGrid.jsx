import React, { useState, useMemo, useEffect } from 'react';

const formatGridTime = (ts) => {
  if (!ts) return 'Just now';
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
  if (s.length >= 19) return s.slice(11, 19);
  return s;
};

export default function RecentVisitorsGrid({
  visitors = [],
  onBlacklist,
  onRemoveBlacklist,
  onRemoveCrop,
  onMergeProfiles,
  onDeleteProfile,
  onToggleGender,
  onFindSimilar,
  onOpenJourney
}) {
  // Live Grid Freeze State (to stop cards from moving/disappearing when new faces arrive)
  const [gridFrozen, setGridFrozen] = useState(false);
  const [frozenVisitors, setFrozenVisitors] = useState([]);

  // Search & Filter controls
  const [searchQuery, setSearchQuery] = useState('');
  const [genderFilter, setGenderFilter] = useState('all'); // 'all', 'male', 'female', 'blacklisted'
  const [displayLimit, setDisplayLimit] = useState(24);

  // Active crop preview per visitor card: { [visitorId]: activeCropIndex }
  const [selectedCropIndex, setSelectedCropIndex] = useState({});

  // Multi-select for manual merging profiles
  const [selectedMergeIds, setSelectedMergeIds] = useState([]);

  // Smart Similarity Batch Merge Workspace Modal
  const [similarityWorkspaceOpen, setSimilarityWorkspaceOpen] = useState(false);
  const [similarPrimary, setSimilarPrimary] = useState(null);
  const [similarCandidates, setSimilarCandidates] = useState([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState([]);
  const [candidateExcludedCrops, setCandidateExcludedCrops] = useState([]); // Base64 crops to exclude
  const [loadingSimilar, setLoadingSimilar] = useState(false);

  // Manual Merge Assistant Modal State
  const [manualMergeModalOpen, setManualMergeModalOpen] = useState(false);
  const [mergePrimaryId, setMergePrimaryId] = useState(null);
  const [manualExcludedCrops, setManualExcludedCrops] = useState([]);
  const [submittingMerge, setSubmittingMerge] = useState(false);

  // Blacklist modal state
  const [modalVisitor, setModalVisitor] = useState(null);
  const [blacklistReason, setBlacklistReason] = useState('Past disturbance at hospital OPD');
  const [submittingBlacklist, setSubmittingBlacklist] = useState(false);

  // Toast Action Notice
  const [actionNotice, setActionNotice] = useState(null);
  const showNotice = (msg, isError = false) => {
    setActionNotice({ msg, isError });
    setTimeout(() => setActionNotice(null), 4000);
  };

  // Manage Live vs Frozen Visitors
  useEffect(() => {
    // If not frozen and no active selection/modal, keep visitors updated
    if (!gridFrozen && selectedMergeIds.length === 0 && !similarityWorkspaceOpen && !manualMergeModalOpen) {
      setFrozenVisitors(visitors);
    }
  }, [visitors, gridFrozen, selectedMergeIds.length, similarityWorkspaceOpen, manualMergeModalOpen]);

  // Current working list of visitors
  const blacklistedCount = useMemo(() => (visitors || []).filter(v => v.is_blacklisted).length, [visitors]);
  const activeVisitorsList = (gridFrozen || selectedMergeIds.length > 0 || similarityWorkspaceOpen || manualMergeModalOpen)
    ? (frozenVisitors.length > 0 ? frozenVisitors : visitors)
    : visitors;

  // Filtered and limited visitors
  const displayedVisitors = useMemo(() => {
    let list = activeVisitorsList || [];
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(v => v.id.toLowerCase().includes(q) || (v.blacklist_reason && v.blacklist_reason.toLowerCase().includes(q)));
    }
    if (genderFilter === 'male') {
      list = list.filter(v => v.gender === 'male' && !v.is_blacklisted);
    } else if (genderFilter === 'female') {
      list = list.filter(v => v.gender === 'female' && !v.is_blacklisted);
    } else if (genderFilter === 'multi') {
      list = list.filter(v => v.is_multi_camera || (v.camera_count && v.camera_count > 1));
    } else if (genderFilter === 'blacklisted') {
      list = list.filter(v => v.is_blacklisted);
    }
    return list.slice(0, displayLimit);
  }, [activeVisitorsList, searchQuery, genderFilter, displayLimit]);

  // Toggle profile selection
  const handleToggleSelectProfile = (id, e) => {
    if (e) e.stopPropagation();
    // Auto-freeze when user begins selecting so cards never jump
    if (!gridFrozen && selectedMergeIds.length === 0) {
      setFrozenVisitors(visitors);
      setGridFrozen(true);
    }
    setSelectedMergeIds(prev => {
      if (prev.includes(id)) {
        const next = prev.filter(x => x !== id);
        return next;
      } else {
        return [...prev, id];
      }
    });
  };

  // Switch crop thumbnail preview
  const handleSelectCrop = (visitorId, idx, e) => {
    if (e) e.stopPropagation();
    setSelectedCropIndex(prev => ({ ...prev, [visitorId]: idx }));
  };

  // Single Crop Direct Removal
  const handleRemoveSingleCrop = async (visitorId, cropIdx, e) => {
    if (e) e.stopPropagation();
    const vis = activeVisitorsList.find(v => v.id === visitorId);
    const crops = (Array.isArray(vis?.crops) && vis.crops.length > 0) ? vis.crops : (vis?.photo_b64 ? [vis.photo_b64] : []);
    const targetCropB64 = (crops && cropIdx < crops.length) ? crops[cropIdx] : null;

    if (crops.length <= 1) {
      if (!window.confirm(`This is the only face capture for ${visitorId}. Removing it will delete the entire profile. Proceed?`)) {
        return;
      }
      if (onDeleteProfile) {
        await onDeleteProfile(visitorId);
        showNotice(`Removed profile ${visitorId}`);
      }
      return;
    }

    if (!window.confirm(`Remove facial crop #${cropIdx + 1} from ${visitorId}? (Removes bad angle or Person B)`)) {
      return;
    }

    if (onRemoveCrop) {
      const ok = await onRemoveCrop(visitorId, cropIdx, targetCropB64);
      if (ok) {
        setSelectedCropIndex(prev => ({ ...prev, [visitorId]: 0 }));
        showNotice(`Removed crop #${cropIdx + 1} from ${visitorId}`);
      }
    }
  };

  // Gender Toggle Handler (Second opinion / manual correction)
  const handleToggleGenderClick = async (vis, e) => {
    if (e) e.stopPropagation();
    const nextGender = vis.gender === 'female' ? 'male' : 'female';
    if (onToggleGender) {
      const ok = await onToggleGender(vis.id, nextGender);
      if (ok) {
        showNotice(`Updated ${vis.id} gender to ${nextGender.toUpperCase()}`);
      }
    }
  };

  // Smart Similarity Search & Workspace Trigger
  const handleOpenSmartSimilarity = async (vis, e) => {
    if (e) e.stopPropagation();
    // Freeze grid
    setFrozenVisitors(visitors);
    setGridFrozen(true);
    setLoadingSimilar(true);
    setSimilarPrimary(vis);
    setSimilarityWorkspaceOpen(true);
    setCandidateExcludedCrops([]);

    try {
      if (onFindSimilar) {
        const res = await onFindSimilar(vis.id);
        if (res && res.candidates) {
          setSimilarCandidates(res.candidates);
          // By default, pre-select candidate profiles with high/medium similarity >= 0.33
          const autoSelect = res.candidates.filter(c => c.similarity >= 0.33).map(c => c.id);
          setSelectedCandidateIds(autoSelect);
        } else {
          setSimilarCandidates([]);
          setSelectedCandidateIds([]);
        }
      }
    } catch (err) {
      alert(`Similarity discovery failed: ${err.message}`);
    } finally {
      setLoadingSimilar(false);
    }
  };

  // Execute Batch Smart Merge
  const handleExecuteSmartMerge = async () => {
    if (!similarPrimary || selectedCandidateIds.length === 0) {
      alert("Please select at least one matching candidate profile to merge.");
      return;
    }
    setSubmittingMerge(true);
    try {
      if (onMergeProfiles) {
        const ok = await onMergeProfiles(similarPrimary.id, selectedCandidateIds, candidateExcludedCrops);
        if (ok) {
          showNotice(`Successfully merged ${selectedCandidateIds.length} candidate profiles into ${similarPrimary.id}!`);
          setSimilarityWorkspaceOpen(false);
          setSimilarCandidates([]);
          setSelectedCandidateIds([]);
          setCandidateExcludedCrops([]);
        }
      }
    } catch (err) {
      alert(`Batch merge error: ${err.message}`);
    } finally {
      setSubmittingMerge(false);
    }
  };

  // Manual Multi-Select Merge Assistant Modal
  const handleOpenManualMergeModal = () => {
    if (selectedMergeIds.length < 2) {
      alert("Please select at least 2 profiles using the checkboxes to merge.");
      return;
    }
    setMergePrimaryId(selectedMergeIds[0]);
    setManualExcludedCrops([]);
    setManualMergeModalOpen(true);
  };

  const handleExecuteManualMerge = async () => {
    if (!mergePrimaryId || selectedMergeIds.length < 2) return;
    const secondaryIds = selectedMergeIds.filter(id => id !== mergePrimaryId);
    setSubmittingMerge(true);
    try {
      if (onMergeProfiles) {
        const ok = await onMergeProfiles(mergePrimaryId, secondaryIds, manualExcludedCrops);
        if (ok) {
          showNotice(`Successfully merged ${selectedMergeIds.length} profiles into ${mergePrimaryId}!`);
          setManualMergeModalOpen(false);
          setSelectedMergeIds([]);
        }
      }
    } catch (err) {
      alert(`Merge error: ${err.message}`);
    } finally {
      setSubmittingMerge(false);
    }
  };

  // Blacklist modal
  const handleConfirmBlacklist = async () => {
    if (!modalVisitor) return;
    setSubmittingBlacklist(true);
    try {
      await onBlacklist(modalVisitor.id, modalVisitor.name || modalVisitor.id, blacklistReason);
      showNotice(`Added ${modalVisitor.id} to Security Watchlist`);
      setModalVisitor(null);
    } catch (e) {
      alert(`Error: ${e.message}`);
    } finally {
      setSubmittingBlacklist(false);
    }
  };

  return (
    <div className="med-card" style={{ padding: '20px', marginBottom: '24px', position: 'relative' }}>
      {/* Toast Notice */}
      {actionNotice && (
        <div style={{
          position: 'fixed',
          top: '24px',
          right: '24px',
          zIndex: 9999,
          backgroundColor: actionNotice.isError ? '#ef4444' : '#059669',
          color: '#ffffff',
          padding: '12px 20px',
          borderRadius: '10px',
          boxShadow: '0 10px 20px rgba(0,0,0,0.2)',
          fontSize: '13px',
          fontWeight: '700',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <span>{actionNotice.isError ? '⚠️' : '✓'}</span>
          <span>{actionNotice.msg}</span>
        </div>
      )}

      {/* Main Section Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h3 style={{ fontSize: '16px', fontWeight: '800', color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span>Unique Visitors & Multi-Crop Profiles</span>
            <span style={{ fontSize: '11px', fontWeight: '700', padding: '2px 8px', borderRadius: '9999px', backgroundColor: '#e0f2fe', color: '#0369a1' }}>
              Multi-Angle Curation
            </span>
          </h3>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
            Color-coded visitor gallery: <strong>Blue = Male</strong>, <strong>Pink = Female</strong>, <strong>Red = Blacklisted</strong>. Click <strong>🔍 Find Similar & Merge</strong> on any card to automatically find and batch-merge duplicate angle profiles.
          </p>
        </div>

        {/* Top Control Bar: Freeze Grid, Search, Filter, Limit */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {/* Live Grid Freeze / Resume Toggle */}
          <button
            type="button"
            onClick={() => {
              if (!gridFrozen) setFrozenVisitors(visitors);
              setGridFrozen(!gridFrozen);
            }}
            title={gridFrozen ? "Grid is frozen. New visitors won't shift cards while you work." : "Grid is live updating."}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              backgroundColor: gridFrozen ? '#fef3c7' : '#f8fafc',
              border: `1px solid ${gridFrozen ? '#f59e0b' : 'var(--border-light)'}`,
              color: gridFrozen ? '#b45309' : 'var(--text-main)',
              fontSize: '12px',
              fontWeight: '700',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <span>{gridFrozen ? '⏸️ Grid Frozen (Curating)' : '▶️ Live Grid Active'}</span>
          </button>

          {/* Search Box */}
          <input
            type="text"
            placeholder="🔎 Search VIS-ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border-light)',
              fontSize: '12px',
              width: '150px',
              outline: 'none'
            }}
          />

          {/* Gender / Category Filter */}
          <select
            value={genderFilter}
            onChange={(e) => setGenderFilter(e.target.value)}
            style={{
              padding: '6px 10px',
              borderRadius: '8px',
              border: '1px solid var(--border-light)',
              fontSize: '12px',
              fontWeight: '600',
              color: 'var(--text-main)',
              backgroundColor: '#ffffff',
              outline: 'none'
            }}
          >
            <option value="all">All Visitors</option>
            <option value="multi">🚶 Multi-Camera Journeys</option>
            <option value="male">♂ Male Only</option>
            <option value="female">♀ Female Only</option>
            <option value="blacklisted">⚠️ Blacklisted Only ({blacklistedCount})</option>
          </select>

          {/* Display Limit Dropdown */}
          <select
            value={displayLimit}
            onChange={(e) => setDisplayLimit(Number(e.target.value))}
            style={{
              padding: '6px 8px',
              borderRadius: '8px',
              border: '1px solid var(--border-light)',
              fontSize: '12px',
              fontWeight: '600',
              color: 'var(--text-main)',
              backgroundColor: '#ffffff',
              outline: 'none'
            }}
          >
            <option value={12}>Show 12</option>
            <option value={24}>Show 24</option>
            <option value={36}>Show 36</option>
            <option value={60}>Show 60</option>
            <option value={150}>Show All</option>
          </select>
        </div>
      </div>

      {/* Pinned Selection Dock (Ensures selected profiles never scroll away or disappear) */}
      {selectedMergeIds.length > 0 && (
        <div style={{
          backgroundColor: '#f0f9ff',
          border: '2px solid #0284c7',
          borderRadius: '12px',
          padding: '12px 18px',
          marginBottom: '18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          boxShadow: '0 4px 12px rgba(2,132,199,0.15)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '18px' }}>🔗</span>
            <div>
              <div style={{ fontSize: '13px', fontWeight: '800', color: '#0369a1' }}>
                {selectedMergeIds.length} Profiles Selected for Consolidation:
              </div>
              <div style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: '#0284c7', marginTop: '2px' }}>
                {selectedMergeIds.join(', ')}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              type="button"
              onClick={() => setSelectedMergeIds([])}
              style={{
                padding: '6px 12px',
                borderRadius: '8px',
                border: '1px solid #bae6fd',
                backgroundColor: '#ffffff',
                color: '#0369a1',
                fontSize: '12px',
                fontWeight: '700',
                cursor: 'pointer'
              }}
            >
              Clear Selection
            </button>

            <button
              type="button"
              disabled={selectedMergeIds.length < 2}
              onClick={handleOpenManualMergeModal}
              style={{
                padding: '7px 18px',
                borderRadius: '8px',
                backgroundColor: selectedMergeIds.length >= 2 ? '#0284c7' : '#94a3b8',
                color: '#ffffff',
                border: 'none',
                fontSize: '12px',
                fontWeight: '800',
                cursor: selectedMergeIds.length >= 2 ? 'pointer' : 'not-allowed',
                boxShadow: selectedMergeIds.length >= 2 ? '0 2px 6px rgba(2,132,199,0.3)' : 'none'
              }}
            >
              🔗 Merge Selected Profiles ({selectedMergeIds.length})
            </button>
          </div>
        </div>
      )}

      {/* Grid of Grouped Person Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))',
        gap: '16px'
      }}>
        {(!displayedVisitors || displayedVisitors.length === 0) ? (
          <div style={{ gridColumn: '1 / -1', padding: '40px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '13px' }}>
            No visitor profiles matching your filter.
          </div>
        ) : (
          displayedVisitors.map((vis) => {
            const isBlk = vis.is_blacklisted;
            const isFemale = vis.gender === 'female';
            const isSelected = selectedMergeIds.includes(vis.id);
            const crops = (Array.isArray(vis.crops) && vis.crops.length > 0) ? vis.crops : (vis.photo_b64 ? [vis.photo_b64] : []);
            const activeIdx = selectedCropIndex[vis.id];
            const hasCustomSelection = activeIdx !== undefined && activeIdx >= 0 && activeIdx < crops.length;
            const safeIdx = hasCustomSelection ? activeIdx : 0;
            const activePhoto = hasCustomSelection ? crops[activeIdx] : (vis.photo_b64 || crops[0]);

            // Distinctive Card Styling: Red for Blacklist, Pink for Female, Blue for Male
            let cardBorder = '2px solid #38bdf8'; // Blue (Male)
            let cardBg = '#ffffff';
            let cardHeaderStripe = 'linear-gradient(90deg, #0284c7, #38bdf8)';
            let badgeBg = '#e0f2fe';
            let badgeColor = '#0369a1';
            let photoBorder = '2px solid #0284c7';

            if (isBlk) {
              cardBorder = '3px solid #dc2626'; // Red (Blacklist)
              cardBg = '#fef2f2';
              cardHeaderStripe = '#dc2626';
              badgeBg = '#fee2e2';
              badgeColor = '#991b1b';
              photoBorder = '2px solid #dc2626';
            } else if (isFemale) {
              cardBorder = '2px solid #fb7185'; // Pink/Rose (Female)
              cardBg = '#fff8f9';
              cardHeaderStripe = 'linear-gradient(90deg, #e11d48, #fb7185)';
              badgeBg = '#ffe4e6';
              badgeColor = '#be123c';
              photoBorder = '2px solid #e11d48';
            }

            if (isSelected) {
              cardBorder = '3px solid #0284c7';
              cardBg = '#f0f9ff';
            }

            return (
              <div
                key={vis.id}
                style={{
                  border: cardBorder,
                  borderRadius: '14px',
                  backgroundColor: cardBg,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  boxShadow: isBlk
                    ? '0 0 15px rgba(220,38,38,0.2)'
                    : isSelected
                    ? '0 4px 14px rgba(2,132,199,0.2)'
                    : '0 2px 6px rgba(0,0,0,0.04)',
                  position: 'relative',
                  overflow: 'hidden',
                  transition: 'all 0.15s ease'
                }}
              >
                {/* Top Colored Accent Stripe */}
                <div style={{ height: '4px', background: cardHeaderStripe, width: '100%' }} />

                <div style={{ padding: '0 16px 16px 16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {/* Person Header with Checkbox, ID, Demographics & Gender Toggle */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => handleToggleSelectProfile(vis.id, e)}
                        title="Select to merge multiple profiles"
                        style={{
                          marginTop: '3px',
                          width: '16px',
                          height: '16px',
                          accentColor: '#0284c7',
                          cursor: 'pointer'
                        }}
                      />
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                          <span style={{
                            fontSize: '13px',
                            fontWeight: '800',
                            color: 'var(--text-main)',
                            fontFamily: 'var(--font-mono)'
                          }}>
                            {vis.id}
                          </span>
                          {isBlk && (
                            <span style={{
                              fontSize: '9px',
                              fontWeight: '900',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              backgroundColor: '#dc2626',
                              color: '#ffffff'
                            }}>
                              BLACKLISTED
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                          {vis.location || 'Gate 01 Main Entry'} • {formatGridTime(vis.started_at || vis.last_seen)}
                        </div>
                        {vis.previous_camera_name && vis.previous_camera_name !== (vis.camera_name || 'Main Porch Entry') && (
                          <div style={{
                            marginTop: '3px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            padding: '1px 6px',
                            borderRadius: '4px',
                            backgroundColor: isBlk ? '#fee2e2' : '#eff6ff',
                            color: isBlk ? '#dc2626' : '#1d4ed8',
                            fontSize: '10px',
                            fontWeight: '700'
                          }}>
                            <span>🔄 Transit:</span>
                            <span>From {vis.previous_camera_name}</span>
                          </div>
                        )}
                        {(vis.is_multi_camera || (vis.camera_count && vis.camera_count > 1)) && (
                          <div style={{
                            marginTop: '3px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            padding: '2px 8px',
                            borderRadius: '6px',
                            backgroundColor: '#f5f3ff',
                            border: '1px solid #ddd6fe',
                            color: '#6d28d9',
                            fontSize: '10px',
                            fontWeight: '700'
                          }}>
                            <span>🟣 {vis.camera_count || 2} Cams:</span>
                            <span>{vis.route_str || 'Cross-Cam Transit'}</span>
                            {vis.dwell_str && <span>({vis.dwell_str})</span>}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Demographic Badges with 1-Click Gender Toggle */}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      {/* Gender Badge with Clickable Toggle */}
                      <button
                        type="button"
                        onClick={(e) => handleToggleGenderClick(vis, e)}
                        title={vis.gender_locked ? "Gender firmly locked (Click to change)" : "Click to toggle & lock gender"}
                        style={{
                          fontSize: '11px',
                          fontWeight: '800',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          backgroundColor: badgeBg,
                          color: badgeColor,
                          border: `1px solid ${isFemale ? '#fecdd3' : '#bae6fd'}`,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}
                      >
                        <span>{isFemale ? '♀ FEMALE' : '♂ MALE'}</span>
                        {vis.gender_locked ? (
                          <span style={{ fontSize: '10px' }} title="Firmly locked">🔒</span>
                        ) : (
                          <span style={{ fontSize: '9px', opacity: 0.7 }}>⇄</span>
                        )}
                      </button>

                      <span style={{
                        fontSize: '11px',
                        fontWeight: '700',
                        padding: '3px 6px',
                        borderRadius: '6px',
                        backgroundColor: '#f1f5f9',
                        color: 'var(--text-muted)'
                      }}>
                        ~{vis.age || 32}y
                      </span>

                      {/* Delete Junk Profile Button */}
                      {onDeleteProfile && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); onDeleteProfile(vis.id); }}
                          title="Permanently delete this profile"
                          style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            color: '#94a3b8',
                            padding: '2px',
                            fontSize: '13px'
                          }}
                        >
                          🗑️
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Main Preview Face Crop + Multi-Crop Filmstrip */}
                  <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                    {/* Primary Large Photo (Body/Outfit View by default, or Selected Facial Crop) */}
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
                      <div
                        onClick={() => {
                          if (hasCustomSelection) {
                            setSelectedCropIndex(prev => ({ ...prev, [vis.id]: undefined }));
                          }
                        }}
                        title={hasCustomSelection ? "Viewing facial crop — Click to return to Outfit view" : "Upper-body & Outfit view — Click any thumbnail on the right to inspect facial crop"}
                        style={{
                          width: '90px',
                          height: '110px',
                          borderRadius: '10px',
                          backgroundColor: '#e2e8f0',
                          overflow: 'hidden',
                          flexShrink: 0,
                          border: hasCustomSelection ? '2px solid #0284c7' : photoBorder,
                          boxShadow: '0 2px 4px rgba(0,0,0,0.08)',
                          position: 'relative',
                          cursor: hasCustomSelection ? 'pointer' : 'default'
                        }}
                      >
                        {activePhoto ? (
                          <img
                            src={activePhoto}
                            alt={vis.id}
                            style={{
                              width: '100%',
                              height: '100%',
                              objectFit: 'cover',
                              objectPosition: 'top center'
                            }}
                          />
                        ) : (
                          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '24px' }}>
                            👤
                          </div>
                        )}
                        <div style={{
                          position: 'absolute',
                          bottom: 0,
                          left: 0,
                          right: 0,
                          background: hasCustomSelection ? 'rgba(2,132,199,0.85)' : 'rgba(15,23,42,0.65)',
                          color: '#ffffff',
                          fontSize: '9px',
                          fontWeight: '700',
                          padding: '2px 4px',
                          textAlign: 'center',
                          backdropFilter: 'blur(2px)'
                        }}>
                          {hasCustomSelection ? `Face #${safeIdx + 1}` : 'Outfit / Torso'}
                        </div>
                      </div>

                      {/* 1-Click Delete Active Crop */}
                      {hasCustomSelection ? (
                        <button
                          type="button"
                          onClick={(e) => handleRemoveSingleCrop(vis.id, safeIdx, e)}
                          title="Remove this specific facial crop (bad angle or Person B)"
                          style={{
                            background: '#fee2e2',
                            border: '1px solid #fecdd3',
                            color: '#b91c1c',
                            borderRadius: '6px',
                            padding: '2px 6px',
                            fontSize: '10px',
                            fontWeight: '700',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '3px'
                          }}
                        >
                          <span>✕</span>
                          <span>Del Crop #{safeIdx + 1}</span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => handleRemoveSingleCrop(vis.id, 0, e)}
                          title="Remove primary facial capture"
                          style={{
                            background: '#f8fafc',
                            border: '1px solid #cbd5e1',
                            color: '#64748b',
                            borderRadius: '6px',
                            padding: '2px 6px',
                            fontSize: '10px',
                            fontWeight: '600',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '3px'
                          }}
                        >
                          <span>✕</span>
                          <span>Del Crop #1</span>
                        </button>
                      )}
                    </div>

                    {/* Right side: Grouped crops list with hover ✕ delete badges */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                        <span style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-muted)' }}>
                          Captured Crops ({crops.length}):
                        </span>
                        <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                          ✕ to delete
                        </span>
                      </div>

                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {crops.map((cropImg, cIdx) => {
                          const isCropActive = hasCustomSelection && safeIdx === cIdx;
                          return (
                            <div
                              key={cIdx}
                              onClick={(e) => {
                                if (e) e.stopPropagation();
                                if (hasCustomSelection && activeIdx === cIdx) {
                                  setSelectedCropIndex(prev => ({ ...prev, [vis.id]: undefined }));
                                } else {
                                  setSelectedCropIndex(prev => ({ ...prev, [vis.id]: cIdx }));
                                }
                              }}
                              title={`Face Angle #${cIdx + 1} (Click to preview, ✕ to delete)`}
                              style={{
                                position: 'relative',
                                width: '36px',
                                height: '36px',
                                borderRadius: '6px',
                                cursor: 'pointer',
                                border: isCropActive ? '2px solid #0284c7' : '1px solid #cbd5e1',
                                transform: isCropActive ? 'scale(1.08)' : 'scale(1)',
                                transition: 'all 0.15s ease',
                                backgroundColor: '#f1f5f9'
                              }}
                            >
                              <img
                                src={cropImg}
                                alt={`Angle ${cIdx + 1}`}
                                style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '4px' }}
                              />

                              {/* Direct Delete Badge on Thumbnail */}
                              <div
                                onClick={(e) => {
                                  if (e) e.stopPropagation();
                                  handleRemoveSingleCrop(vis.id, cIdx, e);
                                }}
                                title="Delete this crop"
                                style={{
                                  position: 'absolute',
                                  top: '-4px',
                                  right: '-4px',
                                  width: '15px',
                                  height: '15px',
                                  borderRadius: '50%',
                                  backgroundColor: '#ef4444',
                                  color: 'white',
                                  fontSize: '10px',
                                  fontWeight: '900',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                                  zIndex: 2
                                }}
                              >
                                ✕
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  {/* Card Footer: Smart Similar Finder & Blacklist Action */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    paddingTop: '10px',
                    borderTop: isBlk ? '1px solid #fecdd3' : '1px solid #f1f5f9',
                    gap: '8px'
                  }}>
                    {/* Smart Similarity & Multi-Merge Trigger */}
                    <button
                      type="button"
                      onClick={(e) => handleOpenSmartSimilarity(vis, e)}
                      style={{
                        padding: '6px 11px',
                        borderRadius: '8px',
                        backgroundColor: '#f0f9ff',
                        color: '#0284c7',
                        border: '1px solid #bae6fd',
                        fontSize: '11px',
                        fontWeight: '800',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '5px',
                        transition: 'all 0.15s ease'
                      }}
                    >
                      <span>🔍 Similar</span>
                    </button>

                    {/* Cross-Camera Journey Audit Button */}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onOpenJourney) onOpenJourney(vis.id);
                      }}
                      title="View Multi-Camera Transit Audit & Checkpoints"
                      style={{
                        padding: '6px 12px',
                        borderRadius: '8px',
                        background: (vis.is_multi_camera || (vis.camera_count && vis.camera_count > 1))
                          ? 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)'
                          : '#f0fdf4',
                        color: (vis.is_multi_camera || (vis.camera_count && vis.camera_count > 1))
                          ? '#ffffff'
                          : '#15803d',
                        border: (vis.is_multi_camera || (vis.camera_count && vis.camera_count > 1))
                          ? 'none'
                          : '1px solid #bbf7d0',
                        fontSize: '11px',
                        fontWeight: '800',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '5px',
                        boxShadow: (vis.is_multi_camera || (vis.camera_count && vis.camera_count > 1))
                          ? '0 2px 6px rgba(124, 58, 237, 0.3)'
                          : 'none'
                      }}
                    >
                      <span>{(vis.is_multi_camera || (vis.camera_count && vis.camera_count > 1)) ? '🗺️ View Journey' : '📍 Journey'}</span>
                      {(vis.is_multi_camera || (vis.camera_count && vis.camera_count > 1)) && (
                        <span style={{
                          backgroundColor: 'rgba(255, 255, 255, 0.25)',
                          padding: '1px 5px',
                          borderRadius: '9999px',
                          fontSize: '10px'
                        }}>
                          {vis.camera_count || 2}
                        </span>
                      )}
                    </button>

                    {/* Blacklist / Watchlist Status */}
                    {!isBlk ? (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setModalVisitor(vis);
                          setBlacklistReason('Past disturbance at hospital OPD');
                        }}
                        style={{
                          padding: '6px 12px',
                          borderRadius: '8px',
                          backgroundColor: '#fff1f2',
                          color: '#e11d48',
                          border: '1px solid #fecdd3',
                          fontSize: '11px',
                          fontWeight: '800',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}
                      >
                        <span>🚫 Blacklist</span>
                      </button>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{
                          fontSize: '11px',
                          fontWeight: '800',
                          color: '#dc2626',
                          padding: '3px 8px',
                          backgroundColor: '#fee2e2',
                          borderRadius: '6px'
                        }}>
                          Watchlist
                        </span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (onRemoveBlacklist) {
                              onRemoveBlacklist(vis.id);
                              showNotice(`Revoked ${vis.id} from Watchlist`);
                            }
                          }}
                          style={{
                            padding: '4px 8px',
                            borderRadius: '6px',
                            backgroundColor: '#f1f5f9',
                            color: '#475569',
                            border: '1px solid #cbd5e1',
                            fontSize: '11px',
                            fontWeight: '700',
                            cursor: 'pointer'
                          }}
                          title="Revoke Blacklist"
                        >
                          Revoke
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* ── SMART SIMILARITY & BATCH MERGE WORKSPACE MODAL ── */}
      {similarityWorkspaceOpen && similarPrimary && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 3000,
          padding: '20px'
        }}>
          <div style={{
            background: '#ffffff',
            borderRadius: '16px',
            maxWidth: '920px',
            width: '100%',
            maxHeight: '92vh',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.3)',
            overflow: 'hidden'
          }}>
            {/* Modal Header */}
            <div style={{
              padding: '18px 24px',
              borderBottom: '1px solid var(--border-light)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              backgroundColor: '#f8fafc'
            }}>
              <div>
                <h4 style={{ fontSize: '18px', fontWeight: '800', color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>🔍 Smart Similar Profiles & Batch Consolidate</span>
                </h4>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                  AI scanned all profiles and identified matching face angles for <strong>{similarPrimary.id}</strong>. Review and curate below, then merge all at once.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSimilarityWorkspaceOpen(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '20px',
                  cursor: 'pointer',
                  color: 'var(--text-muted)'
                }}
              >
                ✕
              </button>
            </div>

            {/* Modal Scrollable Body */}
            <div style={{ padding: '20px 24px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Primary Profile Card */}
              <div style={{
                backgroundColor: '#f0f9ff',
                border: '2px solid #0284c7',
                borderRadius: '12px',
                padding: '16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '14px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  <div style={{ width: '64px', height: '64px', borderRadius: '10px', overflow: 'hidden', border: '2px solid #0284c7', backgroundColor: '#e2e8f0' }}>
                    <img src={similarPrimary.photo_b64} alt={similarPrimary.id} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </div>
                  <div>
                    <span style={{ fontSize: '10px', fontWeight: '800', padding: '2px 8px', borderRadius: '4px', backgroundColor: '#0284c7', color: '#ffffff' }}>
                      PRIMARY TARGET IDENTITY
                    </span>
                    <div style={{ fontSize: '16px', fontWeight: '800', fontFamily: 'var(--font-mono)', color: 'var(--text-main)', marginTop: '4px' }}>
                      {similarPrimary.id}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      {similarPrimary.gender?.toUpperCase()} • ~{similarPrimary.age || 32}y • {similarPrimary.crops?.length || 1} face angles
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '6px' }}>
                  {(similarPrimary.crops || [similarPrimary.photo_b64]).map((c, i) => (
                    <div key={i} style={{ width: '40px', height: '40px', borderRadius: '6px', overflow: 'hidden', border: '1px solid #bae6fd' }}>
                      <img src={c} alt={`Crop ${i}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    </div>
                  ))}
                </div>
              </div>

              {/* Similar Candidates Section */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <label style={{ fontSize: '14px', fontWeight: '800', color: 'var(--text-main)' }}>
                    Matching Duplicate Candidates Found ({similarCandidates.length}):
                  </label>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      type="button"
                      onClick={() => setSelectedCandidateIds(similarCandidates.map(c => c.id))}
                      style={{ fontSize: '11px', fontWeight: '700', padding: '3px 8px', borderRadius: '6px', border: '1px solid var(--border-light)', background: '#fff', cursor: 'pointer' }}
                    >
                      Select All
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedCandidateIds([])}
                      style={{ fontSize: '11px', fontWeight: '700', padding: '3px 8px', borderRadius: '6px', border: '1px solid var(--border-light)', background: '#fff', cursor: 'pointer' }}
                    >
                      Deselect All
                    </button>
                  </div>
                </div>

                {loadingSimilar ? (
                  <div style={{ padding: '36px', textAlign: 'center', color: '#0284c7', fontSize: '13px', fontWeight: '700' }}>
                    Scanning and ranking facial embeddings...
                  </div>
                ) : similarCandidates.length === 0 ? (
                  <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '13px', border: '1px dashed var(--border-light)', borderRadius: '12px' }}>
                    No other profiles matched this person's facial geometry. (Threshold: &gt; 28% similarity)
                  </div>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '14px' }}>
                    {similarCandidates.map((cand) => {
                      const isIncluded = selectedCandidateIds.includes(cand.id);
                      const candCrops = cand.crops && cand.crops.length > 0 ? cand.crops : [cand.photo_b64];

                      return (
                        <div
                          key={cand.id}
                          style={{
                            border: isIncluded ? '2px solid #0284c7' : '1px solid var(--border-light)',
                            borderRadius: '12px',
                            backgroundColor: isIncluded ? '#f0f9ff' : '#ffffff',
                            padding: '14px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '10px',
                            transition: 'all 0.15s ease'
                          }}
                        >
                          {/* Candidate Header with Match Score */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <input
                                type="checkbox"
                                checked={isIncluded}
                                onChange={() => {
                                  setSelectedCandidateIds(prev =>
                                    prev.includes(cand.id) ? prev.filter(x => x !== cand.id) : [...prev, cand.id]
                                  );
                                }}
                                style={{ width: '16px', height: '16px', accentColor: '#0284c7', cursor: 'pointer' }}
                              />
                              <span style={{ fontSize: '13px', fontWeight: '800', fontFamily: 'var(--font-mono)', color: 'var(--text-main)' }}>
                                {cand.id}
                              </span>
                            </div>

                            <span style={{
                              fontSize: '11px',
                              fontWeight: '800',
                              padding: '2px 8px',
                              borderRadius: '9999px',
                              backgroundColor: cand.similarity >= 0.40 ? '#dcfce7' : '#fef3c7',
                              color: cand.similarity >= 0.40 ? '#15803d' : '#b45309'
                            }}>
                              {cand.similarity_pct}% Match
                            </span>
                          </div>

                          {/* Candidate Face Crops with Individual ✕ Exclude Badge */}
                          <div>
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                              Face Crops ({candCrops.length}) — Click ✕ to remove Person B:
                            </div>
                            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                              {candCrops.map((cImg, cIdx) => {
                                const isCropExcluded = candidateExcludedCrops.includes(cImg);
                                return (
                                  <div
                                    key={cIdx}
                                    style={{
                                      position: 'relative',
                                      width: '42px',
                                      height: '42px',
                                      borderRadius: '6px',
                                      overflow: 'hidden',
                                      border: isCropExcluded ? '2px solid #ef4444' : '1px solid #cbd5e1',
                                      opacity: isCropExcluded ? 0.35 : 1
                                    }}
                                  >
                                    <img src={cImg} alt={`Angle ${cIdx}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setCandidateExcludedCrops(prev =>
                                          prev.includes(cImg) ? prev.filter(x => x !== cImg) : [...prev, cImg]
                                        );
                                      }}
                                      title={isCropExcluded ? "Restore crop" : "Exclude bad crop from merge"}
                                      style={{
                                        position: 'absolute',
                                        top: '2px',
                                        right: '2px',
                                        width: '14px',
                                        height: '14px',
                                        borderRadius: '50%',
                                        backgroundColor: isCropExcluded ? '#059669' : '#ef4444',
                                        color: '#ffffff',
                                        fontSize: '9px',
                                        fontWeight: '900',
                                        border: 'none',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        cursor: 'pointer'
                                      }}
                                    >
                                      {isCropExcluded ? '✓' : '✕'}
                                    </button>
                                  </div>
                                );
                              })}
                            </div>
                          </div>

                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            {cand.gender?.toUpperCase()} • ~{cand.age}y • Seen {formatGridTime(cand.started_at || cand.last_seen)}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div style={{
              padding: '16px 24px',
              borderTop: '1px solid var(--border-light)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              backgroundColor: '#f8fafc'
            }}>
              <div style={{ fontSize: '13px', color: 'var(--text-main)' }}>
                <strong>Plan:</strong> Consolidating <strong>{selectedCandidateIds.length} profiles</strong> into <strong>{similarPrimary.id}</strong>.
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setSimilarityWorkspaceOpen(false)}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '8px',
                    border: '1px solid var(--border-light)',
                    color: 'var(--text-muted)',
                    fontSize: '12px',
                    fontWeight: '700',
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleExecuteSmartMerge}
                  disabled={submittingMerge || selectedCandidateIds.length === 0}
                  style={{
                    padding: '8px 22px',
                    borderRadius: '8px',
                    backgroundColor: '#0284c7',
                    color: '#ffffff',
                    fontSize: '12px',
                    fontWeight: '800',
                    border: 'none',
                    cursor: (submittingMerge || selectedCandidateIds.length === 0) ? 'not-allowed' : 'pointer',
                    boxShadow: '0 2px 4px rgba(2,132,199,0.2)'
                  }}
                >
                  {submittingMerge ? 'Merging...' : `🔗 Merge All Selected (${selectedCandidateIds.length}) at Once`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── MANUAL MULTI-SELECT MERGE MODAL ── */}
      {manualMergeModalOpen && mergePrimaryId && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.65)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 3000,
          padding: '20px'
        }}>
          <div style={{
            background: '#ffffff',
            borderRadius: '16px',
            maxWidth: '680px',
            width: '100%',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
            overflow: 'hidden'
          }}>
            <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', backgroundColor: '#f8fafc' }}>
              <div>
                <h4 style={{ fontSize: '17px', fontWeight: '800', color: 'var(--text-main)' }}>
                  🔗 Consolidate Multi-Angle Profiles
                </h4>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Select primary target identity and curate approved face crops before consolidating.
                </p>
              </div>
              <button type="button" onClick={() => setManualMergeModalOpen(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>✕</button>
            </div>

            <div style={{ padding: '20px 24px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ fontSize: '13px', fontWeight: '700', color: 'var(--text-main)', marginBottom: '8px', display: 'block' }}>
                  Target Primary ID:
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '8px' }}>
                  {selectedMergeIds.map(id => (
                    <div
                      key={id}
                      onClick={() => setMergePrimaryId(id)}
                      style={{
                        padding: '10px 12px',
                        borderRadius: '8px',
                        border: mergePrimaryId === id ? '2px solid #0284c7' : '1px solid var(--border-light)',
                        backgroundColor: mergePrimaryId === id ? '#f0f9ff' : '#ffffff',
                        cursor: 'pointer',
                        fontSize: '12px',
                        fontWeight: '800',
                        fontFamily: 'var(--font-mono)',
                        display: 'flex',
                        justifyContent: 'space-between'
                      }}
                    >
                      <span>{id}</span>
                      {mergePrimaryId === id && <span style={{ color: '#0284c7' }}>✓</span>}
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ backgroundColor: '#f1f5f9', padding: '12px 16px', borderRadius: '8px', fontSize: '12px', color: 'var(--text-main)' }}>
                Merging <strong>{selectedMergeIds.length - 1} secondary profiles</strong> into <strong>{mergePrimaryId}</strong>.
              </div>
            </div>

            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'flex-end', gap: '10px', backgroundColor: '#f8fafc' }}>
              <button type="button" onClick={() => setManualMergeModalOpen(false)} style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--border-light)', cursor: 'pointer' }}>Cancel</button>
              <button type="button" onClick={handleExecuteManualMerge} disabled={submittingMerge} style={{ padding: '8px 20px', borderRadius: '8px', backgroundColor: '#0284c7', color: '#fff', border: 'none', fontWeight: '800', cursor: 'pointer' }}>
                {submittingMerge ? 'Merging...' : 'Confirm & Consolidate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── BLACKLIST CONFIRMATION MODAL ── */}
      {modalVisitor && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(3px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 3000
        }}>
          <div style={{
            background: '#ffffff',
            borderRadius: '16px',
            padding: '24px',
            maxWidth: '460px',
            width: '90%',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)'
          }}>
            <h4 style={{ fontSize: '17px', fontWeight: '800', color: '#dc2626', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>⚠️ Blacklist Person Profile</span>
            </h4>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Adding <strong>{modalVisitor.id}</strong> to the security watchlist. All captured facial vectors will be registered for automated instant alerting.
            </p>

            <div style={{ display: 'flex', gap: '10px', marginBottom: '16px' }}>
              {(modalVisitor.crops || [modalVisitor.photo_b64]).slice(0, 5).map((img, i) => (
                <div key={i} style={{ width: '48px', height: '48px', borderRadius: '8px', overflow: 'hidden', border: '1px solid #cbd5e1' }}>
                  <img src={img} alt={`Crop ${i}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
              ))}
            </div>

            <label style={{ display: 'block', fontSize: '12px', fontWeight: '700', color: 'var(--text-main)', marginBottom: '6px' }}>
              Security Reason / Incident Details:
            </label>
            <input
              type="text"
              value={blacklistReason}
              onChange={(e) => setBlacklistReason(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '8px',
                border: '1px solid var(--border-light)',
                fontSize: '13px',
                marginBottom: '20px',
                outline: 'none'
              }}
            />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button type="button" onClick={() => setModalVisitor(null)} style={{ padding: '9px 16px', borderRadius: '8px', border: '1px solid var(--border-light)', color: 'var(--text-muted)', fontSize: '12px', fontWeight: '600', cursor: 'pointer' }}>
                Cancel
              </button>
              <button type="button" onClick={handleConfirmBlacklist} disabled={submittingBlacklist} style={{ padding: '9px 18px', borderRadius: '8px', backgroundColor: '#e11d48', color: '#ffffff', fontSize: '12px', fontWeight: '800', border: 'none', cursor: 'pointer' }}>
                {submittingBlacklist ? 'Registering...' : 'Confirm & Blacklist'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
