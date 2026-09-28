import { useEffect, useRef, useState } from "react";
import { z } from "zod";

import { MEDIA_CHANGED } from "../api";
import { bumpDirty } from "../lib/dirty";
import { mediaUrl, usePolledJson } from "../lib/usePolledJson";
import { defineWidget } from "../registry/types";
import { MediaImage, MediaNote } from "./Photo";

const schema = z.object({
  // album: photos uploaded in the builder; folder: a folder inside your home folder
  source: z.enum(["album", "folder"]).default("album"),
  album: z.string().default("family").meta({ widget: "album" }),
  folder: z.string().default(""),
  // a full photo change takes ~1-2 s to reach the screen; keep this slow
  interval_minutes: z.number().min(0.25).max(1440).default(5),
  order: z.enum(["sequential", "shuffle"]).default("shuffle"),
  fit: z.enum(["cover", "contain"]).default("cover"),
  radius: z.number().int().min(0).max(40).default(8),
  show_name: z.boolean().default(false),
});
type P = z.infer<typeof schema>;

const RESCAN_MS = 60_000;   // pick up photos uploaded or added to the folder

function nextIndex(cur: number, n: number, order: P["order"]): number {
  if (n <= 1) return 0;
  if (order === "sequential") return (cur + 1) % n;
  let i = cur;
  while (i === cur) i = Math.floor(Math.random() * n);
  return i;
}

const prettyName = (path: string) => (path.split("/").pop() ?? "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");

export const Slideshow = defineWidget<P>({
  type: "Slideshow",
  title: "Photo slideshow",
  category: "media",
  schema,
  defaults: { source: "album", album: "family", folder: "", interval_minutes: 5, order: "shuffle", fit: "cover", radius: 8, show_name: false },
  defaultSize: { w: 304, h: 160 },
  minSize: { w: 32, h: 32 },
  Component: ({ item, props }) => {
    const fromAlbum = props.source === "album";
    const where = (fromAlbum ? props.album : props.folder).trim();
    const list = usePolledJson<{ files: string[] }>(
      where ? `/api/media/list?${new URLSearchParams(fromAlbum ? { album: where } : { dir: where })}` : null,
      RESCAN_MS, MEDIA_CHANGED);
    const files = list.data?.files ?? [];
    const n = files.length;
    const [idx, setIdx] = useState(0);
    // what is on screen; only swapped once the next photo has fully loaded,
    // so the device never gets a half-drawn frame
    const [shown, setShown] = useState<{ url: string; path: string } | null>(null);
    const failures = useRef(0);   // consecutive photos that failed to load

    useEffect(() => {
      if (!n) return;
      setIdx((i) => (props.order === "shuffle" && i === 0 ? Math.floor(Math.random() * n) : i % n));
      const t = window.setInterval(() => setIdx((i) => nextIndex(i, n, props.order)),
                                   props.interval_minutes * 60_000);
      return () => window.clearInterval(t);
    }, [n, props.interval_minutes, props.order]);

    const path = n ? files[idx % n] : "";
    const want = path ? mediaUrl(path, item.w, item.h) : "";
    useEffect(() => {
      if (!want) { setShown(null); bumpDirty(); return; }
      let cancelled = false;
      const img = new Image();
      img.onload = () => { if (!cancelled) { failures.current = 0; setShown({ url: want, path }); } };
      img.onerror = () => {
        // skip a broken photo, but stop once every photo in the list has failed
        if (!cancelled && ++failures.current < n) setIdx((i) => nextIndex(i, n, "sequential"));
      };
      img.src = want;
      return () => { cancelled = true; };
    }, [want, path, n]);

    if (!where) return <MediaNote text={fromAlbum ? "Name an album in the inspector" : "Set a photo folder in the inspector, e.g. ~/Pictures/family"} />;
    if (list.error && !n) return <MediaNote text={`Can't open ${where}: ${list.error}`} />;
    if (list.data && !n) return <MediaNote text={fromAlbum ? `Album "${where}" is empty. Upload photos in the inspector.` : `No JPEG/PNG photos in ${where}`} />;
    if (!shown) return <MediaNote text={failures.current >= n ? "None of these photos can be shown (HEIC? export as JPEG)" : "Loading photos…"} />;
    return <MediaImage src={shown.url} fit={props.fit} radius={props.radius}
                       caption={props.show_name ? prettyName(shown.path) : ""} />;
  },
});
