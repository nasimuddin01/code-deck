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

/** The 320x480 screen. `device` = what headless Chromium screenshots.
 * `scale` renders it enlarged with a CSS transform — for embedding hosts
 * (the menu bar popover) so they never have to zoom the page themselves. */
export function Screen({ device = false, scale = 1 }: { device?: boolean; scale?: number }) {
  const layout = useLayoutStore((s) => s.layout);
  const style = scale !== 1 ? { transform: `scale(${scale})`, transformOrigin: "top left" } : undefined;
  return (
    <div className={`screen${device ? " device" : ""}`} id="screen" style={style}>
      {layout?.items.map((it) => <WidgetHost key={it.id} item={it} />)}
    </div>
  );
}

export function Player({ device }: { device: boolean }) {
  const haveLayout = useLayoutStore((s) => s.layout !== null);
  const haveSnapshot = useLive((s) => s.snapshot !== null);
  const scale = Math.max(0.5, Math.min(4, Number(new URLSearchParams(location.search).get("scale")) || 1));

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
    // the page is exactly the (scaled) screen: no margins, nothing scrollable
    document.body.classList.add("player");
    document.body.style.background = "var(--surface)";
    document.body.style.width = `${320 * scale}px`;
    document.body.style.height = `${480 * scale}px`;
  }, [device, scale]);

  return <Screen device={device} scale={scale} />;
}
