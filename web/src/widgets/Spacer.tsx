import { z } from "zod";

import { defineWidget } from "../registry/types";

const schema = z.object({});

/** Invisible box — a layout aid in the builder (shows an outline there only). */
export const Spacer = defineWidget<z.infer<typeof schema>>({
  type: "Spacer",
  title: "Spacer",
  category: "primitives",
  schema,
  defaults: {},
  defaultSize: { w: 64, h: 16 },
  minSize: { w: 4, h: 4 },
  Component: () => null,
});
