import { getState } from "./api";
import { useLive } from "./store/live";
import type { Snapshot } from "./types/state";

// Live state over WebSocket with reconnect; falls back to polling /api/state
// while disconnected so the player never sits on stale data.
export function connectLive(): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let backoff = 500;
  let poll: number | undefined;
  const { setSnapshot, setConnected } = useLive.getState();

  const startPolling = () => {
    if (poll !== undefined) return;
    const tick = () => getState().then(setSnapshot).catch(() => {});
    tick();
    poll = window.setInterval(tick, 2000);
  };
  const stopPolling = () => {
    if (poll !== undefined) window.clearInterval(poll);
    poll = undefined;
  };

  const open = () => {
    if (closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/state`);
    ws.onopen = () => {
      backoff = 500;
      setConnected(true);
      stopPolling();
    };
    ws.onmessage = (ev) => setSnapshot(JSON.parse(ev.data) as Snapshot);
    ws.onclose = () => {
      setConnected(false);
      if (closed) return;
      startPolling();
      window.setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, 10_000);
    };
    ws.onerror = () => ws?.close();
  };

  startPolling(); // immediate first snapshot; WS takes over on open
  open();
  return () => {
    closed = true;
    stopPolling();
    ws?.close();
  };
}
