import { temporal } from "zundo";
import { create } from "zustand";

import { registry } from "../registry";
import { type Layout, type LayoutItem, SCREEN, type Settings } from "../types/layout";

export type Zoom = 1 | 2 | 3;
export interface Rect { x: number; y: number; w: number; h: number }

export const snap = (v: number, grid: number) => Math.round(v / grid) * grid;

/** Clamp a rect to the screen and the widget's minimum size. `grid` snaps the
 * position; `snapSize` additionally snaps width/height (resizes only — a move
 * must never change a widget's size). grid=1 means no snapping. */
export function normalizeRect(type: string, r: Rect, grid: number, snapSize = false): Rect {
  const min = registry[type]?.minSize ?? { w: 8, h: 8 };
  let w = Math.max(min.w, snapSize ? snap(r.w, grid) : Math.round(r.w));
  let h = Math.max(min.h, snapSize ? snap(r.h, grid) : Math.round(r.h));
  w = Math.min(w, SCREEN.w);
  h = Math.min(h, SCREEN.h);
  const x = Math.min(Math.max(0, snap(r.x, grid)), SCREEN.w - w);
  const y = Math.min(Math.max(0, snap(r.y, grid)), SCREEN.h - h);
  return { x, y, w, h };
}

const newId = (type: string, taken: Set<string>) => {
  const base = type.replace(/[^a-z0-9]/gi, "").toLowerCase();
  for (let i = 1; ; i++) {
    const id = `${base}-${i}`;
    if (!taken.has(id)) return id;
  }
};

interface BuilderState {
  layout: Layout | null;       // the draft being edited
  savedJson: string;           // last saved/loaded draft, for the unsaved indicator
  selectedId: string | null;
  zoom: Zoom;
  showGrid: boolean;
  live: boolean;               // autosave on every change
  settingsOpen: boolean;
  paletteDrag: { type: string; x: number; y: number } | null;

  load: (layout: Layout) => void;
  markSaved: () => void;
  select: (id: string | null) => void;
  setZoom: (z: Zoom) => void;
  toggleGrid: () => void;
  setLive: (v: boolean) => void;
  setSettingsOpen: (v: boolean) => void;
  setPaletteDrag: (d: BuilderState["paletteDrag"]) => void;

  updateItem: (id: string, patch: Partial<LayoutItem>) => void;
  setRect: (id: string, r: Rect) => void;
  updateProps: (id: string, props: Record<string, unknown>) => void;
  addItem: (type: string, x: number, y: number) => string | null;
  removeItem: (id: string) => void;
  duplicateItem: (id: string) => void;
  moveZ: (id: string, dir: 1 | -1 | "front" | "back") => void;
  updateSettings: (patch: Partial<Settings>) => void;
}

const mutate = (layout: Layout, id: string, f: (it: LayoutItem) => LayoutItem): Layout => ({
  ...layout,
  items: layout.items.map((it) => (it.id === id ? f(it) : it)),
});

export const useBuilder = create<BuilderState>()(
  temporal(
    (set, get) => ({
      layout: null,
      savedJson: "",
      selectedId: null,
      zoom: 2,
      showGrid: true,
      live: false,
      settingsOpen: false,
      paletteDrag: null,

      load: (layout) => {
        set({ layout, savedJson: JSON.stringify(layout), selectedId: null });
        useBuilder.temporal.getState().clear();
      },
      markSaved: () => set({ savedJson: JSON.stringify(get().layout) }),
      select: (selectedId) => set({ selectedId }),
      setZoom: (zoom) => set({ zoom }),
      toggleGrid: () => set({ showGrid: !get().showGrid }),
      setLive: (live) => set({ live }),
      setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
      setPaletteDrag: (paletteDrag) => set({ paletteDrag }),

      updateItem: (id, patch) => {
        const l = get().layout;
        if (l) set({ layout: mutate(l, id, (it) => ({ ...it, ...patch })) });
      },
      setRect: (id, r) => {
        const l = get().layout;
        if (!l) return;
        const it = l.items.find((i) => i.id === id);
        if (!it || it.locked) return;
        // callers (canvas drags, inspector inputs) decide about snapping; here we only clamp
        set({ layout: mutate(l, id, (i) => ({ ...i, ...normalizeRect(i.type, r, 1) })) });
      },
      updateProps: (id, props) => {
        const l = get().layout;
        if (l) set({ layout: mutate(l, id, (it) => ({ ...it, props: { ...it.props, ...props } })) });
      },
      addItem: (type, x, y) => {
        const l = get().layout;
        const def = registry[type];
        if (!l || !def) return null;
        if (def.singleton && l.items.some((i) => i.type === type)) return null;
        const id = newId(type, new Set(l.items.map((i) => i.id)));
        const rect = normalizeRect(type, { x, y, ...def.defaultSize }, l.grid);
        const item: LayoutItem = { id, type, ...rect, props: { ...def.defaults }, locked: false, hidden: false };
        set({ layout: { ...l, items: [...l.items, item] }, selectedId: id });
        return id;
      },
      removeItem: (id) => {
        const l = get().layout;
        if (!l) return;
        set({ layout: { ...l, items: l.items.filter((i) => i.id !== id) },
              selectedId: get().selectedId === id ? null : get().selectedId });
      },
      duplicateItem: (id) => {
        const l = get().layout;
        const src = l?.items.find((i) => i.id === id);
        if (!l || !src) return;
        const def = registry[src.type];
        if (def?.singleton) return;
        const nid = newId(src.type, new Set(l.items.map((i) => i.id)));
        const rect = normalizeRect(src.type, { x: src.x + l.grid, y: src.y + l.grid, w: src.w, h: src.h }, l.grid);
        set({ layout: { ...l, items: [...l.items, { ...src, id: nid, ...rect, props: { ...src.props } }] }, selectedId: nid });
      },
      moveZ: (id, dir) => {
        const l = get().layout;
        if (!l) return;
        const items = [...l.items];
        const i = items.findIndex((it) => it.id === id);
        if (i < 0) return;
        const [it] = items.splice(i, 1);
        const j = dir === "front" ? items.length : dir === "back" ? 0
          : Math.max(0, Math.min(items.length, i + dir));
        items.splice(j, 0, it);
        set({ layout: { ...l, items } });
      },
      updateSettings: (patch) => {
        const l = get().layout;
        if (l) set({ layout: { ...l, settings: { ...l.settings, ...patch } } });
      },
    }),
    {
      // undo/redo tracks the draft only, not selection/zoom
      partialize: (s) => ({ layout: s.layout }),
      equality: (a, b) => a.layout === b.layout,
      limit: 200,
    },
  ),
);

export const useIsDirty = () => useBuilder((s) => s.layout !== null && JSON.stringify(s.layout) !== s.savedJson);
export const useSelectedItem = () =>
  useBuilder((s) => (s.layout && s.selectedId ? s.layout.items.find((i) => i.id === s.selectedId) ?? null : null));
