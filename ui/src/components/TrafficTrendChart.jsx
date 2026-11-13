import React from 'react';

export default function TrafficTrendChart({ trendData, activeFilter = 'today', onFilterChange }) {
  const data = trendData && trendData.length > 0 ? trendData : [
    { label: '08:00', count: 0 },
    { label: '09:00', count: 0 },
    { label: '10:00', count: 0 },
    { label: '11:00', count: 0 },
    { label: '12:00', count: 0 },
    { label: '13:00', count: 0 },
    { label: '14:00', count: 0 },
    { label: '15:00', count: 0 },
    { label: '16:00', count: 0 },
    { label: '17:00', count: 0 },
    { label: '18:00', count: 0 },
    { label: '19:00', count: 0 }
  ];

  const maxCount = Math.max(...data.map(d => d.count), 0);

  const titleMap = {
    today: 'Hourly Unique Visitor Traffic Flow Trend',
    yesterday: "Yesterday's Unique Visitor Traffic Flow Trend",
    '7d': 'Past 7 Days Unique Visitor Daily Flow',
    '30d': 'Past 30 Days Unique Visitor Traffic Trend'
  };

  const subtitleMap = {
    today: 'Distinct individuals entering through Entry Camera (Males + Females, de-duplicated per hour)',
    yesterday: "Distinct individuals entering through Entry Camera yesterday (Males + Females, de-duplicated)",
    '7d': 'Daily unique arrivals over the last 7 calendar days (Entry Camera)',
    '30d': '3-day aggregated unique arrivals over past 30 days (Entry Camera)'
  };

  const footerMap = {
    today: 'Hourly Unique Entries (Today)',
    yesterday: 'Hourly Unique Entries (Yesterday)',
    '7d': 'Daily Unique Entries (Past 7 Days)',
    '30d': '3-Day Aggregated Unique Entries (Past 30 Days)'
  };

  const peakUnitMap = {
    today: 'unique entries / hour',
    yesterday: 'unique entries / hour',
    '7d': 'unique entries / day',
    '30d': 'unique entries / 3-day window'
  };

  const currentTitle = titleMap[activeFilter] || titleMap.today;
  const currentSubtitle = subtitleMap[activeFilter] || subtitleMap.today;
  const currentFooter = footerMap[activeFilter] || footerMap.today;
  const currentPeakUnit = peakUnitMap[activeFilter] || peakUnitMap.today;

  return (
    <div className="med-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header with Title and Range Filters */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
        <div>
          <h3 style={{ fontSize: '15px', fontWeight: '700', color: 'var(--text-main)' }}>
            {currentTitle}
          </h3>
          <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            {currentSubtitle}
          </p>
        </div>

        <div style={{ display: 'flex', backgroundColor: '#f1f5f9', borderRadius: '8px', padding: '3px', gap: '2px' }}>
          {[
            { id: 'today', label: 'Today' },
            { id: 'yesterday', label: 'Yesterday' },
            { id: '7d', label: '7 Days' },
            { id: '30d', label: '30 Days' }
          ].map((btn) => (
            <button
              key={btn.id}
              type="button"
              onClick={() => onFilterChange && onFilterChange(btn.id)}
              style={{
                padding: '4px 10px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: '700',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: activeFilter === btn.id ? '#ffffff' : 'transparent',
                color: activeFilter === btn.id ? '#0284c7' : 'var(--text-muted)',
                boxShadow: activeFilter === btn.id ? '0 1px 2px rgba(0,0,0,0.08)' : 'none',
                transition: 'all 0.15s ease'
              }}
            >
              {btn.label}
            </button>
          ))}
        </div>
      </div>

      {/* Bar Chart Visualization */}
      <div style={{ height: '240px', display: 'flex', alignItems: 'flex-end', gap: '8px', padding: '16px 8px 8px 8px', borderBottom: '1px solid var(--border-light)' }}>
        {data.map((item, idx) => {
          const hasCount = item.count > 0;
          const maxBarHeight = 160; // Max bar height in pixels
          const barHeightPx = hasCount && maxCount > 0 ? Math.max(8, Math.round((item.count / maxCount) * maxBarHeight)) : 4;
          const isPeak = hasCount && item.count === maxCount;

          return (
            <div
              key={idx}
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                height: '100%',
                justifyContent: 'flex-end',
                position: 'relative'
              }}
            >
              {/* Count tooltip */}
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                marginBottom: '6px',
                gap: '2px',
                minHeight: '26px',
                justifyContent: 'flex-end'
              }}>
                <span style={{
                  fontSize: '11px',
                  fontWeight: '800',
                  color: isPeak ? '#0284c7' : hasCount ? '#0f172a' : '#94a3b8',
                  lineHeight: 1
                }}>
                  {item.count}
                </span>
                {hasCount && (item.males !== undefined || item.females !== undefined) && (
                  <span style={{
                    fontSize: '9px',
                    fontWeight: '700',
                    display: 'flex',
                    gap: '3px',
                    whiteSpace: 'nowrap',
                    lineHeight: 1
                  }}>
                    <span style={{ color: '#0284c7' }} title="Males">{item.males || 0}♂</span>
                    <span style={{ color: '#ec4899' }} title="Females">{item.females || 0}♀</span>
                  </span>
                )}
              </div>

              {/* Bar */}
              <div
                style={{
                  width: '100%',
                  maxWidth: '36px',
                  height: `${barHeightPx}px`,
                  minHeight: hasCount ? '8px' : '4px',
                  borderRadius: '5px 5px 2px 2px',
                  backgroundColor: isPeak ? '#0284c7' : hasCount ? '#38bdf8' : '#e2e8f0',
                  boxShadow: isPeak ? '0 4px 6px -1px rgba(2, 132, 199, 0.3)' : hasCount ? '0 2px 4px -1px rgba(56, 189, 248, 0.2)' : 'none',
                  transition: 'height 0.3s ease, background-color 0.2s',
                  cursor: 'pointer'
                }}
                title={`${item.label}: ${item.count} Total Entered (${item.males || 0} Males, ${item.females || 0} Females)`}
              />

              {/* Label */}
              <div style={{
                fontSize: '10px',
                color: 'var(--text-dim)',
                marginTop: '8px',
                whiteSpace: 'nowrap',
                fontFamily: 'var(--font-mono)',
                fontWeight: '600'
              }}>
                {item.label}
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px', fontSize: '11px', color: 'var(--text-muted)', flexWrap: 'wrap', gap: '8px' }}>
        <span>Peak Traffic: <strong style={{ color: '#0284c7' }}>{maxCount > 0 ? `${maxCount} ${currentPeakUnit}` : '0 entries'}</strong></span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: '#0284c7' }}></span>
            <span>{currentFooter}</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px', color: '#0284c7', fontWeight: '700' }}>
            <span>♂ Males</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px', color: '#ec4899', fontWeight: '700' }}>
            <span>♀ Females</span>
          </span>
        </div>
      </div>
    </div>
  );
}

