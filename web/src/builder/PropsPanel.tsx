import { useMemo } from "react";
import { z } from "zod";

import { registry } from "../registry";
import { matchesTool, useAgents, useTools } from "../store/live";
import { useBuilder, useSelectedItem } from "../store/builder";
import { SCREEN } from "../types/layout";
import { AlbumField, PhotoField } from "./MediaFields";

interface JsonProp {
  widget?: string;           // from zod .meta({ widget }) — e.g. "agent"
  type?: string | string[];
  enum?: unknown[];
  minimum?: number;
  maximum?: number;
  items?: { type?: string };
  description?: string;
}

/** Pick one of the registered agents (built-ins + agents.toml + pushed). The
 * stored value is the agent id; older layouts that stored a display name
 * still resolve to the right option. */
function AgentSelect({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const agents = useAgents();
  const tools = useTools();
  const v = String(value ?? "");
  const current = tools.find((t) => matchesTool(t, v))?.agent_id ?? agents.find((a) => a.name === v)?.id ?? v;
  const opts = agents.length ? agents.filter((a) => a.enabled).map((a) => ({ id: a.id, name: a.name }))
                             : tools.map((t) => ({ id: t.agent_id ?? t.name, name: t.name }));
  if (current && !opts.some((o) => o.id === current)) opts.push({ id: current, name: `${current} (not running)` });
  return (
    <select value={current} onChange={(e) => onChange(e.target.value)}>
      {opts.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
    </select>
  );
}

function Field({ name, spec, value, onChange }: { name: string; spec: JsonProp; value: unknown; onChange: (v: unknown) => void }) {
  const t = Array.isArray(spec.type) ? spec.type[0] : spec.type;
  if (spec.widget === "agent") return <AgentSelect value={value} onChange={onChange} />;
  if (spec.widget === "album") return <AlbumField value={value} onChange={onChange} />;
  if (spec.widget === "photo") return <PhotoField value={value} onChange={onChange} />;
  if (spec.enum) {
    return (
      <select value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
        {spec.enum.map((o) => <option key={String(o)} value={String(o)}>{String(o)}</option>)}
      </select>
    );
  }
  if (t === "boolean") return <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />;
  if (t === "number" || t === "integer") {
    return (
      <input type="number" value={value === undefined || value === null ? "" : Number(value)}
             min={spec.minimum} max={spec.maximum} step={t === "integer" ? 1 : "any"}
             onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))} />
    );
  }
  if (t === "array" && spec.items?.type === "string") {
    return (
      <input type="text" value={Array.isArray(value) ? value.join(", ") : ""} placeholder="comma separated"
             onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
    );
  }
  if (t === "string") {
    const isColor = /color|accent/.test(name);
    return (
      <div className="row">
        <input type="text" value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
        {isColor && <span className="swatch" style={{ background: swatch(String(value ?? "")) }} />}
      </div>
    );
  }
  return (
    <textarea rows={3} value={JSON.stringify(value ?? null)}
              onChange={(e) => { try { onChange(JSON.parse(e.target.value)); } catch { /* keep typing */ } }} />
  );
}

const swatch = (v: string) =>
  ({ orange: "var(--orange)", violet: "var(--violet)", blue: "var(--blue)", good: "var(--good)", warning: "var(--warning)",
     critical: "var(--critical)", attention: "var(--attention)", text: "var(--text)", text2: "var(--text-2)", muted: "var(--text-muted)" }[v] ?? v);

/** Inspector for the selected widget: geometry, props (generated from the
 * widget's zod schema), stacking and visibility. */
export function PropsPanel() {
  const item = useSelectedItem();
  const layout = useBuilder((s) => s.layout);
  const updateItem = useBuilder((s) => s.updateItem);
  const setRect = useBuilder((s) => s.setRect);
  const updateProps = useBuilder((s) => s.updateProps);
  const removeItem = useBuilder((s) => s.removeItem);
  const duplicateItem = useBuilder((s) => s.duplicateItem);
  const moveZ = useBuilder((s) => s.moveZ);

  const def = item ? registry[item.type] : undefined;
  const schema = useMemo(() => {
    if (!def) return null;
    try {
      return z.toJSONSchema(def.schema) as { properties?: Record<string, JsonProp> };
    } catch {
      return null;
    }
  }, [def]);

  if (!item || !def || !layout) {
    return (
      <aside className="pane inspector">
        <div className="pane-title">Inspector</div>
        <div className="hint">
          Select a widget on the screen, or drag one in from the library.<br /><br />
          <b>Keys</b>: arrows nudge (⇧ = 8px) · ⌫ delete · ⌘D duplicate · [ ] stacking · ⌘Z / ⇧⌘Z undo / redo · ⌘S save
        </div>
        <div className="pane-title">Layout</div>
        <div className="kv"><span>widgets</span><span>{layout?.items.length ?? 0}</span></div>
        <div className="kv"><span>screen</span><span>{SCREEN.w}×{SCREEN.h} · grid {layout?.grid}</span></div>
      </aside>
    );
  }

  const props = { ...def.defaults, ...item.props } as Record<string, unknown>;
  const fields = Object.entries(schema?.properties ?? {});
  const num = (k: "x" | "y" | "w" | "h") => (e: React.ChangeEvent<HTMLInputElement>) =>
    setRect(item.id, { x: item.x, y: item.y, w: item.w, h: item.h, [k]: Number(e.target.value) });

  return (
    <aside className="pane inspector">
      <div className="pane-title">{def.title} <span className="muted">· {item.id}</span></div>

      <div className="grid4">
        {(["x", "y", "w", "h"] as const).map((k) => (
          <label key={k}><span>{k}</span><input type="number" value={item[k]} step={layout.grid} onChange={num(k)} disabled={item.locked} /></label>
        ))}
      </div>

      <div className="btn-row">
        <button onClick={() => moveZ(item.id, "back")} title="send to back">⤓</button>
        <button onClick={() => moveZ(item.id, -1)} title="send backward">↓</button>
        <button onClick={() => moveZ(item.id, 1)} title="bring forward">↑</button>
        <button onClick={() => moveZ(item.id, "front")} title="bring to front">⤒</button>
        <button onClick={() => duplicateItem(item.id)} disabled={!!def.singleton} title="duplicate (⌘D)">⧉</button>
        <button className="danger" onClick={() => removeItem(item.id)} title="delete (⌫)">✕</button>
      </div>
      <label className="check"><input type="checkbox" checked={item.locked} onChange={(e) => updateItem(item.id, { locked: e.target.checked })} /> locked</label>
      <label className="check"><input type="checkbox" checked={item.hidden} onChange={(e) => updateItem(item.id, { hidden: e.target.checked })} /> hidden</label>

      {fields.length > 0 && <div className="pane-title">Props</div>}
      {fields.map(([name, spec]) => {
        // upload controls hold several buttons: a <label> would steal their clicks
        const Wrap = spec.widget === "album" || spec.widget === "photo" ? "div" : "label";
        return (
          <Wrap key={name} className="field">
            <span title={spec.description}>{name.replace(/_/g, " ")}</span>
            <Field name={name} spec={spec} value={props[name]} onChange={(v) => updateProps(item.id, { [name]: v })} />
          </Wrap>
        );
      })}
    </aside>
  );
}
