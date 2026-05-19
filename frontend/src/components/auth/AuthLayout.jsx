import React from 'react';
import NexusLogo from '../ui/NexusLogo';
import GlassCard from '../ui/GlassCard';

export default function AuthLayout({ children, mode, onModeChange }) {
  return (
    <main className="auth-page">
      <div className="auth-mesh" />
      <div className="container-fluid min-vh-100">
        <div className="row min-vh-100 align-items-center">
          <section className="col-lg-6 p-4 p-lg-5 auth-brand">
            <NexusLogo size="large" />
            <h1 className="nexus-wordmark gradient-text mt-5 mb-3">NEXUS</h1>
            <p className="fs-4 text-secondary mb-4">Agentic Intelligence Platform</p>
            <p className="text-secondary col-xl-9">
              A deep-space command center for web search, image generation, file-aware reasoning,
              and long-running AI work through one secured gateway.
            </p>
            <div className="d-flex flex-wrap gap-3 mt-5">
              {['Search', 'Generate', 'Analyze', 'Remember'].map((item) => (
                <span className="glass-card-sm px-3 py-2 text-secondary" key={item}>
                  {item}
                </span>
              ))}
            </div>
          </section>
          <section className="col-lg-6 p-4 p-lg-5">
            <GlassCard className="p-4 p-md-5 mx-auto" style={{ maxWidth: 520 }}>
              <div className="d-flex gap-2 mb-4">
                <button
                  className={`btn flex-fill ${mode === 'login' ? 'btn-nexus-primary' : 'btn-nexus-ghost'}`}
                  onClick={() => onModeChange('login')}
                  type="button"
                >
                  Sign In
                </button>
                <button
                  className={`btn flex-fill ${mode === 'register' ? 'btn-nexus-primary' : 'btn-nexus-ghost'}`}
                  onClick={() => onModeChange('register')}
                  type="button"
                >
                  Register
                </button>
              </div>
              {children}
            </GlassCard>
          </section>
        </div>
      </div>
    </main>
  );
}
