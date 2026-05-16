import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ChatLayout from '../components/chat/ChatLayout';
import useWebSocket from '../hooks/useWebSocket';
import useChatStore from '../store/chatStore';

/**
 * ChatPage
 * ─────────
 * Reads :sessionId from the URL via useParams.
 * When the URL sessionId changes, syncs it into chatStore and loads history.
 * Passes sendMessage from the WebSocket hook down to ChatLayout.
 */
function ChatPage() {
  const { sessionId: urlSessionId } = useParams();
  const navigate = useNavigate();

  const activeSessionId  = useChatStore((s) => s.activeSessionId);
  const setActiveSession = useChatStore((s) => s.setActiveSession);
  const loadHistory      = useChatStore((s) => s.loadHistory);
  const sessions         = useChatStore((s) => s.sessions);
  const addSession       = useChatStore((s) => s.addSession);

  // ── Sync URL → store on mount and when URL changes ──────────────────────
  useEffect(() => {
    if (urlSessionId) {
      // URL has a session — activate it and load its history
      if (urlSessionId !== activeSessionId) {
        setActiveSession(urlSessionId);
        loadHistory(urlSessionId);

        // If this session isn't in the sidebar list yet, add it
        const exists = sessions.some((s) => s.id === urlSessionId);
        if (!exists) {
          addSession({
            id: urlSessionId,
            title: 'Loading...',
            createdAt: new Date().toISOString(),
          });
        }
      }
    } else {
      // /chat with no sessionId — create a new session and redirect
      const newId = crypto.randomUUID();
      addSession({
        id: newId,
        title: `Chat ${sessions.length + 1}`,
        createdAt: new Date().toISOString(),
      });
      setActiveSession(newId);
      navigate(`/chat/${newId}`, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlSessionId]);

  // WebSocket connects to the active session
  const { sendMessage } = useWebSocket(activeSessionId);

  return <ChatLayout sendMessage={sendMessage} />;
}

export default ChatPage;
