// The frame pipeline (Python + headless Chromium) polls `window.__cd.dirty`
// and only screenshots when it changed. Anything that changes pixels must
// bump it: store updates, layout changes, clock ticks, overlay animation.

declare global {
  interface Window {
    __cd: { ready: boolean; dirty: number; rev: number };
  }
}

if (typeof window !== "undefined" && !window.__cd) {
  window.__cd = { ready: false, dirty: 0, rev: 0 };
}

export function bumpDirty(): void {
  if (typeof window !== "undefined") window.__cd.dirty += 1;
}

export function setReady(): void {
  if (typeof window !== "undefined") window.__cd.ready = true;
}

export function setRev(rev: number): void {
  if (typeof window !== "undefined") window.__cd.rev = rev;
}
