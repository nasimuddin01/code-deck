// Ports of the small formatters in render/pil_legacy.py.

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

export function money(n: number): string {
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function resetIn(epoch: number, now: number): string {
  const secs = Math.max(0, Math.floor(epoch - now));
  if (secs >= 86400) return `${Math.floor(secs / 86400)}d`;
  if (secs >= 3600) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 60)}m`;
}

export function ago(epoch: number, now: number): string {
  if (!epoch) return "";
  const s = Math.floor(now - epoch);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export function bytesPerSec(v: number): string {
  if (v >= 1_048_576) return `${(v / 1_048_576).toFixed(1)} MB/s`;
  if (v >= 1024) return `${Math.round(v / 1024)} KB/s`;
  return `${Math.round(v)} B/s`;
}

export function gb(bytes: number): string {
  return `${(bytes / 1_073_741_824).toFixed(0)}G`;
}

const pad = (n: number) => String(n).padStart(2, "0");

export function hhmm(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
export function hhmmss(d: Date): string {
  return `${hhmm(d)}:${pad(d.getSeconds())}`;
}
export function dateShort(d: Date): string {
  // "%a %d %b" -> "Thu 17 Sep"
  const wd = d.toLocaleDateString("en-US", { weekday: "short" });
  const mo = d.toLocaleDateString("en-US", { month: "short" });
  return `${wd} ${pad(d.getDate())} ${mo}`;
}

// Named colours a widget prop may use, resolved to theme tokens; any other
// string is passed through (hex etc.).
const NAMED: Record<string, string> = {
  orange: "var(--orange)", violet: "var(--violet)", blue: "var(--blue)",
  good: "var(--good)", warning: "var(--warning)", critical: "var(--critical)",
  attention: "var(--attention)", text: "var(--text)", text2: "var(--text-2)",
  muted: "var(--text-muted)", track: "var(--track)",
};
export function color(name: string | undefined, fallback = "var(--text)"): string {
  if (!name) return fallback;
  return NAMED[name] ?? name;
}

export const TOOL_ACCENT: Record<string, string> = {
  "Claude Code": "var(--orange)",
  "Claude Max": "var(--violet)",
  Codex: "var(--blue)",
};
