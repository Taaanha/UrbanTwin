import type maplibregl from "maplibre-gl";
import { apiJson } from "./api";
import { addBuildings3D, treeFeatures } from "./map3d";

export type FC = { type: "FeatureCollection"; features: unknown[] };
export const EMPTY: FC = { type: "FeatureCollection", features: [] };

export type FloodResult = {
  level_m: number;
  connected_only: boolean;
  source: string;
  attribution?: string | null;
  fetched_at: string;
  vertical_error_assumed_m: number;
  disclaimer: string;
  limits: string[];
  buildings_total: number;
  buildings_without_elevation: number;
  flooded_buildings: { low: number; central: number; high: number };
  flooded_pct: { low: number | null; central: number | null; high: number | null };
  flooded_area_km2: { low: number; central: number; high: number };
  water: FC;
  buildings: FC;
};

const setData = (map: maplibregl.Map, id: string, data: FC) => (map.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(data as never);
const show = (map: maplibregl.Map, id: string, on: boolean) => {
  if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
};

/** Adds every source and layer the Simulation page can show. All start hidden/empty. */
export async function initScenarioLayers(map: maplibregl.Map): Promise<void> {
  const green = await apiJson<FC>("/api/simulation/green/geojson").catch(() => null);
  map.addSource("green", { type: "geojson", data: (green ?? EMPTY) as never });
  map.addLayer({ id: "green-fill", type: "fill", source: "green", paint: { "fill-color": "#22c55e", "fill-opacity": 0.45 } });
  map.addSource("sites", { type: "geojson", data: EMPTY as never });
  map.addLayer({
    id: "sites-circle",
    type: "circle",
    source: "sites",
    paint: { "circle-radius": 8, "circle-color": "#38bdf8", "circle-stroke-color": "#fff", "circle-stroke-width": 2 },
  });
  await addBuildings3D(map, "green-fill");

  map.addSource("src-flood-water", { type: "geojson", data: EMPTY as never });
  map.addLayer(
    {
      id: "flood-water",
      type: "fill-extrusion",
      source: "src-flood-water",
      layout: { visibility: "none" },
      paint: { "fill-extrusion-color": "#0ea5e9", "fill-extrusion-height": 0.3, "fill-extrusion-opacity": 0.55 },
    },
    "sites-circle",
  );
  map.addSource("src-flood-bldg", { type: "geojson", data: EMPTY as never });
  map.addLayer(
    {
      id: "flood-bldg",
      type: "fill-extrusion",
      source: "src-flood-bldg",
      layout: { visibility: "none" },
      paint: { "fill-extrusion-color": "#64748b", "fill-extrusion-height": 0.5, "fill-extrusion-opacity": 0.92, "fill-extrusion-vertical-gradient": true },
    },
    "sites-circle",
  );
  map.addSource("src-access", { type: "geojson", data: EMPTY as never });
  map.addLayer(
    {
      id: "access-3d",
      type: "fill-extrusion",
      source: "src-access",
      layout: { visibility: "none" },
      paint: {
        "fill-extrusion-color": ["case", ["get", "access_after"], "#34d399", "#f43f5e"],
        "fill-extrusion-height": 0.5,
        "fill-extrusion-opacity": 0.92,
        "fill-extrusion-vertical-gradient": true,
      },
    },
    "sites-circle",
  );
  map.addSource("src-trees", { type: "geojson", data: EMPTY as never });
  map.addLayer(
    {
      id: "trees-3d",
      type: "fill-extrusion",
      source: "src-trees",
      layout: { visibility: "none" },
      paint: {
        "fill-extrusion-color": ["interpolate", ["linear"], ["get", "h"], 7, "#15803d", 11, "#4ade80"],
        "fill-extrusion-height": ["get", "h"],
        "fill-extrusion-base": 2,
        "fill-extrusion-opacity": 0.95,
      },
    },
    "sites-circle",
  );
}

export type GreenView = {
  access: FC | null;
  showAfter: boolean;
  view3d: boolean;
  sites: Array<{ longitude: number; latitude: number; trees: number }>;
  crownM: number;
};

export function applyGreen(map: maplibregl.Map, o: GreenView): void {
  const have = Boolean(o.access);
  if (o.access) setData(map, "src-access", o.access);
  map.setPaintProperty("access-3d", "fill-extrusion-color", ["case", ["get", o.showAfter ? "access_after" : "access_before"], "#34d399", "#f43f5e"]);
  map.setPaintProperty("access-3d", "fill-extrusion-height", o.view3d ? ["get", "height_m"] : 0.5);
  show(map, "access-3d", have);
  show(map, "flood-water", false);
  show(map, "flood-bldg", false);
  show(map, "buildings-3d", o.view3d && !have);
  const shownSites = o.showAfter ? o.sites : [];
  setData(map, "sites", {
    type: "FeatureCollection",
    features: shownSites.map((s) => ({ type: "Feature", geometry: { type: "Point", coordinates: [s.longitude, s.latitude] }, properties: {} })),
  });
  const trees = o.showAfter && o.view3d ? shownSites.flatMap((s) => treeFeatures(s.longitude, s.latitude, s.trees, o.crownM)) : [];
  setData(map, "src-trees", { type: "FeatureCollection", features: trees });
  show(map, "trees-3d", trees.length > 0);
}

export type FloodView = { data: FloodResult | null; view3d: boolean; dry: boolean };

/** `dry` draws the same buildings with the water left out, for the "current" side of a swipe comparison. */
export function applyFlood(map: maplibregl.Map, o: FloodView): void {
  show(map, "access-3d", false);
  show(map, "trees-3d", false);
  setData(map, "sites", EMPTY);
  if (!o.data) {
    show(map, "flood-water", false);
    show(map, "flood-bldg", false);
    show(map, "buildings-3d", o.view3d);
    return;
  }
  setData(map, "src-flood-water", o.data.water);
  setData(map, "src-flood-bldg", o.data.buildings);
  map.setPaintProperty(
    "flood-bldg",
    "fill-extrusion-color",
    o.dry ? "#7f9fd4" : ["case", ["get", "flooded"], "#38bdf8", ["get", "flooded_possible"], "#fbbf24", "#64748b"],
  );
  map.setPaintProperty("flood-bldg", "fill-extrusion-height", o.view3d ? ["get", "height_m"] : 0.5);
  map.setPaintProperty("flood-water", "fill-extrusion-height", o.view3d ? 1.2 : 0.3);
  show(map, "flood-bldg", true);
  show(map, "flood-water", !o.dry);
  show(map, "buildings-3d", false);
}

/** Keeps two maps on the same camera. Returns the cleanup function. */
export function syncCameras(a: maplibregl.Map, b: maplibregl.Map): () => void {
  let lock = false;
  const follow = (src: maplibregl.Map, dst: maplibregl.Map) => () => {
    if (lock) return;
    lock = true;
    dst.jumpTo({ center: src.getCenter(), zoom: src.getZoom(), bearing: src.getBearing(), pitch: src.getPitch() });
    lock = false;
  };
  const ab = follow(a, b);
  const ba = follow(b, a);
  a.on("move", ab);
  b.on("move", ba);
  ab();
  return () => {
    a.off("move", ab);
    b.off("move", ba);
  };
}
