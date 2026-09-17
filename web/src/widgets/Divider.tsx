import { z } from "zod";

import { color } from "../lib/format";
import { defineWidget } from "../registry/types";

const schema = z.object({
  color: z.string().default("var(--divider)"),
  thickness: z.number().int().min(1).max(8).default(1),
  vertical: z.boolean().default(false),
});

export const Divider = defineWidget<z.infer<typeof schema>>({
  type: "Divider",
  title: "Divider",
  category: "primitives",
  schema,
  defaults: { color: "var(--divider)", thickness: 1, vertical: false },
  defaultSize: { w: 300, h: 8 },
  minSize: { w: 1, h: 1 },
  Component: ({ item, props }) => {
    const c = color(props.color);
    const style = props.vertical
      ? { left: Math.floor((item.w - props.thickness) / 2), top: 0, width: props.thickness, height: item.h }
      : { left: 0, top: Math.floor((item.h - props.thickness) / 2), width: item.w, height: props.thickness };
    return <div style={{ position: "absolute", background: c, ...style }} />;
  },
});
