import { useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import { apiJson } from "./api";
import { createMap, getBasemap, onStyleReady, setBasemap, type Basemap } from "./map";
import { MapToolbar } from "./ui";

type FC = { type: "FeatureCollection"; features: unknown[] };
type RoadResult = {
  level_m: number;
  disclaimer: string;
  limits: string[];
  not_modelled: string[];
  roads_analysed: number;
  total_km: number;
  exposed_km: { central: number; possible: number };
  by_class: Array<{ highway: string; roads: number; km: number; exposed_km: number; possible_km: number }>;
  most_exposed: Array<{ name: string | null; highway: string; length_m: number; exposed_pct: number }>;
  roads: FC;
};
type PondResult = {
  disclaimer: string;
  limits: string[];
  not_modelled: string[];
  cells_in_zones_pct: number;
  depth_p95_m: number;
  buildings: { total: number; in_zones: number; pct: number | null };
  per_ward: Array<{ ward: string; buildings: number; in_ponding_zones: number; pct: number | null }>;
  drain_context: { osm_drain_features: number; usable_for_gap_analysis: boolean; note: string };
  zones: FC;
};
type FloodStatus = { available: boolean; ground_p5_m?: number; message?: string };

type Source = { cite: string; role: string };
const R1 = "Rahaman, M. S., Hossain, N., Nurain, A., Sarker, P. & Ichihara, S. (2020). Investigation on causes and effects of waterlogging in the southern part of Bangladesh. Management of Sustainable Development, 12(2), Sibiu, Romania.";
const R2 = "Geomark (2011). Existing Drains, Noakhali Pourashava. Field-survey map; also Figure 2 in Rahaman et al. (2020).";
const R3 = "Local Government Engineering Department (LGED). Road Map, Noakhali Sadar Upazila, 1:100,000 (compiled from 1994-95 base maps, Landsat TM 1998, GPS survey 1999, field check 2016).";
const R4 = "UNOSAT (2024). Satellite-based flood assessment of Noakhali City, product 3950 (KOMPSAT-3, about 2.8 m).";
const ELEV = "Elevation: Copernicus GLO-30 DSM (ESA, via AWS Open Data; contains modified Copernicus data), or AWS Terrain Tiles (SRTM-derived) if that download failed. Roads, drains and buildings: OpenStreetMap contributors.";

/** Which published work each tab draws on, and how: model data, background context, or not yet used. */
export const SOURCES_BY_TAB: Record<string, Source[]> = {
  flood: [
    { cite: ELEV, role: "Model data" },
    { cite: R1, role: "Context: waterlogging in wards 1, 2, 4, 5 and 8 is driven by rain and weak drainage" },
    { cite: R2, role: "Reference for checking results (not yet digitized)" },
    { cite: R4, role: "Observed flood extent for checking results (not yet loaded)" },
  ],
  roads: [
    { cite: ELEV, role: "Model data" },
    { cite: R1, role: "Context: waterlogging disrupts traffic and damages roads" },
    { cite: R3, role: "Reference for road classes (not yet used as input)" },
  ],
  drainage: [
    { cite: ELEV, role: "Model data" },
    { cite: R1, role: "Context: drains lack integration and capacity; Gabua khal narrowed by culverts" },
    { cite: R2, role: "Reference for the existing drain network and obstructions (not yet digitized)" },
  ],
  budget: [{ cite: "No published source: unit rates and quantities are placeholders set in the lab.", role: "Assumption" }],
  green: [{ cite: "No published source yet: the walking distance is a setting you choose, and the green-space polygons are demonstration data.", role: "Assumption" }],
};

export function Sources({ id }: { id: string }) {
  const list = SOURCES_BY_TAB[id];
  if (!list) return null;
  const published = list.some((s) => s.role !== "Assumption");
  return (
    <div className="border-b border-slate-800 px-4 py-2 text-[11px] text-slate-400">
      <p className="font-semibold text-slate-300">{published ? "Based on published research and open data" : "Sources"}</p>
      <ul className="mt-1 space-y-1">
        {list.map((s) => (
          <li key={s.cite}>
            {s.cite} <span className="text-sky-300">[{s.role}]</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function NetworkLab({ mode }: { mode: "roads" | "drainage" }) {
  const node = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [basemap, setBase] = useState<Basemap>(getBasemap());
  const [view3d, setView3d] = useState(false);
  const [status, setStatus] = useState<FloodStatus | null>(null);
  const [rise, setRise] = useState(1);
  const [connected, setConnected] = useState(false);
  const [minDepth, setMinDepth] = useState(1);
  const [roads, setRoads] = useState<RoadResult | null>(null);
  const [pond, setPond] = useState<PondResult | null>(null);
  const [drains, setDrains] = useState<FC | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiJson<FloodStatus>("/api/simulation/flood/status").then(setStatus).catch((e: Error) => setError(e.message));
    apiJson<FC>("/api/geo/drains").then(setDrains).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!node.current || mapRef.current) return;
    const map = createMap(node.current);
    mapRef.current = map;
    onStyleReady(map, () => {
      map.resize();
      const empty = { type: "FeatureCollection", features: [] } as never;
      map.addSource("lab-zones", { type: "geojson", data: empty });
      map.addSource("lab-roads", { type: "geojson", data: empty });
      map.addSource("lab-drains", { type: "geojson", data: empty });
      map.addLayer({ id: "lab-zones-fill", type: "fill", source: "lab-zones", paint: { "fill-color": "#38bdf8", "fill-opacity": 0.35 } });
      map.addLayer({
        id: "lab-roads-line",
        type: "line",
        source: "lab-roads",
        paint: {
          "line-color": ["case", [">=", ["get", "exposed_pct"], 50], "#f43f5e", [">=", ["get", "possible_pct"], 50], "#fbbf24", "#94a3b8"],
          "line-width": ["match", ["get", "highway"], ["trunk", "primary", "secondary"], 3.5, ["tertiary"], 2.5, 1.6],
        },
      });
      map.addLayer({ id: "lab-drains-line", type: "line", source: "lab-drains", paint: { "line-color": "#14b8a6", "line-width": 2.5, "line-dasharray": [2, 1] } });
      setReady(true);
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (map && ready) setBasemap(map, basemap);
  }, [basemap, ready]);
  useEffect(() => {
    const map = mapRef.current;
    if (map && ready) map.easeTo({ pitch: view3d ? 50 : 0, duration: 600 });
  }, [view3d, ready]);

  const level = (status?.ground_p5_m ?? 0) + rise;
  useEffect(() => {
    if (!status?.available) return;
    const id = window.setTimeout(async () => {
      setBusy(true);
      setError("");
      try {
        if (mode === "roads") setRoads(await apiJson<RoadResult>(`/api/simulation/roads?level_m=${level}&connected_only=${connected}`));
        else setPond(await apiJson<PondResult>(`/api/simulation/drainage/ponding?min_depth_m=${minDepth}`));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    }, 350);
    return () => window.clearTimeout(id);
  }, [mode, status?.available, level, connected, minDepth]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const set = (id: string, data: unknown) => (map.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData((data ?? { type: "FeatureCollection", features: [] }) as never);
    set("lab-roads", mode === "roads" ? roads?.roads : null);
    set("lab-zones", mode === "drainage" ? pond?.zones : null);
    set("lab-drains", mode === "drainage" ? drains : null);
  }, [mode, roads, pond, drains, ready]);

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[420px_1fr]">
      <aside className="space-y-3 overflow-y-auto border-r border-slate-800 p-4">
        {status && !status.available ? <p className="rounded border border-amber-700 bg-amber-950 p-2 text-amber-200">No elevation data yet. Open the Flood tab and download the elevation first.</p> : null}
        {mode === "roads" ? (
          <>
            <label className="block">
              Water rise above typical low ground: <b>{rise.toFixed(1)} m</b> (model level {level.toFixed(1)} m)
              <input type="range" min={0} max={6} step={0.5} value={rise} onChange={(e) => setRise(Number(e.target.value))} className="mt-1 w-full" />
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={connected} onChange={(e) => setConnected(e.target.checked)} />
              Connected only (water enters from the window edge)
            </label>
            {roads ? (
              <>
                <p>
                  {roads.roads_analysed} roads, {roads.total_km} km. Exposed: <b className="text-rose-300">{roads.exposed_km.central} km</b> (central), up to{" "}
                  <b className="text-amber-300">{roads.exposed_km.possible} km</b> if the elevation model reads 2 m high.
                </p>
                <table className="w-full text-left">
                  <thead className="text-slate-400">
                    <tr><th className="py-1">Road class</th><th>km</th><th>Exposed km</th><th>Possible km</th></tr>
                  </thead>
                  <tbody>
                    {roads.by_class.map((c) => (
                      <tr key={c.highway} className="border-t border-slate-800"><td className="py-1">{c.highway}</td><td>{c.km}</td><td>{c.exposed_km}</td><td>{c.possible_km}</td></tr>
                    ))}
                  </tbody>
                </table>
                {roads.most_exposed.length ? (
                  <div>
                    <p className="font-semibold text-slate-200">Most exposed roads</p>
                    <ul className="list-disc pl-4 text-slate-300">
                      {roads.most_exposed.map((r, i) => (
                        <li key={i}>{r.name ?? `(unnamed ${r.highway})`} · {r.length_m} m · {r.exposed_pct}% exposed</li>
                      ))}
                    </ul>
                  </div>
                ) : <p className="text-slate-400">No road is exposed at this level.</p>}
                <Limits disclaimer={roads.disclaimer} limits={roads.limits} notModelled={roads.not_modelled} />
              </>
            ) : null}
          </>
        ) : (
          <>
            <label className="block">
              Show depressions at least <b>{minDepth.toFixed(1)} m</b> deep
              <input type="range" min={1} max={3} step={1} value={minDepth} onChange={(e) => setMinDepth(Number(e.target.value))} className="mt-1 w-full" />
            </label>
            {pond ? (
              <>
                <p>
                  {pond.cells_in_zones_pct}% of the map is in a depression of this depth; {pond.buildings.in_zones} of {pond.buildings.total} buildings ({pond.buildings.pct}%) are inside. These
                  are broad low-lying basins, not measured ponds.
                </p>
                <table className="w-full text-left">
                  <thead className="text-slate-400"><tr><th className="py-1">Ward (demo grid)</th><th>Buildings</th><th>In zones</th><th>%</th></tr></thead>
                  <tbody>
                    {pond.per_ward.map((w) => (
                      <tr key={w.ward} className="border-t border-slate-800"><td className="max-w-[10rem] truncate py-1" title={w.ward}>{w.ward.split(" (")[0]}</td><td>{w.buildings}</td><td>{w.in_ponding_zones}</td><td>{w.pct ?? "–"}</td></tr>
                    ))}
                  </tbody>
                </table>
                <p className="rounded border border-slate-700 p-2 text-slate-300">
                  Drains in the database: <b>{pond.drain_context.osm_drain_features}</b>. {pond.drain_context.note}
                </p>
                <Limits disclaimer={pond.disclaimer} limits={pond.limits} notModelled={pond.not_modelled} />
              </>
            ) : null}
          </>
        )}
        {busy ? <p className="text-slate-400">Calculating…</p> : null}
        {error ? <p className="rounded border border-amber-700 p-2 text-amber-200">{error}</p> : null}
      </aside>
      <div className="relative min-h-[320px]">
        <div ref={node} style={{ position: "absolute", inset: 0 }} />
        <MapToolbar view3d={view3d} onView3d={setView3d} basemap={basemap} onBasemap={setBase} />
        <div className="glass absolute bottom-3 left-3 z-10 max-w-xs p-3 text-[11px] leading-snug text-slate-300">
          {mode === "roads" ? (
            <p><span className="text-rose-400">Red</span> roads are mostly below the water level; <span className="text-amber-300">amber</span> only if the elevation model reads 2 m high; <span className="text-slate-400">grey</span> stay above. Screening only.</p>
          ) : (
            <p><span className="text-sky-400">Blue</span> = closed low-lying basins in the elevation model; <span className="text-teal-300">dashed teal</span> = the few drains in the database. A ranking aid, not a map of real ponds.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Limits({ disclaimer, limits, notModelled }: { disclaimer: string; limits: string[]; notModelled: string[] }) {
  return (
    <details className="text-slate-400">
      <summary className="cursor-pointer text-slate-300">Limits and what is not modelled</summary>
      <p className="mt-1 text-amber-300">{disclaimer}</p>
      <ul className="mt-1 list-disc space-y-1 pl-4">{limits.map((l) => <li key={l}>{l}</li>)}</ul>
      <p className="mt-1">Not modelled: {notModelled.join("; ")}.</p>
    </details>
  );
}
