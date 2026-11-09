import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import maplibregl from "maplibre-gl";
import { createMap, onStyleReady } from "../map";
import { useParams } from "react-router-dom";

type IssueRow = {
  public_id: string;
  category: string;
  severity: string;
  status: string;
  title: string;
  latitude: number;
  longitude: number;
  road?: string | null;
  road_distance_m?: number | null;
  drain?: string | null;
  ward?: string | null;
};

type Snapshot = {
  disclaimer: string;
  drain_limitation: string;
  osm_drain_features: number;
  issue: IssueRow;
  assets: Array<{
    kind: string;
    name?: string;
    distance_m: number;
    notes: string;
  }>;
  relations: Array<{
    relation_type: string;
    distance_m: number;
    days_apart?: number | null;
    from_public_id?: string;
    to_public_id?: string;
    notes: string;
  }>;
  history: Array<{ at?: string; kind: string; summary: string }>;
};

type Graph = {
  disclaimer: string;
  nodes: Array<{ id: string; kind: string; label?: string | null }>;
  edges: Array<{
    from: string;
    to: string;
    relation_type: string;
    distance_m?: number;
    notes?: string;
  }>;
};

type GeoJSON = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: string; coordinates: unknown };
    properties: Record<string, unknown>;
  }>;
};

export default function Intelligence() {
  const params = useParams();
  const mapNode = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [issues, setIssues] = useState<IssueRow[]>([]);
  const [selected, setSelected] = useState<Snapshot | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [disclaimer, setDisclaimer] = useState("");
  const [drainNote, setDrainNote] = useState("");
  const [drains, setDrains] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function loadLists() {
    const summary = await apiFetch("/api/intelligence/summary").then((r) => r.json());
    setDisclaimer(summary.disclaimer ?? "");
    setDrainNote(summary.drain_limitation ?? "");
    setDrains(summary.osm_drain_features ?? 0);
    const list = await apiFetch("/api/intelligence/issues").then((r) => r.json());
    setIssues(list.items ?? []);
    const graphBody = (await apiFetch("/api/intelligence/graph").then((r) => r.json())) as Graph;
    setGraph(graphBody);
  }

  async function openIssue(publicId: string) {
    const body = (await apiFetch(`/api/intelligence/issues/${publicId}`).then((r) => r.json())) as Snapshot;
    setSelected(body);
  }

  async function refresh() {
    const body = await apiFetch("/api/intelligence/refresh", { method: "POST" }).then((r) => r.json());
    setMessage(`Recomputed ${body.assets} asset links and ${body.relations} issue relations.`);
    await loadLists();
    const map = mapRef.current;
    if (map?.getSource("src-intel")) {
      const geojson = (await apiFetch("/api/intelligence/geojson").then((r) => r.json())) as GeoJSON;
      (map.getSource("src-intel") as maplibregl.GeoJSONSource).setData(geojson);
    }
    if (selected) {
      await openIssue(selected.issue.public_id);
    }
  }

  useEffect(() => {
    void loadLists();
    if (params.publicId) {
      void openIssue(params.publicId);
    }
  }, [params.publicId]);

  useEffect(() => {
    if (!mapNode.current || mapRef.current) return;
    const map = createMap(mapNode.current);
    map.setZoom(14);
    mapRef.current = map;
    const onReady = async () => {
      map.resize();
      const roads = (await apiFetch("/api/geo/roads").then((r) => r.json())) as GeoJSON;
      const drainLayer = (await apiFetch("/api/geo/drains").then((r) => r.json())) as GeoJSON;
      const intel = (await apiFetch("/api/intelligence/geojson").then((r) => r.json())) as GeoJSON;
      map.addSource("src-roads", { type: "geojson", data: roads });
      map.addSource("src-drains", { type: "geojson", data: drainLayer });
      map.addSource("src-intel", { type: "geojson", data: intel });
      map.addLayer({
        id: "roads-line",
        type: "line",
        source: "src-roads",
        paint: { "line-color": "#64748b", "line-width": 1.2 },
      });
      map.addLayer({
        id: "drains-line",
        type: "line",
        source: "src-drains",
        paint: { "line-color": "#0f766e", "line-width": 2, "line-dasharray": [2, 1] },
      });
      map.addLayer({
        id: "intel-links",
        type: "line",
        source: "src-intel",
        filter: ["==", ["geometry-type"], "LineString"],
        paint: {
          "line-color": ["match", ["get", "asset_kind"], "drain", "#0d9488", "water", "#0284c7", "#f59e0b"],
          "line-width": 2,
          "line-dasharray": [1, 1],
        },
      });
      map.addLayer({
        id: "intel-issues",
        type: "circle",
        source: "src-intel",
        filter: ["==", ["get", "record_type"], "verified_issue"],
        paint: {
          "circle-radius": 8,
          "circle-color": "#ea580c",
          "circle-stroke-width": 1,
          "circle-stroke-color": "#0f172a",
        },
      });
      map.on("click", "intel-issues", (event) => {
        const publicId = event.features?.[0]?.properties?.public_id;
        if (typeof publicId === "string") {
          void openIssue(publicId);
        }
      });
    };
    onStyleReady(map, () => void onReady());
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <div className="flex h-full min-h-0">
      <aside className="w-80 overflow-auto border-r border-slate-800 p-4 text-sm">
        <p className="text-xs uppercase tracking-wide text-slate-500">City Intelligence</p>
        <p className="mt-2 text-xs text-amber-300">{disclaimer}</p>
        <p className="mt-2 text-xs text-slate-400">{drainNote}</p>
        <p className="mt-2 text-xs">OSM drain features in envelope: {drains ?? "—"}</p>
        <button className="mt-3 w-full rounded bg-sky-700 py-2" onClick={() => void refresh()}>
          Recompute spatial links
        </button>
        {message ? <p className="mt-2 text-xs text-emerald-400">{message}</p> : null}
        <p className="mt-4 font-semibold">Verified issues ({issues.length})</p>
        <ul className="mt-2 space-y-2">
          {issues.map((item) => (
            <li key={item.public_id}>
              <button
                className="w-full rounded border border-slate-800 p-2 text-left hover:border-slate-600"
                onClick={() => void openIssue(item.public_id)}
              >
                <p className="font-mono text-xs">{item.public_id}</p>
                <p>
                  {item.category} · {item.status}
                </p>
                <p className="text-xs text-slate-400">
                  {item.road ? `${item.road} (${item.road_distance_m} m)` : "No OSM road within 60 m"}
                </p>
                <p className="text-xs text-slate-500">{item.drain ? `Drain: ${item.drain}` : "No OSM drain snap"}</p>
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <main ref={mapNode} className="min-w-0 flex-1" />
      <aside className="w-96 overflow-auto border-l border-slate-800 p-4 text-sm">
        {!selected ? (
          <p className="text-slate-400">Select a verified issue to inspect road, drain, and recurrence context.</p>
        ) : (
          <div className="space-y-3">
            <h1 className="font-mono text-lg">{selected.issue.public_id}</h1>
            <p>
              {selected.issue.category} · {selected.issue.severity} · {selected.issue.status}
            </p>
            <p className="text-xs text-slate-400">{selected.issue.title}</p>
            <h2 className="font-semibold">Infrastructure links</h2>
            {selected.assets.length === 0 ? (
              <p className="text-xs text-slate-400">No spatial snaps yet. Recompute links.</p>
            ) : (
              selected.assets.map((asset) => (
                <p key={`${asset.kind}-${asset.name}`} className="text-xs text-slate-300">
                  <span className="uppercase text-slate-500">{asset.kind}</span> · {asset.name} · {asset.distance_m} m
                  <br />
                  {asset.notes}
                </p>
              ))
            )}
            <h2 className="font-semibold">Issue relations</h2>
            {selected.relations.length === 0 ? (
              <p className="text-xs text-slate-400">No nearby, same-road, or recurrence flags.</p>
            ) : (
              selected.relations.map((row, index) => (
                <p key={index} className="text-xs text-slate-300">
                  {row.relation_type}: {row.from_public_id} → {row.to_public_id} · {row.distance_m} m
                  {row.days_apart != null ? ` · ${row.days_apart} days` : ""}
                  <br />
                  {row.notes}
                </p>
              ))
            )}
            <h2 className="font-semibold">History</h2>
            {selected.history.map((event, index) => (
              <p key={index} className="text-xs text-slate-400">
                {event.at}: {event.summary}
              </p>
            ))}
            <h2 className="font-semibold">Relationship graph</h2>
            <ul className="space-y-1 text-xs text-slate-400">
              {(graph?.edges ?? [])
                .filter(
                  (edge) =>
                    edge.from.includes(selected.issue.public_id) || edge.to.includes(selected.issue.public_id),
                )
                .map((edge) => (
                  <li key={`${edge.from}-${edge.to}-${edge.relation_type}`}>
                    {edge.from} — {edge.relation_type} → {edge.to}
                  </li>
                ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}
