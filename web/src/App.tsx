import { useEffect } from "react";

import { Builder } from "./builder/Builder";
import { Preview } from "./builder/Preview";
import { Player } from "./player/Player";
import { Setup } from "./setup/Setup";
import { connectLive } from "./ws";
import { useLayoutStore } from "./store/layout";
import { useLive } from "./store/live";

// No router: /player is what the device shows (and what headless Chromium
// screenshots); /preview is a read-only device frame; /setup is the setup
// wizard; everything else is the builder.
export default function App() {
  const params = new URLSearchParams(location.search);
  const path = location.pathname;
  const device = params.get("device") === "1";
  const layoutRev = useLive((s) => s.snapshot?.layout_rev ?? 0);
  const fetchLayout = useLayoutStore((s) => s.fetch);

  useEffect(() => connectLive(), []);
  useEffect(() => {
    void fetchLayout();
  }, [fetchLayout, layoutRev]); // server bumps layout_rev on every save

  if (path.startsWith("/player")) return <Player device={device} />;
  if (path.startsWith("/preview")) return <Preview />;
  if (path.startsWith("/setup")) return <Setup />;
  return <Builder />;
}
