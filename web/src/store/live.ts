import { create } from "zustand";

import { bumpDirty, setRev } from "../lib/dirty";
import type { DeviceState, Overlay, SessionInfo, Snapshot, SystemStats, ToolStats } from "../types/state";

interface LiveState {
  snapshot: Snapshot | null;
  connected: boolean;
  setSnapshot: (s: Snapshot) => void;
  setConnected: (c: boolean) => void;
}

export const useLive = create<LiveState>((set) => ({
  snapshot: null,
  connected: false,
  setSnapshot: (snapshot) => {
    set({ snapshot });
    setRev(snapshot.rev);
    bumpDirty();
  },
  setConnected: (connected) => set({ connected }),
}));

// selector hooks — widgets never touch the raw snapshot
const EMPTY_TOOLS: ToolStats[] = [];

export const useTools = (): ToolStats[] => useLive((s) => s.snapshot?.tools ?? EMPTY_TOOLS);
export const useTool = (name: string): ToolStats | undefined =>
  useLive((s) => s.snapshot?.tools.find((t) => t.name === name));
export const useSystem = (): SystemStats | null => useLive((s) => s.snapshot?.system ?? null);
export const useOverlay = (): Overlay | null => useLive((s) => s.snapshot?.attention.overlay ?? null);
export const useDevice = (): DeviceState | undefined => useLive((s) => s.snapshot?.device);

export interface SessionRow {
  accent: string;
  tool: string;
  session: SessionInfo;
}

/** All sessions across tools, sorted like the v1 renderer: live, then
 * needs-you, then most recent. */
export function sortSessions(tools: ToolStats[], accents: Record<string, string>, only?: string[]): SessionRow[] {
  const rows: SessionRow[] = [];
  for (const t of tools) {
    if (only && only.length && !only.includes(t.name)) continue;
    for (const s of t.sessions) rows.push({ accent: accents[t.name] ?? "var(--blue)", tool: t.name, session: s });
  }
  rows.sort((a, b) => {
    const ka = [a.session.live ? 1 : 0, a.session.needs_input ? 1 : 0, a.session.last_active];
    const kb = [b.session.live ? 1 : 0, b.session.needs_input ? 1 : 0, b.session.last_active];
    for (let i = 0; i < 3; i++) if (ka[i] !== kb[i]) return kb[i] - ka[i];
    return 0;
  });
  return rows;
}
