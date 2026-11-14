import type maplibregl from "maplibre-gl";
import { apiFetch } from "./api";

export type PlaceHit = { label: string; sub?: string; lon: number; lat: number; kind: "road" | "place" };

// Search is limited to the Noakhali Paurashava area (lon/lat west, north, east, south).
const VIEWBOX = { west: 91.05, north: 22.9, east: 91.15, south: 22.83 };

type RoadIndexEntry = { name: string; lon: number; lat: number };
let roadIndex: Promise<RoadIndexEntry[]> | null = null;

/** Named roads from our own data, one entry per name (the middle of its longest segment). Cached; a failure is retried next time. */
function loadRoadIndex(): Promise<RoadIndexEntry[]> {
  if (!roadIndex) {
    roadIndex = apiFetch("/api/geo/roads", {}, { quiet: true })
      .then((r) => r.json())
      .then((data: { features: Array<{ properties?: { name?: string | null }; geometry?: { type: string; coordinates: number[][] } }> }) => {
        const best = new Map<string, { len: number; entry: RoadIndexEntry }>();
        for (const f of data.features) {
          const name = f.properties?.name?.trim();
          const coords = f.geometry?.type === "LineString" ? f.geometry.coordinates : null;
          if (!name || !coords?.length) continue;
          const mid = coords[Math.floor(coords.length / 2)];
          const prev = best.get(name.toLowerCase());
          if (!prev || coords.length > prev.len) best.set(name.toLowerCase(), { len: coords.length, entry: { name, lon: mid[0], lat: mid[1] } });
        }
        return [...best.values()].map((b) => b.entry);
      })
      .catch((e) => {
        roadIndex = null;
        throw e;
      });
  }
  return roadIndex;
}

/** Instant suggestions from the municipality's own road names (works offline from the server's data). */
export async function searchRoads(query: string, limit = 5): Promise<PlaceHit[]> {
  const q = query.trim().toLowerCase();
  if (q.length < 2) return [];
  const [roads, landmarks] = await Promise.all([loadRoadIndex(), loadLandmarks()]);
  const named: PlaceHit[] = landmarks
    .filter((l) => l.name.toLowerCase().includes(q))
    .map((l) => ({ label: l.name, sub: "Landmark", lon: l.lon, lat: l.lat, kind: "road" as const }));
  return [...named, ...roads
    .filter((r) => r.name.toLowerCase().includes(q))
    .sort((a, b) => Number(!a.name.toLowerCase().startsWith(q)) - Number(!b.name.toLowerCase().startsWith(q)) || a.name.length - b.name.length)
    .slice(0, limit)
    .map((r) => ({ label: r.name, sub: "Road", lon: r.lon, lat: r.lat, kind: "road" as const }))].slice(0, limit + named.length);
}

let landmarkList: Promise<Array<{ name: string; lat: number; lon: number }>> | null = null;
function loadLandmarks() {
  if (!landmarkList) {
    landmarkList = apiFetch("/api/geo/landmarks", {}, { quiet: true })
      .then((r) => r.json())
      .then((d: { items: Array<{ name: string; lat: number; lon: number }> }) => d.items)
      .catch(() => {
        landmarkList = null;
        return [];
      });
  }
  return landmarkList;
}

/** OpenStreetMap place search (Nominatim), restricted to the study area. Only sent when the person presses Search. */
export async function searchPlaces(query: string, signal?: AbortSignal, limit = 6): Promise<PlaceHit[]> {
  const q = query.trim();
  if (q.length < 2) return [];
  const url =
    "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=" +
    limit +
    "&countrycodes=bd&bounded=1&accept-language=en,bn&viewbox=" +
    `${VIEWBOX.west},${VIEWBOX.north},${VIEWBOX.east},${VIEWBOX.south}&q=${encodeURIComponent(q)}`;
  const response = await fetch(url, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`search ${response.status}`);
  const rows = (await response.json()) as Array<{ lat: string; lon: string; display_name: string; name?: string }>;
  return rows.map((r) => {
    const [first, ...rest] = r.display_name.split(",").map((s) => s.trim());
    return { label: r.name || first, sub: rest.slice(0, 3).join(", "), lon: Number(r.lon), lat: Number(r.lat), kind: "place" as const };
  });
}

/** Adds the named-road lines and their labels (labels follow the road). Safe to call once the style is ready. */
export async function addRoadLabels(map: maplibregl.Map): Promise<void> {
  if (map.getLayer("road-names")) return;
  const data = await apiFetch("/api/geo/roads", {}, { quiet: true }).then((r) => r.json());
  if (map.getLayer("road-names")) return;
  if (!map.getSource("src-roads")) map.addSource("src-roads", { type: "geojson", data });
  map.addLayer({
    id: "roads-line",
    type: "line",
    source: "src-roads",
    paint: { "line-color": "#f8fafc", "line-opacity": 0.55, "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.8, 18, 3] },
  });
  map.addLayer({
    id: "road-names",
    type: "symbol",
    source: "src-roads",
    minzoom: 14.5,
    filter: ["has", "name"],
    layout: {
      "symbol-placement": "line",
      "text-field": ["get", "name"],
      "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
      "text-size": ["interpolate", ["linear"], ["zoom"], 15, 10, 18, 14],
      "text-letter-spacing": 0.04,
      "text-pitch-alignment": "viewport",
    },
    paint: { "text-color": "#0f172a", "text-halo-color": "#ffffff", "text-halo-width": 1.6 },
  });
}
