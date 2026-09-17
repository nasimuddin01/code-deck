import type { Layout } from "./types/layout";
import type { Snapshot } from "./types/state";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return (await res.json()) as T;
}

export const getState = () => fetch("/api/state").then((r) => json<Snapshot>(r));
export const getLayout = () => fetch("/api/layout").then((r) => json<unknown>(r));
export const putLayout = (layout: Layout) =>
  fetch("/api/layout", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(layout),
  }).then((r) => json<unknown>(r));
export const resetLayout = () => fetch("/api/layout/reset", { method: "POST" }).then((r) => json<unknown>(r));
export const setBrightness = (value: number) =>
  fetch("/api/device/brightness", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ value }),
  }).then((r) => json<{ brightness: number }>(r));
