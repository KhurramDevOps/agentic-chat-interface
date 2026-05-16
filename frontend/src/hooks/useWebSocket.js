import { useEffect, useRef, useCallback } from 'react';
import useChatStore from '../store/chatStore';

const WS_BASE = process.env.REACT_APP_WS_URL || 'ws://localhost:3001';
const MAX_RETRIES = 5;
const RETRY_BASE_MS = 1000;

/**
 * useWebSocket(sessionId)
 * ────────────────────────
 * Manages the WebSocket lifecycle for a single chat session.
 *
 * - Opens a connection to WS_BASE/api/v1/stream/ws/{sessionId} on mount.
 * - Routes inbound JSON events to the appropriate chatStore actions.
 * - Implements exponential backoff reconnection (max 5 attempts).
 * - Tears down the socket on unmount or when sessionId changes.
 *
 * Returns: sendMessage(payload) — call this to send a chat turn.
 */
function useWebSocket(sessionId) {
  const wsRef = useRef(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef(null);
  const isMountedRef = useRef(true);

  const appendStreamingToken = useChatStore((s) => s.appendStreamingToken);
  const finalizeStream = useChatStore((s) => s.finalizeStream);
  const setError = useChatStore((s) => s.setError);

  const connect = useCallback(() => {
    if (!sessionId) return;

    const url = `${WS_BASE}/api/v1/stream/ws/${sessionId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      retryCountRef.current = 0;
      console.log(`[WS] Connected — session: ${sessionId}`);
    };

    ws.onmessage = (event) => {
      let parsed;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        console.warn('[WS] Non-JSON message received:', event.data);
        return;
      }

      const { event_type, delta, message } = parsed;

      switch (event_type) {
        case 'status':
          // Status messages are informational — log only for now
          console.log(`[WS] Status: ${message}`);
          break;

        case 'token':
          if (delta) appendStreamingToken(delta);
          break;

        case 'complete':
          finalizeStream();
          break;

        case 'error':
          console.error(`[WS] Agent error: ${message}`);
          setError(message || 'An error occurred during streaming.');
          break;

        default:
          console.warn('[WS] Unknown event_type:', event_type);
      }
    };

    ws.onerror = (err) => {
      console.error('[WS] Socket error:', err);
    };

    ws.onclose = (event) => {
      console.log(`[WS] Closed — code: ${event.code}, clean: ${event.wasClean}`);

      // Do not reconnect if component unmounted or close was intentional (1000)
      if (!isMountedRef.current || event.code === 1000) return;

      if (retryCountRef.current < MAX_RETRIES) {
        const delay = RETRY_BASE_MS * Math.pow(2, retryCountRef.current);
        retryCountRef.current += 1;
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${retryCountRef.current}/${MAX_RETRIES})`);
        retryTimerRef.current = setTimeout(connect, delay);
      } else {
        setError('Connection lost. Please refresh the page.');
      }
    };
  }, [sessionId, appendStreamingToken, finalizeStream, setError]);

  useEffect(() => {
    isMountedRef.current = true;
    connect();

    return () => {
      isMountedRef.current = false;
      clearTimeout(retryTimerRef.current);
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
  }, [connect]);

  /**
   * sendMessage(payload)
   * Sends a JSON payload over the WebSocket.
   * Payload shape:
   * {
   *   request_id: string,
   *   messages: [{ role: 'user', content: string }],
   *   model: string,
   *   memory_context_id: string
   * }
   */
  const sendMessage = useCallback((payload) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Cannot send — socket not open.');
      setError('Connection is not ready. Please wait a moment and try again.');
      return;
    }
    wsRef.current.send(JSON.stringify(payload));
  }, [setError]);

  return { sendMessage };
}

export default useWebSocket;
