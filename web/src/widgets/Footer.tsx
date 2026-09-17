import { z } from "zod";

import { fmtTokens, hhmmss, money } from "../lib/format";
import { useNow } from "../lib/useNow";
import { defineWidget } from "../registry/types";
import { useTools } from "../store/live";

const schema = z.object({
  show_updated: z.boolean().default(true),
});

export const Footer = defineWidget<z.infer<typeof schema>>({
  type: "Footer",
  title: "Footer totals",
  category: "accounts",
  schema,
  defaults: { show_updated: true },
  defaultSize: { w: 320, h: 18 },
  minSize: { w: 160, h: 14 },
  Component: ({ props }) => {
    const tools = useTools();
    const now = useNow(props.show_updated ? "second" : "minute");
    const cost = tools.reduce((a, t) => a + t.cost_usd, 0);
    const tok = tools.reduce((a, t) => a + t.tokens_in + t.tokens_out, 0);
    return (
      <>
        <div className="t mono" style={{ left: 10, top: 4, fontSize: 11, color: "var(--text-2)" }}>{money(cost)}</div>
        <div className="t mono" style={{ left: 92, top: 4, fontSize: 11, color: "var(--text-2)" }}>{fmtTokens(tok)} tok</div>
        {props.show_updated && (
          <div className="t r" style={{ right: 10, top: 4, fontSize: 8, color: "var(--text-muted)" }}>upd {hhmmss(now)}</div>
        )}
      </>
    );
  },
});
