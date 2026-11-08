import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import maplibregl from "maplibre-gl";

type HealthResponse = {
  status: string;
  database?: string;
};

type GeoJSON = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: string; coordinates: unknown };
    properties: Record<string, unknown>;
  }>;
};

type LayerId =
  | "study"
  | "upazila"
  | "wards"
  | "roads"
  | "buildings"
  | "water"
  | "drains";

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

type ReportItem = {
  tracking_id: string;
  category: string;
  severity: string;
  status: string;
  description: string;
  latitude: number;
  longitude: number;
};

export default function Dashboard() {
  const mapNode = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [visible, setVisible] = useState<Record<LayerId, boolean>>({
    study: true,
    upazila: false,
    wards: false,
    roads: true,
    buildings: true,
    water: true,
    drains: true,
  });

  useEffect(() => {
    apiFetch("/api/health")
      .then((response) => response.json())
      .then(setHealth)
      .catch(() => undefined);
    apiFetch("/api/geo/summary")
      .then((response) => response.json())
      .then(setSummary)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (severity) params.set("severity", severity);
    if (status) params.set("status", status);
    const query = params.toString();
    apiFetch(`/api/reports${query ? `?${query}` : ""}`)
      .then((response) => response.json())
      .then((body) => setReports(body.items ?? []))
      .catch(() => undefined);
    const map = mapRef.current;
    if (map?.getSource("src-reports")) {
      void apiFetch(`/api/reports/geojson${query ? `?${query}` : ""}`)
        .then((response) => response.json())
        .then((data) => {
          const source = map.getSource("src-reports") as maplibregl.GeoJSONSource;
          source.setData(data);
        });
    }
  }, [category, severity, status]);

  useEffect(() => {
    if (!mapNode.current || mapRef.current) {
      return;
    }
    const map = new maplibregl.Map({
      container: mapNode.current,
      center: [91.099, 22.869],
      zoom: 13,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;
    const onReady = () => {
      map.resize();
      void loadLayers(map);
    };
    if (map.loaded()) onReady();
    else map.once("load", onReady);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    const set = (ids: string[], on: boolean) => {
      ids.forEach((id) => {
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
        }
      });
    };
    set(["study-fill", "study-line"], visible.study);
    set(["upazila-line"], visible.upazila);
    set(["wards-fill", "wards-line"], visible.wards);
    set(["roads-line"], visible.roads);
    set(["buildings-fill"], visible.buildings);
    set(["water-fill", "water-line"], visible.water);
    set(["drains-line"], visible.drains);
  }, [visible]);

  async function setReportStatus(trackingId: string, next: string) {
    await apiFetch(`/api/reports/track/${trackingId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    setStatus((current) => current);
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (severity) params.set("severity", severity);
    const query = params.toString();
    const body = await apiFetch(`/api/reports${query ? `?${query}` : ""}`).then((r) => r.json());
    setReports(body.items ?? []);
  }

  const backendOk = health?.status === "ok" && health.database === "connected";

  return (
    <div className="flex h-full min-h-0">
      <aside className="w-80 overflow-auto border-r border-slate-800 p-4 text-sm">
        <p className="text-xs uppercase tracking-wide text-slate-500">City Monitor</p>
        <p className={backendOk ? "text-emerald-400" : "text-amber-400"}>
          {backendOk ? "PostGIS connected" : "Backend offline"}
        </p>
        <p className="mt-2 text-xs text-amber-300">
          Map dots are citizen reports, not verified issues.
        </p>
        <label className="mt-3 block">
          Category
          <select className="mt-1 w-full rounded bg-slate-900 p-1" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All</option>
            <option value="pothole">Pothole</option>
            <option value="damaged_road">Damaged road</option>
            <option value="blocked_drainage">Blocked drainage</option>
            <option value="waterlogging">Waterlogging</option>
            <option value="garbage">Garbage</option>
            <option value="flooding">Flooding</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="mt-2 block">
          Severity
          <select className="mt-1 w-full rounded bg-slate-900 p-1" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">All</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </label>
        <label className="mt-2 block">
          Status
          <select className="mt-1 w-full rounded bg-slate-900 p-1" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="submitted">Submitted</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="under_review">Under review</option>
            <option value="insufficient_evidence">Insufficient evidence</option>
            <option value="resolved_unverified">Resolved (unverified)</option>
          </select>
        </label>
        <p className="mt-4 font-semibold">OSM layers</p>
        {(Object.keys(LAYER_LABELS) as LayerId[]).map((id) => (
          <label key={id} className="mt-1 flex gap-2">
            <input
              type="checkbox"
              checked={visible[id]}
              onChange={() => setVisible((cur) => ({ ...cur, [id]: !cur[id] }))}
            />
            {LAYER_LABELS[id]}
          </label>
        ))}
        <p className="mt-4 text-xs text-slate-500">
          Roads {summary.roads ?? "—"} · Buildings {summary.buildings ?? "—"}
        </p>
        <p className="mt-4 font-semibold">Reports ({reports.length})</p>
        <ul className="mt-2 space-y-2">
          {reports.map((item) => (
            <li key={item.tracking_id} className="rounded border border-slate-800 p-2">
              <p className="font-mono text-xs">{item.tracking_id}</p>
              <p>
                {item.category} · {item.severity}
              </p>
              <p className="text-xs text-slate-400 line-clamp-2">{item.description}</p>
              <select
                className="mt-1 w-full rounded bg-slate-900 p-1 text-xs"
                value={item.status}
                onChange={(event) => void setReportStatus(item.tracking_id, event.target.value)}
              >
                <option value="submitted">submitted</option>
                <option value="acknowledged">acknowledged</option>
                <option value="under_review">under_review</option>
                <option value="insufficient_evidence">insufficient_evidence</option>
                <option value="resolved_unverified">resolved_unverified</option>
              </select>
            </li>
          ))}
        </ul>
      </aside>
      <main ref={mapNode} className="min-w-0 flex-1" />
    </div>
  );
}

async function loadLayers(map: maplibregl.Map) {
  const collections = await Promise.all(
    (Object.keys(LAYER_ENDPOINTS) as LayerId[]).map(async (id) => {
      const data = (await apiFetch(LAYER_ENDPOINTS[id]).then((r) => r.json())) as GeoJSON;
      return [id, data] as const;
    }),
  );
  for (const [id, data] of collections) {
    if (!map.getSource(`src-${id}`)) {
      map.addSource(`src-${id}`, { type: "geojson", data });
    }
  }
  addFill(map, "study-fill", "src-study", "#38bdf8", 0.06);
  addLine(map, "study-line", "src-study", "#38bdf8", 2);
  addLine(map, "upazila-line", "src-upazila", "#c084fc", 2, [2, 2]);
  addFill(map, "wards-fill", "src-wards", "#f59e0b", 0.12);
  addLine(map, "wards-line", "src-wards", "#b45309", 1);
  addLine(map, "roads-line", "src-roads", "#1e293b", 1.4);
  addFill(map, "buildings-fill", "src-buildings", "#64748b", 0.45);
  addFill(map, "water-fill", "src-water", "#0ea5e9", 0.45);
  addLine(map, "water-line", "src-water", "#0369a1", 1);
  addLine(map, "drains-line", "src-drains", "#0f766e", 2);

  const reports = (await apiFetch("/api/reports/geojson").then((r) => r.json())) as GeoJSON;
  if (!map.getSource("src-reports")) {
    map.addSource("src-reports", { type: "geojson", data: reports });
    map.addLayer({
      id: "reports-circle",
      type: "circle",
      source: "src-reports",
      paint: {
        "circle-radius": 7,
        "circle-stroke-width": 1,
        "circle-stroke-color": "#0f172a",
        "circle-color": [
          "match",
          ["get", "status"],
          "insufficient_evidence",
          "#94a3b8",
          "resolved_unverified",
          "#22c55e",
          [
            "match",
            ["get", "severity"],
            "critical",
            "#dc2626",
            "high",
            "#ea580c",
            "medium",
            "#eab308",
            "#64748b",
          ],
        ],
      },
    });
    map.on("click", "reports-circle", (event) => {
      const props = event.features?.[0]?.properties ?? {};
      new maplibregl.Popup()
        .setLngLat(event.lngLat)
        .setHTML(
          `<strong>${props.tracking_id}</strong><p>${props.category} · ${props.severity}</p><p>Citizen report, not a verified issue.</p>`,
        )
        .addTo(map);
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

function addLine(
  map: maplibregl.Map,
  id: string,
  source: string,
  color: string,
  width: number,
  dash?: number[],
) {
  if (map.getLayer(id)) return;
  map.addLayer({
    id,
    type: "line",
    source,
    paint: {
      "line-color": color,
      "line-width": width,
      ...(dash ? { "line-dasharray": dash } : {}),
    },
  });
}
