import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import NexusLogo from '../components/ui/NexusLogo';

export default function LandingPage() {
  const navigate = useNavigate();
  useEffect(() => {
    document.title = 'Nexus AI';
  }, []);

  return (
    <main className="auth-page d-flex align-items-center">
      <div className="auth-mesh" />
      <div className="container position-relative py-5">
        <div className="row align-items-center min-vh-100">
          <div className="col-lg-7">
            <NexusLogo size="large" />
            <h1 className="nexus-wordmark gradient-text mt-5 mb-3">NEXUS</h1>
            <p className="fs-3 text-secondary mb-4">Agentic Intelligence Platform</p>
            <p className="lead text-secondary col-xl-10">
              A secure full-stack command center for real-time AI streaming, multi-turn context,
              authenticated workspaces, and production-ready agentic workflows.
            </p>
            <div className="d-flex flex-wrap gap-3 mt-5">
              <button className="btn btn-nexus-primary btn-lg" onClick={() => navigate('/auth/register')} type="button">
                Register
              </button>
              <button className="btn btn-nexus-ghost btn-lg px-4" onClick={() => navigate('/auth/signin')} type="button">
                Sign In
              </button>
            </div>
          </div>
          <div className="col-lg-5 mt-5 mt-lg-0">
            <div className="glass-card p-4 p-md-5">
              <p className="text-accent mb-2">Built for continuity</p>
              <h2 className="h4 gradient-text mb-4">Agentic chat that remembers context</h2>
              <div className="feature-highlight-list">
                <div className="glass-card-sm p-3">✦ Long-term memory across sessions</div>
                <div className="glass-card-sm p-3">✦ Agentic web search with live thinking</div>
                <div className="glass-card-sm p-3">✦ Image & file analysis</div>
                <div className="glass-card-sm p-3">✦ Multi-turn context with secure auth</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
