import React from 'react';
import GlassCard from '../components/ui/GlassCard';

export default function NotFoundPage() {
  return (
    <main className="app-surface d-flex align-items-center justify-content-center p-4">
      <GlassCard className="p-5 text-center">
        <h1 className="gradient-text mb-3">Signal Lost</h1>
        <p className="text-secondary mb-4">That Nexus route does not exist.</p>
        <button className="btn btn-nexus-primary" onClick={() => window.location.assign('/')}>
          Return Home
        </button>
      </GlassCard>
    </main>
  );
}
