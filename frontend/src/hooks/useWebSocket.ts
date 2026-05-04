/* WebSocket hook — auto-reconnect, JSON parsing */
import { useEffect, useRef, useCallback, useState } from 'react';

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  enabled?: boolean;
  reconnectMs?: number;
}

export function useWebSocket({ url, onMessage, enabled = true, reconnectMs = 3000 }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef<UseWebSocketOptions['onMessage']>(onMessage);
  const shouldReconnectRef = useRef(false);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    if (!enabled || !url || !shouldReconnectRef.current) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const fullUrl = `${protocol}//${window.location.host}${url}`;
    const ws = new WebSocket(fullUrl);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      if (shouldReconnectRef.current) {
        reconnectTimer.current = setTimeout(connect, reconnectMs);
      }
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        onMessageRef.current?.(data);
      } catch { /* ignore non-JSON */ }
    };

    wsRef.current = ws;
  }, [url, enabled, reconnectMs]);

  useEffect(() => {
    shouldReconnectRef.current = Boolean(enabled);
    if (!enabled || !url) {
      setConnected(false);
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
      return () => {
        shouldReconnectRef.current = false;
      };
    }

    connect();
    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect, enabled, url]);

  return { connected };
}
