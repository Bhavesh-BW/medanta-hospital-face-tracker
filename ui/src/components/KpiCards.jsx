import React from 'react';

export default function KpiCards({ kpis, period = 'today' }) {
  const p = (kpis?.period || period || 'today').toLowerCase();
  const periodLabelMap = {
    today: 'Today (Live Shift)',
    yesterday: 'Yesterday',
    '7d': 'Past 7 Days',
    '30d': 'Past 30 Days'
  };
  const pText = periodLabelMap[p] || 'Today';

  const cards = [
    {
      id: 'total',
      label: 'TOTAL VISITORS DETECTED',
      value: kpis?.total_visitors_detected ?? 0,
      subtext: `Total hospital footfall (${pText})`,
      accent: '#0284c7', // Sky Blue
      bgLight: '#f0f9ff',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0284c7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      )
    },
    {
      id: 'male',
      label: 'MALE VISITORS',
      value: kpis?.male_visitors ?? 0,
      subtext: `Male demographic (${pText})`,
      accent: '#0284c7', // Sky
      bgLight: '#f0f9ff',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0284c7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="7" r="4" />
          <path d="M5.5 21v-2a6.5 6.5 0 0 1 13 0v2" />
        </svg>
      )
    },
    {
      id: 'female',
      label: 'FEMALE VISITORS',
      value: kpis?.female_visitors ?? 0,
      subtext: `Female demographic (${pText})`,
      accent: '#e11d48', // Rose
      bgLight: '#fff1f2',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#e11d48" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="7" r="4" />
          <path d="M6 21v-2a6 6 0 0 1 12 0v2" />
          <path d="M12 17v4" />
        </svg>
      )
    },
    {
      id: 'unique',
      label: 'UNIQUE VISITORS VERIFIED',
      value: kpis?.unique_visitors_verified ?? 0,
      subtext: `Distinct individuals (${pText})`,
      accent: '#059669', // Emerald
      bgLight: '#ecfdf5',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <polyline points="16 11 18 13 22 9" />
        </svg>
      )
    }
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px', marginBottom: '24px' }}>
      {cards.map((card) => (
        <div 
          key={card.id}
          className="med-card"
          style={{
            padding: '20px 24px',
            display: 'flex',
            alignItems: 'center',
            gap: '18px',
            borderLeft: `4px solid ${card.accent}`
          }}
        >
          <div style={{
            width: '48px',
            height: '48px',
            borderRadius: '12px',
            backgroundColor: card.bgLight,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            {card.icon}
          </div>
          <div>
            <div style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: '4px' }}>
              {card.label}
            </div>
            <div style={{ fontSize: '28px', fontWeight: '800', color: 'var(--text-main)', lineHeight: '1.1' }}>
              {Number(card.value).toLocaleString()}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
              {card.subtext}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

