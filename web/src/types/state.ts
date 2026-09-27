// Mirrors the Python dataclasses / StateStore sections (snake_case on purpose:
// the wire format is `dataclasses.asdict`, no mapping layer).

export type AttentionKind = "needs" | "idle" | "";

export interface SessionInfo {
  id: string;
  label: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  active: boolean;
  last_active: number;
  live: boolean;
  needs_input: boolean;
  attention_kind: AttentionKind;
  cwd?: string;
}

export type ToolName = "Claude Code" | "Claude Max" | "Codex";

export interface ToolStats {
  name: ToolName | string;
  model: string;
  sessions_today: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  activity_24h: number[];
  live: boolean;
  active: boolean;
  cost_estimated: boolean;
  quota_pct: number | null;
  quota_resets_at: number | null;
  note: string;
  sessions: SessionInfo[];
  agent_id?: string;   // registry id: "claude-code", "codex", "aider", ...
  color?: string;      // theme name or hex from agents.toml
  source?: string;     // claude-code | claude-max | codex | push | command | jsonl | otel | python
}

export interface AgentInfo {
  id: string;
  name: string;
  color: string;
  source: string;
  enabled: boolean;
  builtin: boolean;
  dynamic: boolean;
  error: string;
}

export type SystemMetric = "cpu_pct" | "mem_pct" | "net_up_bps" | "net_down_bps";

export interface SystemStats {
  cpu_pct: number;
  mem_pct: number;
  mem_used: number;
  mem_total: number;
  disk_pct: number;
  disk_used: number;
  disk_total: number;
  net_up_bps: number;
  net_down_bps: number;
  history: Record<SystemMetric, number[]>;
}

export interface Overlay {
  session_id: string;
  label: string;
  kind: AttentionKind;
  started_at: number;
  seconds: number;
}

export interface DeviceState {
  connected: boolean;
  renderer: string | null;
  brightness: number | null;
  last_push_ms: number | null;
  last_rect: [number, number, number, number] | null;
  frames_pushed: number;
  last_error: string | null;
  chromium_ok: boolean | null;
}

export interface Snapshot {
  rev: number;
  ts: number;
  tools: ToolStats[];
  agents?: AgentInfo[];
  system: SystemStats | null;
  attention: { overlay: Overlay | null };
  device: DeviceState;
  layout_rev: number;
}
