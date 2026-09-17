import { useEffect } from "react";

import { setReady } from "../lib/dirty";
import { registry, resolveProps } from "../registry";
import { useLayoutStore } from "../store/layout";
import { useLive } from "../store/live";
import type { LayoutItem } from "../types/layout";

export function WidgetHost({ item }: { item: LayoutItem }) {
  const def = registry[item.type];
  if (!def || item.hidden) return null;
  const props = resolveProps(def, item.props);
  const C = def.Component;
  return (
    <div className="w" data-id={item.id} style={{ left: item.x, top: item.y, width: item.w, height: item.h }}>
      <C item={item} props={props} />
    </div>
  );
}

/** The 320x480 screen. `device` = what headless Chromium screenshots. */
export function Screen({ device = false }: { device?: boolean }) {
  const layout = useLayoutStore((s) => s.layout);
  return (
    <div className={`screen${device ? " device" : ""}`} id="screen">
      {layout?.items.map((it) => <WidgetHost key={it.id} item={it} />)}
    </div>
  );
}

export function Player({ device }: { device: boolean }) {
  const haveLayout = useLayoutStore((s) => s.layout !== null);
  const haveSnapshot = useLive((s) => s.snapshot !== null);

  // ready = fonts loaded + first snapshot + layout + two painted frames; the
  // frame pipeline waits for this before its first screenshot
  useEffect(() => {
    if (!haveLayout || !haveSnapshot) return;
    let cancelled = false;
    document.fonts.ready.then(() => {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (!cancelled) setReady();
      }));
    });
    return () => {
      cancelled = true;
    };
  }, [haveLayout, haveSnapshot]);

  useEffect(() => {
    if (device) document.body.classList.add("device");
    document.body.style.background = "var(--surface)";
  }, [device]);

  return <Screen device={device} />;
}
