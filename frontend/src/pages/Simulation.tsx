import { useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import { apiJson, money } from "../api";
import { createMap, getBasemap, onStyleReady, setBasemap, type Basemap } from "../map";
import { set3D } from "../map3d";
import { applyFlood, applyGreen, initScenarioLayers, syncCameras, type FC, type FloodResult } from "../scenarioMap";
import { HBars, MapToolbar, Notice, Panel, wardLabel } from "../ui";
import { CandidateBadge, CompareHandle, RangeBar } from "../widgets";

type WardRow = {
  ward_id: number;
  ward: string;
  green_pct: number;
  access_pct: number | null;
  buildings: number;
  buildings_with_access: number;
};
type Baseline = {
  disclaimer: string;
  assumptions: string[];
  green_features: number;
  green_is_demo: boolean;
  data_warning: string | null;
  per_ward: WardRow[];
  city: { buildings: number; access_pct: number | null; green_m2: number };
};
type Uncertainty = {
  basis: string;
  access_after_pct: { low: number | null; central: number | null; high: number | null };
  gain_points: { low: number | null; high: number | null };
  not_modelled: string[];
};
type Scenario = {
  public_id: string;
  name: string;
  assumptions: string;
  result: {
    disclaimer: string;
    canopy_radius_m?: number;
    uncertainty?: Uncertainty;
    sites: Array<{ longitude: number; latitude: number; ward: string; trees: number; newly_covered_buildings: number | null }>;
    total_trees: number;
    indicative_planting_cost_bdt: number | null;
    cost_note: string;
    city_before: { access_pct: number | null; green_m2: number };
    city_after: { access_pct: number | null; green_m2: number };
    access_gain_points: number | null;
    wards: Array<{ ward: string; green_pct_before: number; green_pct_after: number; access_pct_before: number | null; access_pct_after: number | null }>;
  };
};
type Method = { method: string; spent_bdt: number; included_count: number; total_priority_score: number; wards_served: number; notes: string };
type BudgetRun = { budget_bdt: number; methods: Record<string, Method> };
type FloodStatus = {
  available: boolean;
  message?: string;
  source?: string;
  fetched_at?: string;
  ground_min_m?: number;
  ground_max_m?: number;
  ground_median_m?: number;
  ground_p5_m?: number;
  ground_p25_m?: number;
  ground_p95_m?: number;
  baseline_note?: string;
  vertical_error_assumed_m?: number;
  limits: string[];
};

const input = "rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs";
const btn = "rounded bg-sky-700 px-3 py-1 text-xs text-white disabled:opacity-50";
const pct = (v: number | null | undefined) => (v == null ? "–" : `${v}%`);
type Tab = "green" | "flood" | "budget";

export default function Simulation() {
  const [tab, setTab] = useState<Tab>("green");
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [active, setActive] = useState<Scenario | null>(null);
  const [sites, setSites] = useState(10);
  const [trees, setTrees] = useState(25);
  const [radius, setRadius] = useState(400);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [budgets, setBudgets] = useState("30000, 100000, 300000");
  const [runs, setRuns] = useState<BudgetRun[]>([]);
  const [budgetNote, setBudgetNote] = useState("");
  const mapNode = useRef<HTMLDivElement | null>(null);
  const mapNode2 = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const map2Ref = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [ready2, setReady2] = useState(false);
  const [view3d, setView3d] = useState(false);
  const [basemap, setBase] = useState<Basemap>(getBasemap());
  const [showAfter, setShowAfter] = useState(true);
  const [compare, setCompare] = useState(false);
  const [pos, setPos] = useState(50);
  const [accessData, setAccessData] = useState<{ id: string; data: FC } | null>(null);

  // flood what-if
  const [floodStatus, setFloodStatus] = useState<FloodStatus | null>(null);
  const [rise, setRise] = useState(1);
  const [connected, setConnected] = useState(true);
  const [flood, setFlood] = useState<FloodResult | null>(null);
  const [floodBusy, setFloodBusy] = useState(false);
  const [floodError, setFloodError] = useState("");

  const showMap = tab !== "budget";
  const haveScenario = tab === "flood" ? Boolean(flood) : Boolean(active);
  const comparing = compare && haveScenario;
  const baseline5 = floodStatus?.available ? (floodStatus.ground_p5_m ?? null) : null;
  const level = baseline5 == null ? null : Math.round((baseline5 + rise) * 10) / 10;

  useEffect(() => {
    apiJson<Baseline>("/api/simulation/green/baseline").then(setBaseline).catch((e: Error) => setError(e.message));
    apiJson<FloodStatus>("/api/simulation/flood/status")
      .then((s) => {
        setFloodStatus(s);
      })
      .catch(() => setFloodStatus({ available: false, message: "Could not reach the elevation service.", limits: [] }));
  }, []);

  // main map
  useEffect(() => {
    if (!showMap || !mapNode.current || mapRef.current) return;
    const map = createMap(mapNode.current);
    mapRef.current = map;
    onStyleReady(map, async () => {
      try {
        await initScenarioLayers(map);
      } catch (e) {
        console.error("Scenario layers could not start", e);
      }
      setReady(true);
    });
    return () => {
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [showMap]);

  // second map for the before/after swipe: shows the "current" state on the left of the divider
  useEffect(() => {
    if (!comparing) return;
    if (!ready || !mapNode2.current || !mapRef.current) {
      console.warn("[compare] waiting", { mainReady: ready, node: Boolean(mapNode2.current), main: Boolean(mapRef.current) });
      return;
    }
    const main = mapRef.current;
    const map2 = createMap(mapNode2.current, { controls: false });
    map2Ref.current = map2;
    let unsync: (() => void) | null = null;
    onStyleReady(map2, async () => {
      await initScenarioLayers(map2);
      setBasemap(map2, getBasemap());
      unsync = syncCameras(main, map2);
      setReady2(true);
    });
    return () => {
      unsync?.();
      map2.remove();
      map2Ref.current = null;
      setReady2(false);
    };
  }, [comparing, ready]);

  // camera + basemap
  useEffect(() => {
    const map = mapRef.current;
    if (map && ready) set3D(map, view3d, []);
  }, [view3d, ready]);
  useEffect(() => {
    const map = mapRef.current;
    if (map && ready) setBasemap(map, basemap);
    const m2 = map2Ref.current;
    if (m2 && ready2) setBasemap(m2, basemap);
  }, [basemap, ready, ready2]);

  // per-building green-space access for the active scenario (recomputed on the server with the same rules as the run)
  useEffect(() => {
    if (!active) {
      setAccessData(null);
      return;
    }
    let alive = true;
    apiJson<FC>(`/api/simulation/scenarios/${active.public_id}/buildings`)
      .then((data) => alive && setAccessData({ id: active.public_id, data }))
      .catch(() => alive && setError("Could not load the per-building access layer for this scenario."));
    return () => {
      alive = false;
    };
  }, [active]);

  // water-level what-if (debounced while the slider moves)
  useEffect(() => {
    if (tab !== "flood" || !floodStatus?.available || baseline5 == null) return;
    let alive = true;
    setFloodBusy(true);
    const timer = window.setTimeout(() => {
      apiJson<FloodResult>(`/api/simulation/flood?level_m=${level}&connected_only=${connected}`)
        .then((data) => {
          if (!alive) return;
          setFlood(data);
          setFloodError("");
        })
        .catch((e: Error) => alive && setFloodError(e.message))
        .finally(() => alive && setFloodBusy(false));
    }, 350);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [tab, floodStatus?.available, level, connected]); // eslint-disable-line react-hooks/exhaustive-deps

  // draw the current scenario on the main map (and the "current" state on the second map while swiping)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const haveAccess = Boolean(active && accessData && accessData.id === active.public_id);
    const crown = active?.result.canopy_radius_m ?? 3;
    const run = (m: maplibregl.Map, before: boolean) => {
      if (tab === "flood") applyFlood(m, { data: flood, view3d, dry: before });
      else
        applyGreen(m, {
          access: haveAccess ? accessData!.data : null,
          showAfter: before ? false : comparing ? true : showAfter,
          view3d,
          sites: active?.result.sites ?? [],
          crownM: crown,
        });
    };
    run(map, false);
    const m2 = map2Ref.current;
    if (m2 && ready2 && comparing) run(m2, true);
  }, [tab, active, accessData, showAfter, view3d, ready, ready2, comparing, flood]);

  async function runGreen(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = await apiJson<Scenario>("/api/simulation/green", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: `${sites} sites × ${trees} trees`, strategy: "gap_fill", sites, trees_per_site: trees, access_radius_m: radius }),
      });
      setScenarios((prev) => [body, ...prev]);
      setActive(body);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runBudgets(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const list = budgets.split(",").map((v) => Number(v.trim())).filter((v) => v > 0);
      const body = await apiJson<{ disclaimer: string; runs: BudgetRun[]; interventions_considered: number }>("/api/simulation/budget", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ budgets_bdt: list }),
      });
      setRuns(body.runs);
      setBudgetNote(`${body.disclaimer} (${body.interventions_considered} interventions considered)`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function downloadElevation() {
    setFloodBusy(true);
    setFloodError("");
    try {
      const s = await apiJson<FloodStatus>("/api/simulation/flood/dem", { method: "POST" });
      setFloodStatus(s);
    } catch (err) {
      setFloodError((err as Error).message);
    } finally {
      setFloodBusy(false);
    }
  }

  const tabBtn = (id: Tab, label: string) => (
    <button className={`rounded px-3 py-1 ${tab === id ? "bg-slate-800" : ""}`} onClick={() => setTab(id)}>
      {label}
    </button>
  );
  const u = active?.result.uncertainty;

  return (
    <div className="flex h-full flex-col text-xs">
      <div className="flex flex-wrap gap-2 border-b border-slate-800 px-4 py-2">
        {tabBtn("green", "Green space & accessibility")}
        {tabBtn("flood", "Flood what-if (3D)")}
        {tabBtn("budget", "Repair budget scenarios")}
        {error ? <span className="ml-3 self-center text-amber-300">{error}</span> : null}
      </div>

      {showMap ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[420px_1fr]">
          <aside className="space-y-3 overflow-y-auto border-r border-slate-800 p-4">
            {tab === "green" ? (
              <>
                {baseline?.data_warning ? <p className="rounded border border-amber-700 bg-amber-950 p-2 text-amber-200">{baseline.data_warning}</p> : null}
                {baseline?.green_is_demo ? <p className="rounded border border-sky-800 bg-sky-950 p-2 text-sky-200">Green spaces shown are DEMO polygons, not real parks.</p> : null}
                <form onSubmit={runGreen} className="space-y-2 rounded border border-slate-800 p-3">
                  <h2 className="text-sm font-medium">Plan new planting sites</h2>
                  <label className="flex items-center justify-between gap-2">
                    Sites
                    <input type="number" min={1} max={60} value={sites} onChange={(e) => setSites(Number(e.target.value))} className={input} />
                  </label>
                  <label className="flex items-center justify-between gap-2">
                    Trees per site
                    <input type="number" min={1} max={500} value={trees} onChange={(e) => setTrees(Number(e.target.value))} className={input} />
                  </label>
                  <label className="flex items-center justify-between gap-2">
                    Access distance (m)
                    <input type="number" min={50} max={2000} value={radius} onChange={(e) => setRadius(Number(e.target.value))} className={input} />
                  </label>
                  <p className="text-slate-500">Sites are chosen greedily: each one covers the most buildings that currently have no green space within reach.</p>
                  <button className={btn} disabled={busy}>Run scenario</button>
                </form>

                {active ? (
                  <Panel title={`${active.name}`} subtitle={active.public_id} action={<CandidateBadge />}>
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-lg bg-slate-950/60 p-2.5 ring-1 ring-slate-800">
                        <p className="eyebrow">Green access</p>
                        <p className="num mt-1 text-sm text-slate-400">
                          {pct(active.result.city_before.access_pct)} <span className="text-slate-600">→</span>{" "}
                          <span className="text-lg font-semibold text-emerald-300">{pct(active.result.city_after.access_pct)}</span>
                        </p>
                        {active.result.access_gain_points != null ? (
                          <p className="num text-[11px] text-emerald-400">+{active.result.access_gain_points} points</p>
                        ) : null}
                      </div>
                      <div className="rounded-lg bg-slate-950/60 p-2.5 ring-1 ring-slate-800">
                        <p className="eyebrow">Trees</p>
                        <p className="num mt-1 text-lg font-semibold text-white">{active.result.total_trees}</p>
                        <p className="text-[11px] text-slate-500">{active.result.sites.length} sites</p>
                      </div>
                      <div className="rounded-lg bg-slate-950/60 p-2.5 ring-1 ring-slate-800">
                        <p className="eyebrow">Indicative cost</p>
                        <p className="num mt-1 text-sm font-semibold text-white">{money(active.result.indicative_planting_cost_bdt)}</p>
                      </div>
                    </div>
                    {u ? (
                      <div className="mt-3 rounded-lg bg-slate-950/60 p-2.5 ring-1 ring-slate-800">
                        <p className="eyebrow mb-2">Access after planting, with uncertainty</p>
                        <RangeBar low={u.access_after_pct.low} central={u.access_after_pct.central} high={u.access_after_pct.high} format={(v) => `${v}%`} />
                        <p className="mt-2 text-[11px] text-slate-500">{u.basis}</p>
                        <details className="mt-1 text-[11px] text-slate-500">
                          <summary className="cursor-pointer text-slate-400">Not modelled at all</summary>
                          <ul className="mt-1 list-disc pl-4">
                            {u.not_modelled.map((n) => (
                              <li key={n}>{n}</li>
                            ))}
                          </ul>
                        </details>
                      </div>
                    ) : null}
                    <p className="mt-2 text-[11px] text-slate-500">{active.result.cost_note}</p>
                    <h4 className="eyebrow mb-2 mt-4">Green-space access by ward (after)</h4>
                    <HBars
                      rows={active.result.wards.map((w) => ({
                        label: `${wardLabel(w.ward)} · ${pct(w.access_pct_before)} → ${pct(w.access_pct_after)}`,
                        value: w.access_pct_after ?? 0,
                        color: "#34d399",
                      }))}
                      suffix="%"
                    />
                    <p className="mt-3 text-[11px] text-slate-500">{active.result.disclaimer}</p>
                  </Panel>
                ) : baseline ? (
                  <Panel title="Current conditions" subtitle="Before any planting">
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-lg bg-slate-950/60 p-2.5 ring-1 ring-slate-800">
                        <p className="eyebrow">Buildings</p>
                        <p className="num mt-1 text-lg font-semibold text-white">{baseline.city.buildings}</p>
                      </div>
                      <div className="rounded-lg bg-slate-950/60 p-2.5 ring-1 ring-slate-800">
                        <p className="eyebrow">Within reach</p>
                        <p className="num mt-1 text-lg font-semibold text-emerald-300">{pct(baseline.city.access_pct)}</p>
                      </div>
                      <div className="rounded-lg bg-slate-950/60 p-2.5 ring-1 ring-slate-800">
                        <p className="eyebrow">Green polygons</p>
                        <p className="num mt-1 text-lg font-semibold text-white">{baseline.green_features}</p>
                      </div>
                    </div>
                    <h4 className="eyebrow mb-2 mt-4">Green-space access by ward</h4>
                    <HBars
                      rows={baseline.per_ward.map((w) => ({
                        label: `${wardLabel(w.ward)} · green cover ${w.green_pct}%`,
                        value: w.access_pct ?? 0,
                        color: (w.access_pct ?? 0) < 10 ? "#fb923c" : "#34d399",
                      }))}
                      suffix="%"
                    />
                    <p className="mt-2 text-[11px] text-slate-500">Bar length is the share of buildings within walking reach of green space.</p>
                  </Panel>
                ) : null}

                {scenarios.length > 1 ? (
                  <div>
                    <h3 className="mb-1 text-sm font-medium">This session's scenarios</h3>
                    <ul className="space-y-1">
                      {scenarios.map((s) => (
                        <li key={s.public_id}>
                          <button className="text-sky-300 underline" onClick={() => setActive(s)}>{s.name}</button> → {pct(s.result.city_after.access_pct)} access
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <details className="text-slate-400">
                  <summary className="cursor-pointer text-slate-300">Assumptions and limits</summary>
                  <ul className="mt-1 list-disc pl-4">
                    {(baseline?.assumptions ?? []).map((a) => <li key={a}>{a}</li>)}
                  </ul>
                  <p className="mt-1">{baseline?.disclaimer}</p>
                </details>
              </>
            ) : (
              <>
                <Notice tone="warn">
                  <strong>Water-level what-if, not a flood forecast.</strong> It shows which ground and buildings sit at or below the water height you pick,
                  using a coarse public elevation model. No rain, drains, tides or embankments are modelled.
                </Notice>
                {floodStatus && !floodStatus.available ? (
                  <Panel title="Elevation data needed" subtitle="Downloaded once, then cached on the server">
                    <p className="text-slate-400">{floodStatus.message}</p>
                    <button className={`${btn} mt-3`} onClick={downloadElevation} disabled={floodBusy}>
                      {floodBusy ? "Downloading…" : "Download elevation"}
                    </button>
                    <p className="mt-2 text-[11px] text-slate-500">Uses open AWS Terrain Tiles (SRTM-derived). The machine running the API needs internet for this one step.</p>
                  </Panel>
                ) : null}
                {floodStatus?.available && level != null ? (
                  <Panel
                    title="Water rise"
                    subtitle={`Ground in this window: 5th to 95th percentile ${floodStatus.ground_p5_m} to ${floodStatus.ground_p95_m} m (surface model)`}
                    action={<CandidateBadge>Scenario · not a forecast</CandidateBadge>}
                  >
                    <label className="block">
                      <span className="flex items-baseline justify-between">
                        <span className="eyebrow">Rise above the low-lying ground</span>
                        <span className="num text-lg font-semibold text-sky-300">+{rise.toFixed(1)} m</span>
                      </span>
                      <input type="range" min={0} max={8} step={0.1} value={rise} onChange={(e) => setRise(Number(e.target.value))} className="mt-2 w-full accent-sky-400" />
                      <span className="num flex justify-between text-[10px] text-slate-500">
                        <span>0 m</span>
                        <span>8 m</span>
                      </span>
                      <span className="mt-1 block text-[11px] text-slate-500">
                        Water surface = {level.toFixed(1)} m in the model. {floodStatus.baseline_note}
                      </span>
                    </label>
                    <label className="mt-3 flex items-start gap-2 text-slate-300">
                      <input type="checkbox" checked={connected} onChange={(e) => setConnected(e.target.checked)} className="mt-0.5" />
                      <span>
                        Water must reach each cell through connected low ground from the edge of the study window
                        <span className="block text-[11px] text-slate-500">Untick to also count isolated low spots (a rain-pooling reading).</span>
                      </span>
                    </label>
                  </Panel>
                ) : null}
                {flood ? (
                  <Panel title="Result" subtitle={floodBusy ? "Updating…" : `Model water surface ${flood.level_m.toFixed(1)} m`}>
                    <p className="text-slate-200">
                      <span className="num text-2xl font-semibold text-sky-300">{flood.flooded_buildings.central}</span>
                      <span className="text-slate-400"> of {flood.buildings_total} buildings ({pct(flood.flooded_pct.central)}) stand at or below water {rise.toFixed(1)} m above the low-lying ground.</span>
                    </p>
                    <div className="mt-3">
                      <RangeBar
                        low={flood.flooded_buildings.low}
                        central={flood.flooded_buildings.central}
                        high={flood.flooded_buildings.high}
                        max={Math.max(flood.buildings_total, 1)}
                        color="#38bdf8"
                      />
                    </div>
                    <p className="mt-2 text-[11px] text-slate-400">
                      The range assumes the elevation model is off by ±{flood.vertical_error_assumed_m} m. That error size is an assumption, not a measurement for Noakhali.
                    </p>
                    <p className="num mt-2 text-slate-300">
                      Ground below water: {flood.flooded_area_km2.central} km² <span className="text-slate-500">(plausible {flood.flooded_area_km2.low} to {flood.flooded_area_km2.high})</span>
                    </p>
                    {flood.buildings_without_elevation ? (
                      <p className="mt-1 text-[11px] text-amber-300">{flood.buildings_without_elevation} buildings lie outside the elevation window and are not counted.</p>
                    ) : null}
                    <details className="mt-3 text-[11px] text-slate-400">
                      <summary className="cursor-pointer text-slate-300">Limits of this what-if</summary>
                      <ul className="mt-1 list-disc space-y-1 pl-4">
                        {flood.limits.map((l) => (
                          <li key={l}>{l}</li>
                        ))}
                      </ul>
                      <p className="mt-1">Source: {flood.source}. Downloaded {flood.fetched_at.slice(0, 10)}.</p>
                    </details>
                  </Panel>
                ) : null}
                {floodError ? <Notice tone="warn">{floodError}</Notice> : null}
              </>
            )}
          </aside>

          <div className="relative min-h-[320px]">
            <div ref={mapNode} style={{ position: "absolute", inset: 0 }} />
            {comparing ? <div ref={mapNode2} style={{ position: "absolute", inset: 0, clipPath: `inset(0 ${100 - pos}% 0 0)` }} /> : null}
            {comparing ? (
              <CompareHandle pos={pos} onPos={setPos} left={tab === "flood" ? "Current (dry)" : "Before planting"} right={tab === "flood" ? `Water at ${flood?.level_m.toFixed(1)} m` : "After planting"} />
            ) : null}
            <MapToolbar
              view3d={view3d}
              onView3d={setView3d}
              basemap={basemap}
              onBasemap={setBase}
              extra={
                haveScenario ? (
                  <div className="flex flex-col gap-1.5">
                    <button
                      onClick={() => setCompare(!compare)}
                      className={`rounded-lg px-2 py-1.5 text-[11px] font-medium ${compare ? "bg-amber-400 text-slate-950" : "bg-slate-950/70 text-slate-200 hover:text-white"}`}
                    >
                      ⇄ Swipe compare
                    </button>
                    {tab === "green" && !compare ? (
                      <div className="flex gap-1 rounded-lg bg-slate-950/70 p-0.5 text-[11px] font-medium">
                        {[
                          [false, "Before"],
                          [true, "After planting"],
                        ].map(([v, label]) => (
                          <button
                            key={String(label)}
                            onClick={() => setShowAfter(v as boolean)}
                            className={`rounded-md px-2 py-1 ${showAfter === v ? "bg-emerald-400 text-slate-950" : "text-slate-300"}`}
                          >
                            {label as string}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null
              }
            />
            {tab === "green" && active ? (
              <div className="glass absolute bottom-3 left-3 z-10 max-w-xs p-3 text-[11px] leading-snug text-slate-300">
                <p className="eyebrow mb-1">Green-space access</p>
                <p>
                  <span className="text-emerald-400">Green</span> buildings have green space within {radius} m (straight line);{" "}
                  <span className="text-rose-400">red</span> do not. Trees are drawn in an illustrative pattern at each planting site, at mature crown size.
                </p>
              </div>
            ) : null}
            {tab === "flood" && flood ? (
              <div className="glass absolute bottom-3 left-3 z-10 max-w-xs p-3 text-[11px] leading-snug text-slate-300">
                <p className="eyebrow mb-1">Water-level what-if</p>
                <p>
                  <span className="text-sky-400">Blue</span> buildings sit at or below {flood.level_m.toFixed(1)} m; <span className="text-amber-300">amber</span> only if the
                  elevation model is {flood.vertical_error_assumed_m} m too high; <span className="text-slate-400">grey</span> stay above. Not a forecast.
                </p>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          <form onSubmit={runBudgets} className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              Budgets in BDT (comma separated, up to 6)
              <input value={budgets} onChange={(e) => setBudgets(e.target.value)} className={`${input} w-80`} />
            </label>
            <button className={btn} disabled={busy}>Compare methods</button>
          </form>
          {budgetNote ? <p className="text-slate-400">{budgetNote}</p> : null}
          {runs.map((run) => (
            <div key={run.budget_bdt} className="overflow-x-auto rounded border border-slate-800">
              <div className="bg-slate-900 p-2 text-sm font-medium">Budget {money(run.budget_bdt)}</div>
              <table className="w-full text-left">
                <thead className="text-slate-400">
                  <tr><th className="p-2">Method</th><th className="p-2">Items funded</th><th className="p-2">Priority score gained</th><th className="p-2">Wards served</th><th className="p-2">Spent</th></tr>
                </thead>
                <tbody>
                  {Object.values(run.methods).map((m) => (
                    <tr key={m.method} className="border-t border-slate-800" title={m.notes}>
                      <td className="p-2 font-mono">{m.method}</td><td className="p-2">{m.included_count}</td>
                      <td className="p-2">{m.total_priority_score}</td><td className="p-2">{m.wards_served}</td><td className="p-2">{money(m.spent_bdt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {!runs.length ? <p className="text-slate-500">Generate interventions in City Planner first, then compare how each method spends a fixed budget. Nothing here approves a project.</p> : null}
        </div>
      )}
    </div>
  );
}
