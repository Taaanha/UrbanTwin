import { useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import { apiJson, money } from "../api";
import { createMap } from "../map";

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
type Scenario = {
  public_id: string;
  name: string;
  assumptions: string;
  result: {
    disclaimer: string;
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

type FC = { type: "FeatureCollection"; features: unknown[] };
const input = "rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs";
const btn = "rounded bg-sky-700 px-3 py-1 text-xs text-white disabled:opacity-50";
const pct = (v: number | null) => (v == null ? "–" : `${v}%`);

export default function Simulation() {
  const [tab, setTab] = useState<"green" | "budget">("green");
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
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    apiJson<Baseline>("/api/simulation/green/baseline").then(setBaseline).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (tab !== "green" || !mapNode.current || mapRef.current) return;
    const map = createMap(mapNode.current);
    mapRef.current = map;
    map.on("load", async () => {
      const green = await apiJson<FC>("/api/simulation/green/geojson").catch(() => null);
      map.addSource("green", { type: "geojson", data: (green ?? { type: "FeatureCollection", features: [] }) as never });
      map.addLayer({ id: "green-fill", type: "fill", source: "green", paint: { "fill-color": "#22c55e", "fill-opacity": 0.45 } });
      map.addSource("sites", { type: "geojson", data: { type: "FeatureCollection", features: [] } as never });
      map.addLayer({ id: "sites-circle", type: "circle", source: "sites", paint: { "circle-radius": 8, "circle-color": "#38bdf8", "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [tab]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !active) return;
    const data: FC = {
      type: "FeatureCollection",
      features: active.result.sites.map((s) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [s.longitude, s.latitude] },
        properties: { ward: s.ward },
      })),
    };
    const apply = () => (map.getSource("sites") as maplibregl.GeoJSONSource | undefined)?.setData(data as never);
    if (map.isStyleLoaded() && map.getSource("sites")) apply();
    else map.once("idle", apply);
  }, [active, tab]);

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

  return (
    <div className="flex h-full flex-col text-xs">
      <div className="flex gap-2 border-b border-slate-800 px-4 py-2">
        <button className={`rounded px-3 py-1 ${tab === "green" ? "bg-slate-800" : ""}`} onClick={() => setTab("green")}>
          Green space & accessibility
        </button>
        <button className={`rounded px-3 py-1 ${tab === "budget" ? "bg-slate-800" : ""}`} onClick={() => setTab("budget")}>
          Repair budget scenarios
        </button>
        {error ? <span className="ml-3 self-center text-amber-300">{error}</span> : null}
      </div>

      {tab === "green" ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[420px_1fr]">
          <aside className="space-y-3 overflow-y-auto border-r border-slate-800 p-4">
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
              <div className="space-y-2 rounded border border-slate-800 bg-slate-900 p-3">
                <h3 className="text-sm font-medium">{active.name} · {active.public_id}</h3>
                <p>
                  Buildings with green space within {radius} m: <b>{pct(active.result.city_before.access_pct)}</b> → <b>{pct(active.result.city_after.access_pct)}</b>
                  {active.result.access_gain_points != null ? ` (+${active.result.access_gain_points} points)` : ""}
                </p>
                <p>
                  {active.result.total_trees} trees · {money(active.result.indicative_planting_cost_bdt)} indicative. {active.result.cost_note}
                </p>
                <table className="w-full text-left">
                  <thead className="text-slate-400">
                    <tr><th>Ward</th><th>Green %</th><th>Access %</th></tr>
                  </thead>
                  <tbody>
                    {active.result.wards.map((w) => (
                      <tr key={w.ward} className="border-t border-slate-800">
                        <td>{w.ward.replace(" (demonstration grid)", "")}</td>
                        <td>{w.green_pct_before} → {w.green_pct_after}</td>
                        <td>{pct(w.access_pct_before)} → {pct(w.access_pct_after)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-slate-500">{active.result.disclaimer}</p>
              </div>
            ) : baseline ? (
              <div className="rounded border border-slate-800 bg-slate-900 p-3">
                <h3 className="text-sm font-medium">Current conditions</h3>
                <p>
                  {baseline.city.buildings} buildings · {pct(baseline.city.access_pct)} within reach of green space · {baseline.green_features} green polygons
                </p>
                <table className="mt-2 w-full text-left">
                  <thead className="text-slate-400"><tr><th>Ward</th><th>Green %</th><th>Access %</th></tr></thead>
                  <tbody>
                    {baseline.per_ward.map((w) => (
                      <tr key={w.ward_id} className="border-t border-slate-800">
                        <td>{w.ward.replace(" (demonstration grid)", "")}</td><td>{w.green_pct}</td><td>{pct(w.access_pct)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
          </aside>
          <div ref={mapNode} className="min-h-[320px]" />
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
