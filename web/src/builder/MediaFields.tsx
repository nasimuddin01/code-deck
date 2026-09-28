import { useCallback, useEffect, useRef, useState } from "react";

import { MEDIA_CHANGED, deletePhoto, listAlbum, listAlbums, uploadPhoto } from "../api";
import { mediaUrl } from "../lib/usePolledJson";

const fileName = (path: string) => path.split("/").pop() ?? path;

/** Upload files one at a time (the server takes raw bytes per request). */
function useUploader(album: string, onDone?: (paths: string[]) => void) {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const upload = useCallback(async (files: FileList | File[]) => {
    const list = Array.from(files).filter((f) => f.type.startsWith("image/") || /\.(jpe?g|png|webp|gif|bmp|tiff?|heic)$/i.test(f.name));
    if (!list.length || !album) return;
    setBusy(true);
    const done: string[] = [];
    const failed: string[] = [];
    for (let i = 0; i < list.length; i++) {
      setStatus(`Uploading ${i + 1} of ${list.length}…`);
      try {
        done.push((await uploadPhoto(album, list[i])).path);
      } catch (e) {
        const msg = String((e as Error).message);
        failed.push(`${list[i].name}: ${/415/.test(msg) ? "can't read it (HEIC? export as JPEG)" : /413/.test(msg) ? "too large" : "failed"}`);
      }
    }
    setBusy(false);
    setStatus(failed.length ? `${done.length} added. Skipped ${failed.join("; ")}` : `${done.length} photo${done.length === 1 ? "" : "s"} added`);
    if (done.length) onDone?.(done);
  }, [album, onDone]);
  return { upload, status, busy };
}

function UploadButton({ label, multiple, disabled, onFiles }: {
  label: string; multiple: boolean; disabled?: boolean; onFiles: (f: FileList) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" disabled={disabled} onClick={(e) => { e.preventDefault(); ref.current?.click(); }}>{label}</button>
      <input ref={ref} type="file" accept="image/*" multiple={multiple} style={{ display: "none" }}
             onChange={(e) => { if (e.target.files?.length) onFiles(e.target.files); e.target.value = ""; }} />
    </>
  );
}

/** Slideshow: pick/name an album, upload into it, see and remove its photos. */
export function AlbumField({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const album = String(value ?? "").trim();
  const [albums, setAlbums] = useState<string[]>([]);
  const [files, setFiles] = useState<string[]>([]);
  const [over, setOver] = useState(false);
  const valid = /^[A-Za-z0-9][A-Za-z0-9 _-]{0,39}$/.test(album);

  // the album list only changes on upload/delete; the files of one album
  // also when the name in the box changes
  useEffect(() => {
    const load = () => listAlbums().then((r) => setAlbums(r.albums.map((a) => a.name))).catch(() => {});
    load();
    window.addEventListener(MEDIA_CHANGED, load);
    return () => window.removeEventListener(MEDIA_CHANGED, load);
  }, []);
  useEffect(() => {
    if (!valid) { setFiles([]); return; }
    let stale = false;
    const load = () => listAlbum(album).then((r) => { if (!stale) setFiles(r.files); }).catch(() => { if (!stale) setFiles([]); });
    load();
    window.addEventListener(MEDIA_CHANGED, load);
    return () => { stale = true; window.removeEventListener(MEDIA_CHANGED, load); };
  }, [album, valid]);

  const { upload, status, busy } = useUploader(valid ? album : "");

  return (
    <div className="media-field"
         onDragOver={(e) => { e.preventDefault(); setOver(true); }}
         onDragLeave={() => setOver(false)}
         onDrop={(e) => { e.preventDefault(); setOver(false); if (e.dataTransfer.files.length) upload(e.dataTransfer.files); }}>
      <input type="text" list="cd-albums" value={String(value ?? "")} placeholder="album name, e.g. family"
             onChange={(e) => onChange(e.target.value)} />
      <datalist id="cd-albums">{albums.map((a) => <option key={a} value={a} />)}</datalist>
      {!valid && album && <div className="media-status bad">Letters, digits, spaces, - and _ only</div>}
      <div className={`media-drop${over ? " over" : ""}`}>
        {files.length ? (
          <div className="media-grid">
            {files.map((p) => (
              <div key={p} className="media-thumb" title={fileName(p)}>
                <img src={mediaUrl(p, 56, 56)} alt="" draggable={false} />
                <button type="button" className="danger" title="remove from album"
                        onClick={(e) => { e.preventDefault(); if (confirm(`Remove ${fileName(p)} from "${album}"?`)) deletePhoto(album, fileName(p)).catch(() => {}); }}>
                  ✕
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="media-empty">{valid ? "No photos yet. Drop photos here or upload." : "Name an album first."}</div>
        )}
      </div>
      <div className="row">
        <UploadButton label={busy ? "Uploading…" : "Upload photos"} multiple disabled={!valid || busy} onFiles={upload} />
        <span className="muted">{files.length} photo{files.length === 1 ? "" : "s"}</span>
      </div>
      {status && <div className="media-status">{status}</div>}
    </div>
  );
}

/** Photo: type a path, or upload one photo (kept in the "photos" album). */
export function PhotoField({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const path = String(value ?? "");
  const { upload, status, busy } = useUploader("photos", (paths) => onChange(paths[paths.length - 1]));
  return (
    <div className="media-field">
      {path.trim() && <img className="media-preview" src={mediaUrl(path.trim(), 120, 80)} alt="" />}
      <input type="text" value={path} placeholder="~/Pictures/family/beach.jpg" onChange={(e) => onChange(e.target.value)} />
      <div className="row">
        <UploadButton label={busy ? "Uploading…" : "Upload a photo"} multiple={false} disabled={busy} onFiles={upload} />
      </div>
      {status && <div className="media-status">{status}</div>}
    </div>
  );
}
