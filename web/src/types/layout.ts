import { z } from "zod";

// Mirrors server/layout.py. z-order = array order.
export const LayoutItemSchema = z.object({
  id: z.string().min(1),
  type: z.string().min(1),
  x: z.number().int().min(0),
  y: z.number().int().min(0),
  w: z.number().int().min(1),
  h: z.number().int().min(1),
  props: z.record(z.string(), z.unknown()).default({}),
  locked: z.boolean().default(false),
  hidden: z.boolean().default(false),
});

export const SettingsSchema = z.object({
  overlay_enabled: z.boolean().default(true),
  overlay_seconds: z.number().positive().max(120).default(10),
  brightness: z.number().int().min(0).max(255).default(39),
  refresh_seconds: z.number().min(1).max(300).default(10),
});

export const LayoutSchema = z.object({
  schema_version: z.literal(1),
  screen: z.object({ w: z.number().int(), h: z.number().int() }).default({ w: 320, h: 480 }),
  grid: z.number().int().min(1).default(8),
  items: z.array(LayoutItemSchema),
  settings: SettingsSchema.prefault({}), // zod 4: fill nested defaults from an empty object
});

export type LayoutItem = z.infer<typeof LayoutItemSchema>;
export type Settings = z.infer<typeof SettingsSchema>;
export type Layout = z.infer<typeof LayoutSchema>;

export const SCREEN = { w: 320, h: 480 } as const;
