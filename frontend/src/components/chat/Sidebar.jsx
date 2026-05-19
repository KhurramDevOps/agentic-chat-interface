import React, { useContext } from 'react';
import { ChatContext } from '../../context/ChatContext';
import { useAuth } from '../../hooks/useAuth';
import { useDeleteSession, useSessions } from '../../hooks/useChat';
import { formatRelativeTime } from '../../utils/timeUtils';
import NexusLogo from '../ui/NexusLogo';

export default function Sidebar({ onSelect }) {
  const { logout, user } = useAuth();
  const { activeSessionId, selectSession, startNewChat } = useContext(ChatContext);
  const { data: sessions = [], isLoading } = useSessions();
  const deleteSession = useDeleteSession();

  const chooseSession = (session) => {
    selectSession(session);
    onSelect?.();
  };

  const removeSession = (event, sessionId) => {
    event.stopPropagation();
    if (window.confirm('Delete this conversation?')) {
      deleteSession.mutate(sessionId);
    }
  };

  return (
    <aside className="sidebar-panel glass-card p-3 h-100">
      <div className="d-flex align-items-center justify-content-between mb-3">
        <NexusLogo />
        <div className="dropdown">
          <button className="btn btn-nexus-ghost rounded-circle" data-bs-toggle="dropdown" type="button" title="Account">
            {(user?.name || user?.email || 'U').slice(0, 1).toUpperCase()}
          </button>
          <div className="dropdown-menu dropdown-menu-end p-2">
            <div className="px-3 py-2">
              <strong className="d-block">{user?.name || 'Nexus User'}</strong>
              <span className="text-secondary small">{user?.email}</span>
            </div>
            <button className="dropdown-item rounded-2" onClick={logout} type="button">
              <i className="bi bi-box-arrow-right me-2" />
              Sign Out
            </button>
          </div>
        </div>
      </div>
      <button className="btn btn-nexus-primary w-100 mb-3" onClick={startNewChat} type="button">
        <i className="bi bi-plus-lg me-2" />
        New Chat
      </button>
      <div className="session-list d-flex flex-column gap-2 pe-1">
        {isLoading ? (
          <>
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </>
        ) : sessions.length ? (
          sessions.map((session) => {
            const sessionId = session.id || session._id || session.session_id;
            return (
              <button
                className={`session-item glass-card-sm text-start p-3 ${activeSessionId === sessionId ? 'active glow-border' : ''}`}
                key={sessionId}
                onClick={() => chooseSession(session)}
                type="button"
              >
                <div className="d-flex justify-content-between gap-2">
                  <strong className="text-truncate">{session.name || session.title || 'Untitled Chat'}</strong>
                  <span className="session-delete">
                    <button className="btn btn-sm btn-nexus-ghost" onClick={(event) => removeSession(event, sessionId)} type="button" title="Delete">
                      <i className="bi bi-trash" />
                    </button>
                  </span>
                </div>
                <span className="text-secondary small">{formatRelativeTime(session.lastMessageAt || session.last_message_at || session.updatedAt)}</span>
              </button>
            );
          })
        ) : (
          <div className="glass-card-sm p-4 text-center text-secondary">
            <i className="bi bi-stars fs-2 d-block mb-2 text-accent" />
            No conversations yet. Start one!
          </div>
        )}
      </div>
    </aside>
  );
}
