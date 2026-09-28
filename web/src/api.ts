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

// -- photos (Photo / Slideshow widgets) --------------------------------------
export interface UploadedPhoto { album: string; path: string; name: string }

export const MEDIA_CHANGED = "cd:media-changed";   // window event: an album changed
const mediaChanged = () => window.dispatchEvent(new Event(MEDIA_CHANGED));

export const listAlbums = () =>
  fetch("/api/media/albums").then((r) => json<{ albums: { name: string; count: number }[] }>(r));
export const listAlbum = (album: string) =>
  fetch(`/api/media/list?${new URLSearchParams({ album })}`).then((r) => json<{ files: string[] }>(r));
export const uploadPhoto = (album: string, file: File) =>
  fetch(`/api/media/albums/${encodeURIComponent(album)}?${new URLSearchParams({ name: file.name })}`, {
    method: "POST",
    headers: { "content-type": file.type || "application/octet-stream" },
    body: file,
  }).then((r) => json<UploadedPhoto>(r)).then((p) => { mediaChanged(); return p; });
export const deletePhoto = (album: string, name: string) =>
  fetch(`/api/media/albums/${encodeURIComponent(album)}/${encodeURIComponent(name)}`, { method: "DELETE" })
    .then((r) => json<unknown>(r)).then(mediaChanged);
