import { useEffect, useRef, useState } from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { apiFetch } from "../api";
import { webglAvailable } from "../map";
import { Link } from "react-router-dom";
import { Notice, PageHeader, SEVERITY_COLOR, SeverityBadge, StatusBadge, categoryLabel } from "../ui";

const REFRESH_MS = 15_000;
const CENTER = { lon: 91.099, lat: 22.869 };
const SEVERITY_HEIGHT: Record<string, number> = { critical: 120, high: 90, medium: 60, low: 40 };

type Picked = { trackingId: string; category: string; severity: string; status: string };
type Detail = { description?: string; location_text?: string | null; created_at?: string };

type Feature ={ geometry?: { type: string; coordinates: number[] }; properties?: Record<string, unknown> };

export default function Live3D() {
  const box = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<{ count: number; at: Date | null }>({ count: 0, at: null });
  const [error, setError] = useState("");
  const [satellite, setSatellite] = useState(false);
  const [selected, setSelected] = useState<Picked | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);

  useEffect(() => {
    setDetail(null);
    if (!selected?.trackingId) return;
    const controller = new AbortController();
    apiFetch(`/api/reports/track/${encodeURIComponent(selected.trackingId)}`, { signal: controller.signal }, { quiet: true })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setDetail(d))
      .catch(() => undefined);
    return () => controller.abort();
  }, [selected]);
  const layers = useRef<{ osm?: Cesium.ImageryLayer; sat?: Cesium.ImageryLayer }>({});

  useEffect(() => {
    if (!box.current) return;
    if (!webglAvailable()) {
      setError("This browser has WebGL turned off or unsupported, so the 3D view cannot start.");
      return;
    }
    // No Ion account needed: OpenStreetMap imagery, flat terrain, and our own building footprints.
    const viewer = new Cesium.Viewer(box.current, {
      baseLayer: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: true,
    });
    layers.current.osm = viewer.imageryLayers.addImageryProvider(
      new Cesium.OpenStreetMapImageryProvider({ url: "https://tile.openstreetmap.org/" }),
    );
    layers.current.sat = viewer.imageryLayers.addImageryProvider(
      new Cesium.UrlTemplateImageryProvider({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        maximumLevel: 19,
        credit: "Imagery © Esri, Maxar, Earthstar Geographics",
      }),
    );
    layers.current.sat.show = false;
    // Visible ground even while (or if) the map tiles cannot load.
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1e293b");
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(CENTER.lon, CENTER.lat - 0.012, 1400),
      orientation: { heading: 0, pitch: Cesium.Math.toRadians(-40), roll: 0 },
    });

    let stop = false;
    const picks = new Map<string, Picked>();

    // Our own details panel replaces Cesium's built-in info box.
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((click: { position: Cesium.Cartesian2 }) => {
      const hit = viewer.scene.pick(click.position);
      const id = hit?.id instanceof Cesium.Entity ? String(hit.id.id) : "";
      setSelected(picks.get(id) ?? null);
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    async function loadBuildings() {
      try {
        const data = await apiFetch("/api/geo/buildings").then((r) => r.json());
        const ds = await Cesium.GeoJsonDataSource.load(data);
        if (stop) return;
        const now = Cesium.JulianDate.now();
        for (const e of ds.entities.values) {
          if (!e.polygon) continue;
          const h = Number(e.properties?.height_m?.getValue(now) ?? 6) || 6;
          e.polygon.height = new Cesium.ConstantProperty(0);
          e.polygon.extrudedHeight = new Cesium.ConstantProperty(h);
          e.polygon.material = new Cesium.ColorMaterialProperty(Cesium.Color.fromCssColorString("#9fb4d8").withAlpha(0.9));
          e.polygon.outline = new Cesium.ConstantProperty(false);
        }
        await viewer.dataSources.add(ds);
      } catch {
        if (!stop) setError("Building footprints could not be loaded; reports are still shown.");
      }
    }

    async function refreshReports() {
      try {
        const res = await apiFetch("/api/reports/geojson", {}, { quiet: true });
        if (!res.ok) throw new Error(String(res.status));
        const data = (await res.json()) as { features: Feature[] };
        if (stop) return;
        viewer.entities.removeAll();
        picks.clear();
        for (const f of data.features) {
          if (f.geometry?.type !== "Point") continue;
          const [lon, lat] = f.geometry.coordinates;
          const p = f.properties ?? {};
          const sev = String(p.severity ?? "low");
          const color = Cesium.Color.fromCssColorString(SEVERITY_COLOR[sev] ?? "#38bdf8");
          const top = SEVERITY_HEIGHT[sev] ?? 40;
          viewer.entities.add({
            name: String(p.tracking_id ?? "Report"),
            position: Cesium.Cartesian3.fromDegrees(lon, lat, top),
            point: { pixelSize: 13, color, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
            polyline: {
              positions: Cesium.Cartesian3.fromDegreesArrayHeights([lon, lat, 0, lon, lat, top]),
              width: 2,
              material: color.withAlpha(0.8),
            },
            id: String(p.tracking_id ?? `r-${lon}-${lat}`),
          });
          picks.set(String(p.tracking_id ?? `r-${lon}-${lat}`), { trackingId: String(p.tracking_id ?? ""), category: String(p.category ?? ""), severity: sev, status: String(p.status ?? "") });
        }
        setStatus({ count: viewer.entities.values.length, at: new Date() });
        setError((e) => (e.startsWith("Live reports") ? "" : e));
      } catch {
        if (!stop) setError("Live reports could not be refreshed (staff login may be needed). Retrying automatically.");
      }
    }

    void loadBuildings();
    void refreshReports();
    const timer = window.setInterval(() => void refreshReports(), REFRESH_MS);

    return () => {
      stop = true;
      window.clearInterval(timer);
      handler.destroy();
      viewer.destroy();
    };
  }, []);

  useEffect(() => {
    const { osm, sat } = layers.current;
    if (osm) osm.show = !satellite;
    if (sat) sat.show = satellite;
  }, [satellite]);

  return (
    <div className="flex h-full flex-col gap-3">
      <PageHeader eyebrow="Live view" title="3D City">
        <div className="flex items-center gap-3 text-xs text-slate-400">
          <span>
            {status.count} live reports{status.at ? ` · updated ${status.at.toLocaleTimeString()}` : ""}
          </span>
          <button type="button" className="rounded-md border border-slate-700 px-2 py-1 hover:bg-slate-800" onClick={() => setSatellite((s) => !s)}>
            {satellite ? "Street map" : "Satellite"}
          </button>
        </div>
      </PageHeader>
      {error ? <Notice>{error}</Notice> : null}
      <div className="relative min-h-[520px] flex-1">
        <div ref={box} className="absolute inset-0 isolate z-0 overflow-hidden rounded-xl border border-slate-800" />
        {selected ? (
          <aside className="glass absolute left-3 top-3 z-10 w-72 max-w-[calc(100%-1.5rem)] space-y-2 p-3 text-xs text-slate-200">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="eyebrow">Report</p>
                <p className="num text-sm font-semibold text-white">{selected.trackingId}</p>
              </div>
              <button type="button" aria-label="Close details" className="rounded px-1.5 text-slate-400 hover:text-white" onClick={() => setSelected(null)}>
                ✕
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <SeverityBadge value={selected.severity} />
              <StatusBadge value={selected.status} />
            </div>
            <p>
              <span className="text-slate-400">Category: </span>
              {categoryLabel(selected.category)}
            </p>
            {detail?.location_text ? (
              <p>
                <span className="text-slate-400">Place: </span>
                {detail.location_text}
              </p>
            ) : null}
            {detail?.description ? <p className="max-h-28 overflow-auto text-slate-300">{detail.description}</p> : <p className="text-slate-500">Loading details…</p>}
            <Link to={`/investigator/${selected.trackingId}`} className="inline-block rounded-md bg-sky-600 px-2.5 py-1.5 font-medium text-white hover:bg-sky-500">
              Open in Investigator
            </Link>
          </aside>
        ) : null}
      </div>
      <p className="text-[11px] text-slate-500">
        Drag to pan, scroll to zoom, right-drag or Ctrl+drag to tilt. Marker height shows severity; click a marker for details. Buildings are OSM footprints with estimated heights.
      </p>
    </div>
  );
}
