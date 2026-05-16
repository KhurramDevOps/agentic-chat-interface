import React from 'react';
import { useNavigate } from 'react-router-dom';
import useChatStore from '../../store/chatStore';
import useAuthStore from '../../store/authStore';
import '../../styles/Chat.css';

/**
 * Sidebar
 * ────────
 * Session list + New Chat button.
 * Uses useNavigate to push /chat/:sessionId — URL is the source of truth.
 */
function Sidebar() {
  const navigate = useNavigate();

  const sessions        = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const addSession      = useChatStore((s) => s.addSession);

  const user   = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const handleNewChat = () => {
    const id = crypto.randomUUID();
    addSession({
      id,
      title: `Chat ${sessions.length + 1}`,
      createdAt: new Date().toISOString(),
    });
    // Navigate — ChatPage useEffect will pick this up and activate the session
    navigate(`/chat/${id}`);
  };

  const handleSessionClick = (sessionId) => {
    navigate(`/chat/${sessionId}`);
  };

  return (
    <div className="sidebar">

      <div className="sidebar-header">
        <span className="sidebar-title">Stitch Nexus AI</span>
      </div>

      <button className="sidebar-new-btn" onClick={handleNewChat}>
        + New Chat
      </button>

      <div className="sidebar-sessions">
        {sessions.length === 0 && (
          <p className="sidebar-empty">No sessions yet.</p>
        )}
        {sessions.map((session) => (
          <button
            key={session.id}
            className={`sidebar-session-item ${session.id === activeSessionId ? 'sidebar-session-item--active' : ''}`}
            onClick={() => handleSessionClick(session.id)}
          >
            {session.title}
          </button>
        ))}
      </div>

      <div className="sidebar-footer">
        {user && <span className="sidebar-user">{user.name || user.email}</span>}
        <button className="sidebar-logout-btn" onClick={logout}>
          Logout
        </button>
      </div>

    </div>
  );
}

export default Sidebar;
