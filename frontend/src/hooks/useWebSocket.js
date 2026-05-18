import { useEffect, useRef, useCallback } from 'react';
import useChatStore from '../store/chatStore';

const WS_BASE = process.env.REACT_APP_WS_URL || 'ws://localhost:5001';
const MAX_RETRIES = 5;
const RETRY_BASE_MS = 1500;

function useWebSocket(sessionId) {
  const wsRef         = useRef(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef(null);
  const isMountedRef  = useRef(true);

  const appendStreamingToken = useChatStore((s) => s.appendStreamingToken);
  const finalizeStream       = useChatStore((s) => s.finalizeStream);
  const setError             = useChatStore((s) => s.setError);
  const updateSessionTitle   = useChatStore((s) => s.updateSessionTitle);
  const activeSessionId      = useChatStore((s) => s.activeSessionId);

  const connect = useCallback(() => {
    if (!sessionId) return;

    const url = WS_BASE + '/api/v1/stream/ws/' + sessionId;
    console.log('[WS] Connecting to ' + url);

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      retryCountRef.current = 0;
      console.log('[WS] Connected — session: ' + sessionId);
    };

    ws.onmessage = (event) => {
      let parsed;
      try {
        parsed = JSON.parse(event.data);
      } catch (_) {
        console.warn('[WS] Non-JSON message:', event.data);
        return;
      }

      const eventType = parsed.event_type;
      const delta     = parsed.delta;
      const message   = parsed.message;
      const title     = parsed.title;

      if (eventType === 'status') {
        console.log('[WS] Status: ' + message);
      } else if (eventType === 'token') {
        if (delta) appendStreamingToken(delta);
      } else if (eventType === 'complete') {
        finalizeStream();
      } else if (eventType === 'error') {
        console.error('[WS] Agent error: ' + message);
        setError(message || 'An error occurred during streaming.');
      } else if (eventType === 'title_update') {
        if (title && activeSessionId) {
          updateSessionTitle(activeSessionId, title);
        }
      } else {
        console.warn('[WS] Unknown event_type:', eventType);
      }
    };

    ws.onerror = () => {
      console.warn('[WS] Socket error — will retry on close.');
    };

    ws.onclose = (event) => {
      console.log('[WS] Closed — code: ' + event.code + ', clean: ' + event.wasClean);

      if (!isMountedRef.current || event.code === 1000 || event.code === 1001) return;

      if (retryCountRef.current < MAX_RETRIES) {
        const delay = RETRY_BASE_MS * Math.pow(2, retryCountRef.current);
        retryCountRef.current += 1;
        console.log('[WS] Retry ' + retryCountRef.current + '/' + MAX_RETRIES + ' in ' + delay + 'ms');
        retryTimerRef.current = setTimeout(connect, delay);
      } else {
        setError(
          'Cannot connect to AI service at ' + WS_BASE + '. ' +
          'Run: cd service-ai && uv run uvicorn app.main:app --reload'
        );
      }
    };
  }, [sessionId, appendStreamingToken, finalizeStream, setError, updateSessionTitle, activeSessionId]);

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
      setError('AI service not connected. Run: cd service-ai && uv run uvicorn app.main:app --reload');
      return;
    }
    wsRef.current.send(JSON.stringify(payload));
  }, [setError]);

  return { sendMessage };
}

export default useWebSocket;
