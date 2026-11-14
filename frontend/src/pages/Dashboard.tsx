import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import maplibregl from "maplibre-gl";
import { apiFetch, apiJson } from "../api";
import { createMap, getBasemap, onStyleReady, setBasemap, webglAvailable, type Basemap } from "../map";
import { addBuildings3D, PITCH_3D } from "../map3d";
import {
  CATEGORY_LABEL,
  Icon,
  MapToolbar,
  SEVERITY_COLOR,
  SEVERITY_ORDER,
  SeverityBadge,
  StatusBadge,
  Switch,
  categoryLabel,
  titleCase,
} from "../ui";

/** Reports at the very same coordinates (e.g. all filed from the default map centre) draw on top of each other: count them. */
function withStacks<T extends { features: Array<{ geometry: { coordinates: unknown }; properties: Record<string, unknown> }> }>(data: T): T {
  const key = (f: { geometry: { coordinates: unknown } }) => (f.geometry.coordinates as number[]).map((x) => x.toFixed(5)).join(",");
  const counts = new Map<string, number>();
  for (const f of data.features) counts.set(key(f), (counts.get(key(f)) ?? 0) + 1);
  for (const f of data.features) f.properties.stack = counts.get(key(f)) ?? 1;
  return data;
}

type GeoJSON = {
  type: "FeatureCollection";
  features: Array<{ type: "Feature"; geometry: { type: string; coordinates: unknown }; properties: Record<string, unknown> }>;
};

type LayerId = "study" | "upazila" | "wards" | "roads" | "buildings" | "water" | "drains";

const LAYER_ENDPOINTS: Record<LayerId, string> = {
  study: "/api/geo/study-area",
  upazila: "/api/geo/admin-boundaries",
  wards: "/api/geo/wards",
  roads: "/api/geo/roads",
  buildings: "/api/geo/buildings",
  water: "/api/geo/water",
  drains: "/api/geo/drains",
};

const LAYER_LABELS: Record<LayerId, string> = {
  study: "Study envelope",
  upazila: "Sadar Upazila (OSM)",
  wards: "Wards (demo grid)",
  roads: "Roads (OSM)",
  buildings: "Buildings (OSM)",
  water: "Water (OSM)",
  drains: "Drains (OSM)",
};

const STATUSES = ["submitted", "acknowledged", "under_review", "insufficient_evidence", "resolved_unverified"];

type ReportItem = {
  tracking_id: string;
  category: string;
  severity: string;
  status: string;
  description: string;
  location_text?: string | null;
  latitude: number;
  longitude: number;
  evidence?: Array<{ id: number; url: string; original_name?: string | null }>;
};

type LapseItem = {
  tracking_id: string;
  category: string;
  severity: string;
  status: string;
  created_at: string;
  longitude: number;
  latitude: number;
};
type Lapse = { items: LapseItem[]; start: number; end: number };

const chip = (active: boolean) =>
  `rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
    active ? "border-sky-400 bg-sky-500/20 text-sky-100" : "border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200"
  }`;

export default function Dashboard() {
  const [params] = useSearchParams();
  const mapNode = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [all, setAll] = useState<ReportItem[]>([]);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [category, setCategory] = useState(params.get("category") ?? "");
  const [severity, setSeverity] = useState(params.get("severity") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [selected, setSelected] = useState<ReportItem | null>(null);
  const [stackCount, setStackCount] = useState(1);
  const [heat, setHeat] = useState(true);
  const [view3d, setView3d] = useState(false);
  const [basemap, setBase] = useState<Basemap>(getBasemap());
  const [panel, setPanel] = useState(true);
  const [visible, setVisible] = useState<Record<LayerId, boolean>>({
    study: true,
    upazila: false,
    wards: false,
    roads: true,
    buildings: true,
    water: true,
    drains: true,
  });
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [lapseOn, setLapseOn] = useState(false);
  const [lapse, setLapse] = useState<Lapse | null>(null);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [lapseError, setLapseError] = useState("");

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (category) p.set("category", category);
    if (severity) p.set("severity", severity);
    if (status) p.set("status", status);
    const q = p.toString();
    return q ? `?${q}` : "";
  }, [category, severity, status]);

  useEffect(() => {
    apiFetch("/api/geo/summary").then((r) => r.json()).then(setSummary).catch(() => undefined);
    apiFetch("/api/reports").then((r) => r.json()).then((b) => setAll(b.items ?? [])).catch(() => undefined);
  }, []);

  const refreshAll = useCallback(() => {
    void apiFetch("/api/reports").then((r) => r.json()).then((b) => setAll(b.items ?? []));
  }, []);

  useEffect(() => {
    apiFetch(`/api/reports${query}`).then((r) => r.json()).then((b) => setReports(b.items ?? [])).catch(() => undefined);
    const map = mapRef.current;
    if (map?.getSource("src-reports") && !lapseOn) {
      void apiFetch(`/api/reports/geojson${query}`)
        .then((r) => r.json())
        .then((data) => (map.getSource("src-reports") as maplibregl.GeoJSONSource).setData(withStacks(data)));
    }
  }, [query, mapReady, lapseOn]);

  useEffect(() => {
    if (!mapNode.current || mapRef.current) return;
    if (!webglAvailable()) setMapError(true);
    const map = createMap(mapNode.current);
    mapRef.current = map;
    const onReady = () => {
      map.resize();
      void loadLayers(map, query).then(() => setMapReady(true));
    };
    onStyleReady(map, onReady);
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // layer visibility
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const set = (ids: string[], on: boolean) =>
      ids.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", on ? "visible" : "none"));
    set(["study-fill", "study-line"], visible.study);
    set(["upazila-line"], visible.upazila);
    set(["wards-fill", "wards-line"], visible.wards);
    set(["roads-line"], visible.roads);
    set(["buildings-fill"], visible.buildings && !view3d);
    set(["buildings-3d"], visible.buildings && view3d);
    set(["water-fill", "water-line"], visible.water);
    set(["drains-line"], visible.drains);
    set(["reports-heat"], heat);
  }, [visible, heat, view3d, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    map.easeTo({ pitch: view3d ? PITCH_3D : 0, bearing: view3d ? -20 : 0, duration: 800 });
  }, [view3d, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (map && mapReady) setBasemap(map, basemap);
  }, [basemap, mapReady]);

  // click on a map point selects the report
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const onClick = (e: maplibregl.MapLayerMouseEvent) => {
      const id = e.features?.[0]?.properties?.tracking_id as string | undefined;
      const hit = all.find((r) => r.tracking_id === id);
      setStackCount(Number(e.features?.[0]?.properties?.stack ?? 1));
      if (hit) setSelected(hit);
    };
    const pointer = () => (map.getCanvas().style.cursor = "pointer");
    const reset = () => (map.getCanvas().style.cursor = "");
    map.on("click", "reports-circle", onClick);
    map.on("mouseenter", "reports-circle", pointer);
    map.on("mouseleave", "reports-circle", reset);
    return () => {
      map.off("click", "reports-circle", onClick);
      map.off("mouseenter", "reports-circle", pointer);
      map.off("mouseleave", "reports-circle", reset);
    };
  }, [all, mapReady]);

  // highlight the selected report
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const src = map.getSource("src-selected") as maplibregl.GeoJSONSource | undefined;
    src?.setData({
      type: "FeatureCollection",
      features: selected ? [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [selected.longitude, selected.latitude] } }] : [],
    });
  }, [selected, mapReady]);

  // time-lapse: replay the last 30 days of citizen reports
  useEffect(() => {
    if (!lapseOn) {
      setLapse(null);
      setPlaying(false);
      setLapseError("");
      return;
    }
    let alive = true;
    apiJson<{ items: LapseItem[]; start: string; end: string }>("/api/insights/timelapse?days=30")
      .then((body) => {
        if (!alive) return;
        const start = Date.parse(body.start);
        setLapse({ items: body.items, start, end: Date.parse(body.end) });
        setCursor(start);
        setLapseError("");
      })
      .catch((e: Error) => alive && setLapseError(e.message));
    return () => {
      alive = false;
    };
  }, [lapseOn]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !lapseOn || !lapse) return;
    const features = lapse.items
      .filter(
        (i) =>
          Date.parse(i.created_at) <= cursor &&
          (!category || i.category === category) &&
          (!severity || i.severity === severity) &&
          (!status || i.status === status),
      )
      .map((i) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [i.longitude, i.latitude] },
        properties: { tracking_id: i.tracking_id, category: i.category, severity: i.severity, status: i.status },
      }));
    (map.getSource("src-reports") as maplibregl.GeoJSONSource | undefined)?.setData(withStacks({ type: "FeatureCollection", features }) as never);
  }, [lapseOn, lapse, cursor, category, severity, status, mapReady]);

  useEffect(() => {
    if (!playing || !lapse) return;
    const step = (lapse.end - lapse.start) / 180;
    const id = window.setInterval(() => {
      setCursor((c) => {
        const next = c + step;
        if (next >= lapse.end) {
          setPlaying(false);
          return lapse.end;
        }
        return next;
      });
    }, 100);
    return () => window.clearInterval(id);
  }, [playing, lapse]);

  const lapseShown = lapse ? lapse.items.filter((i) => Date.parse(i.created_at) <= cursor).length : 0;
  const fmtDay = (ms: number) => new Date(ms).toLocaleDateString("en-GB", { day: "2-digit", month: "short" });

  function pick(item: ReportItem) {
    setSelected(item);
    if (mapError) return;
    mapRef.current?.flyTo({ center: [item.longitude, item.latitude], zoom: Math.max(mapRef.current.getZoom(), 16), duration: 700 });
  }

  async function setReportStatus(trackingId: string, next: string) {
    await apiFetch(`/api/reports/track/${trackingId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    setSelected((cur) => (cur && cur.tracking_id === trackingId ? { ...cur, status: next } : cur));
    const body = await apiFetch(`/api/reports${query}`).then((r) => r.json());
    setReports(body.items ?? []);
    refreshAll();
    const map = mapRef.current;
    if (map?.getSource("src-reports") && !lapseOn) {
      const data = await apiFetch(`/api/reports/geojson${query}`).then((r) => r.json());
      (map.getSource("src-reports") as maplibregl.GeoJSONSource).setData(withStacks(data));
    }
  }

  const countBy = (key: "category" | "severity") =>
    all.reduce<Record<string, number>>((acc, r) => ((acc[r[key]] = (acc[r[key]] ?? 0) + 1), acc), {});
  const catCounts = countBy("category");
  const sevCounts = countBy("severity");
  const filtered = Boolean(category || severity || status);

  return (
    <div className="relative flex h-full min-h-0">
      {/* left control rail */}
      <aside
        className={`z-10 flex shrink-0 flex-col border-r border-slate-800 bg-slate-950/90 backdrop-blur transition-[width] ${
          panel ? "w-[22rem] max-w-[88vw]" : "w-0 overflow-hidden border-r-0"
        }`}
      >
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4 text-sm">
          <div>
            <p className="eyebrow">Module 1</p>
            <h2 className="text-base font-semibold text-white">City Monitor</h2>
            <p className="mt-1 rounded-md bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-200 ring-1 ring-amber-500/30">
              Map dots are citizen reports, not verified issues.
            </p>
          </div>

          <div>
            <p className="eyebrow mb-2">Category</p>
            <div className="flex flex-wrap gap-1.5">
              <button className={chip(!category)} onClick={() => setCategory("")}>
                All <span className="num opacity-70">{all.length}</span>
              </button>
              {Object.keys(CATEGORY_LABEL).map((c) => (
                <button key={c} className={chip(category === c)} onClick={() => setCategory(category === c ? "" : c)}>
                  {CATEGORY_LABEL[c]} <span className="num opacity-70">{catCounts[c] ?? 0}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="eyebrow mb-2">Severity</p>
            <div className="grid grid-cols-4 gap-1.5">
              {SEVERITY_ORDER.map((s) => (
                <button
                  key={s}
                  onClick={() => setSeverity(severity === s ? "" : s)}
                  className="rounded-lg border px-1 py-1.5 text-center text-[11px] transition-colors"
                  style={{
                    borderColor: severity === s ? SEVERITY_COLOR[s] : "#263554",
                    background: severity === s ? `${SEVERITY_COLOR[s]}26` : "transparent",
                    color: severity === s ? "#fff" : "#8696b4",
                  }}
                >
                  <span className="block h-1 rounded-full" style={{ background: SEVERITY_COLOR[s], opacity: severity && severity !== s ? 0.3 : 1 }} />
                  <span className="mt-1 block">{titleCase(s)}</span>
                  <span className="num block text-sm font-semibold text-slate-100">{sevCounts[s] ?? 0}</span>
                </button>
              ))}
            </div>
          </div>

          <label className="block">
            <span className="eyebrow">Status</span>
            <select className="mt-1.5 w-full px-2 py-1.5 text-xs" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {titleCase(s)}
                </option>
              ))}
            </select>
          </label>

          {filtered ? (
            <button
              className="text-xs text-sky-300 underline-offset-2 hover:underline"
              onClick={() => {
                setCategory("");
                setSeverity("");
                setStatus("");
              }}
            >
              Clear filters
            </button>
          ) : null}

          <div>
            <p className="eyebrow mb-1.5">Map</p>
            <Switch checked={heat} onChange={() => setHeat(!heat)} label="Report density heatmap" />
            {(Object.keys(LAYER_LABELS) as LayerId[]).map((id) => (
              <Switch key={id} checked={visible[id]} onChange={() => setVisible((cur) => ({ ...cur, [id]: !cur[id] }))} label={LAYER_LABELS[id]} />
            ))}
            <p className="mt-1 px-2 text-[11px] text-slate-500">
              Roads {summary.roads ?? "—"} · Buildings {summary.buildings ?? "—"}
            </p>
          </div>

          <div>
            <p className="eyebrow mb-2">
              Reports <span className="num text-slate-300">({reports.length})</span>
            </p>
            <ul className="space-y-2">
              {reports.map((item) => (
                <li key={item.tracking_id}>
                  <button
                    onClick={() => pick(item)}
                    className={`w-full rounded-lg border p-2.5 text-left transition-colors ${
                      selected?.tracking_id === item.tracking_id ? "border-sky-400 bg-sky-500/10" : "border-slate-800 bg-slate-900/40 hover:border-slate-600"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] text-slate-300">{item.tracking_id}</span>
                      <SeverityBadge value={item.severity} />
                    </div>
                    <p className="mt-1 text-xs font-medium text-slate-100">{categoryLabel(item.category)}</p>
                    <p className="line-clamp-2 text-[11px] text-slate-400">{item.description}</p>
                    {item.location_text ? <p className="mt-0.5 truncate text-[11px] text-slate-500">📍 {item.location_text}</p> : null}
                    {item.evidence?.length ? (
                      <div className="mt-1.5 flex gap-1.5">
                        {item.evidence.slice(0, 3).map((file) => (
                          <img
                            key={file.id}
                            src={file.url}
                            alt={`Photo for ${item.tracking_id}`}
                            loading="lazy"
                            className="h-12 w-16 rounded border border-slate-700 object-cover"
                            onError={(e) => ((e.currentTarget.style.display = "none"))}
                          />
                        ))}
                      </div>
                    ) : null}
                  </button>
                </li>
              ))}
              {!reports.length ? <li className="text-xs text-slate-500">No reports match these filters.</li> : null}
            </ul>
          </div>
        </div>
      </aside>

      {/* map */}
      <div className="relative min-w-0 flex-1">
        <div ref={mapNode} style={{ position: "absolute", inset: 0 }} />

        <MapToolbar view3d={view3d} onView3d={setView3d} basemap={basemap} onBasemap={setBase} />

        <button
          onClick={() => setPanel(!panel)}
          className="glass absolute left-3 top-3 z-10 grid h-9 w-9 place-items-center text-slate-300 hover:text-white"
          aria-label={panel ? "Hide panel" : "Show panel"}
        >
          <Icon name="layers" className="h-4 w-4" />
        </button>

        <div className="glass pointer-events-none absolute left-1/2 top-3 z-10 hidden -translate-x-1/2 items-center gap-5 px-4 py-2 sm:flex">
          <Stat label="Shown" value={reports.length} />
          <Stat label="Critical" value={sevCounts.critical ?? 0} color={SEVERITY_COLOR.critical} />
          <Stat label="High" value={sevCounts.high ?? 0} color={SEVERITY_COLOR.high} />
          <Stat label="Total reports" value={all.length} />
        </div>

        <div className="glass absolute left-1/2 top-[4.25rem] z-10 w-[min(26rem,calc(100%-6rem))] -translate-x-1/2 px-3 py-2 text-[11px] text-slate-300">
          <div className="flex items-center justify-between gap-2">
            <button
              onClick={() => setLapseOn(!lapseOn)}
              className={`rounded-md px-2 py-1 font-medium ${lapseOn ? "bg-amber-400 text-slate-950" : "bg-slate-800/80 text-slate-200 hover:text-white"}`}
            >
              {lapseOn ? "Exit time-lapse" : "⏵ Time-lapse · last 30 days"}
            </button>
            {lapseOn && lapse ? (
              <span className="num text-slate-300">
                {fmtDay(cursor)} · {lapseShown} of {lapse.items.length} reports
              </span>
            ) : null}
          </div>
          {lapseOn && lapse && lapse.items.length > 0 ? (
            <div className="mt-2 flex items-center gap-2">
              <button
                aria-label={playing ? "Pause" : "Play"}
                className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-sky-600 text-white hover:bg-sky-500"
                onClick={() => {
                  if (!playing && cursor >= lapse.end) setCursor(lapse.start);
                  setPlaying(!playing);
                }}
              >
                {playing ? "❚❚" : "▶"}
              </button>
              <input
                type="range"
                aria-label="Time-lapse position"
                className="min-w-0 flex-1 accent-sky-400"
                min={lapse.start}
                max={lapse.end}
                step={(lapse.end - lapse.start) / 720}
                value={cursor}
                onChange={(e) => {
                  setPlaying(false);
                  setCursor(Number(e.target.value));
                }}
              />
            </div>
          ) : null}
          {lapseOn && lapse && lapse.items.length === 0 ? (
            <p className="mt-2 text-slate-400">No reports were received in the last 30 days, so there is nothing to replay.</p>
          ) : null}
          {lapseOn && lapse ? <p className="mt-1 text-[10.5px] text-slate-500">Each point appears when the citizen report was received. Reports, not verified issues.</p> : null}
          {lapseError ? <p className="mt-1 text-amber-300">{lapseError}</p> : null}
        </div>

        <div className="glass absolute bottom-3 left-3 z-10 px-3 py-2 text-[11px] text-slate-300">
          <p className="eyebrow mb-1">Severity</p>
          <div className="flex gap-3">
            {SEVERITY_ORDER.map((s) => (
              <span key={s} className="flex items-center gap-1">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: SEVERITY_COLOR[s] }} />
                {titleCase(s)}
              </span>
            ))}
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" /> Resolved (unverified)
            </span>
          </div>
        </div>

        {selected ? (
          <div className="glass rise absolute bottom-3 right-14 z-10 w-72 max-w-[calc(100%-1.5rem)] p-3.5 text-xs">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-mono text-[11px] text-slate-400">{selected.tracking_id}</p>
                <p className="text-sm font-semibold text-white">{categoryLabel(selected.category)}</p>
              </div>
              <button className="text-slate-500 hover:text-white" aria-label="Close" onClick={() => setSelected(null)}>
                ✕
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <SeverityBadge value={selected.severity} />
              <StatusBadge value={selected.status} />
            </div>
            <p className="mt-2 text-slate-300">{selected.description}</p>
            {selected.location_text ? <p className="mt-1 text-[12px] text-slate-400">Place: {selected.location_text}</p> : null}
            {selected.evidence?.length ? (
              <div className="mt-2 space-y-2">
                <p className="eyebrow">
                  Photos ({selected.evidence.length})
                </p>
                {selected.evidence.map((file) => (
                  <a key={file.id} href={file.url} target="_blank" rel="noreferrer" title="Open the full photo in a new tab" className="block">
                    <img
                      src={file.url}
                      alt={`Photo attached to ${selected.tracking_id}`}
                      className="max-h-48 w-full rounded border border-slate-700 object-cover"
                      onError={(e) => ((e.currentTarget.style.display = "none"))}
                    />
                  </a>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-[11px] text-slate-500">No photo attached.</p>
            )}
            {stackCount > 1 && (
              <p className="mt-2 text-[11px] text-rose-200">
                {stackCount} reports share this exact point (often filed without moving the pin). Showing the most severe on top.
              </p>
            )}
            <p className="mt-2 text-[11px] text-amber-200/90">Citizen report, not a verified issue.</p>
            <label className="mt-3 block">
              <span className="eyebrow">Update status</span>
              <select
                className="mt-1 w-full px-2 py-1.5 text-xs"
                value={selected.status}
                onChange={(e) => void setReportStatus(selected.tracking_id, e.target.value)}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <Link
              to={`/investigator/${selected.tracking_id}`}
              className="mt-3 flex items-center justify-center gap-1.5 rounded-lg bg-sky-600 px-3 py-2 font-medium text-white hover:bg-sky-500"
            >
              Open in Investigator <Icon name="arrow" className="h-3.5 w-3.5" />
            </Link>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="text-center">
      <div className="num text-lg font-semibold leading-5" style={{ color: color ?? "#fff" }}>
        {value}
      </div>
      <div className="eyebrow">{label}</div>
    </div>
  );
}

async function loadLayers(map: maplibregl.Map, query: string) {
  const collections = await Promise.all(
    (Object.keys(LAYER_ENDPOINTS) as LayerId[]).map(async (id) => {
      const data = (await apiFetch(LAYER_ENDPOINTS[id]).then((r) => r.json())) as GeoJSON;
      return [id, data] as const;
    }),
  );
  for (const [id, data] of collections) {
    if (!map.getSource(`src-${id}`)) map.addSource(`src-${id}`, { type: "geojson", data });
  }
  addFill(map, "study-fill", "src-study", "#22d3ee", 0.05);
  addLine(map, "study-line", "src-study", "#22d3ee", 2);
  addLine(map, "upazila-line", "src-upazila", "#c084fc", 2, [2, 2]);
  addFill(map, "wards-fill", "src-wards", "#f59e0b", 0.1);
  addLine(map, "wards-line", "src-wards", "#f59e0b", 1);
  addLine(map, "roads-line", "src-roads", "#6b7fa3", 1.2);
  addFill(map, "buildings-fill", "src-buildings", "#8aa0c4", 0.28);
  await addBuildings3D(map);
  addFill(map, "water-fill", "src-water", "#0ea5e9", 0.4);
  addLine(map, "water-line", "src-water", "#38bdf8", 1);
  addLine(map, "drains-line", "src-drains", "#2dd4bf", 2);

  if (!map.getSource("src-reports")) {
    const reports = (await apiFetch(`/api/reports/geojson${query}`).then((r) => r.json())) as GeoJSON;
    map.addSource("src-reports", { type: "geojson", data: withStacks(reports) });
    map.addSource("src-selected", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    // density heatmap, weighted by reported severity (a visual aid only)
    map.addLayer({
      id: "reports-heat",
      type: "heatmap",
      source: "src-reports",
      paint: {
        "heatmap-weight": ["match", ["get", "severity"], "critical", 1, "high", 0.75, "medium", 0.5, 0.3],
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 12, 22, 16, 48],
        "heatmap-intensity": 1.1,
        "heatmap-opacity": 0.75,
        "heatmap-color": [
          "interpolate",
          ["linear"],
          ["heatmap-density"],
          0, "rgba(34,211,238,0)",
          0.25, "rgba(34,211,238,0.55)",
          0.5, "rgba(250,204,21,0.8)",
          0.8, "rgba(251,146,60,0.9)",
          1, "rgba(244,63,94,0.95)",
        ],
      },
    });
    // ring around places where several reports sit on exactly the same point
    map.addLayer({
      id: "reports-stack",
      type: "circle",
      source: "src-reports",
      filter: [">", ["get", "stack"], 1],
      paint: {
        "circle-radius": ["+", 9, ["*", 3, ["sqrt", ["get", "stack"]]]],
        "circle-color": "rgba(244,63,94,0.10)",
        "circle-stroke-color": "#f43f5e",
        "circle-stroke-width": 2,
        "circle-stroke-opacity": 0.9,
      },
    });
    map.addLayer({
      id: "reports-circle",
      type: "circle",
      source: "src-reports",
      layout: { "circle-sort-key": ["match", ["get", "severity"], "critical", 4, "high", 3, "medium", 2, 1] },
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 5, 17, 9],
        "circle-stroke-width": 1.5,
        "circle-stroke-color": "#070d1a",
        "circle-color": [
          "match",
          ["get", "status"],
          "insufficient_evidence", "#94a3b8",
          "resolved_unverified", "#34d399",
          ["match", ["get", "severity"], "critical", "#f43f5e", "high", "#fb923c", "medium", "#facc15", "#38bdf8"],
        ],
      },
    });
    map.addLayer({
      id: "reports-selected",
      type: "circle",
      source: "src-selected",
      paint: { "circle-radius": 16, "circle-color": "rgba(34,211,238,0.12)", "circle-stroke-color": "#22d3ee", "circle-stroke-width": 2 },
    });
  }
}

function addFill(map: maplibregl.Map, id: string, source: string, color: string, opacity: number) {
  if (map.getLayer(id)) return;
  map.addLayer({
    id,
    type: "fill",
    source,
    filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
    paint: { "fill-color": color, "fill-opacity": opacity },
  });
}

function addLine(map: maplibregl.Map, id: string, source: string, color: string, width: number, dash?: number[]) {
  if (map.getLayer(id)) return;
  map.addLayer({
    id,
    type: "line",
    source,
    paint: { "line-color": color, "line-width": width, ...(dash ? { "line-dasharray": dash } : {}) },
  });
}
