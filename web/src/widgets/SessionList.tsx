import { z } from "zod";

import { ago, fmtTokens, TOOL_ACCENT } from "../lib/format";
import { useNow } from "../lib/useNow";
import { defineWidget } from "../registry/types";
import { type SessionRow, sortSessions, useTools } from "../store/live";

const ROW_H = 40, GAP = 4;

const schema = z.object({
  max_rows: z.number().int().min(1).max(12).default(5),
  tools: z.array(z.string()).default(["Claude Code", "Claude Max", "Codex"]),
});

function Row({ row, y, w, now }: { row: SessionRow; y: number; w: number; now: number }) {
  const s = row.session;
  const nameCol = s.needs_input ? "var(--attention)" : row.accent;
  const model = `${s.model.replace("claude-", "")}${s.id ? ` · ${s.id}` : ""}`;
  let status: string, scol: string;
  if (s.needs_input) {
    status = s.attention_kind === "idle" ? "turn ended" : "needs you";
    scol = "var(--attention)";
  } else if (s.live) {
    status = "live"; scol = "var(--good)";
  } else {
    status = ago(s.last_active, now); scol = "var(--text-muted)";
  }
  const showDot = s.needs_input || s.live;
  return (
    <div style={{ position: "absolute", left: 0, top: y, width: w, height: ROW_H }}>
      <div className="dot" style={{ left: 2, top: ROW_H / 2 - 4, width: 8, height: 8, background: s.active ? row.accent : "var(--track)" }} />
      <div className="t ell" style={{ left: 18, top: 3, maxWidth: 150, fontSize: 13, fontWeight: 700, color: nameCol }}>
        {s.label || "session"}
      </div>
      <div className="t ell mono" style={{ left: 18, top: 22, maxWidth: 150, fontSize: 9, color: "var(--text-muted)" }}>
        {model}
      </div>
      <div className="t r mono" style={{ right: 6, top: 4, fontSize: 12, color: "var(--text-2)" }}>
        {fmtTokens(s.tokens_in)}/{fmtTokens(s.tokens_out)}
      </div>
      <div className="t r" style={{ right: 6, top: 23, fontSize: 9, color: scol, display: "flex", alignItems: "center", gap: 3 }}>
        {showDot && <span style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: scol }} />}
        <span>{status}</span>
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: ROW_H, height: 1, background: "var(--divider)" }} />
    </div>
  );
}

/** Combined session list — port of pil_legacy's rows + `_session_row`. */
export const SessionList = defineWidget<z.infer<typeof schema>>({
  type: "SessionList",
  title: "Session list",
  category: "sessions",
  schema,
  defaults: { max_rows: 5, tools: ["Claude Code", "Claude Max", "Codex"] },
  defaultSize: { w: 300, h: 216 },
  minSize: { w: 160, h: ROW_H + GAP },
  Component: ({ item, props }) => {
    const tools = useTools();
    const now = useNow("minute").getTime() / 1000;
    const rows = sortSessions(tools, TOOL_ACCENT, props.tools);
    const fit = Math.max(1, Math.floor(item.h / (ROW_H + GAP)));
    const maxRows = Math.min(props.max_rows, fit);
    let shown = rows.slice(0, maxRows);
    const overflow = rows.length - shown.length;
    if (overflow > 0) shown = rows.slice(0, Math.max(0, maxRows - 1));
    return (
      <>
        {shown.map((r, i) => (
          <Row key={`${r.tool}:${r.session.id}`} row={r} y={i * (ROW_H + GAP)} w={item.w} now={now} />
        ))}
        {overflow > 0 && (
          <div className="t" style={{ left: 0, top: shown.length * (ROW_H + GAP) + 8, fontSize: 10, color: "var(--text-muted)" }}>
            +{overflow + 1} more sessions
          </div>
        )}
      </>
    );
  },
});
