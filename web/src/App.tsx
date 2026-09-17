import { useEffect } from "react";

import { Preview } from "./builder/Preview";
import { Player } from "./player/Player";
import { connectLive } from "./ws";
import { useLayoutStore } from "./store/layout";
import { useLive } from "./store/live";

// No router: two entry points. /player is what the device shows (and what
// headless Chromium screenshots); everything else is the builder shell.
export default function App() {
  const params = new URLSearchParams(location.search);
  const isPlayer = location.pathname.startsWith("/player");
  const device = params.get("device") === "1";
  const layoutRev = useLive((s) => s.snapshot?.layout_rev ?? 0);
  const fetchLayout = useLayoutStore((s) => s.fetch);

  useEffect(() => connectLive(), []);
  useEffect(() => {
    void fetchLayout();
  }, [fetchLayout, layoutRev]); // server bumps layout_rev on every save

  return isPlayer ? <Player device={device} /> : <Preview />;
}
