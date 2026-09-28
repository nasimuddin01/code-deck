import { useEffect, useState } from "react";

import { MEDIA_CHANGED } from "../api";
import { bumpDirty } from "./dirty";

export interface Polled<T> {
  data: T | null;
  error: string | null;
}

/** GET `url` now and every `periodMs`, re-rendering (and marking the frame
 * dirty) only when the response changes. `url` null = idle. Errors keep the
 * last good data so a flaky network never blanks a widget. */
export function usePolledJson<T>(url: string | null, periodMs: number): Polled<T> {
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
    const load = async () => {
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
      if (!cancelled) timer = window.setTimeout(load, periodMs);
    };
    // an upload/delete in the builder: reload now instead of at the next poll
    const now = () => { window.clearTimeout(timer); load(); };
    window.addEventListener(MEDIA_CHANGED, now);
    load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.removeEventListener(MEDIA_CHANGED, now);
    };
  }, [url, periodMs]);
  return state;
}

/** Server-resized copy of a local photo, big enough for a w x h box. */
export function mediaUrl(path: string, w: number, h: number): string {
  // 2x so it stays crisp in the zoomed builder; the device renders at 1x
  const cap = (n: number) => Math.max(16, Math.min(1280, Math.round(n * 2)));
  return `/api/media/file?${new URLSearchParams({ path, w: String(cap(w)), h: String(cap(h)) })}`;
}
