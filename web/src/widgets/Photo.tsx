import { useEffect, useState } from "react";
import { z } from "zod";

import { bumpDirty } from "../lib/dirty";
import { mediaUrl } from "../lib/usePolledJson";
import { defineWidget } from "../registry/types";

const schema = z.object({
  // upload one in the inspector, or a file inside your home folder
  path: z.string().default("").meta({ widget: "photo" }),
  fit: z.enum(["cover", "contain"]).default("cover"),
  radius: z.number().int().min(0).max(40).default(8),
  caption: z.string().default(""),
});
type P = z.infer<typeof schema>;

/** Placeholder / error text centred in a panel. */
export function MediaNote({ text }: { text: string }) {
  return (
    <>
      <div className="panel" />
      <div style={{ position: "absolute", inset: 8, display: "flex", alignItems: "center", justifyContent: "center",
                    textAlign: "center", fontSize: 10, lineHeight: 1.3, color: "var(--text-muted)" }}>
        {text}
      </div>
    </>
  );
}

/** The photo itself; marks the frame dirty once it has painted. */
export function MediaImage({ src, fit, radius, caption, onError }: {
  src: string; fit: "cover" | "contain"; radius: number; caption?: string; onError?: () => void;
}) {
  return (
    <>
      <img
        src={src}
        alt=""
        draggable={false}
        onLoad={() => requestAnimationFrame(() => bumpDirty())}
        onError={onError}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: fit,
                 borderRadius: radius, background: fit === "contain" ? "var(--panel)" : undefined }}
      />
      {caption && (
        <div className="t ell" style={{ left: 0, right: 0, bottom: 0, padding: "12px 8px 5px", fontSize: 10, fontWeight: 600,
                                         color: "#fff", background: "linear-gradient(transparent, rgba(0,0,0,0.65))",
                                         borderRadius: `0 0 ${radius}px ${radius}px` }}>
          {caption}
        </div>
      )}
    </>
  );
}

export const Photo = defineWidget<P>({
  type: "Photo",
  title: "Photo",
  category: "media",
  schema,
  defaults: { path: "", fit: "cover", radius: 8, caption: "" },
  defaultSize: { w: 304, h: 160 },
  minSize: { w: 32, h: 32 },
  Component: ({ item, props }) => {
    const [failed, setFailed] = useState(false);
    const src = props.path.trim() ? mediaUrl(props.path.trim(), item.w, item.h) : "";
    useEffect(() => {
      setFailed(false);
      bumpDirty();
    }, [src]);
    if (!src) return <MediaNote text="Upload a photo in the inspector" />;
    if (failed) return <MediaNote text={`Can't show ${props.path}. JPEG/PNG inside your home folder only.`} />;
    return <MediaImage src={src} fit={props.fit} radius={props.radius} caption={props.caption}
                       onError={() => { setFailed(true); bumpDirty(); }} />;
  },
});
