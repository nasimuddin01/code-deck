import { create } from "zustand";

import { bumpDirty, setRev } from "../lib/dirty";
import { accentOf } from "../lib/format";
import type { AgentInfo, DeviceState, Overlay, SessionInfo, Snapshot, SystemStats, ToolStats } from "../types/state";

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
const EMPTY_AGENTS: AgentInfo[] = [];

/** An agent's stats by registry id ("codex") or display name ("Codex"). */
export const matchesTool = (t: ToolStats, ref: string): boolean => t.agent_id === ref || t.name === ref;
export const useTool = (ref: string): ToolStats | undefined =>
  useLive((s) => s.snapshot?.tools.find((t) => matchesTool(t, ref)));
export const useAgents = (): AgentInfo[] => useLive((s) => s.snapshot?.agents ?? EMPTY_AGENTS);
export const useSystem = (): SystemStats | null => useLive((s) => s.snapshot?.system ?? null);
export const useOverlay = (): Overlay | null => useLive((s) => s.snapshot?.attention.overlay ?? null);
export const useDevice = (): DeviceState | undefined => useLive((s) => s.snapshot?.device);

export interface SessionRow {
  accent: string;
  tool: string;
  session: SessionInfo;
}

// Layouts saved before custom agents listed these three explicitly; treat
// that list as "every agent" so new agents show up without editing the layout.
const LEGACY_ALL = ["Claude Code", "Claude Max", "Codex"];
const isLegacyAll = (only: string[]) =>
  only.length === LEGACY_ALL.length && LEGACY_ALL.every((n) => only.includes(n));

/** All sessions across agents: waiting on you first (so a blocked agent is
 * never pushed below the fold), then live, then most recent. `only` (ids or
 * names) filters; empty = all. */
export function sortSessions(tools: ToolStats[], only?: string[]): SessionRow[] {
  const filter = only && only.length && !isLegacyAll(only) ? only : null;
  const rows: SessionRow[] = [];
  for (const t of tools) {
    if (filter && !filter.some((ref) => matchesTool(t, ref))) continue;
    for (const s of t.sessions) rows.push({ accent: accentOf(t), tool: t.name, session: s });
  }
  rows.sort((a, b) => {
    const ka = [a.session.needs_input ? 1 : 0, a.session.live ? 1 : 0, a.session.last_active];
    const kb = [b.session.needs_input ? 1 : 0, b.session.live ? 1 : 0, b.session.last_active];
    for (let i = 0; i < 3; i++) if (ka[i] !== kb[i]) return kb[i] - ka[i];
    return 0;
  });
  return rows;
}
