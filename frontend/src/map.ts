import maplibregl from "maplibre-gl";

/** Shared OSM raster base map centred on the Noakhali study area. */
export function createMap(container: HTMLElement): maplibregl.Map {
  const map = new maplibregl.Map({
    container,
    center: [91.099, 22.869],
    zoom: 13.5,
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
  map.once("load", () => map.resize());
  return map;
}
