import { useEffect, useMemo, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import { apiFetch } from "../api";
import { createMap, getBasemap, onStyleReady, setBasemap, type Basemap } from "../map";
import ROAD_LINES from "../data/noakhaliRoadLines.json";
import ROAD_NETWORK from "../data/noakhaliRoadNetwork.json";
import { Badge, Donut, HBars, Kpi, Notice, PageHeader, Panel, categoryLabel, titleCase, type Slice } from "../ui";
import {
  ALL_CASES,
  DISTRICT_FACTS as D,
  EVIDENCE_LABEL,
  FLOOD_DRAINAGE_LOG,
  HOSPITAL_REPAIR_LAKH,
  HOSPITAL_ROAD_SPEND,
  HOSPITAL_TOTAL_LAKH,
  KNOWN_UNKNOWN,
  RECORD_REQUESTS,
  RECURRENCE_COLOR,
  RECURRENCE_LABEL,
  ROADS,
  SOURCES,
  WATERLOGGING,
  WORKSTREAMS,
  type Evidence,
  type Recurrence,
  type RoadCase,
} from "../data/noakhaliInvestigation";

type Feat = { type: "Feature"; geometry: unknown; properties: Record<string, unknown> | null };
type FC = { type: "FeatureCollection"; features: Feat[] };
const RECURRENCES = Object.keys(RECURRENCE_LABEL) as Recurrence[];
const DISTRICT: [[number, number], [number, number]] = [[90.93, 22.3], [91.32, 23.12]];
const EMPTY: FC = { type: "FeatureCollection", features: [] };
const lakh = (v: number) => `৳${v.toLocaleString("en-US", { maximumFractionDigits: 2 })} lakh`;
const crore = (v: number) => `৳${v.toLocaleString("en-US")} crore`;

const REAL = ROAD_LINES as unknown as FC;

/** Road condition scale. "good" only ever means verified. "unverified" is the honest default. */
type NetStatus = "good" | "fair" | "poor" | "failed" | "wl" | "unverified";
const NET_COLOR: Record<NetStatus, string> = { good: "#34d399", fair: "#facc15", poor: "#fb923c", failed: "#ef4444", wl: "#2dd4bf", unverified: "#7d8aa3" };
const NET_LABEL: Record<NetStatus, string> = { good: "Good", fair: "Fair", poor: "Poor", failed: "Failed / repeat repair", wl: "Waterlogging-affected", unverified: "Unverified (no evidence)" };
const NET_ORDER: NetStatus[] = ["good", "fair", "poor", "failed", "wl", "unverified"];
const RANK: Record<NetStatus, number> = { unverified: 0, good: 1, fair: 2, poor: 3, failed: 4, wl: 0 };
const FROM_RECURRENCE: Record<Recurrence, NetStatus> = { repeat: "failed", repair: "poor", damage: "fair", planned: "unverified" };
const FROM_SEVERITY: Record<string, NetStatus> = { low: "fair", medium: "poor", high: "failed", critical: "failed" };

/** Roads the dossier documents (Hospital Road, waterlogging roads). */
const EVIDENCE_BY_OSM = new Map<number, NetStatus>();
for (const f of REAL.features) {
  const id = Number(f.properties?.osm_id);
  if (f.properties?.caseId) EVIDENCE_BY_OSM.set(id, FROM_RECURRENCE[ALL_CASES.find((c) => c.id === f.properties?.caseId)?.recurrence ?? "planned"]);
  else if (f.properties?.wl && !EVIDENCE_BY_OSM.has(id)) EVIDENCE_BY_OSM.set(id, "wl");
}

type Seg = { feat: Feat; id: number; name: string; highway: string; coords: number[][]; km: number; sim: NetStatus };
const kmOf = (coords: number[][]) => {
  let m = 0;
  for (let i = 1; i < coords.length; i++) m += Math.hypot((coords[i][0] - coords[i - 1][0]) * 102_000, (coords[i][1] - coords[i - 1][1]) * 111_000);
  return m / 1000;
};
const hash01 = (n: number) => {
  let h = (n ^ 0x9e3779b9) >>> 0;
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35) >>> 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
};
const SEGS: Seg[] = (ROAD_NETWORK as unknown as FC).features.map((f) => {
  const p = f.properties as { i: number; n: string; h: string };
  const coords = (f.geometry as { coordinates: number[][] }).coordinates;
  return { feat: f, id: p.i, name: p.n, highway: p.h, coords, km: kmOf(coords), sim: "unverified" };
});
// ILLUSTRATIVE ONLY: a smooth, repeatable pseudo-condition (worse near the centre) so the colour scheme can be previewed.
{
  const scores = SEGS.map((g) => {
    const [x, y] = g.coords[Math.floor(g.coords.length / 2)];
    const field = 0.5 + 0.5 * Math.sin(x * 260 + 1.3) * Math.cos(y * 300);
    const centre = Math.max(0, 1 - Math.hypot((x - 91.0995) * 102, (y - 22.8696) * 111) / 3);
    return 0.35 * field + 0.35 * centre + 0.45 * hash01(g.id);
  });
  const sorted = [...scores].sort((a, b) => a - b);
  const q = (f: number) => sorted[Math.floor(f * (sorted.length - 1))];
  const [q1, q2, q3] = [q(0.28), q(0.58), q(0.85)];
  SEGS.forEach((g, i) => (g.sim = scores[i] <= q1 ? "good" : scores[i] <= q2 ? "fair" : scores[i] <= q3 ? "poor" : "failed"));
}

type Mode = "preview" | "evidence";
type ReportItem = { severity: string; category: string; status: string; demo: boolean };
type ReportHit = { status: NetStatus; items: ReportItem[] };
type ReportPoint = ReportItem & { x: number; y: number };
/** Citizen reports within 35 m of each road; the worst severity sets the road's status. */
function matchReports(points: ReportPoint[]): Map<number, ReportHit> {
  const out = new Map<number, ReportHit>();
  for (const pt of points) {
    const status = FROM_SEVERITY[pt.severity];
    if (!status) continue;
    let best: Seg | null = null;
    let bestD = 35;
    for (const g of SEGS) {
      for (let i = 1; i < g.coords.length; i++) {
        const ax = (g.coords[i - 1][0] - pt.x) * 102_000, ay = (g.coords[i - 1][1] - pt.y) * 111_000;
        const bx = (g.coords[i][0] - pt.x) * 102_000, by = (g.coords[i][1] - pt.y) * 111_000;
        const dx = bx - ax, dy = by - ay;
        const t = Math.max(0, Math.min(1, dx || dy ? -(ax * dx + ay * dy) / (dx * dx + dy * dy) : 0));
        const d = Math.hypot(ax + t * dx, ay + t * dy);
        if (d < bestD) { bestD = d; best = g; }
      }
    }
    if (!best) continue;
    const hit = out.get(best.id) ?? { status: "unverified" as NetStatus, items: [] };
    if (RANK[status] > RANK[hit.status]) hit.status = status;
    hit.items.push({ severity: pt.severity, category: pt.category, status: pt.status, demo: pt.demo });
    out.set(best.id, hit);
  }
  return out;
}
const SEG_BY_ID = new Map(SEGS.map((g) => [g.id, g]));
function buildNetwork(mode: Mode, reports: Map<number, ReportHit>): { fc: FC; km: Record<NetStatus, number>; total: number } {
  const km: Record<NetStatus, number> = { good: 0, fair: 0, poor: 0, failed: 0, wl: 0, unverified: 0 };
  const features = SEGS.map((g) => {
    const ev = EVIDENCE_BY_OSM.get(g.id);
    const status: NetStatus = ev ?? (mode === "preview" ? g.sim : reports.get(g.id)?.status ?? "unverified");
    km[status] += g.km;
    return { ...g.feat, properties: { status, name: g.name, highway: g.highway, osm: g.id } };
  });
  return { fc: { type: "FeatureCollection", features }, km, total: Object.values(km).reduce((a, b) => a + b, 0) };
}
const MUNICIPALITY: [[number, number], [number, number]] = [[91.075, 22.847], [91.123, 22.891]];
const WL_COUNT = new Set(REAL.features.filter((f) => f.properties?.wl).map((f) => f.properties?.wl)).size;

/** Real OSM line where we have one; otherwise a short dashed stub at the indicative position (NOT an alignment). */
const lineFor = (c: RoadCase): Feat[] => {
  const props = { id: c.id, recurrence: c.recurrence, evidence: c.evidence };
  const real = REAL.features.filter((f) => f.properties?.caseId === c.id);
  return real.map((f) => ({ ...f, properties: { ...props, approx: false } }));
};
const caseLines = (rows: RoadCase[]): FC => ({ type: "FeatureCollection", features: rows.flatMap(lineFor) });

export default function Observatory() {
  const mapNode = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [basemap, setBase] = useState<Basemap>(getBasemap);
  const [filter, setFilter] = useState<Recurrence | "all">("all");
  const [upazila, setUpazila] = useState("all");
  const [selectedId, setSelectedId] = useState("R01");
  const [mode, setMode] = useState<Mode>("preview");
  const [reportStatus, setReportStatus] = useState<Map<number, ReportHit>>(new Map());
  const [card, setCard] = useState<{ kind: "road"; id: number } | { kind: "case"; id: string } | null>(null);
  const [reportInfo, setReportInfo] = useState<{ total: number; demo: number } | "login" | null>(null);
  const net = useMemo(() => buildNetwork(mode, reportStatus), [mode, reportStatus]);

  const upazilas = useMemo(() => ["all", ...Array.from(new Set(ALL_CASES.map((c) => c.upazila))).sort()], []);
  const visible = useMemo(
    () => ALL_CASES.filter((c) => (filter === "all" || c.recurrence === filter) && (upazila === "all" || c.upazila === upazila)),
    [filter, upazila],
  );
  const selected = ALL_CASES.find((c) => c.id === selectedId) ?? ALL_CASES[0];

  // ---- headline numbers, all derived from the register ----
  const evidenceCounts = (["A", "B", "C"] as Evidence[]).map((e) => ({ e, n: ROADS.filter((r) => r.evidence === e).length }));
  const recurrenceCounts = RECURRENCES.map((k) => ({ k, n: ROADS.filter((r) => r.recurrence === k).length }));
  const repairShare = Math.round((HOSPITAL_REPAIR_LAKH / 179) * 100);
  const fundedShare = Math.round((D.lgedRepairedCrore / D.lgedNeedCrore) * 100);
  const damagedShare = Math.round((D.municipalityDamagedKm / D.municipalityNetworkKm) * 100);

  // ---- map ----
  useEffect(() => {
    if (!mapNode.current || mapRef.current) return;
    const map = createMap(mapNode.current);
    mapRef.current = map;
    let alive = true;
    onStyleReady(map, () => {
      if (!alive) return;
      map.resize();
      map.addSource("network", { type: "geojson", data: net.fc as never });
      map.addSource("cases", { type: "geojson", data: caseLines(ALL_CASES) as never });
      map.addSource("picked", { type: "geojson", data: EMPTY as never });
      const color = ["match", ["get", "recurrence"], "repeat", RECURRENCE_COLOR.repeat, "repair", RECURRENCE_COLOR.repair, "damage", RECURRENCE_COLOR.damage, RECURRENCE_COLOR.planned] as never;
      const statusColor = ["match", ["get", "status"], ...NET_ORDER.flatMap((k) => [k, NET_COLOR[k]]), NET_COLOR.unverified] as never;
      const cls = ["match", ["get", "highway"], ["primary", "trunk", "secondary"], 2.6, ["tertiary", "unclassified"], 1.9, 1.3] as never;
      // grey (unverified) roads first so coloured roads always draw on top of them
      map.addLayer({ id: "net-grey", type: "line", source: "network", filter: ["==", ["get", "status"], "unverified"], layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": NET_COLOR.unverified, "line-opacity": 0.9, "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["*", cls, 0.3], 14, ["*", cls, 0.55], 17, ["*", cls, 1.4]] as never } });
      map.addLayer({ id: "net-colored", type: "line", source: "network", filter: ["!=", ["get", "status"], "unverified"], layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": statusColor, "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["*", cls, 0.5], 14, ["*", cls, 0.9], 17, ["*", cls, 1.8]] as never } });
      map.addLayer({ id: "picked-line", type: "line", source: "picked", layout: { "line-cap": "round" }, paint: { "line-color": "#ffffff", "line-width": 5, "line-opacity": 0.55 } });
      // one thin line, one colour per road, no outlines or dashes
      map.addLayer({ id: "case-solid", type: "line", source: "cases", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": color, "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.6, 14, 2.4, 17, 4] as never } });
      map.addLayer({ id: "net-hit", type: "line", source: "network", paint: { "line-color": "#000", "line-width": 12, "line-opacity": 0 } }, "picked-line");
      map.addLayer({ id: "case-hit", type: "line", source: "cases", paint: { "line-color": "#000", "line-width": 14, "line-opacity": 0 } });
      map.on("click", "case-hit", (e) => {
        const id = e.features?.[0]?.properties?.id as string | undefined;
        if (id) {
          setSelectedId(id);
          setCard({ kind: "case", id });
        }
      });
      map.on("click", "net-hit", (e) => {
        if (map.queryRenderedFeatures(e.point, { layers: ["case-hit"] }).length) return; // a register road wins
        const osm = Number(e.features?.[0]?.properties?.osm);
        if (osm) setCard({ kind: "road", id: osm });
      });
      for (const layer of ["case-hit", "net-hit"]) {
        map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
      }
      map.fitBounds(MUNICIPALITY, { padding: 20, duration: 0 });
      setReady(true);
    });
    return () => {
      alive = false;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("cases") as maplibregl.GeoJSONSource).setData(caseLines(visible) as never);
  }, [visible, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const seg = card?.kind === "road" ? SEG_BY_ID.get(card.id) : undefined;
    (map.getSource("picked") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: seg ? [seg.feat] : lineFor(selected) } as never);
  }, [selected, card, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("network") as maplibregl.GeoJSONSource).setData(net.fc as never);
  }, [net, ready]);

  // Live citizen reports colour the roads they sit on (staff login required by the API).
  useEffect(() => {
    let alive = true;
    void apiFetch("/api/reports/geojson", {}, { quiet: true })
      .then(async (r) => {
        if (!alive) return;
        if (!r.ok) return setReportInfo("login");
        const data = (await r.json()) as { features: Array<{ geometry: { coordinates: number[] }; properties: { severity: string; category: string; status: string; is_demo: boolean } }> };
        const pts: ReportPoint[] = data.features.map((f) => ({ x: f.geometry.coordinates[0], y: f.geometry.coordinates[1], severity: f.properties.severity, category: f.properties.category, status: f.properties.status, demo: f.properties.is_demo }));
        setReportStatus(matchReports(pts));
        setReportInfo({ total: pts.length, demo: data.features.filter((f) => f.properties.is_demo).length });
      })
      .catch(() => alive && setReportInfo("login"));
    return () => { alive = false; };
  }, []);

  const flyTo = (c: RoadCase) => {
    setSelectedId(c.id);
    setCard({ kind: "case", id: c.id });
    mapRef.current?.flyTo({ center: c.at, zoom: c.id === "R01" ? 15.3 : c.id === "W01" ? 10.5 : 12.5, duration: 900 });
  };
  const info = useMemo(() => {
    if (!card) return null;
    type B = { t: string; c: string };
    if (card.kind === "case") {
      const c = ALL_CASES.find((x) => x.id === card.id);
      if (!c) return null;
      return {
        title: c.road, subtitle: `${c.id} · ${c.upazila}`,
        badges: [{ t: RECURRENCE_LABEL[c.recurrence], c: RECURRENCE_COLOR[c.recurrence] }, { t: EVIDENCE_LABEL[c.evidence], c: "#94a3b8" }] as B[],
        lead: c.issue, bullets: c.detail ?? [],
        foot: c.precision === "osm" ? c.locationNote : `${c.locationNote} This road is not drawn on the map yet.`,
      };
    }
    const g = SEG_BY_ID.get(card.id);
    if (!g) return null;
    const ev = EVIDENCE_BY_OSM.get(g.id);
    const hit = reportStatus.get(g.id);
    const shown: NetStatus = ev ?? (mode === "preview" ? g.sim : hit?.status ?? "unverified");
    const wlName = REAL.features.find((f) => Number(f.properties?.osm_id) === g.id && f.properties?.wl)?.properties?.wl as string | undefined;
    const hotspot = WATERLOGGING.find((h) => wlName && h.osmNames?.includes(wlName));
    const jul = FLOOD_DRAINAGE_LOG.find((e) => e.date === "Jul 2025");
    let lead = "No problem is recorded for this road, and no condition evidence exists for it yet.";
    const bullets: string[] = [];
    let source = "No evidence";
    if (ev === "wl") {
      lead = `Reported waterlogging after heavy rain${hotspot ? ` (${hotspot.name})` : ""}, July 2025.`;
      if (jul) bullets.push(jul.text);
      bullets.push("A road repaired without fixing its drainage may fail again.");
      source = "Documented (BSS / Daily Star)";
    }
    if (hit) {
      lead = ev ? lead : `${hit.items.length} citizen report${hit.items.length > 1 ? "s" : ""} within 35 m of this road.`;
      hit.items.forEach((r) => bullets.push(`${categoryLabel(r.category)}, ${r.severity} severity, ${titleCase(r.status)}${r.demo ? " (demo report)" : ""}`));
      if (!ev) source = "Citizen reports";
    }
    if (!ev && !hit && mode === "preview") {
      lead = "No problem is recorded for this road. Its colour is simulated for the preview.";
      source = "Simulated";
    }
    return {
      title: g.name || `Unnamed ${titleCase(g.highway).toLowerCase()} road`, subtitle: `OSM way ${g.id} · ${g.km.toFixed(2)} km`,
      badges: [{ t: NET_LABEL[shown], c: NET_COLOR[shown] }, { t: source, c: "#94a3b8" }, { t: titleCase(g.highway), c: "#64748b" }] as B[],
      lead, bullets, foot: "Real OSM geometry. Condition is evidence-based unless marked simulated.",
    };
  }, [card, mode, reportStatus]);

  const resetView = () => mapRef.current?.fitBounds(DISTRICT, { padding: 30, duration: 700 });
  const focusMaijdee = () => mapRef.current?.fitBounds(MUNICIPALITY, { padding: 20, duration: 900 });

  const donut: Slice[] = recurrenceCounts.map(({ k, n }) => ({ label: RECURRENCE_LABEL[k], value: n, color: RECURRENCE_COLOR[k] }));
  const spendRows: Slice[] = HOSPITAL_ROAD_SPEND.map((r) => ({
    label: `${r.period} · ${r.work}${r.counted ? "" : " (allocation, not spend)"}`,
    value: r.lakh,
    color: !r.counted ? "#475569" : r.period === "2018" ? "#60a5fa" : "#ef4444",
  }));

  return (
    <div className="space-y-4 p-4 md:p-6">
      <PageHeader eyebrow="Noakhali · Infrastructure accountability" title="Noakhali Infrastructure Observatory">
        <Badge color="#22d3ee">Research dossier · updated through 14 Nov 2026</Badge>
      </PageHeader>

      <Notice tone="warn">
        This is an evidence-based investigation, not an audit. Reported figures come from different dates and categories and must not be added together.
        A contract award is not proof of completed work or payment, and allegations about materials or subcontracting are not established findings.
        No corruption score or contractor ranking is shown, because the evidence does not support one.
      </Notice>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Kpi label="Roads on the register" value={ROADS.length} sub={`${evidenceCounts.map((c) => `${c.n}${c.e}`).join(" · ")} evidence class`} icon="map" color="#22d3ee" />
        <Kpi label="Documented repeat repair" value={recurrenceCounts.find((c) => c.k === "repeat")?.n ?? 0} sub="Hospital Road, Maijdee (only case with a repair history)" icon="flame" color="#ef4444" />
        <Kpi label="Hospital Road spend on repairs" value={`${repairShare}%`} sub={`${lakh(HOSPITAL_REPAIR_LAKH)} of repairs vs ${lakh(179)} built in 2018`} icon="coin" color="#fb923c" />
        <Kpi label="Municipal roads severely damaged" value={`${damagedShare}%`} sub={`${D.municipalityDamagedKm} of ${D.municipalityNetworkKm} km (July 2026 report)`} icon="alert" color="#facc15" />
      </div>

      {/* map + register + charts */}
      <div className="grid gap-4 xl:grid-cols-[19rem_minmax(0,1fr)_21rem]">
        <Panel title="Road register" subtitle={`${visible.length} of ${ALL_CASES.length} shown`} className="flex max-h-[44rem] flex-col xl:max-h-[40rem]">
          <div className="mb-2 flex flex-wrap gap-1.5">
            <button className={chip(filter === "all")} onClick={() => setFilter("all")}>All</button>
            {RECURRENCES.map((k) => (
              <button key={k} className={chip(filter === k)} onClick={() => setFilter(k)} style={filter === k ? { background: RECURRENCE_COLOR[k], color: "#0b1220" } : undefined}>
                <span className="mr-1 inline-block h-2 w-2 rounded-full align-middle" style={{ background: RECURRENCE_COLOR[k] }} />
                {RECURRENCE_LABEL[k].split(" (")[0].split(" /")[0]}
              </button>
            ))}
          </div>
          <select value={upazila} onChange={(e) => setUpazila(e.target.value)} className="mb-2 w-full px-2 py-1.5 text-xs" aria-label="Filter by upazila">
            {upazilas.map((u) => (
              <option key={u} value={u}>{u === "all" ? "All upazilas" : u}</option>
            ))}
          </select>
          <ul className="-mr-2 min-h-0 flex-1 space-y-1 overflow-y-auto pr-2">
            {visible.map((c) => (
              <li key={c.id}>
                <button onClick={() => flyTo(c)} className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${c.id === selectedId ? "border-sky-400/70 bg-sky-500/10" : "border-slate-800 hover:border-slate-600 hover:bg-slate-800/50"}`}>
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: RECURRENCE_COLOR[c.recurrence] }} />
                    <span className="num text-slate-500">{c.id}</span>
                    <span className="text-slate-400">{c.upazila}</span>
                    <span className="ml-auto rounded bg-slate-800 px-1.5 text-slate-300">{c.evidence}</span>
                  </div>
                  <p className="mt-0.5 text-xs leading-snug text-slate-100">{c.road}</p>
                </button>
              </li>
            ))}
            {!visible.length ? <li className="text-xs text-slate-500">No roads match this filter.</li> : null}
          </ul>
        </Panel>

        <section className="panel relative overflow-hidden p-0">
          <div ref={mapNode} className="h-[34rem] w-full xl:h-[40rem]" />
          <div className="glass pointer-events-auto absolute left-3 top-3 z-10 flex flex-wrap gap-1 p-1.5 text-[11px]">
            <button className={seg(false)} onClick={resetView}>District</button>
            <button className={seg(false)} onClick={focusMaijdee}>Municipality network</button>
            <span className="mx-1 w-px bg-slate-700" />
            <button className={seg(mode === "preview")} onClick={() => setMode("preview")}>Illustrative conditions</button>
            <button className={seg(mode === "evidence")} onClick={() => setMode("evidence")}>Real evidence only</button>
            <span className="mx-1 w-px bg-slate-700" />
            {(["dark", "standard", "satellite"] as const).map((b) => (
              <button key={b} className={seg(basemap === b)} onClick={() => { setBase(b); if (mapRef.current) setBasemap(mapRef.current, b); }}>
                {b === "dark" ? "Dark" : b === "standard" ? "Street" : "Satellite"}
              </button>
            ))}
          </div>
          {info ? (
            <div className="glass absolute right-3 top-3 z-20 max-h-[calc(100%-1.5rem)] w-72 overflow-y-auto p-3 text-xs">
              <button onClick={() => setCard(null)} aria-label="Close road details" className="absolute right-2 top-2 rounded p-1 text-slate-400 hover:text-white">✕</button>
              <p className="eyebrow pr-6">{info.subtitle}</p>
              <h3 className="mt-0.5 pr-6 text-sm font-semibold leading-snug text-white">{info.title}</h3>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {info.badges.map((b) => <Badge key={b.t} color={b.c}>{b.t}</Badge>)}
              </div>
              <p className="mt-2 font-medium leading-relaxed text-slate-100">{info.lead}</p>
              {info.bullets.length ? (
                <ul className="mt-1.5 list-disc space-y-1 pl-4 leading-relaxed text-slate-400">{info.bullets.map((t, i) => <li key={i}>{t}</li>)}</ul>
              ) : null}
              <p className="mt-2 border-t border-slate-800 pt-2 text-[11px] leading-snug text-slate-500">{info.foot}</p>
            </div>
          ) : null}
          {mode === "preview" ? (
            <div className="pointer-events-none absolute left-1/2 top-16 z-10 -translate-x-1/2 rounded-full bg-amber-400 px-3 py-1 text-[11px] font-semibold text-slate-950 shadow">
              Illustrative preview: simulated conditions, not real data
            </div>
          ) : null}
          <div className="glass pointer-events-none absolute bottom-3 left-3 z-10 max-w-[17rem] p-2.5 text-[11px] leading-snug text-slate-300">
            <p className="eyebrow mb-1.5">{mode === "preview" ? "Road condition (simulated)" : "Road condition (evidence)"}</p>
            {NET_ORDER.map((k) => (
              <p key={k} className="flex items-center gap-2"><span className="h-[3px] w-4 rounded" style={{ background: NET_COLOR[k] }} />{NET_LABEL[k]}</p>
            ))}
            <p className="mt-1.5 text-slate-400">Every line is real OSM geometry. Register roads outside the municipality have no OSM geometry yet, so they appear in the list but not on the map.</p>
          </div>
        </section>

        <div className="space-y-4">
          <Panel title="Selected road" subtitle={`${selected.id} · ${selected.upazila}`}>
            <h3 className="text-sm font-semibold leading-snug text-white">{selected.road}</h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge color={RECURRENCE_COLOR[selected.recurrence]}>{RECURRENCE_LABEL[selected.recurrence]}</Badge>
              <Badge color="#94a3b8">{EVIDENCE_LABEL[selected.evidence]}</Badge>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">{selected.issue}</p>
            {selected.detail ? (
              <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-relaxed text-slate-400">
                {selected.detail.map((t) => <li key={t}>{t}</li>)}
              </ul>
            ) : null}
            <p className="mt-2 border-t border-slate-800 pt-2 text-[11px] leading-snug text-slate-500">
              Location: {selected.precision === "osm" ? "from OSM geometry. " : ""}{selected.locationNote}
            </p>
          </Panel>

          <Panel title="Recurrence on the register" subtitle="Only one road has a documented repair history">
            <Donut slices={donut} centerLabel="roads" size={120} />
            <p className="mt-3 text-[11px] leading-snug text-slate-500">
              A road in a repair tender shows a maintenance need, not repeated failure. The rest of the register is the pipeline to investigate.
            </p>
          </Panel>

          <Panel title="Municipality road network" subtitle={`${Math.round(net.total)} km of OSM roads · ${mode === "preview" ? "simulated preview" : "real evidence only"}`}>
            <HBars rows={NET_ORDER.filter((k) => net.km[k] > 0 || k === "good").map((k) => ({ label: NET_LABEL[k], value: Math.round(net.km[k] * 10) / 10, color: NET_COLOR[k] }))} suffix=" km" />
            {mode === "preview" ? (
              <p className="mt-3 rounded-md bg-amber-400/10 p-2 text-[11px] leading-snug text-amber-200">
                These condition colours are simulated so you can see the scheme. Only Hospital Road (failed) and the waterlogging roads are real evidence. Switch to "Real evidence only" for the truthful view.
              </p>
            ) : (
              <p className="mt-3 text-[11px] leading-snug text-slate-500">
                {Math.round((net.km.unverified / net.total) * 100)}% of the network is grey because no condition has been recorded. Green is used only for roads confirmed fine.{" "}
                {reportInfo === "login"
                  ? "Log in as staff to colour roads by citizen-report severity."
                  : reportInfo
                    ? `Roads within 35 m of one of ${reportInfo.total} citizen reports (${reportInfo.demo} demo) are coloured by the worst report severity: low yellow, medium orange, high or critical red.`
                    : "Loading citizen reports."}
              </p>
            )}
          </Panel>

          <Panel title="Waterlogging hotspots" subtitle="Maijdee / municipality, July 2025">
            <p className="text-xs leading-relaxed text-slate-300">
              {WATERLOGGING.length} locations reported, in three separate reports between April and December 2025. {WL_COUNT} matched to real OSM roads and drawn on the map; the rest are listed here until their position is verified.
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {WATERLOGGING.map((h) => (
                <span key={h.name} className={`rounded-full px-2 py-0.5 text-[11px] ${h.osmNames ? "bg-teal-400/15 text-teal-200" : "bg-slate-800 text-slate-400"}`}>{h.name}</span>
              ))}
            </div>
          </Panel>
        </div>
      </div>

      {/* Case 01 */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Case 01 · Hospital Road, Maijdee" subtitle="Reported project amounts, not independently verified payments" action={<Badge color="#ef4444">Highest priority</Badge>}>
          <HBars rows={spendRows} suffix=" lakh" />
          <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-800 pt-3 text-xs">
            <div><dt className="eyebrow">Reported historical total</dt><dd className="num mt-1 text-lg font-semibold text-white">{lakh(HOSPITAL_TOTAL_LAKH)}</dd><dd className="text-slate-500">2018 construction + three repairs</dd></div>
            <div><dt className="eyebrow">FY 2026–27 allocation</dt><dd className="num mt-1 text-lg font-semibold text-slate-300">{lakh(75)}</dd><dd className="text-slate-500">excluded from the total: an allocation is not spend</dd></div>
          </dl>
        </Panel>
        <Panel title="What happened on Hospital Road" subtitle="1,050 m · serves over 100 hospitals and clinics">
          <ol className="relative space-y-3 border-l border-slate-700 pl-4 text-xs">
            {[
              ["2018", "Initial construction, ৳1.79 crore"],
              ["FY 2024–25", "Repair contract ৳21.29 lakh, then further carpeting ৳20.95 lakh"],
              ["FY 2025–26", "Further repair, ৳5.99 lakh"],
              ["3 Jul 2026", "Sealcoat work completed"],
              ["4 Jul 2026", "Residents report the surface peeling; the municipality reportedly issues a notice to the contractor"],
              ["Response", "Contractor blames rainfall and promises corrective work"],
              ["FY 2026–27", "৳75 lakh renovation allocation across 3 packages"],
            ].map(([when, what], i) => (
              <li key={when + what} className="relative">
                <span className="absolute -left-[1.3rem] top-1 h-2.5 w-2.5 rounded-full border-2 border-slate-950" style={{ background: i >= 3 && i <= 5 ? "#ef4444" : "#60a5fa" }} />
                <p className="font-medium text-slate-100">{when}</p>
                <p className="text-slate-400">{what}</p>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-[11px] leading-snug text-slate-500">
            Next step: check against the original contract awards, bills and completion certificates. An RTI request for the estimate, bill of quantities, measurement book, completion certificate, lab test reports and defect-liability correspondence would settle it.
          </p>
        </Panel>
      </div>

      {/* District context */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="District: LGED roads needing urgent repair" subtitle="July 2025 assessment">
          <p className="num text-3xl font-semibold text-white">{D.lgedUrgentKm.toLocaleString("en-US")} km</p>
          <div className="mt-3"><HBars rows={D.lgedBreakdown.map((b) => ({ ...b }))} suffix=" km" /></div>
          <p className="mt-3 text-xs leading-relaxed text-slate-400">
            LGED estimated about {crore(D.lgedNeedCrore)} was needed. In FY 2024–25, {D.lgedRepairedKm} km were repaired for a reported {crore(D.lgedRepairedCrore)}, about {fundedShare}% of the estimated need. These are different measures, shown side by side, not a like-for-like ratio.
          </p>
        </Panel>
        <Panel title="Noakhali Municipality" subtitle="July 2026 report">
          <p className="num text-3xl font-semibold text-white">{D.municipalityDamagedKm} <span className="text-base font-normal text-slate-400">of {D.municipalityNetworkKm} km severely damaged</span></p>
          <ul className="mt-3 list-disc space-y-1.5 pl-4 text-xs leading-relaxed text-slate-400">
            <li>Only {D.municipalityRepairedKm} km of the {D.municipalityNetworkKm} km network had been repaired.</li>
            <li>Reported requirement: {crore(D.municipalityNeedCrore)} for roads, footpaths and drains.</li>
            <li>December 2025: ৳65 lakh spent on drain cleaning last fiscal year against ৳500 crore estimated for drainage rehabilitation. Two very different categories.</li>
          </ul>
        </Panel>
        <Panel title="2024 floods and 2026 contracts" subtitle="Context, not additive">
          <ul className="space-y-2 text-xs leading-relaxed text-slate-400">
            <li><span className="num text-base font-semibold text-white">{D.floodDamagedKm.toLocaleString("en-US")} km</span> of roads, {D.floodBridges} bridges and {D.floodCulverts} culverts reported damaged, about {crore(D.floodCrore)} combined. Begumganj, Senbagh and Sadar were hit hardest.</li>
            <li><span className="num text-base font-semibold text-white">{crore(D.procurement.crore)}</span> across {D.procurement.contracts} LGED Noakhali contracts in 2026 ({D.procurement.firms} firms, median {lakh(D.procurement.medianLakh)}). Compiled by ProcureIndex from e-GP awards; award values, not disbursements.</li>
          </ul>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Flood and drainage record" subtitle="Repairing a road without fixing its drainage may just recreate the failure">
          <ul className="space-y-2.5 text-xs">
            {FLOOD_DRAINAGE_LOG.map((e) => (
              <li key={e.date + e.area} className="flex gap-3">
                <span className="num w-16 shrink-0 text-slate-500">{e.date}</span>
                <div><p className="font-medium text-slate-100">{e.area}</p><p className="leading-relaxed text-slate-400">{e.text} <span className="text-slate-600">· {e.source}</span></p></div>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="What we know and what we don't">
          <ul className="space-y-1.5 text-xs">
            {KNOWN_UNKNOWN.map(([q, a]) => (
              <li key={q} className="flex items-center gap-2">
                <Badge color={a === "yes" ? "#34d399" : a === "no" ? "#f87171" : "#facc15"}>{a === "yes" ? "Yes" : a === "no" ? "No" : "Partly"}</Badge>
                <span className="text-slate-300">{q}</span>
              </li>
            ))}
          </ul>
          <p className="eyebrow mb-1.5 mt-4">Five workstreams</p>
          <ol className="list-decimal space-y-1 pl-4 text-xs text-slate-400">
            {WORKSTREAMS.map(([t, d]) => <li key={t}><span className="text-slate-200">{t}:</span> {d}</li>)}
          </ol>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Records to request" subtitle="To turn news reports into a defensible database">
          <ul className="space-y-1.5 text-xs">
            {RECORD_REQUESTS.map(([a, d]) => <li key={a}><span className="text-slate-200">{a}:</span> <span className="text-slate-400">{d}</span></li>)}
          </ul>
        </Panel>
        <Panel title="Sources" subtitle="Evidence class A official · B named news · C lead">
          <ul className="list-disc space-y-1 pl-4 text-xs text-slate-400">{SOURCES.map((s) => <li key={s}>{s}</li>)}</ul>
          <p className="mt-3 text-[11px] leading-snug text-slate-500">
            Road names differ between procurement records and news reports. Use government road IDs, chainage and geometry, not names, to merge records.
          </p>
        </Panel>
      </div>
    </div>
  );
}

const chip = (active: boolean) =>
  `rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${active ? "bg-sky-500 text-slate-950" : "bg-slate-800 text-slate-300 hover:text-white"}`;
const seg = (active: boolean) => `rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${active ? "bg-sky-500 text-slate-950" : "text-slate-300 hover:text-white"}`;
