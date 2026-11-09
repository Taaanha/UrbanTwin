import type maplibregl from "maplibre-gl";
import { apiFetch } from "./api";

export const PITCH_3D = 58;

/** Closed ring approximating a circle of `radiusM` metres around a point (for 3D columns and tree crowns). */
export function circleRing(lon: number, lat: number, radiusM: number, steps = 12): number[][] {
  const dLat = radiusM / 110_574;
  const dLon = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180));
  const ring: number[][] = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return ring;
}

export const columnFeature = (lon: number, lat: number, radiusM: number, props: Record<string, unknown>) => ({
  type: "Feature" as const,
  geometry: { type: "Polygon" as const, coordinates: [circleRing(lon, lat, radiusM)] },
  properties: props,
});

/**
 * Illustrative tree crowns for a planting site: one column per tree in a sunflower-seed pattern.
 * The pattern is for picturing the scale only; real tree positions are not modelled.
 */
export function treeFeatures(lon: number, lat: number, trees: number, crownRadiusM: number) {
  const discRadius = crownRadiusM * Math.sqrt(trees);
  const golden = Math.PI * (3 - Math.sqrt(5));
  const out = [];
  for (let i = 0; i < trees; i++) {
    const r = discRadius * Math.sqrt((i + 0.5) / trees) * 0.94;
    const a = i * golden;
    const dLat = (r * Math.sin(a)) / 110_574;
    const dLon = (r * Math.cos(a)) / (111_320 * Math.cos((lat * Math.PI) / 180));
    out.push(columnFeature(lon + dLon, lat + dLat, crownRadiusM * 0.8, { h: 7 + ((i * 7) % 5) }));
  }
  return out;
}

const DEFAULT_COLOR = [
  "interpolate",
  ["linear"],
  ["get", "height_m"],
  3,
  "#4c6a9c",
  10,
  "#7f9fd4",
  25,
  "#c3d6f7",
] as unknown as maplibregl.ExpressionSpecification;

let buildingsPromise: Promise<unknown> | null = null;
/** One shared request for the footprints (both swipe maps and the page need them); a failure is not remembered. */
function loadBuildings(): Promise<unknown> {
  if (!buildingsPromise) {
    buildingsPromise = apiFetch("/api/geo/buildings")
      .then((r) => r.json())
      .catch((e) => {
        buildingsPromise = null;
        throw e;
      });
  }
  return buildingsPromise;
}

/** Adds the `buildings-3d` extrusion layer (hidden). Fetches the footprints if the page has not loaded them yet. */
export async function addBuildings3D(map: maplibregl.Map, before?: string): Promise<void> {
  if (map.getLayer("buildings-3d")) return;
  if (!map.getSource("src-buildings")) {
    const data = await loadBuildings();
    if (!map.getSource("src-buildings")) map.addSource("src-buildings", { type: "geojson", data });
  }
  if (map.getLayer("buildings-3d")) return;
  map.addLayer(
    {
      id: "buildings-3d",
      type: "fill-extrusion",
      source: "src-buildings",
      layout: { visibility: "none" },
      paint: {
        "fill-extrusion-color": DEFAULT_COLOR,
        "fill-extrusion-height": ["get", "height_m"],
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.92,
        "fill-extrusion-vertical-gradient": true,
      },
    },
    before && map.getLayer(before) ? before : undefined,
  );
}

/** Tilts the camera and shows/hides extrusions. `flatLayers` are the 2D layers hidden while 3D is on. */
export function set3D(map: maplibregl.Map, on: boolean, flatLayers: string[] = ["buildings-fill"]): void {
  try {
    map.setLight({ anchor: "map", color: "#ffffff", intensity: 0.38, position: [1.4, 215, 38] });
  } catch {
    /* lighting is cosmetic */
  }
  for (const id of flatLayers) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "none" : "visible");
  if (map.getLayer("buildings-3d")) map.setLayoutProperty("buildings-3d", "visibility", on ? "visible" : "none");
  map.easeTo({ pitch: on ? PITCH_3D : 0, bearing: on ? -20 : 0, duration: 800 });
}
