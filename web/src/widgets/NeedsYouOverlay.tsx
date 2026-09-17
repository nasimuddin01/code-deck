import { useEffect, useState } from "react";
import { z } from "zod";

import { bumpDirty } from "../lib/dirty";
import { nowSeconds } from "../lib/useNow";
import { defineWidget } from "../registry/types";
import { useOverlay } from "../store/live";

const schema = z.object({
  fade_card: z.boolean().default(true),
});

/** Full-screen attention banner. The server decides when it starts
 * (`attention.overlay`); we animate from `started_at`. Only the card fades
 * (a CSS opacity transition) — the scrim is constant, so after the first
 * full-frame push every later push is just the card's rectangle. */
export const NeedsYouOverlay = defineWidget<z.infer<typeof schema>>({
  type: "NeedsYouOverlay",
  title: "Needs-you overlay",
  category: "overlay",
  schema,
  defaults: { fade_card: true },
  defaultSize: { w: 320, h: 480 },
  minSize: { w: 320, h: 480 },
  singleton: true,
  Component: ({ props }) => {
    const ov = useOverlay();
    const [, force] = useState(0);
    const active = !!ov && nowSeconds() - ov.started_at < ov.seconds;

    // re-check expiry + keep the frame dirty while animating
    useEffect(() => {
      if (!active) return;
      let raf = 0;
      const loop = () => {
        bumpDirty();
        force((n) => n + 1);
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
      return () => cancelAnimationFrame(raf);
    }, [active, ov?.started_at]);

    if (!ov || !active) return null;
    const elapsed = nowSeconds() - ov.started_at;
    const opacity = props.fade_card ? Math.max(0, 1 - elapsed / ov.seconds) : 1;
    const title = ov.kind === "idle" ? "TURN ENDED" : "NEEDS YOU";
    const cw = 250, ch = 128, cx = (320 - cw) / 2, cy = (480 - ch) / 2;
    return (
      <div style={{ position: "absolute", inset: 0, background: "rgba(10,10,9,0.647)" }}>
        <div
          style={{
            position: "absolute", left: cx, top: cy, width: cw, height: ch, opacity,
            background: "#242422", borderRadius: 16, border: "3px solid var(--attention)",
          }}
        >
          <div className="dot" style={{ left: cw / 2 - 5 - 3, top: 26 - 3, width: 10, height: 10, background: "var(--attention)" }} />
          <div className="t" style={{ left: 0, right: 0, top: 60 - 3, transform: "translateY(-50%)", textAlign: "center", fontSize: 24, fontWeight: 700, color: "var(--attention)" }}>
            {title}
          </div>
          <div className="t ell" style={{ left: 14, right: 14, top: 96 - 3, transform: "translateY(-50%)", textAlign: "center", fontSize: 15, fontWeight: 700, color: "var(--text)" }}>
            {ov.label || "session"}
          </div>
        </div>
      </div>
    );
  },
});
