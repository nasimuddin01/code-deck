import { z } from "zod";

import { usePolledJson } from "../lib/usePolledJson";
import { defineWidget } from "../registry/types";

const schema = z.object({
  // "Dhaka" or "Dhaka, Bangladesh"; latitude/longitude win when both are set
  city: z.string().default(""),
  latitude: z.number().min(-90).max(90).optional(),
  longitude: z.number().min(-180).max(180).optional(),
  units: z.enum(["celsius", "fahrenheit"]).default("celsius"),
  label: z.string().default(""),
  show_uv: z.boolean().default(true),
  show_feels_like: z.boolean().default(true),
  show_high_low: z.boolean().default(true),
  show_humidity: z.boolean().default(false),
  show_wind: z.boolean().default(false),
  refresh_minutes: z.number().min(5).max(180).default(15),
});
type P = z.infer<typeof schema>;

interface Wx {
  place: string;
  temp: number | null;
  feels_like: number | null;
  humidity: number | null;
  wind: number | null;
  wind_unit: string;
  uv: number | null;
  uv_max: number | null;
  code: number | null;
  is_day: boolean;
  high: number | null;
  low: number | null;
}

type Kind = "clear" | "partly" | "cloudy" | "fog" | "drizzle" | "rain" | "snow" | "storm";

// WMO weather interpretation codes (Open-Meteo)
function describe(code: number | null): { kind: Kind; text: string } {
  if (code === null) return { kind: "cloudy", text: "—" };
  if (code === 0) return { kind: "clear", text: "Clear" };
  if (code === 1) return { kind: "partly", text: "Mostly clear" };
  if (code === 2) return { kind: "partly", text: "Partly cloudy" };
  if (code === 3) return { kind: "cloudy", text: "Overcast" };
  if (code === 45 || code === 48) return { kind: "fog", text: "Fog" };
  if (code >= 51 && code <= 57) return { kind: "drizzle", text: "Drizzle" };
  if (code >= 61 && code <= 67) return { kind: "rain", text: code >= 65 ? "Heavy rain" : "Rain" };
  if (code >= 71 && code <= 77) return { kind: "snow", text: "Snow" };
  if (code >= 80 && code <= 82) return { kind: "rain", text: "Showers" };
  if (code === 85 || code === 86) return { kind: "snow", text: "Snow showers" };
  if (code >= 95) return { kind: "storm", text: "Thunderstorm" };
  return { kind: "cloudy", text: "Cloudy" };
}

/** WHO UV scale: low / moderate / high / very high+ */
function uvColor(uv: number): string {
  if (uv < 3) return "var(--good)";
  if (uv < 6) return "var(--warning)";
  if (uv < 8) return "var(--orange)";
  return "var(--critical)";
}

const SUN = "#fab219", MOON = "#c3c2b7", CLOUD = "#c3c2b7", CLOUD_DARK = "#84837a", WATER = "#4aa3ff";

function Icon({ kind, day, size }: { kind: Kind; day: boolean; size: number }) {
  const sun = day
    ? <g><circle cx="15" cy="15" r="6" fill={SUN} />
        {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
          <line key={a} x1="15" y1="4" x2="15" y2="6.5" stroke={SUN} strokeWidth="2" strokeLinecap="round"
                transform={`rotate(${a} 15 15)`} />))}</g>
    : <path d="M19 8a8 8 0 1 0 5 12 6.5 6.5 0 0 1-5-12z" fill={MOON} />;
  const cloud = (fill: string, dx = 0, dy = 0) => (
    <path transform={`translate(${dx} ${dy})`} fill={fill}
          d="M11 30h17a6 6 0 0 0 .5-12 8 8 0 0 0-15.3-2.2A6.5 6.5 0 0 0 11 30z" />
  );
  const drops = (n: number, col: string, long: boolean) => [...Array(n)].map((_, i) => (
    <line key={i} x1={14 + i * 6} y1="32" x2={12 + i * 6} y2={long ? 38 : 35} stroke={col} strokeWidth="2" strokeLinecap="round" />
  ));
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" style={{ position: "static" }}>
      {kind === "clear" && <g transform="translate(5 5)">{sun}</g>}
      {kind === "partly" && <>{<g transform="translate(-1 -3)">{sun}</g>}{cloud(CLOUD, 2, 2)}</>}
      {kind === "cloudy" && <>{cloud(CLOUD_DARK, -4, -3)}{cloud(CLOUD, 2, 1)}</>}
      {kind === "fog" && <>{cloud(CLOUD_DARK, 0, -4)}
        {[30, 35].map((y) => <line key={y} x1="8" y1={y} x2="32" y2={y} stroke={CLOUD} strokeWidth="2" strokeLinecap="round" />)}</>}
      {kind === "drizzle" && <>{cloud(CLOUD, 0, -4)}{drops(3, WATER, false)}</>}
      {kind === "rain" && <>{cloud(CLOUD, 0, -4)}{drops(3, WATER, true)}</>}
      {kind === "snow" && <>{cloud(CLOUD, 0, -4)}
        {[14, 20, 26].map((x) => <circle key={x} cx={x} cy="34" r="1.8" fill="#fff" />)}</>}
      {kind === "storm" && <>{cloud(CLOUD_DARK, 0, -4)}<path d="M21 27l-5 7h4l-2 6 6-8h-4l2-5z" fill={SUN} /></>}
    </svg>
  );
}

export const Weather = defineWidget<P>({
  type: "Weather",
  title: "Weather",
  category: "media",
  schema,
  defaults: {
    city: "", units: "celsius", label: "", show_uv: true, show_feels_like: true, show_high_low: true,
    show_humidity: false, show_wind: false, refresh_minutes: 15,
  },
  defaultSize: { w: 304, h: 72 },
  minSize: { w: 120, h: 48 },
  Component: ({ item, props }) => {
    const hasCoords = props.latitude !== undefined && props.longitude !== undefined;
    const q = new URLSearchParams({ units: props.units });
    if (props.city.trim()) q.set("city", props.city.trim());
    if (hasCoords) { q.set("lat", String(props.latitude)); q.set("lon", String(props.longitude)); }
    const url = hasCoords || props.city.trim() ? `/api/weather?${q}` : null;
    const { data: wx, error } = usePolledJson<Wx>(url, props.refresh_minutes * 60_000);
    const { w, h } = item;

    if (!url || (!wx && error)) {
      return (
        <>
          <div className="panel" />
          <div className="t" style={{ left: 12, top: 10, fontSize: 9, fontWeight: 700, color: "var(--text-muted)" }}>WEATHER</div>
          <div className="t ell" style={{ left: 12, top: 26, maxWidth: w - 24, fontSize: 10, color: "var(--text-muted)" }}>
            {url ? error : "Set a city in the inspector"}
          </div>
        </>
      );
    }
    const deg = (v: number | null) => (v === null || v === undefined ? "—" : `${Math.round(v)}°`);
    const d = describe(wx?.code ?? null);
    const icon = Math.min(h - 16, 44);
    const title = (props.label || wx?.place || props.city || "WEATHER").toUpperCase();

    // right column: the detail lines the user switched on
    const lines: { k: string; v: string; col?: string }[] = [];
    if (wx && props.show_high_low) lines.push({ k: "H/L", v: `${deg(wx.high)} ${deg(wx.low)}` });
    if (wx && props.show_uv && wx.uv !== null) {
      const peak = wx.uv_max !== null && wx.uv_max > wx.uv ? ` · ${Math.round(wx.uv_max)} max` : "";
      lines.push({ k: "UV", v: `${Math.round(wx.uv)}${peak}`, col: uvColor(Math.round(wx.uv)) });
    }
    if (wx && props.show_feels_like) lines.push({ k: "FEELS", v: deg(wx.feels_like) });
    if (wx && props.show_humidity && wx.humidity !== null) lines.push({ k: "HUM", v: `${Math.round(wx.humidity)}%` });
    if (wx && props.show_wind && wx.wind !== null) lines.push({ k: "WIND", v: `${Math.round(wx.wind)} ${wx.wind_unit}` });
    const fit = Math.max(1, Math.floor((h - 12) / 13));
    const shown = w >= 220 ? lines.slice(0, fit) : [];
    const colW = 104, colX = w - 12 - colW;
    const leftMax = (shown.length ? colX : w - 12) - 10;

    return (
      <>
        <div className="panel" />
        <div style={{ position: "absolute", left: 8, top: Math.round((h - icon) / 2) }}>
          <Icon kind={d.kind} day={wx?.is_day ?? true} size={icon} />
        </div>
        <div className="t ell" style={{ left: icon + 14, top: 8, maxWidth: leftMax - icon - 4, fontSize: 9, fontWeight: 700, color: "var(--text-muted)" }}>
          {title}
        </div>
        <div className="t" style={{ left: icon + 14, top: 21, fontSize: Math.min(26, h - 34), fontWeight: 700, color: "var(--text)" }}>
          {wx ? deg(wx.temp) : "…"}
        </div>
        <div className="t ell" style={{ left: icon + 14, top: h - 14, maxWidth: leftMax - icon - 4, fontSize: 9, color: "var(--text-2)" }}>
          {d.text}
        </div>
        {shown.map((l, i) => (
          <div key={l.k} className="t" style={{ left: colX, top: Math.round((h - shown.length * 13) / 2) + i * 13 + 1, width: colW,
                                                  display: "flex", justifyContent: "space-between", fontSize: 10 }}>
            <span style={{ color: "var(--text-muted)", fontWeight: 700, fontSize: 8, paddingTop: 1 }}>{l.k}</span>
            <span className="mono" style={{ color: l.col ?? "var(--text)" }}>{l.v}</span>
          </div>
        ))}
      </>
    );
  },
});
