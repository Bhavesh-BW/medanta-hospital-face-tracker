import React, { useState, useEffect, useCallback, useRef } from 'react';
import KpiCards from './components/KpiCards';
import LiveHudFeed from './components/LiveHudFeed';
import TrafficTrendChart from './components/TrafficTrendChart';
import RecentVisitorsGrid from './components/RecentVisitorsGrid';
import BlacklistSecurityHub from './components/BlacklistSecurityHub';
import PassageLogTable from './components/PassageLogTable';
import CinematicThreatAlert from './components/CinematicThreatAlert';
import JourneyTimelineModal from './components/JourneyTimelineModal';
import { playTacticalChime } from './utils/alertSound';

export default function App() {
  const [clockTime, setClockTime] = useState(() => {
    return new Date().toLocaleTimeString('en-US', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    }) + ' IST';
  });

  useEffect(() => {
    const timer = setInterval(() => {
      setClockTime(new Date().toLocaleTimeString('en-US', {
        timeZone: 'Asia/Kolkata',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      }) + ' IST');
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const [kpis, setKpis] = useState(null);
  const [cameras, setCameras] = useState([]);
  const [activeCamera, setActiveCamera] = useState('main');
  const [viewMode, setViewMode] = useState('grid');
  const [selectedJourneyId, setSelectedJourneyId] = useState(null);
  const [trendRange, setTrendRange] = useState('today');
  const trendRangeRef = useRef('today');
  const [trendData, setTrendData] = useState([]);
  const [visitors, setVisitors] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [activeAlert, setActiveAlert] = useState(null);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [loading, setLoading] = useState(true);

  // Fetch KPI & status data
  const fetchData = useCallback(async () => {
    try {
      const currentRange = trendRangeRef.current || 'today';
      const [kpiRes, camRes, trendRes, visRes, watchRes, alertRes] = await Promise.all([
        fetch(`/api/kpis?range=${encodeURIComponent(currentRange)}`).then(r => r.json()).catch(() => null),
        fetch('/api/cameras').then(r => r.json()).catch(() => null),
        fetch(`/api/traffic-trend?range=${encodeURIComponent(currentRange)}`).then(r => r.json()).catch(() => null),
        fetch('/api/visitors?limit=100').then(r => r.json()).catch(() => null),
        fetch('/api/watchlist').then(r => r.json()).catch(() => null),
        fetch('/api/alerts').then(r => r.json()).catch(() => null)
      ]);

      if (kpiRes) setKpis(kpiRes);
      if (camRes?.cameras) {
        setCameras(camRes.cameras);
        if (camRes.active) setActiveCamera(camRes.active);
      }
      if (trendRes) setTrendData(trendRes);
      if (visRes) setVisitors(visRes);
      if (watchRes) setWatchlist(watchRes);
      if (alertRes) setAlerts(alertRes);
    } catch (e) {
      console.error("Fetch data error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const dismissedTargetsRef = useRef(new Set());

  // Connect to SSE real-time alert stream for instantaneous movie-style alerts
  useEffect(() => {
    let evtSource = null;
    try {
      evtSource = new EventSource('/api/alerts/events');
      evtSource.addEventListener('alert', (e) => {
        try {
          const alertPayload = JSON.parse(e.data);
          const wid = alertPayload.watchlist_id ? String(alertPayload.watchlist_id).toLowerCase() : null;
          const name = alertPayload.person_name ? String(alertPayload.person_name).toLowerCase() : null;
          const aid = alertPayload.id ? String(alertPayload.id).toLowerCase() : null;

          // If user previously closed/dismissed this target, DO NOT SHOW POPUP
          if (
            (wid && dismissedTargetsRef.current.has(wid)) ||
            (name && dismissedTargetsRef.current.has(name)) ||
            (aid && dismissedTargetsRef.current.has(aid))
          ) {
            console.log("[Alert Suppressed - Target previously dismissed]:", name || wid);
            return;
          }

          console.log("[Threat Alert Event Received]:", alertPayload);
          setActiveAlert(alertPayload);
          fetchData();
        } catch (err) {
          console.error("Alert parse error:", err);
        }
      });
    } catch (err) {
      console.warn("SSE connection error:", err);
    }

    return () => {
      if (evtSource) evtSource.close();
    };
  }, [fetchData]);

  const handleDismissAlert = (alertToDismiss) => {
    const target = alertToDismiss || activeAlert;
    if (target) {
      if (target.watchlist_id) dismissedTargetsRef.current.add(String(target.watchlist_id).toLowerCase());
      if (target.person_name) dismissedTargetsRef.current.add(String(target.person_name).toLowerCase());
      if (target.id) dismissedTargetsRef.current.add(String(target.id).toLowerCase());

      // Notify backend to permanently suppress repeat alerts for this target
      fetch('/api/alerts/dismiss', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          watchlist_id: target.watchlist_id,
          person_name: target.person_name,
          id: target.id
        })
      }).catch(() => {});
    }
    setActiveAlert(null);
  };

  // Periodic polling for KPIs and visitor logs
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 4000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleSwitchCamera = async (camId) => {
    try {
      const res = await fetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera: camId })
      });
      if (res.ok) {
        setActiveCamera(camId);
        fetchData();
      }
    } catch (e) {
      console.error("Switch camera error:", e);
    }
  };

  const handleAddCamera = async ({ name, location, rtsp }) => {
    try {
      const res = await fetch('/api/cameras/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, location, rtsp })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to add camera');
      await fetchData();
      const newId = data.camera_id || data.camera?.id;
      if (newId) {
        await handleSwitchCamera(newId);
      }
      return { success: true };
    } catch (e) {
      return { success: false, error: e.message };
    }
  };

  const handleRemoveCamera = async (camId) => {
    if (camId === 'main') {
      alert("Primary Main Porch Entry camera is protected and cannot be deleted.");
      return;
    }
    if (!window.confirm("Are you sure you want to remove this camera checkpoint?")) return;
    try {
      const res = await fetch('/api/cameras/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera_id: camId })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to remove camera');
      await fetchData();
    } catch (e) {
      alert(`Error removing camera: ${e.message}`);
    }
  };

  const handleTrendRangeChange = async (newRange) => {
    setTrendRange(newRange);
    trendRangeRef.current = newRange;
    try {
      const [trendRes, kpiRes] = await Promise.all([
        fetch(`/api/traffic-trend?range=${encodeURIComponent(newRange)}`).then(r => r.json()).catch(() => null),
        fetch(`/api/kpis?range=${encodeURIComponent(newRange)}`).then(r => r.json()).catch(() => null)
      ]);
      if (Array.isArray(trendRes)) {
        setTrendData(trendRes);
      }
      if (kpiRes) {
        setKpis(kpiRes);
      }
    } catch (e) {
      console.error("Trend/KPI fetch error:", e);
    }
  };

  const handleBlacklist = async (personId, name, reason) => {
    const res = await fetch('/api/blacklist/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ person_id: personId, name, reason })
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Failed to blacklist');
    await fetchData();
  };

  const handleRemoveBlacklist = async (wid) => {
    if (!window.confirm("Revoke blacklist status for this person?")) return;
    const res = await fetch('/api/blacklist/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ watchlist_id: wid })
    });
    if (res.ok) {
      fetchData();
    }
  };

  const handleEnrollManual = async (photoB64, name, reason) => {
    const res = await fetch('/api/blacklist/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ photo_b64: photoB64, name, reason, is_photo: true })
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Failed to enroll');
    await fetchData();
  };

  const handleRemoveCrop = async (visitorId, cropIndex) => {
    try {
      const res = await fetch('/api/visitors/remove-crop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visitor_id: visitorId, crop_index: cropIndex })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to remove crop');
      await fetchData();
      return true;
    } catch (e) {
      alert(`Error removing crop: ${e.message}`);
      return false;
    }
  };

  const handleMergeProfiles = async (primaryId, mergeIds, excludedCrops = []) => {
    try {
      const res = await fetch('/api/visitors/merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ primary_id: primaryId, merge_ids: mergeIds, excluded_crops: excludedCrops })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to merge profiles');
      await fetchData();
      return true;
    } catch (e) {
      alert(`Error merging profiles: ${e.message}`);
      return false;
    }
  };

  const handleDeleteProfile = async (visitorId) => {
    if (!window.confirm(`Are you sure you want to delete visitor profile ${visitorId}?`)) return;
    try {
      const res = await fetch('/api/visitors/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visitor_id: visitorId })
      });
      if (res.ok) {
        await fetchData();
      }
    } catch (e) {
      alert(`Error deleting profile: ${e.message}`);
    }
  };

  const handleToggleGender = async (visitorId, newGender) => {
    try {
      const res = await fetch('/api/visitors/toggle-gender', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visitor_id: visitorId, gender: newGender })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to update gender');
      await fetchData();
      return true;
    } catch (e) {
      alert(`Error updating gender: ${e.message}`);
      return false;
    }
  };

  const handleFindSimilar = async (visitorId) => {
    try {
      const res = await fetch(`/api/visitors/similar?visitor_id=${encodeURIComponent(visitorId)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to find similar profiles');
      return data;
    } catch (e) {
      alert(`Error finding similar profiles: ${e.message}`);
      return null;
    }
  };

  const handleTriggerTestAlert = async () => {
    try {
      if (soundEnabled) {
        playTacticalChime();
      }
      await fetch('/api/alerts/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Vikramaditya Rao',
          reason: 'Barred from OPD Premises (Past Disturbance)'
        })
      });
    } catch (e) {
      console.error("Test alert error:", e);
    }
  };

  return (
    <div style={{ minHeight: '100vh', padding: '24px 32px', maxWidth: '1720px', margin: '0 auto' }}>
      {/* Tactical Threat Alert Floating Card */}
      <CinematicThreatAlert
        alert={activeAlert}
        onDismiss={handleDismissAlert}
        soundEnabled={soundEnabled}
      />

      {/* Visitor Cross-Camera Journey Audit Modal */}
      <JourneyTimelineModal
        visitorId={selectedJourneyId}
        isOpen={Boolean(selectedJourneyId)}
        onClose={() => setSelectedJourneyId(null)}
        onBlacklist={(vid) => {
          handleBlacklist(vid, null, 'Flagged from Journey Audit');
        }}
      />

      {/* Main Header Matching localhost:3010 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h1 style={{ fontSize: '22px', fontWeight: '800', color: 'var(--text-main)', letterSpacing: '-0.02em' }}>
              Medanta Visitor Demographics & Traffic Intelligence
            </h1>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              borderRadius: '9999px',
              backgroundColor: '#ecfdf5',
              color: '#059669',
              fontSize: '11px',
              fontWeight: '700'
            }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981' }}></span>
              Live
            </span>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 10px',
              borderRadius: '9999px',
              backgroundColor: '#f8fafc',
              border: '1px solid var(--border-light)',
              color: '#059669',
              fontSize: '12px',
              fontWeight: '700',
              fontFamily: 'var(--font-mono)'
            }}>
              🟢 {clockTime}
            </span>
          </div>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Real-time visitor demographic analytics, male & female footfall breakdown, hourly traffic trends, and visual face capture audit log for Medanta The Medicity.
          </p>
        </div>

        {/* Header Right Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Period Selector (Matches PPE Monitor) */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            padding: '5px 12px',
            borderRadius: '8px',
            boxShadow: '0 1px 2px rgba(0,0,0,0.04)'
          }}>
            <span style={{ fontSize: '12px', fontWeight: '700', color: 'var(--text-muted)' }}>Period:</span>
            <select
              value={trendRange}
              onChange={(e) => handleTrendRangeChange(e.target.value)}
              style={{
                border: 'none',
                backgroundColor: 'transparent',
                fontSize: '12px',
                fontWeight: '700',
                color: '#0284c7',
                cursor: 'pointer',
                outline: 'none',
                padding: '2px 0'
              }}
            >
              <option value="today">• Today (Live Shift)</option>
              <option value="yesterday">Yesterday</option>
              <option value="7d">Past 7 Days</option>
              <option value="30d">Past 30 Days</option>
            </select>
          </div>

          {/* Sound Toggle */}
          <button
            type="button"
            onClick={() => {
              const nextState = !soundEnabled;
              setSoundEnabled(nextState);
              if (nextState) {
                playTacticalChime();
              }
            }}
            title={soundEnabled ? 'Threat Alert Sound Enabled' : 'Threat Alert Sound Muted'}
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              backgroundColor: soundEnabled ? '#f0fdf4' : '#f8fafc',
              border: `1px solid ${soundEnabled ? '#bbf7d0' : 'var(--border-light)'}`,
              color: soundEnabled ? '#15803d' : 'var(--text-muted)',
              fontSize: '12px',
              fontWeight: '700',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              cursor: 'pointer'
            }}
          >
            <span>{soundEnabled ? '🔔 Sound ON' : '🔕 Sound OFF'}</span>
          </button>

          {/* Test Movie Alert Button */}
          <button
            type="button"
            onClick={handleTriggerTestAlert}
            style={{
              padding: '8px 14px',
              borderRadius: '8px',
              backgroundColor: '#fff1f2',
              border: '1px solid #fecdd3',
              color: '#e11d48',
              fontSize: '12px',
              fontWeight: '800',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              cursor: 'pointer',
              boxShadow: '0 1px 2px rgba(225,29,72,0.1)'
            }}
          >
            <span>⚡ Test Movie Alert HUD</span>
          </button>

          {/* Refresh Button */}
          <button
            type="button"
            onClick={fetchData}
            style={{
              padding: '8px 14px',
              borderRadius: '8px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--border-light)',
              color: 'var(--text-main)',
              fontSize: '12px',
              fontWeight: '600',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              cursor: 'pointer'
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
            </svg>
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Top 4 Demographic KPI Cards (Filtered by Period) */}
      <KpiCards kpis={kpis} period={trendRange} />

      {/* Dynamic Multi-Camera Main Stage */}
      {viewMode === 'grid' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', marginBottom: '24px' }}>
          <LiveHudFeed
            activeCamera={activeCamera}
            cameras={cameras}
            onSwitchCamera={handleSwitchCamera}
            onAddCamera={handleAddCamera}
            onRemoveCamera={handleRemoveCamera}
            fps={kpis?.fps}
            isRtspConnected={kpis?.is_rtsp_connected}
            onOpenJourney={(id) => setSelectedJourneyId(id)}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            onDataRefresh={fetchData}
          />
          <TrafficTrendChart
            trendData={trendData}
            activeFilter={trendRange}
            onFilterChange={handleTrendRangeChange}
          />
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)',
          gap: '24px',
          marginBottom: '24px'
        }}>
          <LiveHudFeed
            activeCamera={activeCamera}
            cameras={cameras}
            onSwitchCamera={handleSwitchCamera}
            onAddCamera={handleAddCamera}
            onRemoveCamera={handleRemoveCamera}
            fps={kpis?.fps}
            isRtspConnected={kpis?.is_rtsp_connected}
            onOpenJourney={(id) => setSelectedJourneyId(id)}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            onDataRefresh={fetchData}
          />
          <TrafficTrendChart
            trendData={trendData}
            activeFilter={trendRange}
            onFilterChange={handleTrendRangeChange}
          />
        </div>
      )}

      {/* Recent Verified Visitors & Face Captures Gallery (with 1-Click Blacklist, Crop Removal, Smart Similar Merge & Gender Toggle) */}
      <RecentVisitorsGrid
        visitors={visitors}
        onBlacklist={handleBlacklist}
        onRemoveCrop={handleRemoveCrop}
        onMergeProfiles={handleMergeProfiles}
        onDeleteProfile={handleDeleteProfile}
        onToggleGender={handleToggleGender}
        onFindSimilar={handleFindSimilar}
        onOpenJourney={(id) => setSelectedJourneyId(id)}
      />

      {/* Blacklist Security Watchlist & Incident Hub */}
      <BlacklistSecurityHub
        watchlist={watchlist}
        alerts={alerts}
        onRemoveBlacklist={handleRemoveBlacklist}
        onEnrollManual={handleEnrollManual}
      />

      {/* Immutable Passage Audit Log Table */}
      <PassageLogTable
        visitors={visitors}
        alerts={alerts}
        onOpenJourney={(id) => setSelectedJourneyId(id)}
      />
    </div>
  );
}

