import { z } from "zod";

import { accentOf, color, money, resetIn } from "../lib/format";
import { nowSeconds } from "../lib/useNow";
import { defineWidget } from "../registry/types";
import { useTool } from "../store/live";
import { SparkSvg } from "./Sparkline";

const schema = z.object({
  // auto: quota % if the agent reports one, else spend
  variant: z.enum(["auto", "cost", "quota"]).default("auto"),
  tool: z.string().default("claude-code").meta({ widget: "agent" }),
  label: z.string().default("CLAUDE · VTX"),
  // "auto" = the agent's own colour (agents.toml)
  accent: z.string().default("auto"),
  cost_alert: z.number().min(0).default(200),   // $ / day -> red hero
  quota_warn: z.number().min(0).max(100).default(75),
  quota_crit: z.number().min(0).max(100).default(80),
});
type P = z.infer<typeof schema>;

function Bar({ x, y, w, h, frac, col }: { x: number; y: number; w: number; h: number; frac: number; col: string }) {
  const fw = Math.round(w * Math.max(0, Math.min(1, frac)));
  return (
    <>
      <div style={{ position: "absolute", left: x, top: y, width: w, height: h, borderRadius: h / 2, background: "var(--track)" }} />
      {fw > 0 && <div style={{ position: "absolute", left: x, top: y, width: fw, height: h, borderRadius: h / 2, background: col }} />}
    </>
  );
}

/** One full-width account row — port of pil_legacy._tile. */
export const AccountCard = defineWidget<P>({
  type: "AccountCard",
  title: "Account card",
  category: "accounts",
  schema,
  defaults: { variant: "auto", tool: "claude-code", label: "CLAUDE · VTX", accent: "auto", cost_alert: 200, quota_warn: 75, quota_crit: 80 },
  defaultSize: { w: 304, h: 50 },
  minSize: { w: 160, h: 40 },
  Component: ({ item, props }) => {
    const st = useTool(props.tool);
    const accent = props.accent === "auto" ? accentOf(st) : color(props.accent);
    const variant = props.variant === "auto" ? (st && st.quota_pct !== null ? "quota" : "cost") : props.variant;
    const { w, h } = item;
    const dw = 96, dx = w - 14 - dw, hy = 8, dy = h - 17, subY = h - 21;

    let hero: React.ReactNode = null;
    let sub = "";
    let deco: React.ReactNode = null;

    if (!st) {
      hero = <span style={{ color: "var(--text-muted)" }}>—</span>;
      sub = "no data";
    } else if (variant === "cost") {
      const liveN = st.sessions.filter((s) => s.live).length;
      const heroCol = st.cost_usd >= props.cost_alert ? "var(--critical)" : "var(--text)";
      hero = <span style={{ color: heroCol }}>{money(st.cost_usd)}</span>;
      sub = `${liveN} live · ${st.sessions_today} today${st.cost_estimated ? " · est" : ""}`;
      deco = (
        <div style={{ position: "absolute", left: dx, top: dy }}>
          <SparkSvg w={dw} h={11} values={st.activity_24h} stroke={accent} />
        </div>
      );
    } else if (st.quota_pct !== null) {
      const q = st.quota_pct;
      const qcol = q >= props.quota_crit ? "var(--critical)" : q >= props.quota_warn ? "var(--warning)" : "var(--good)";
      hero = <span style={{ color: qcol }}>{`${Math.round(q)}%`}</span>;
      sub = `weekly${st.quota_resets_at ? ` · ${resetIn(st.quota_resets_at, nowSeconds())} left` : ""}`;
      deco = <Bar x={dx} y={dy + 4} w={dw} h={5} frac={q / 100} col={qcol} />;
    } else {
      hero = <span style={{ color: "var(--text-muted)", fontSize: 15 }}>{st.note || "—"}</span>;
      sub = "subscription";
      deco = <Bar x={dx} y={dy + 4} w={dw} h={5} frac={0} col={accent} />;
    }

    const heroTop = st && variant !== "cost" && st.quota_pct === null ? hy + 4 : hy;
    return (
      <>
        <div className="panel" />
        <div className="dot" style={{ left: 13, top: 11, width: 8, height: 8, background: accent }} />
        <div className="t ell" style={{ left: 28, top: 9, maxWidth: w / 2, fontSize: 11, fontWeight: 700, color: "var(--text-2)" }}>
          {props.label}
        </div>
        <div className="t r" style={{ right: 14, top: heroTop, fontSize: 22, fontWeight: 700 }}>{hero}</div>
        <div className="t ell" style={{ left: 28, top: subY, maxWidth: dx - 28 - 8, fontSize: 9, color: "var(--text-muted)" }}>
          {sub}
        </div>
        {deco}
      </>
    );
  },
});
