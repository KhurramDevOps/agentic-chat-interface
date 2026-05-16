import { useEffect, useRef, useCallback } from 'react';
import useChatStore from '../store/chatStore';

/**
 * WebSocket connects directly to the Python FastAPI service.
 * The Node gateway does NOT proxy WebSocket traffic.
 *
 * Python service: ws://localhost:8000/api/v1/stream/ws/{sessionId}
 */
const WS_BASE = process.env.REACT_APP_WS_URL || 'ws://localhost:8000';

const MAX_RETRIES = 5;
const RETRY_BASE_MS = 1500;

function useWebSocket(sessionId) {
  const wsRef = useRef(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef(null);
  const isMountedRef = useRef(true);

  const appendStreamingToken = useChatStore((s) => s.appendStreamingToken);
  const finalizeStream       = useChatStore((s) => s.finalizeStream);
  const setError             = useChatStore((s) => s.setError);

  const connect = useCallback(() => {
    if (!sessionId) return;

    const url = `${WS_BASE}/api/v1/stream/ws/${sessionId}`;
    console.log(`[WS] Connecting to ${url}`);

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
        console.warn('[WS] Non-JSON message:', event.data);
        return;
      }

      const { event_type, delta, message } = parsed;

      switch (event_type) {
        case 'status':
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

    ws.onerror = () => {
      // onerror fires before onclose — log only, let onclose handle retry
      console.warn('[WS] Socket error — will attempt reconnect if applicable.');
    };

    ws.onclose = (event) => {
      console.log(`[WS] Closed — code: ${event.code}, clean: ${event.wasClean}`);

      // 1000 = normal close, 1001 = going away — don't retry
      if (!isMountedRef.current || event.code === 1000 || event.code === 1001) return;

      if (retryCountRef.current < MAX_RETRIES) {
        const delay = RETRY_BASE_MS * Math.pow(2, retryCountRef.current);
        retryCountRef.current += 1;
        console.log(`[WS] Retry ${retryCountRef.current}/${MAX_RETRIES} in ${delay}ms`);
        retryTimerRef.current = setTimeout(connect, delay);
      } else {
        setError(
          `Cannot connect to the AI service at ${WS_BASE}. ` +
          'Make sure the Python service is running: cd service-ai && uv run uvicorn app.main:app --reload'
        );
      }
    };
  }, [sessionId, appendStreamingToken, finalizeStream, setError]);

  useEffect(() => {
    isMountedRef.current = true;
    retryCountRef.current = 0;
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

  const sendMessage = useCallback((payload) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError(
        `AI service not connected (${WS_BASE}). ` +
        'Start the Python service: cd service-ai && uv run uvicorn app.main:app --reload'
      );
      return;
    }
    wsRef.current.send(JSON.stringify(payload));
  }, [setError]);

  return { sendMessage };
}

export default useWebSocket;
