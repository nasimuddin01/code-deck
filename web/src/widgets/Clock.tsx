import { z } from "zod";

import { color, dateShort, hhmm, hhmmss } from "../lib/format";
import { useNow } from "../lib/useNow";
import { defineWidget } from "../registry/types";

const schema = z.object({
  variant: z.enum(["hhmm", "hhmm_ss", "date", "hhmm_date"]).default("hhmm"),
  size: z.number().int().min(8).max(96).default(20),
  align: z.enum(["left", "center", "right"]).default("right"),
  color: z.string().default("text"),
  mono: z.boolean().default(true),
});

export const Clock = defineWidget<z.infer<typeof schema>>({
  type: "Clock",
  title: "Clock / date",
  category: "time",
  schema,
  defaults: { variant: "hhmm", size: 20, align: "right", color: "text", mono: true },
  defaultSize: { w: 96, h: 24 },
  minSize: { w: 40, h: 12 },
  Component: ({ item, props }) => {
    const now = useNow(props.variant === "hhmm_ss" ? "second" : "minute");
    const main =
      props.variant === "date" ? dateShort(now) : props.variant === "hhmm_ss" ? hhmmss(now) : hhmm(now);
    const justify = props.align === "left" ? "flex-start" : props.align === "center" ? "center" : "flex-end";
    return (
      <div
        style={{
          position: "absolute", inset: 0, display: "flex", flexDirection: "column",
          alignItems: justify, justifyContent: "flex-start", gap: 4,
          color: color(props.color), fontFamily: props.mono ? "var(--font-mono)" : undefined,
        }}
      >
        <div style={{ fontSize: props.size, whiteSpace: "nowrap" }}>{main}</div>
        {props.variant === "hhmm_date" && (
          <div style={{ fontSize: Math.max(8, Math.round(props.size * 0.45)), color: "var(--text-muted)", fontFamily: "var(--font-sans)" }}>
            {dateShort(now)}
          </div>
        )}
        <span style={{ display: "none" }}>{item.id}</span>
      </div>
    );
  },
});
