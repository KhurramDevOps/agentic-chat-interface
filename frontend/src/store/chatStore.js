import { create } from 'zustand';
import { getHistory } from '../api/historyApi';

/**
 * chatStore.js
 * ─────────────
 * Zustand store for all chat state.
 *
 * State:
 *   sessions        — [{ id, title, createdAt }]
 *   activeSessionId — currently open session UUID
 *   messages        — committed messages [{ id, role, content, timestamp }]
 *   isStreaming     — true while WebSocket is receiving token events
 *   streamingContent— accumulates token deltas during an active stream
 *   error           — last error string or null
 */

const useChatStore = create((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  isStreaming: false,
  streamingContent: '',
  error: null,

  // ── Session management ──────────────────────────────────────────────────

  setActiveSession: (sessionId) => {
    set({
      activeSessionId: sessionId,
      messages: [],
      streamingContent: '',
      isStreaming: false,
      error: null,
    });
  },

  addSession: (session) => {
    // Prevent duplicates
    const exists = get().sessions.some((s) => s.id === session.id);
    if (exists) return;
    set((state) => ({ sessions: [session, ...state.sessions] }));
  },

  /**
   * Update a session's title in the sidebar.
   * Called when a 'title_update' WebSocket event arrives (Issue 4).
   */
  updateSessionTitle: (sessionId, title) => {
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId ? { ...s, title } : s
      ),
    }));
  },

  // ── Message management ──────────────────────────────────────────────────

  addMessage: (role, content) => {
    const message = {
      id: crypto.randomUUID(),
      role,
      content,
      timestamp: new Date().toISOString(),
    };
    set((state) => ({ messages: [...state.messages, message] }));
  },

  /**
   * Load raw message array directly into state (used by ChatPage on session switch).
   */
  loadMessages: (rawMessages) => {
    const messages = rawMessages.map((m) => ({
      id: crypto.randomUUID(),
      role: m.role,
      content: m.content,
      timestamp: m.timestamp || new Date().toISOString(),
    }));
    set({ messages });
  },

  /**
   * Fetch history from the API for a sessionId and populate messages.
   * Called by ChatPage whenever the URL sessionId changes.
   */
  loadHistory: async (sessionId) => {
    set({ messages: [], isStreaming: false, streamingContent: '', error: null });
    try {
      const { data } = await getHistory(sessionId);
      const msgs = data?.messages || [];
      if (msgs.length > 0) {
        const messages = msgs.map((m) => ({
          id: crypto.randomUUID(),
          role: m.role,
          content: m.content,
          timestamp: m.timestamp || new Date().toISOString(),
        }));
        set({ messages });

        // If the session title is still a placeholder, update it from history
        const firstUser = msgs.find((m) => m.role === 'user');
        if (firstUser) {
          const sessions = get().sessions;
          const session = sessions.find((s) => s.id === sessionId);
          if (session && session.title === 'Loading...') {
            const preview = firstUser.content.slice(0, 30);
            get().updateSessionTitle(sessionId, preview + (firstUser.content.length > 30 ? '…' : ''));
          }
        }
      }
    } catch (err) {
      // 404 = new session, not an error
      if (err?.response?.status !== 404) {
        console.warn('[chatStore] loadHistory failed:', err.message);
      }
    }
  },

  // ── Streaming ───────────────────────────────────────────────────────────

  appendStreamingToken: (delta) => {
    set((state) => ({
      isStreaming: true,
      streamingContent: state.streamingContent + delta,
    }));
  },

  finalizeStream: () => {
    const { streamingContent } = get();
    if (streamingContent.trim()) {
      const message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: streamingContent,
        timestamp: new Date().toISOString(),
      };
      set((state) => ({
        messages: [...state.messages, message],
        isStreaming: false,
        streamingContent: '',
      }));
    } else {
      set({ isStreaming: false, streamingContent: '' });
    }
  },

  // ── Error & cleanup ─────────────────────────────────────────────────────

  setError: (error) => set({ error, isStreaming: false, streamingContent: '' }),
  clearError: () => set({ error: null }),

  clearSession: () => {
    set({ messages: [], streamingContent: '', isStreaming: false, error: null });
  },
}));

export default useChatStore;
