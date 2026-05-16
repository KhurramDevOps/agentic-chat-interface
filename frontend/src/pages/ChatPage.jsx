import React, { useEffect } from 'react';
import ChatLayout from '../components/chat/ChatLayout';
import useWebSocket from '../hooks/useWebSocket';
import useChatStore from '../store/chatStore';
import { getHistory } from '../api/historyApi';

/**
 * ChatPage
 * ─────────
 * Top-level page for the chat interface.
 *
 * Responsibilities:
 *   - Initialises the WebSocket connection for the active session.
 *   - Loads conversation history from the API when the active session changes.
 *   - Passes sendMessage down to ChatLayout.
 */
function ChatPage() {
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const loadMessages = useChatStore((s) => s.loadMessages);
  const clearSession = useChatStore((s) => s.clearSession);

  // WebSocket lifecycle — reconnects automatically when sessionId changes
  const { sendMessage } = useWebSocket(activeSessionId);

  // Load history whenever the active session changes
  useEffect(() => {
    if (!activeSessionId) return;

    clearSession();

    getHistory(activeSessionId)
      .then(({ data }) => {
        const msgs = data?.messages || [];
        if (msgs.length > 0) {
          loadMessages(msgs);
        }
      })
      .catch((err) => {
        // History not found is expected for brand-new sessions — not an error
        if (err?.response?.status !== 404) {
          console.warn('[ChatPage] Failed to load history:', err.message);
        }
      });
  }, [activeSessionId, loadMessages, clearSession]);

  return <ChatLayout sendMessage={sendMessage} />;
}

export default ChatPage;
