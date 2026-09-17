import { useEffect } from "react";

import { categories, registry } from "../registry";
import { snap, useBuilder } from "../store/builder";
import { SCREEN } from "../types/layout";

/** Widget library. Drag an entry onto the device to place it (a ghost follows
 * the pointer); clicking adds it at the first free grid slot. */
export function Palette() {
  const layout = useBuilder((s) => s.layout);
  const zoom = useBuilder((s) => s.zoom);
  const addItem = useBuilder((s) => s.addItem);
  const paletteDrag = useBuilder((s) => s.paletteDrag);
  const setPaletteDrag = useBuilder((s) => s.setPaletteDrag);

  useEffect(() => {
    if (!paletteDrag) return;
    const onMove = (e: PointerEvent) => setPaletteDrag({ ...paletteDrag, x: e.clientX, y: e.clientY });
    const onUp = (e: PointerEvent) => {
      const stage = document.getElementById("stage");
      const def = registry[paletteDrag.type];
      if (stage && def && layout) {
        const r = stage.getBoundingClientRect();
        if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) {
          const x = (e.clientX - r.left) / zoom - def.defaultSize.w / 2;
          const y = (e.clientY - r.top) / zoom - def.defaultSize.h / 2;
          addItem(paletteDrag.type, snap(x, layout.grid), snap(y, layout.grid));
        }
      }
      setPaletteDrag(null);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [paletteDrag, layout, zoom, addItem, setPaletteDrag]);

  const clickAdd = (type: string) => {
    if (!layout) return;
    const def = registry[type];
    // first grid row where the widget fits without overlapping anything
    const g = layout.grid;
    for (let y = 0; y + def.defaultSize.h <= SCREEN.h; y += g) {
      for (let x = 0; x + def.defaultSize.w <= SCREEN.w; x += g) {
        const hit = layout.items.some((it) => !it.hidden && x < it.x + it.w && x + def.defaultSize.w > it.x && y < it.y + it.h && y + def.defaultSize.h > it.y);
        if (!hit) { addItem(type, x, y); return; }
      }
    }
    addItem(type, 0, 0);
  };

  return (
    <aside className="pane palette">
      <div className="pane-title">Widgets</div>
      {categories.map((c) => {
        const defs = Object.values(registry).filter((d) => d.category === c.key);
        if (!defs.length) return null;
        return (
          <div key={c.key} className="pal-group">
            <div className="pal-cat">{c.title}</div>
            {defs.map((d) => {
              const disabled = !!d.singleton && !!layout?.items.some((i) => i.type === d.type);
              return (
                <div
                  key={d.type}
                  className={`pal-item${disabled ? " disabled" : ""}`}
                  title={disabled ? "already on the layout" : "drag onto the screen, or click to add"}
                  onPointerDown={(e) => {
                    if (disabled) return;
                    e.preventDefault();
                    setPaletteDrag({ type: d.type, x: e.clientX, y: e.clientY });
                  }}
                  onClick={() => !disabled && !paletteDrag && clickAdd(d.type)}
                >
                  <span className="pal-name">{d.title}</span>
                  <span className="pal-size">{d.defaultSize.w}×{d.defaultSize.h}</span>
                </div>
              );
            })}
          </div>
        );
      })}
      {paletteDrag && (
        <div className="pal-ghost" style={{ left: paletteDrag.x + 12, top: paletteDrag.y + 12 }}>
          {registry[paletteDrag.type]?.title}
        </div>
      )}
    </aside>
  );
}
