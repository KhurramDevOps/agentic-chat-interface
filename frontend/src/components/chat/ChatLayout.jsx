import React, { Component, useState } from 'react';
import AppShell from '../layout/AppShell';
import GlassCard from '../ui/GlassCard';
import ChatWindow from './ChatWindow';
import Sidebar from './Sidebar';

class ChatErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <GlassCard className="p-5 text-center m-auto" style={{ maxWidth: 520 }}>
          <h2 className="gradient-text">Something went wrong</h2>
          <p className="text-secondary">The chat interface crashed safely. Reload to restore the session.</p>
          <button className="btn btn-nexus-primary" onClick={() => window.location.reload()} type="button">
            Reload
          </button>
        </GlassCard>
      );
    }
    return this.props.children;
  }
}

export default function ChatLayout() {
  const [showMobileSidebar, setShowMobileSidebar] = useState(false);

  return (
    <AppShell>
      <div className="d-md-none p-2">
        <button className="btn btn-nexus-ghost" onClick={() => setShowMobileSidebar(true)} type="button">
          <i className="bi bi-list me-2" />
          Conversations
        </button>
      </div>
      <div className="chat-shell">
        <div className="d-none d-md-block sidebar-panel">
          <Sidebar />
        </div>
        <GlassCard className="chat-panel p-3">
          <ChatErrorBoundary>
            <ChatWindow />
          </ChatErrorBoundary>
        </GlassCard>
      </div>
      {showMobileSidebar ? (
        <div className="position-fixed top-0 start-0 w-100 h-100 d-md-none" style={{ background: 'rgba(6, 9, 16, .72)', zIndex: 1050 }}>
          <div className="h-100 p-2" style={{ width: 310, maxWidth: '86vw' }}>
            <Sidebar onSelect={() => setShowMobileSidebar(false)} />
          </div>
          <button className="btn btn-nexus-primary position-absolute top-0 end-0 m-3" onClick={() => setShowMobileSidebar(false)} type="button">
            <i className="bi bi-x-lg" />
          </button>
        </div>
      ) : null}
    </AppShell>
  );
}
