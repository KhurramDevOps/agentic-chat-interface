import { create } from 'zustand';

/**
 * chatStore.js
 * ─────────────
 * Zustand store for all chat state.
 *
 * State shape:
 *   sessions        — list of { id, title, createdAt }
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
    set((state) => ({
      sessions: [session, ...state.sessions],
    }));
  },

  // ── Message management ──────────────────────────────────────────────────

  /**
   * Commit a message to the permanent message list.
   * role: 'user' | 'assistant'
   */
  addMessage: (role, content) => {
    const message = {
      id: crypto.randomUUID(),
      role,
      content,
      timestamp: new Date().toISOString(),
    };
    set((state) => ({
      messages: [...state.messages, message],
    }));
  },

  /**
   * Load history from the API response into the message list.
   * Replaces current messages for the active session.
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

  // ── Streaming ───────────────────────────────────────────────────────────

  /**
   * Called on every 'token' WebSocket event.
   * Accumulates delta text into streamingContent.
   */
  appendStreamingToken: (delta) => {
    set((state) => ({
      isStreaming: true,
      streamingContent: state.streamingContent + delta,
    }));
  },

  /**
   * Called on 'complete' WebSocket event.
   * Moves accumulated streamingContent into the committed messages list.
   */
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
    set({
      messages: [],
      streamingContent: '',
      isStreaming: false,
      error: null,
    });
  },
}));

export default useChatStore;
