import { useEffect, useRef } from "react";

import { setBrightness } from "../api";
import { useBuilder } from "../store/builder";

/** Device + overlay settings. Brightness is applied to the panel live (debounced);
 * everything here is also part of the layout and persists on Save. */
export function SettingsDrawer() {
  const layout = useBuilder((s) => s.layout);
  const updateSettings = useBuilder((s) => s.updateSettings);
  const setOpen = useBuilder((s) => s.setSettingsOpen);
  const timer = useRef<number | undefined>(undefined);
  const brightness = layout?.settings.brightness ?? 39;

  useEffect(() => () => window.clearTimeout(timer.current), []);
  if (!layout) return null;
  const s = layout.settings;

  const onBrightness = (v: number) => {
    updateSettings({ brightness: v });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setBrightness(v).catch(() => {}), 250);
  };

  return (
    <div className="drawer">
      <div className="pane-title">Settings <button className="link" onClick={() => setOpen(false)}>close</button></div>
      <label className="field">
        <span>brightness · {brightness}</span>
        <input type="range" min={0} max={255} value={brightness} onChange={(e) => onBrightness(Number(e.target.value))} />
      </label>
      <label className="check">
        <input type="checkbox" checked={s.overlay_enabled} onChange={(e) => updateSettings({ overlay_enabled: e.target.checked })} />
        full-screen banner when a session needs you
      </label>
      <label className="field">
        <span>banner seconds</span>
        <input type="number" min={1} max={120} value={s.overlay_seconds} onChange={(e) => updateSettings({ overlay_seconds: Number(e.target.value) })} />
      </label>
      <label className="field">
        <span>stats refresh (s)</span>
        <input type="number" min={1} max={300} value={s.refresh_seconds} onChange={(e) => updateSettings({ refresh_seconds: Number(e.target.value) })} />
      </label>
      <div className="hint">Brightness changes the panel immediately. The rest applies on Save.</div>
    </div>
  );
}
