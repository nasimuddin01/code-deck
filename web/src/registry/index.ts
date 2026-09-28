import type { WidgetDef } from "./types";
import { AccountCard } from "../widgets/AccountCard";
import { Clock } from "../widgets/Clock";
import { Divider } from "../widgets/Divider";
import { Footer } from "../widgets/Footer";
import { Header } from "../widgets/Header";
import { NeedsYouOverlay } from "../widgets/NeedsYouOverlay";
import { Photo } from "../widgets/Photo";
import { SessionList } from "../widgets/SessionList";
import { Slideshow } from "../widgets/Slideshow";
import { Spacer } from "../widgets/Spacer";
import { Sparkline } from "../widgets/Sparkline";
import { SystemTile } from "../widgets/SystemTile";
import { Text } from "../widgets/Text";
import { Weather } from "../widgets/Weather";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const all: WidgetDef<any>[] = [
  Header, Clock, AccountCard, Sparkline, SessionList, Footer,
  SystemTile, Weather, Photo, Slideshow, Text, Divider, Spacer, NeedsYouOverlay,
];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const registry: Record<string, WidgetDef<any>> = Object.fromEntries(all.map((d) => [d.type, d]));

export const categories: { key: WidgetDef["category"]; title: string }[] = [
  { key: "accounts", title: "Accounts" },
  { key: "sessions", title: "Sessions" },
  { key: "system", title: "System" },
  { key: "time", title: "Time" },
  { key: "media", title: "Photos & weather" },
  { key: "primitives", title: "Primitives" },
  { key: "overlay", title: "Overlay" },
];

/** Validate props against the widget schema; fall back to defaults. */
export function resolveProps<P>(def: WidgetDef<P>, raw: unknown): P {
  const r = def.schema.safeParse({ ...(def.defaults as object), ...((raw as object) ?? {}) });
  return r.success ? r.data : def.defaults;
}
