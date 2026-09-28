import { useEffect, useState } from "react";

import { bumpDirty } from "./dirty";

export interface Polled<T> {
  data: T | null;
  error: string | null;
}

/** GET `url` now and every `periodMs`, re-rendering (and marking the frame
 * dirty) only when the response changes. `url` null = idle. Errors keep the
 * last good data so a flaky network never blanks a widget. A window event
 * named `refreshOn` reloads at once (the builder fires one after an upload). */
export function usePolledJson<T>(url: string | null, periodMs: number, refreshOn?: string): Polled<T> {
  const [state, setState] = useState<Polled<T>>({ data: null, error: null });
  useEffect(() => {
    if (!url) {
      setState({ data: null, error: null });
      bumpDirty();
      return;
    }
    let cancelled = false;
    let last = "";
    let timer: number;
    let gen = 0;   // only the newest load() schedules the next one
    const load = async () => {
      const my = ++gen;
      try {
        const res = await fetch(url);
        const text = await res.text();
        if (!res.ok) {
          let msg = `${res.status}`;
          try { msg = (JSON.parse(text) as { detail?: string }).detail ?? msg; } catch { /* not json */ }
          throw new Error(msg);
        }
        if (!cancelled && text !== last) {
          last = text;
          setState({ data: JSON.parse(text) as T, error: null });
          bumpDirty();
        }
      } catch (e) {
        if (!cancelled) {
          setState((s) => (s.error === String((e as Error).message) ? s : { data: s.data, error: (e as Error).message }));
          bumpDirty();
        }
      }
      if (!cancelled && my === gen) timer = window.setTimeout(load, periodMs);
    };
    const now = () => { window.clearTimeout(timer); load(); };
    if (refreshOn) window.addEventListener(refreshOn, now);
    load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (refreshOn) window.removeEventListener(refreshOn, now);
    };
  }, [url, periodMs, refreshOn]);
  return state;
}

/** Server-resized copy of a local photo, big enough for a w x h box. */
export function mediaUrl(path: string, w: number, h: number): string {
  // 2x so it stays crisp in the zoomed builder; the device renders at 1x.
  // Rounded up to 64 px steps so a resize drag reuses a handful of server
  // thumbnails instead of making one per pixel.
  const cap = (n: number) => Math.max(64, Math.min(1280, Math.ceil((n * 2) / 64) * 64));
  return `/api/media/file?${new URLSearchParams({ path, w: String(cap(w)), h: String(cap(h)) })}`;
}
