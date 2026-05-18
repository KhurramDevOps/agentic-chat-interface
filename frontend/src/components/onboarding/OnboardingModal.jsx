import React, { useState } from 'react';
import GlassCard from '../ui/GlassCard';

export default function OnboardingModal({ user, onClose }) {
  const [name, setName] = useState(user?.name || '');

  const handleSubmit = (event) => {
    event.preventDefault();
    localStorage.setItem('nexus_display_name', name.trim() || user?.name || 'there');
    onClose();
  };

  return (
    <div className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center p-4" style={{ background: 'rgba(6, 9, 16, .72)', backdropFilter: 'blur(22px)', zIndex: 1060 }}>
      <GlassCard className="p-5 text-center" style={{ maxWidth: 560 }}>
        <div className="nexus-avatar mx-auto mb-4" style={{ height: 62, width: 62, fontSize: 28 }}>N</div>
        <h2 className="gradient-text mb-3">Welcome to Nexus AI</h2>
        <p className="text-secondary mb-4">Before we start, what should I call you?</p>
        <form onSubmit={handleSubmit}>
          <input
            autoFocus
            className="form-control form-control-lg text-center mb-4"
            onChange={(event) => setName(event.target.value)}
            value={name}
          />
          <button className="btn btn-nexus-primary btn-lg w-100" type="submit">
            Let's Go <i className="bi bi-arrow-right ms-2" />
          </button>
        </form>
      </GlassCard>
    </div>
  );
}
