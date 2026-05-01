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
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!enabled) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const fullUrl = `${protocol}//${window.location.host}${url}`;
    const ws = new WebSocket(fullUrl);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      if (enabled) {
        reconnectTimer.current = setTimeout(connect, reconnectMs);
      }
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        onMessage?.(data);
      } catch { /* ignore non-JSON */ }
    };

    wsRef.current = ws;
  }, [url, onMessage, enabled, reconnectMs]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected };
}
