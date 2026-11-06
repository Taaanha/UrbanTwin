import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";

const NOAKHALI_CENTER: [number, number] = [91.099, 22.869];

type HealthResponse = {
  status: string;
  service?: string;
  database?: string;
  postgis?: string;
  detail?: string;
};

export default function App() {
  const mapNode = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then(async (response) => {
        const body = (await response.json()) as HealthResponse;
        if (!cancelled) {
          setHealth(body);
          setHealthError(null);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setHealthError(error instanceof Error ? error.message : "Backend unreachable");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!mapNode.current || mapRef.current) {
      return;
    }

    const map = new maplibregl.Map({
      container: mapNode.current,
      center: NOAKHALI_CENTER,
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
    new maplibregl.Marker({ color: "#1d4ed8" })
      .setLngLat(NOAKHALI_CENTER)
      .setPopup(
        new maplibregl.Popup({ offset: 16 }).setText(
          "Noakhali Paurashava (approximate centre for Phase 0)",
        ),
      )
      .addTo(map);

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  const backendOk = health?.status === "ok" && health.database === "connected";

  return (
    <div className="flex h-full flex-col bg-slate-950 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-800 px-6 py-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-400">UrbanTwin</p>
          <h1 className="text-lg font-semibold">Noakhali Paurashava map</h1>
        </div>
        <div className="text-right text-sm">
          {healthError ? (
            <p className="text-amber-400">Backend offline — start FastAPI on port 8000</p>
          ) : backendOk ? (
            <p className="text-emerald-400">
              API + PostGIS connected ({health?.postgis})
            </p>
          ) : (
            <p className="text-slate-400">Checking backend…</p>
          )}
        </div>
      </header>
      <main ref={mapNode} className="min-h-0 flex-1" />
    </div>
  );
}
