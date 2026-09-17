import { create } from "zustand";

import { getLayout, putLayout } from "../api";
import { bumpDirty } from "../lib/dirty";
import { type Layout, LayoutSchema } from "../types/layout";

interface LayoutState {
  layout: Layout | null;
  error: string | null;
  fetch: () => Promise<void>;
  save: (layout: Layout) => Promise<void>;
  setLocal: (layout: Layout) => void; // builder edits before save
}

export const useLayoutStore = create<LayoutState>((set) => ({
  layout: null,
  error: null,
  fetch: async () => {
    try {
      const raw = await getLayout();
      const parsed = LayoutSchema.safeParse(raw);
      if (!parsed.success) {
        set({ error: parsed.error.message });
        return;
      }
      set({ layout: parsed.data, error: null });
      bumpDirty();
    } catch (e) {
      set({ error: String(e) });
    }
  },
  save: async (layout) => {
    const saved = LayoutSchema.parse(await putLayout(layout));
    set({ layout: saved, error: null });
    bumpDirty();
  },
  setLocal: (layout) => {
    set({ layout });
    bumpDirty();
  },
}));
