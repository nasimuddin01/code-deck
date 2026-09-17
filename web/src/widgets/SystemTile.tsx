import { z } from "zod";

import { bytesPerSec, color, gb } from "../lib/format";
import { defineWidget } from "../registry/types";
import { useSystem } from "../store/live";
import { SparkSvg } from "./Sparkline";

const METRICS = ["cpu", "mem", "disk", "net_up", "net_down"] as const;
const schema = z.object({
  metric: z.enum(METRICS).default("cpu"),
  label: z.string().default(""),
  accent: z.string().default("text2"),
  warn: z.number().min(0).max(100).default(80), // % -> warning colour (cpu/mem/disk)
});
type P = z.infer<typeof schema>;

const LABEL: Record<P["metric"], string> = { cpu: "CPU", mem: "MEMORY", disk: "DISK", net_up: "NET ↑", net_down: "NET ↓" };

export const SystemTile = defineWidget<P>({
  type: "SystemTile",
  title: "System tile",
  category: "system",
  schema,
  defaults: { metric: "cpu", label: "", accent: "text2", warn: 80 },
  defaultSize: { w: 148, h: 50 },
  minSize: { w: 96, h: 36 },
  Component: ({ item, props }) => {
    const sys = useSystem();
    const { w, h } = item;
    let hero = "—", sub = "", pct: number | null = null, series: number[] = [];
    if (sys) {
      switch (props.metric) {
        case "cpu": pct = sys.cpu_pct; hero = `${Math.round(pct)}%`; series = sys.history.cpu_pct; break;
        case "mem": pct = sys.mem_pct; hero = `${Math.round(pct)}%`; sub = `${gb(sys.mem_used)} / ${gb(sys.mem_total)}`; series = sys.history.mem_pct; break;
        case "disk": pct = sys.disk_pct; hero = `${Math.round(pct)}%`; sub = `${gb(sys.disk_used)} / ${gb(sys.disk_total)}`; break;
        case "net_up": hero = bytesPerSec(sys.net_up_bps); series = sys.history.net_up_bps; break;
        case "net_down": hero = bytesPerSec(sys.net_down_bps); series = sys.history.net_down_bps; break;
      }
    }
    const heroCol = pct !== null && pct >= props.warn ? "var(--warning)" : "var(--text)";
    const accent = color(props.accent);
    // left column: label / hero / sub; right: sparkline, vertically centred,
    // sized so a "1.2 MB/s" hero never runs under it
    const dw = Math.max(40, Math.min(72, w - 100)), dx = w - 12 - dw;
    const sh = 12, sy = Math.round((h - sh) / 2) + 4;
    return (
      <>
        <div className="panel" />
        <div className="t ell" style={{ left: 12, top: 7, maxWidth: dx - 16, fontSize: 9, fontWeight: 700, color: "var(--text-muted)" }}>
          {props.label || LABEL[props.metric]}
        </div>
        <div className="t ell" style={{ left: 12, top: 19, maxWidth: dx - 16, fontSize: 17, fontWeight: 700, color: heroCol }}>{hero}</div>
        {sub && <div className="t ell" style={{ left: 12, top: h - 12, maxWidth: dx - 16, fontSize: 8, color: "var(--text-muted)" }}>{sub}</div>}
        {series.length > 1 && (
          <div style={{ position: "absolute", left: dx, top: sy }}>
            <SparkSvg w={dw} h={sh} values={series} stroke={accent} />
          </div>
        )}
      </>
    );
  },
});
