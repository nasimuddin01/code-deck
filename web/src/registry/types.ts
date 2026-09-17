import type { FC } from "react";
import type { z } from "zod";

import type { LayoutItem } from "../types/layout";

export type WidgetCategory = "accounts" | "sessions" | "system" | "time" | "primitives" | "overlay";

/** How the component library grows: one WidgetDef per widget, registered in
 * registry/index.ts. The builder derives its palette and props panel from
 * this; the player validates props against `schema` and falls back to
 * `defaults` so an old layout can never crash the device. */
export interface WidgetDef<P = Record<string, unknown>> {
  type: string;
  title: string;
  category: WidgetCategory;
  schema: z.ZodType<P>;
  defaults: P;
  defaultSize: { w: number; h: number };
  minSize: { w: number; h: number };
  /** only one instance per layout (e.g. the overlay) */
  singleton?: boolean;
  Component: FC<{ item: LayoutItem; props: P }>;
}

export function defineWidget<P>(def: WidgetDef<P>): WidgetDef<P> {
  return def;
}
