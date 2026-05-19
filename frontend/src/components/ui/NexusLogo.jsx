import React from 'react';

export default function NexusLogo({ size = 'normal' }) {
  const large = size === 'large';
  return (
    <div className="d-inline-flex align-items-center gap-3">
      <svg width={large ? 58 : 38} height={large ? 58 : 38} viewBox="0 0 64 64" aria-hidden="true">
        <defs>
          <linearGradient id="nexusLogoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#4f8eff" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
        <rect x="5" y="5" width="54" height="54" rx="16" fill="rgba(255,255,255,.04)" stroke="rgba(255,255,255,.14)" />
        <path d="M18 46V18h7l14 18V18h7v28h-7L25 28v18h-7Z" fill="url(#nexusLogoGradient)" />
        <circle cx="14" cy="14" r="2.5" fill="#4f8eff" />
        <circle cx="50" cy="50" r="2.5" fill="#a78bfa" />
        <path d="M16 16l32 32" stroke="rgba(79,142,255,.5)" strokeWidth="1" />
      </svg>
      <div>
        <div className="fw-bold gradient-text" style={{ fontFamily: 'var(--font-display)', fontSize: large ? 24 : 18 }}>NEXUS</div>
        <div className="text-secondary" style={{ fontSize: large ? 13 : 11 }}>Agentic AI</div>
      </div>
    </div>
  );
}
