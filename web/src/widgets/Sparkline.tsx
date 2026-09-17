import { z } from "zod";

import { color } from "../lib/format";
import { defineWidget } from "../registry/types";
import { useSystem, useTool } from "../store/live";
import type { SystemMetric } from "../types/state";

/** Pure SVG sparkline, identical geometry to the PIL one: baseline track,
 * 2px stroke, values scaled to max. */
export function SparkSvg({ w, h, values, stroke }: { w: number; h: number; values: number[]; stroke: string }) {
  const top = Math.max(0, ...values);
  const n = values.length;
  const pts = n > 1 && top > 0
    ? values.map((v, i) => `${(i * w) / (n - 1)},${h - (v / top) * (h - 2)}`).join(" ")
    : "";
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ position: "static" }}>
      <line x1={0} y1={h - 0.5} x2={w} y2={h - 0.5} stroke="var(--track)" strokeWidth={1} />
      {pts && <polyline points={pts} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
    </svg>
  );
}

const schema = z.object({
  source: z.string().default("tool:Claude Code"), // "tool:<name>" | "system:<metric>"
  color: z.string().default("orange"),
});

export function useSeries(source: string): number[] {
  const [kind, key] = source.split(":", 2);
  const tool = useTool(kind === "tool" ? key : "__none__");
  const sys = useSystem();
  if (kind === "tool") return tool?.activity_24h ?? [];
  if (kind === "system" && sys) return sys.history[key as SystemMetric] ?? [];
  return [];
}

export const Sparkline = defineWidget<z.infer<typeof schema>>({
  type: "Sparkline",
  title: "Sparkline",
  category: "system",
  schema,
  defaults: { source: "tool:Claude Code", color: "orange" },
  defaultSize: { w: 96, h: 16 },
  minSize: { w: 24, h: 8 },
  Component: ({ item, props }) => {
    const values = useSeries(props.source);
    return (
      <div style={{ position: "absolute", inset: 0 }}>
        <SparkSvg w={item.w} h={item.h} values={values} stroke={color(props.color)} />
      </div>
    );
  },
});
