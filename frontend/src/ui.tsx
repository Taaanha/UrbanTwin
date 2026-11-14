import { Component, useState, type ErrorInfo, type ReactNode } from "react";
import { Link } from "react-router-dom";

/* ---------- palette shared by charts, badges and map ---------- */
export const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;
export const SEVERITY_COLOR: Record<string, string> = {
  critical: "#f43f5e",
  high: "#fb923c",
  medium: "#facc15",
  low: "#38bdf8",
};
export const CATEGORY_LABEL: Record<string, string> = {
  pothole: "Pothole",
  damaged_road: "Damaged road",
  blocked_drainage: "Blocked drainage",
  waterlogging: "Waterlogging",
  garbage: "Garbage",
  flooding: "Flooding",
  other: "Other",
};
export const STATUS_COLOR: Record<string, string> = {
  submitted: "#38bdf8",
  acknowledged: "#818cf8",
  under_review: "#facc15",
  insufficient_evidence: "#94a3b8",
  resolved_unverified: "#34d399",
  open: "#fb923c",
  verified: "#34d399",
  in_progress: "#22d3ee",
  completed: "#34d399",
  planned: "#818cf8",
  approved: "#22d3ee",
  proposed: "#94a3b8",
};
export const CHART_COLORS = ["#22d3ee", "#818cf8", "#34d399", "#fb923c", "#f472b6", "#facc15", "#94a3b8"];

export const titleCase = (key: string): string => {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};
/** "Ward 5 · Guptangk, Harinarayanpur, … (demonstration grid)" -> a chart-friendly label that keeps the ward number and first areas. */
export const wardLabel = (name: string, max = 42): string => {
  const text = name.replace(" (demonstration grid)", "");
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
};
export const categoryLabel =(key: string): string => CATEGORY_LABEL[key] ?? titleCase(key);

/* ---------- icons (inline, no dependency) ---------- */
const PATHS: Record<string, string> = {
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  map: "M9 4 3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5-5",
  brain: "M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V4a3 3 0 0 0-3 0zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1",
  wrench: "M14 6a4 4 0 0 0 5 5l-9 9a2.1 2.1 0 0 1-3-3l9-9a4 4 0 0 0-2-2zM14 6l2-2 4 4-2 2",
  shield: "M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6zM9 12l2 2 4-4",
  flask: "M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M8 15h8",
  database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 11a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  pin: "M12 21s7-6 7-11a7 7 0 1 0-14 0c0 5 7 11 7 11zM12 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  alert: "M12 3 2 20h20zM12 10v5M12 17.5v.5",
  check: "M5 12l5 5 9-10",
  layers: "M12 3 3 8l9 5 9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5",
  flame: "M12 3c1 3 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-6 1-9z",
  coin: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v10M9.5 9.5c0-1 1-1.5 2.5-1.5s2.5.7 2.5 1.7-1 1.5-2.5 1.8-2.5.8-2.5 1.8 1 1.7 2.5 1.7 2.5-.5 2.5-1.5",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  arrow: "M5 12h14M13 6l6 6-6 6",
  user: "M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 20c0-4 4-6 8-6s8 2 8 6",
  menu: "M4 7h16M4 12h16M4 17h16",
};

export function Icon({ name, className = "h-4 w-4" }: { name: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d={PATHS[name] ?? PATHS.grid} />
    </svg>
  );
}

/* ---------- containers ---------- */
export function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel p-4 ${className}`}>
      {title ? (
        <header className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
            {subtitle ? <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p> : null}
          </div>
          {action}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function PageHeader({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1 className="text-xl font-semibold tracking-tight text-white">{title}</h1>
      </div>
      {children}
    </header>
  );
}

export function Badge({ children, color = "#94a3b8" }: { children: ReactNode; color?: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium leading-4"
      style={{ color, background: `${color}1f`, boxShadow: `inset 0 0 0 1px ${color}40` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {children}
    </span>
  );
}

export const SeverityBadge = ({ value }: { value: string }) => (
  <Badge color={SEVERITY_COLOR[value] ?? "#94a3b8"}>{titleCase(value)}</Badge>
);
export const StatusBadge = ({ value }: { value: string }) => (
  <Badge color={STATUS_COLOR[value] ?? "#94a3b8"}>{titleCase(value)}</Badge>
);

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-1.5 text-left text-xs text-slate-300 hover:bg-slate-800/60"
    >
      <span>{label}</span>
      <span className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${checked ? "bg-sky-500" : "bg-slate-700"}`}>
        <span
          className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${checked ? "left-3.5" : "left-0.5"}`}
        />
      </span>
    </button>
  );
}

/* ---------- charts (SVG, no dependency) ---------- */
export function Sparkline({ data, color = "#22d3ee", height = 28 }: { data: number[]; color?: string; height?: number }) {
  if (data.length < 2) return <div style={{ height }} />;
  const max = Math.max(1, ...data);
  const w = 100;
  const pts = data.map((v, i) => [(i / (data.length - 1)) * w, height - 2 - (v / max) * (height - 4)] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const id = `sp${color.replace("#", "")}${data.length}`;
  return (
    <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }} aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.35" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L${w},${height} L0,${height} Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function Kpi({
  label,
  value,
  sub,
  to,
  icon,
  color = "#22d3ee",
  spark,
  step,
}: {
  label: string;
  value: string | number;
  sub?: string;
  to?: string;
  icon: string;
  color?: string;
  spark?: number[];
  step?: number;
}) {
  const body = (
    <div className="panel rise group relative h-full overflow-hidden p-4 transition-colors hover:border-sky-500/60">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="eyebrow flex items-center gap-1.5">
            {step ? <span className="rounded bg-slate-800 px-1 text-[10px] text-slate-300">{step}</span> : null}
            {label}
          </p>
          <p className="num mt-2 text-3xl font-semibold text-white">{value}</p>
        </div>
        <span
          className="grid h-9 w-9 shrink-0 place-items-center rounded-lg"
          style={{ background: `${color}1f`, color, boxShadow: `inset 0 0 0 1px ${color}40` }}
        >
          <Icon name={icon} className="h-[18px] w-[18px]" />
        </span>
      </div>
      {sub ? <p className="mt-1 truncate text-xs text-slate-400">{sub}</p> : null}
      {spark ? (
        <div className="mt-2">
          <Sparkline data={spark} color={color} />
        </div>
      ) : null}
    </div>
  );
  return to ? (
    <Link to={to} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

export function AreaChart({ data, color = "#22d3ee", height = 170 }: { data: Array<{ date: string; count: number }>; color?: string; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const w = 600;
  const pad = 6;
  const max = Math.max(1, ...data.map((d) => d.count));
  const x = (i: number) => pad + (i / Math.max(1, data.length - 1)) * (w - pad * 2);
  const y = (v: number) => height - pad - (v / max) * (height - pad * 2);
  const line = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.count).toFixed(1)}`).join(" ");
  const total = data.reduce((a, d) => a + d.count, 0);
  if (!data.length) return <p className="text-xs text-slate-500">No data.</p>;
  const h = hover != null ? data[hover] : null;
  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${w} ${height}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height }}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setHover(Math.max(0, Math.min(data.length - 1, Math.round(((e.clientX - r.left) / r.width) * (data.length - 1)))));
        }}
      >
        <defs>
          <linearGradient id="area-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor={color} stopOpacity="0.4" />
            <stop offset="1" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((t) => (
          <line key={t} x1="0" x2={w} y1={height * t} y2={height * t} stroke="#263554" strokeDasharray="3 5" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
        <path d={`${line} L${x(data.length - 1)},${height} L${x(0)},${height} Z`} fill="url(#area-fill)" />
        <path d={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {hover != null ? <line x1={x(hover)} x2={x(hover)} y1="0" y2={height} stroke={color} strokeOpacity="0.5" vectorEffect="non-scaling-stroke" /> : null}
      </svg>
      {h ? (
        <div
          className="pointer-events-none absolute top-0 -translate-x-1/2 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] shadow-lg"
          style={{ left: `${(hover! / Math.max(1, data.length - 1)) * 100}%` }}
        >
          <span className="text-slate-400">{h.date}</span> <span className="num font-semibold text-white">{h.count}</span>
        </div>
      ) : null}
      <div className="mt-1 flex justify-between text-[10px] text-slate-500">
        <span>{data[0].date}</span>
        <span>
          {total} reports · peak {max}/day
        </span>
        <span>{data[data.length - 1].date}</span>
      </div>
    </div>
  );
}

export type Slice = { label: string; value: number; color: string };

export function Donut({ slices, centerLabel, size = 150 }: { slices: Slice[]; centerLabel: string; size?: number }) {
  const total = slices.reduce((a, s) => a + s.value, 0);
  const r = 52;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
          <circle cx="70" cy="70" r={r} fill="none" stroke="#182440" strokeWidth="16" />
          {total > 0
            ? slices
                .filter((s) => s.value > 0)
                .map((s) => {
                  const len = (s.value / total) * c;
                  const el = (
                    <circle
                      key={s.label}
                      cx="70"
                      cy="70"
                      r={r}
                      fill="none"
                      stroke={s.color}
                      strokeWidth="16"
                      strokeDasharray={`${Math.max(0, len - 1.5)} ${c - Math.max(0, len - 1.5)}`}
                      strokeDashoffset={-offset}
                    />
                  );
                  offset += len;
                  return el;
                })
            : null}
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="num text-2xl font-semibold text-white">{total}</div>
            <div className="eyebrow">{centerLabel}</div>
          </div>
        </div>
      </div>
      <ul className="min-w-[8rem] flex-1 space-y-1.5 text-xs">
        {slices.map((s) => (
          <li key={s.label} className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-sm" style={{ background: s.color }} />
            <span className="flex-1 truncate text-slate-300">{s.label}</span>
            <span className="num text-slate-100">{s.value}</span>
            <span className="num w-9 text-right text-slate-500">{total ? Math.round((s.value / total) * 100) : 0}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HBars({ rows, empty = "No records yet.", suffix = "" }: { rows: Slice[]; empty?: string; suffix?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length) return <p className="text-xs text-slate-500">{empty}</p>;
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.label} className="text-xs">
          <div className="mb-1 flex justify-between text-slate-300">
            <span>{r.label}</span>
            <span className="num text-slate-100">
              {r.value}
              {suffix}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: r.color }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Funnel({ stages }: { stages: Array<{ stage: string; count: number }> }) {
  const max = Math.max(1, ...stages.map((s) => s.count));
  return (
    <ol className="space-y-2">
      {stages.map((s, i) => (
        <li key={s.stage} className="flex items-center gap-3 text-xs">
          <span className="w-32 shrink-0 text-slate-300">{s.stage}</span>
          <div className="relative h-6 flex-1 overflow-hidden rounded bg-slate-800/70">
            <div
              className="h-full rounded"
              style={{
                width: `${Math.max(3, (s.count / max) * 100)}%`,
                background: `linear-gradient(90deg, ${CHART_COLORS[i % CHART_COLORS.length]}55, ${CHART_COLORS[i % CHART_COLORS.length]})`,
              }}
            />
            <span className="num absolute inset-y-0 left-2 flex items-center font-semibold text-white">{s.count}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Category x severity heat matrix. Cell intensity is relative to the largest cell. */
export function HeatMatrix({ cells, onCell }: { cells: Array<{ category: string; severity: string; count: number }>; onCell?: (category: string, severity: string) => void }) {
  const categories = Array.from(new Set([...Object.keys(CATEGORY_LABEL), ...cells.map((c) => c.category)])).filter((cat) =>
    cells.some((c) => c.category === cat),
  );
  const get = (cat: string, sev: string) => cells.find((c) => c.category === cat && c.severity === sev)?.count ?? 0;
  const max = Math.max(1, ...cells.map((c) => c.count));
  if (!categories.length) return <p className="text-xs text-slate-500">No reports yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th />
            {SEVERITY_ORDER.map((s) => (
              <th key={s} className="pb-1 text-center font-medium" style={{ color: SEVERITY_COLOR[s] }}>
                {titleCase(s)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((cat) => (
            <tr key={cat}>
              <th className="whitespace-nowrap pr-2 text-left font-normal text-slate-300">{categoryLabel(cat)}</th>
              {SEVERITY_ORDER.map((sev) => {
                const n = get(cat, sev);
                const a = n ? 0.15 + 0.75 * (n / max) : 0;
                return (
                  <td key={sev}>
                    <button
                      type="button"
                      disabled={!n}
                      onClick={() => onCell?.(cat, sev)}
                      title={`${categoryLabel(cat)} · ${sev}: ${n}`}
                      className="num grid h-9 w-full place-items-center rounded-md text-sm font-semibold disabled:cursor-default"
                      style={{
                        background: n ? `${SEVERITY_COLOR[sev]}${Math.round(a * 255).toString(16).padStart(2, "0")}` : "#0d1628",
                        color: n ? "#fff" : "#3c4c6e",
                        boxShadow: n ? undefined : "inset 0 0 0 1px #182440",
                      }}
                    >
                      {n || "·"}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-slate-500">Colour strength is relative to the busiest cell. Click a cell to open it on the map.</p>
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  const c = tone === "warn" ? "#fbbf24" : "#22d3ee";
  return (
    <div
      className="flex items-start gap-2 rounded-lg px-3 py-2 text-xs"
      style={{ color: tone === "warn" ? "#fde68a" : "#a5f3fc", background: `${c}12`, boxShadow: `inset 0 0 0 1px ${c}40` }}
    >
      <Icon name={tone === "warn" ? "alert" : "check"} className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

/** Keeps the app shell alive when one page throws (for example WebGL is unavailable for a map). */
export class PageBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page error", error, info.componentStack);
  }
  render() {
    if (!this.state.error) return this.props.children;
    const webgl = /webgl/i.test(this.state.error.message);
    return (
      <div className="p-6">
        <Notice tone="warn">
          <p className="font-medium">This page could not start.</p>
          <p className="mt-1 text-amber-100/80">
            {webgl
              ? "The map needs WebGL, which this browser has turned off or does not support. Enable hardware acceleration in the browser settings, or try Chrome or Edge."
              : this.state.error.message}
          </p>
          <button className="mt-2 rounded-md border border-amber-500/50 px-2 py-1" onClick={() => window.location.reload()}>
            Reload
          </button>
        </Notice>
      </div>
    );
  }
}

/** 2D/3D and basemap switches that float over a map. */
export function MapToolbar({
  view3d,
  onView3d,
  basemap,
  onBasemap,
  extra,
}: {
  view3d: boolean;
  onView3d: (on: boolean) => void;
  basemap: "dark" | "standard" | "satellite";
  onBasemap: (b: "dark" | "standard" | "satellite") => void;
  extra?: ReactNode;
}) {
  const seg = (active: boolean) => `rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${active ? "bg-sky-500 text-slate-950" : "text-slate-300 hover:text-white"}`;
  return (
    <div className="glass pointer-events-auto absolute right-3 top-3 z-10 flex flex-col gap-2 p-2">
      <div className="flex gap-1 rounded-lg bg-slate-950/70 p-0.5">
        <button className={seg(!view3d)} onClick={() => onView3d(false)}>
          2D
        </button>
        <button className={seg(view3d)} onClick={() => onView3d(true)}>
          3D
        </button>
      </div>
      <div className="flex gap-1 rounded-lg bg-slate-950/70 p-0.5">
        {(["dark", "standard", "satellite"] as const).map((b) => (
          <button key={b} className={seg(basemap === b)} onClick={() => onBasemap(b)}>
            {b === "dark" ? "Dark" : b === "standard" ? "Street" : "Satellite"}
          </button>
        ))}
      </div>
      {extra}
      {view3d ? (
        <p className="max-w-[11rem] text-[10px] leading-snug text-slate-400">
          Drag with right mouse (or two fingers) to rotate. Building heights are estimated by type unless OSM has them.
        </p>
      ) : null}
    </div>
  );
}
