import { describe, expect, it } from "vitest";

import defaultLayout from "../../../server/src/code_deck/layouts/default.json";
import { LayoutSchema, SCREEN } from "../types/layout";
import { registry, resolveProps } from "./index";

describe("widget registry", () => {
  it("every widget's defaults satisfy its own schema", () => {
    for (const def of Object.values(registry)) {
      expect(def.schema.safeParse(def.defaults).success, def.type).toBe(true);
      expect(def.defaultSize.w).toBeGreaterThanOrEqual(def.minSize.w);
      expect(def.defaultSize.h).toBeGreaterThanOrEqual(def.minSize.h);
    }
  });

  it("falls back to defaults on invalid props", () => {
    const def = registry.AccountCard;
    expect(resolveProps(def, { variant: "bogus" })).toEqual(def.defaults);
    expect(resolveProps(def, { label: "X" }).label).toBe("X");
  });
});

describe("default layout", () => {
  it("validates and only uses registered widgets inside the screen", () => {
    const lay = LayoutSchema.parse(defaultLayout);
    for (const it of lay.items) {
      expect(registry[it.type], `unknown widget ${it.type}`).toBeDefined();
      expect(it.x + it.w).toBeLessThanOrEqual(SCREEN.w);
      expect(it.y + it.h).toBeLessThanOrEqual(SCREEN.h);
      expect(registry[it.type].schema.safeParse({ ...registry[it.type].defaults, ...it.props }).success, it.id).toBe(true);
    }
    const singles = lay.items.filter((i) => registry[i.type].singleton).map((i) => i.type);
    expect(new Set(singles).size).toBe(singles.length);
  });
});
