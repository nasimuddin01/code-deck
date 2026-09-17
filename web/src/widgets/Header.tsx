import { z } from "zod";

import { dateShort, hhmm } from "../lib/format";
import { useNow } from "../lib/useNow";
import { defineWidget } from "../registry/types";
import { useTools } from "../store/live";

const schema = z.object({
  title: z.string().default("CODE DECK"),
  show_clock: z.boolean().default(true),
  show_source: z.boolean().default(true),
});

export const Header = defineWidget<z.infer<typeof schema>>({
  type: "Header",
  title: "Header",
  category: "time",
  schema,
  defaults: { title: "CODE DECK", show_clock: true, show_source: true },
  defaultSize: { w: 320, h: 46 },
  minSize: { w: 120, h: 24 },
  Component: ({ item, props }) => {
    const tools = useTools();
    const now = useNow("minute");
    const live = tools.length > 0 && tools.every((t) => t.live);
    return (
      <>
        <div className="t" style={{ left: 10, top: 8, fontSize: 13, fontWeight: 700, color: "var(--text-2)" }}>
          {props.title}
        </div>
        {props.show_source && (
          <>
            <div className="dot" style={{ left: 10, top: 30, width: 6, height: 6, background: live ? "var(--good)" : "var(--warning)" }} />
            <div className="t" style={{ left: 21, top: 26, fontSize: 9, color: "var(--text-muted)" }}>
              {live ? "LIVE" : "DUMMY DATA"}
            </div>
          </>
        )}
        {props.show_clock && (
          <>
            <div className="t mono r" style={{ right: item.w - (item.w - 10), top: 6, fontSize: 20, color: "var(--text)" }}>
              {hhmm(now)}
            </div>
            <div className="t r" style={{ right: 10, top: 30, fontSize: 9, color: "var(--text-muted)" }}>
              {dateShort(now)}
            </div>
          </>
        )}
      </>
    );
  },
});
