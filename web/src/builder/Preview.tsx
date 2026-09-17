import { Screen } from "../player/Player";
import { useDevice, useLive } from "../store/live";

/** Placeholder builder shell: a device-framed live preview of the player.
 * The drag-and-drop editor lands in the next phase and replaces this. */
export function Preview() {
  const dev = useDevice();
  const connected = useLive((s) => s.connected);
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", gap: 20, padding: 32, color: "var(--text-2)", fontFamily: "var(--font-sans)" }}>
      <div style={{ fontSize: 14, letterSpacing: 2, fontWeight: 700 }}>CODE DECK · PREVIEW</div>
      <div style={{ padding: 18, background: "#111", borderRadius: 28, boxShadow: "0 30px 80px rgba(0,0,0,.6)" }}>
        <div style={{ transform: "scale(2)", transformOrigin: "top left", width: 320, height: 480, marginRight: 320, marginBottom: 480 }}>
          <Screen />
        </div>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
        {connected ? "live" : "reconnecting…"} · device {dev?.connected ? "connected" : "absent"} · renderer {dev?.renderer ?? "—"}
        {dev?.last_push_ms != null ? ` · last push ${dev.last_push_ms} ms` : ""}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
        This is exactly what the screen shows (<a href="/player" style={{ color: "var(--attention)" }}>/player</a>). The layout builder is coming next.
      </div>
    </div>
  );
}
