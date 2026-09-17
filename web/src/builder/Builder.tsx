import { useEffect, useRef } from "react";
import { useStore } from "zustand";

import { resetLayout } from "../api";
import { useBuilder, useIsDirty } from "../store/builder";
import { useLayoutStore } from "../store/layout";
import { useDevice, useLive } from "../store/live";
import { LayoutSchema, type Layout } from "../types/layout";
import { Canvas } from "./Canvas";
import { Palette } from "./Palette";
import { PropsPanel } from "./PropsPanel";
import { SettingsDrawer } from "./SettingsDrawer";
import "./builder.css";

const isTyping = () => {
  const el = document.activeElement as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
};

function DeviceChip() {
  const dev = useDevice();
  const connected = useLive((s) => s.connected);
  const ok = !!dev?.connected;
  return (
    <span className={`chip${ok ? " ok" : ""}`} title={dev?.last_error ?? ""}>
      <span className="chip-dot" />
      {!connected ? "server offline" : ok ? `device · ${dev?.renderer} · ${dev?.last_push_ms ?? "–"} ms` : "device absent"}
    </span>
  );
}

export function Builder() {
  const serverLayout = useLayoutStore((s) => s.layout);
  const saveToServer = useLayoutStore((s) => s.save);
  const b = useBuilder();
  const dirty = useIsDirty();
  const canUndo = useStore(useBuilder.temporal, (s) => s.pastStates.length > 0);
  const canRedo = useStore(useBuilder.temporal, (s) => s.futureStates.length > 0);
  const saving = useRef(false);

  // first load only: later server bumps come from our own saves
  useEffect(() => {
    if (serverLayout && !b.layout) b.load(serverLayout);
  }, [serverLayout, b]);

  const save = async () => {
    if (!b.layout || saving.current) return;
    saving.current = true;
    try {
      await saveToServer(b.layout);
      b.markSaved();
    } finally {
      saving.current = false;
    }
  };

  // live mode: autosave 500 ms after the last change
  useEffect(() => {
    if (!b.live || !dirty) return;
    const t = window.setTimeout(save, 500);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [b.live, dirty, b.layout]);

  const reset = async () => {
    if (!confirm("Reset the layout to the built-in default? Your saved layout will be replaced.")) return;
    const lay = LayoutSchema.parse(await resetLayout()) as Layout;
    b.load(lay);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === "z") { e.preventDefault(); (e.shiftKey ? useBuilder.temporal.getState().redo : useBuilder.temporal.getState().undo)(); return; }
      if (meta && e.key.toLowerCase() === "s") { e.preventDefault(); void save(); return; }
      if (isTyping()) return;
      const st = useBuilder.getState();
      const it = st.layout?.items.find((i) => i.id === st.selectedId);
      if (!it) return;
      if (meta && e.key.toLowerCase() === "d") { e.preventDefault(); st.duplicateItem(it.id); return; }
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); st.removeItem(it.id); return; }
      if (e.key === "[") { st.moveZ(it.id, e.shiftKey ? "back" : -1); return; }
      if (e.key === "]") { st.moveZ(it.id, e.shiftKey ? "front" : 1); return; }
      const step = e.shiftKey ? (st.layout?.grid ?? 8) : 1;
      const d: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
      if (d[e.key]) {
        e.preventDefault();
        const [dx, dy] = d[e.key];
        // nudge bypasses grid snapping so 1px moves are possible
        st.updateItem(it.id, { x: Math.max(0, Math.min(320 - it.w, it.x + dx)), y: Math.max(0, Math.min(480 - it.h, it.y + dy)) });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="builder">
      <header className="toolbar">
        <span className="brand">CODE DECK <span className="muted">builder</span></span>
        <span className="sep" />
        <button onClick={() => useBuilder.temporal.getState().undo()} disabled={!canUndo} title="undo (⌘Z)">undo</button>
        <button onClick={() => useBuilder.temporal.getState().redo()} disabled={!canRedo} title="redo (⇧⌘Z)">redo</button>
        <span className="sep" />
        <label className="inline">zoom
          <select value={b.zoom} onChange={(e) => b.setZoom(Number(e.target.value) as 1 | 2 | 3)}>
            <option value={1}>1×</option><option value={2}>2×</option><option value={3}>3×</option>
          </select>
        </label>
        <label className="inline"><input type="checkbox" checked={b.showGrid} onChange={b.toggleGrid} /> grid</label>
        <button onClick={() => b.setSettingsOpen(!b.settingsOpen)}>settings</button>
        <span className="grow" />
        <DeviceChip />
        <a className="link" href="/player" target="_blank" rel="noreferrer">player ↗</a>
        <span className="sep" />
        <label className="inline" title="save automatically after every change"><input type="checkbox" checked={b.live} onChange={(e) => b.setLive(e.target.checked)} /> live</label>
        <button onClick={reset} title="restore the built-in layout">reset</button>
        <button className={`primary${dirty ? " dirty" : ""}`} onClick={save} disabled={!dirty} title="push to device (⌘S)">
          {dirty ? "Save · push to device" : "Saved"}
        </button>
      </header>
      <Palette />
      <main className="center">
        <Canvas />
        {b.settingsOpen && <SettingsDrawer />}
      </main>
      <PropsPanel />
    </div>
  );
}
