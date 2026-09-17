import { z } from "zod";

import { color } from "../lib/format";
import { defineWidget } from "../registry/types";

const schema = z.object({
  text: z.string().default("Label"),
  size: z.number().int().min(6).max(72).default(11),
  color: z.string().default("text2"),
  bold: z.boolean().default(false),
  mono: z.boolean().default(false),
  align: z.enum(["left", "center", "right"]).default("left"),
});

export const Text = defineWidget<z.infer<typeof schema>>({
  type: "Text",
  title: "Text",
  category: "primitives",
  schema,
  defaults: { text: "Label", size: 11, color: "text2", bold: false, mono: false, align: "left" },
  defaultSize: { w: 120, h: 16 },
  minSize: { w: 16, h: 8 },
  Component: ({ props }) => (
    <div
      className={`t ell${props.mono ? " mono" : ""}`}
      style={{
        left: 0, right: 0, top: 0, textAlign: props.align, fontSize: props.size,
        fontWeight: props.bold ? 700 : 400, color: color(props.color),
      }}
    >
      {props.text}
    </div>
  ),
});
