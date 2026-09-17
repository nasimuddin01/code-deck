import { useCallback, useRef, useState } from "react";

import { WidgetHost } from "../player/Player";
import { registry } from "../registry";
import { normalizeRect, type Rect, useBuilder } from "../store/builder";
import { type LayoutItem, SCREEN } from "../types/layout";

type Handle = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
const HANDLES: Handle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const CURSOR: Record<Handle, string> = {
  n: "ns-resize", s: "ns-resize", e: "ew-resize", w: "ew-resize",
  ne: "nesw-resize", sw: "nesw-resize", nw: "nwse-resize", se: "nwse-resize",
};

interface Drag {
  mode: "move" | "resize";
  id: string;
  handle?: Handle;
  startX: number;
  startY: number;
  orig: Rect;
}

function resized(orig: Rect, handle: Handle, dx: number, dy: number): Rect {
  let { x, y, w, h } = orig;
  if (handle.includes("e")) w = orig.w + dx;
  if (handle.includes("s")) h = orig.h + dy;
  if (handle.includes("w")) { x = orig.x + dx; w = orig.w - dx; }
  if (handle.includes("n")) { y = orig.y + dy; h = orig.h - dy; }
  return { x, y, w, h };
}

/** The editable device screen: the real widgets underneath (pointer-events
 * off), a hit layer on top for selection, move and resize. Drags keep their
 * in-progress rect in local state and commit once on release, so each drag is
 * a single undo step. */
export function Canvas() {
  const layout = useBuilder((s) => s.layout);
  const zoom = useBuilder((s) => s.zoom);
  const showGrid = useBuilder((s) => s.showGrid);
  const selectedId = useBuilder((s) => s.selectedId);
  const select = useBuilder((s) => s.select);
  const setRect = useBuilder((s) => s.setRect);
  const paletteDrag = useBuilder((s) => s.paletteDrag);

  const drag = useRef<Drag | null>(null);
  const [preview, setPreview] = useState<{ id: string; rect: Rect } | null>(null);

  const begin = useCallback((e: React.PointerEvent, item: LayoutItem, mode: Drag["mode"], handle?: Handle) => {
    if (item.locked) { select(item.id); return; }
    e.stopPropagation();
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    select(item.id);
    drag.current = { mode, id: item.id, handle, startX: e.clientX, startY: e.clientY,
                     orig: { x: item.x, y: item.y, w: item.w, h: item.h } };
  }, [select]);

  const move = useCallback((e: React.PointerEvent) => {
    const d = drag.current;
    if (!d || !layout) return;
    const dx = (e.clientX - d.startX) / zoom;
    const dy = (e.clientY - d.startY) / zoom;
    const item = layout.items.find((i) => i.id === d.id);
    if (!item) return;
    const raw = d.mode === "move"
      ? { ...d.orig, x: d.orig.x + dx, y: d.orig.y + dy }
      : resized(d.orig, d.handle!, dx, dy);
    setPreview({ id: d.id, rect: normalizeRect(item.type, raw, layout.grid, d.mode === "resize") });
  }, [layout, zoom]);

  const end = useCallback(() => {
    const d = drag.current;
    if (d && preview && preview.id === d.id) setRect(d.id, preview.rect);
    drag.current = null;
    setPreview(null);
  }, [preview, setRect]);

  if (!layout) return <div className="canvas-wrap"><div className="hint">loading layout…</div></div>;

  const W = SCREEN.w * zoom, H = SCREEN.h * zoom;
  const items = layout.items.map((it) => (preview && preview.id === it.id ? { ...it, ...preview.rect } : it));

  return (
    <div className="canvas-wrap" onPointerDown={() => select(null)}>
      <div className="bezel" style={{ padding: 18 }}>
        <div id="stage" className="stage" style={{ width: W, height: H }} onPointerDown={(e) => e.stopPropagation()}>
          <div className="screen" style={{ transform: `scale(${zoom})`, transformOrigin: "top left", pointerEvents: "none" }}>
            {items.map((it) => <WidgetHost key={it.id} item={it} />)}
          </div>
          {showGrid && (
            <div className="grid" style={{ backgroundSize: `${layout.grid * zoom}px ${layout.grid * zoom}px` }} />
          )}
          <div className="hit-layer" onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
            {items.map((it) => {
              const sel = it.id === selectedId;
              const def = registry[it.type];
              return (
                <div
                  key={it.id}
                  className={`hit${sel ? " selected" : ""}${it.locked ? " locked" : ""}${it.hidden ? " hidden" : ""}${def?.category === "overlay" ? " overlay" : ""}`}
                  style={{ left: it.x * zoom, top: it.y * zoom, width: it.w * zoom, height: it.h * zoom }}
                  title={`${def?.title ?? it.type} · ${it.id}`}
                  onPointerDown={(e) => begin(e, it, "move")}
                >
                  {(it.type === "Spacer" || it.hidden) && <span className="ghost-label">{def?.title ?? it.type}</span>}
                  {sel && !it.locked && HANDLES.map((hd) => (
                    <div
                      key={hd}
                      className={`handle ${hd}`}
                      style={{ cursor: CURSOR[hd] }}
                      onPointerDown={(e) => begin(e, it, "resize", hd)}
                    />
                  ))}
                </div>
              );
            })}
          </div>
          {paletteDrag && <div className="drop-hint">drop to add {registry[paletteDrag.type]?.title}</div>}
        </div>
      </div>
      {preview && (
        <div className="coords">{preview.rect.x},{preview.rect.y} · {preview.rect.w}×{preview.rect.h}</div>
      )}
    </div>
  );
}
