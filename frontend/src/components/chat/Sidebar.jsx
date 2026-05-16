import React from 'react';
import useChatStore from '../../store/chatStore';
import useAuthStore from '../../store/authStore';
import '../../styles/Chat.css';

/**
 * Sidebar
 * ────────
 * Displays the list of chat sessions and a "New Chat" button.
 * Also shows the logged-in user's name and a logout button.
 */
function Sidebar() {
  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const setActiveSession = useChatStore((s) => s.setActiveSession);
  const addSession = useChatStore((s) => s.addSession);

  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const handleNewChat = () => {
    const id = crypto.randomUUID();
    const session = {
      id,
      title: `Chat ${sessions.length + 1}`,
      createdAt: new Date().toISOString(),
    };
    addSession(session);
    setActiveSession(id);
  };

  return (
    <div className="sidebar">

      {/* App title */}
      <div className="sidebar-header">
        <span className="sidebar-title">Stitch Nexus AI</span>
      </div>

      {/* New Chat button */}
      <button className="sidebar-new-btn" onClick={handleNewChat}>
        + New Chat
      </button>

      {/* Session list */}
      <div className="sidebar-sessions">
        {sessions.length === 0 && (
          <p className="sidebar-empty">No sessions yet.</p>
        )}
        {sessions.map((session) => (
          <button
            key={session.id}
            className={`sidebar-session-item ${session.id === activeSessionId ? 'sidebar-session-item--active' : ''}`}
            onClick={() => setActiveSession(session.id)}
          >
            {session.title}
          </button>
        ))}
      </div>

      {/* User info + logout */}
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
