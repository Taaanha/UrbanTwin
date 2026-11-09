import maplibregl from "maplibre-gl";

export type Basemap = "dark" | "standard" | "satellite";
const KEY = "urbantwin.basemap";

export function getBasemap(): Basemap {
  try {
    const v = localStorage.getItem(KEY);
    return v === "standard" || v === "satellite" ? v : "dark";
  } catch {
    return "dark";
  }
}

export function setBasemap(map: maplibregl.Map, mode: Basemap): void {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    /* preference simply will not persist */
  }
  const show = { "base-dark": "dark", "base-osm": "standard", "base-sat": "satellite" } as const;
  for (const [layer, name] of Object.entries(show)) {
    if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", mode === name ? "visible" : "none");
  }
}

/**
 * Runs `callback` once the map's (inline) style has been parsed, i.e. the base layers exist and overlays can be added.
 * The "load" event is no use here because it waits for background tiles, and `isStyleLoaded()` is also false
 * while tiles download, so overlays would never start when the tile server is slow, blocked or offline.
 */
export function onStyleReady(map: maplibregl.Map, callback: () => void): void {
  let done = false;
  let timer: ReturnType<typeof setInterval> | undefined;
  const ready = () => {
    try {
      return Boolean(map.getLayer("base-dark")) || Boolean(map.getSource("osm"));
    } catch {
      return false;
    }
  };
  const check = () => {
    if (done || !ready()) return;
    done = true;
    if (timer) clearInterval(timer);
    map.off("styledata", check);
    map.off("load", check);
    callback();
  };
  map.on("styledata", check);
  map.on("load", check);
  // Safety net: poll until the style object has been parsed (events can fire before the layers exist).
  timer = setInterval(check, 50);
  map.once("remove", () => { done = true; if (timer) clearInterval(timer); });
  setTimeout(() => { if (!done) console.warn("[map] style still not ready after 15 s"); }, 15_000);
  check();
}

export function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/** A do-nothing stand-in so pages keep working (lists, filters, forms) when WebGL is unavailable. */
function stubMap(container: HTMLElement): maplibregl.Map {
  container.innerHTML =
    '<div class="grid h-full w-full place-items-center bg-slate-950 p-6"><div class="glass max-w-sm p-4 text-center text-xs text-slate-300">' +
    '<p class="text-sm font-semibold text-white">The map could not start</p>' +
    '<p class="mt-1">This browser has WebGL turned off or unsupported. Turn on hardware acceleration, or open the page in Chrome or Edge. Everything except the map still works.</p>' +
    "</div></div>";
  // eslint-disable-next-line prefer-const
  let proxy: unknown;
  proxy = new Proxy(function () {}, {
    get: (_t, prop) => (typeof prop === "symbol" || prop === "then" ? undefined : proxy),
    set: () => true,
    apply: () => proxy,
  });
  return proxy as maplibregl.Map;
}

/**
 * Shared base map centred on the Noakhali study area.
 * All raster basemaps are in the style so the toggle never reloads overlays:
 * "dark" = dimmed OpenStreetMap tiles, "standard" = OpenStreetMap tiles, "satellite" = Esri imagery. No API keys.
 */
export function createMap(container: HTMLElement, options: { controls?: boolean } = {}): maplibregl.Map {
  const mode = getBasemap();
  if (!webglAvailable()) return stubMap(container);
  const map = new maplibregl.Map({
    container,
    center: [91.099, 22.869],
    zoom: 13.5,
    attributionControl: { compact: true },
    style: {
      version: 8,
      sources: {
        osm: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: "© OpenStreetMap contributors",
        },
        // Esri World Imagery needs no key. Please keep the attribution; check Esri's terms before any public launch.
        sat: {
          type: "raster",
          tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
          tileSize: 256,
          maxzoom: 19,
          attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
        },
      },
      layers: [
        { id: "base-sat", type: "raster", source: "sat", layout: { visibility: mode === "satellite" ? "visible" : "none" } },
        { id: "base-osm", type: "raster", source: "osm", layout: { visibility: mode === "standard" ? "visible" : "none" } },
        {
          id: "base-dark",
          type: "raster",
          source: "osm",
          layout: { visibility: mode === "dark" ? "visible" : "none" },
          // Keyless "dark": the same OSM tiles, dimmed and desaturated so overlays stand out.
          paint: { "raster-brightness-max": 0.42, "raster-saturation": -0.75, "raster-contrast": 0.15 },
        },
      ],
    },
  });
  if (options.controls !== false) map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  map.once("load", () => map.resize());
  let lastTileWarning = 0;
  map.on("error", (event) => {
    const status = (event.error as { status?: number } | undefined)?.status;
    const isTile = Boolean((event as { tile?: unknown }).tile) || (event as { sourceId?: string }).sourceId === "osm" || (event as { sourceId?: string }).sourceId === "sat";
    if (!isTile || Date.now() - lastTileWarning < 30_000) return;
    lastTileWarning = Date.now();
    window.dispatchEvent(
      new CustomEvent("urbantwin-problem", {
        detail: `Map background tiles are not loading${status ? ` (error ${status})` : ""}. This is usually the network or a blocked tile server. Your data layers still work; try another background (Dark, Street or Satellite).`,
      }),
    );
  });
  return map;
}
