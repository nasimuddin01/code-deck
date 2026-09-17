import { useEffect, useState } from "react";

import { bumpDirty } from "./dirty";

let frozen: number | null = null;
// ?now=<epoch seconds>&freeze=1 pins the clock for golden-image tests
if (typeof location !== "undefined") {
  const p = new URLSearchParams(location.search);
  const n = p.get("now");
  if (n && p.get("freeze") === "1") frozen = Number(n) * 1000;
}

/** Current time, re-rendering (and marking the frame dirty) once per unit. */
export function useNow(unit: "second" | "minute" = "minute"): Date {
  const [now, setNow] = useState(() => new Date(frozen ?? Date.now()));
  useEffect(() => {
    if (frozen !== null) return;
    let timer: number;
    const period = unit === "second" ? 1000 : 60_000;
    const tick = () => {
      setNow(new Date());
      bumpDirty();
      timer = window.setTimeout(tick, period - (Date.now() % period) + 5);
    };
    timer = window.setTimeout(tick, period - (Date.now() % period) + 5);
    return () => window.clearTimeout(timer);
  }, [unit]);
  return now;
}

export function nowSeconds(): number {
  return (frozen ?? Date.now()) / 1000;
}
