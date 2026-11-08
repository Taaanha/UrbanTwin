import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import maplibregl from "maplibre-gl";

type Rate = {
  id: number;
  action_code: string;
  category: string;
  unit: string;
  amount_bdt: number;
  is_demo: boolean;
  notes: string;
};

type Intervention = {
  public_id: string;
  action_code: string;
  issue_public_id: string;
  title: string;
  category: string;
  severity: string;
  quantity: number;
  unit: string;
  priority_score: number;
  ward?: string;
  longitude: number;
  latitude: number;
  assumptions: string;
  cost: {
    is_indicative: boolean;
    total_low_bdt: number;
    total_mid_bdt: number;
    total_high_bdt: number;
    labour_bdt: number;
    materials_bdt: number;
    equipment_bdt: number;
    contingency_bdt: number;
  };
};

type Plan = {
  method: string;
  notes: string;
  budget_bdt: number;
  spent_bdt: number;
  remaining_bdt: number;
  included_count: number;
  deferred_count: number;
  included: Intervention[];
  deferred: Intervention[];
};

type Compare = {
  disclaimer: string;
  limitations: string[];
  plans: Plan[];
};

function money(value: number) {
  return `BDT ${Math.round(value).toLocaleString("en-BD")}`;
}

export default function Planner() {
  const mapNode = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [rates, setRates] = useState<Rate[]>([]);
  const [items, setItems] = useState<Intervention[]>([]);
  const [compare, setCompare] = useState<Compare | null>(null);
  const [budget, setBudget] = useState("200000");
  const [method, setMethod] = useState("greedy_value");
  const [selected, setSelected] = useState<Intervention | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const plan = compare?.plans.find((row) => row.method === method) ?? compare?.plans[0];

  async function loadRates() {
    const body = await apiFetch("/api/planner/rates").then((r) => r.json());
    setRates(body.items ?? []);
  }

  async function loadInterventions() {
    const body = await apiFetch("/api/planner/interventions").then((r) => r.json());
    setItems(body.items ?? []);
  }

  async function generate() {
    const body = await apiFetch("/api/planner/interventions/generate", { method: "POST" }).then((r) => r.json());
    setItems(body.items ?? []);
    setMessage(`Drafted ${body.interventions} indicative interventions.`);
  }

  async function runCompare() {
    const amount = Number(budget);
    const body = (await apiFetch("/api/planner/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ budget_bdt: amount }),
    }).then((r) => r.json())) as Compare;
    setCompare(body);
    setMessage(`Compared four budget methods (3 greedy + OR-Tools optimal) under ${money(amount)}.`);
  }

  async function saveRate(id: number, amount: string) {
    const value = Number(amount);
    if (!value) return;
    await apiFetch(`/api/planner/rates/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount_bdt: value }),
    });
    await loadRates();
  }

  useEffect(() => {
    void loadRates();
    void loadInterventions();
  }, []);

  useEffect(() => {
    if (!mapNode.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapNode.current,
      center: [91.099, 22.869],
      zoom: 14,
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
    const onReady = () => map.resize();
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
    const collection = {
      type: "FeatureCollection" as const,
      features: (plan ? [...plan.included, ...plan.deferred] : items).map((item) => ({
        type: "Feature" as const,
        geometry: { type: "Point", coordinates: [item.longitude, item.latitude] },
        properties: {
          public_id: item.public_id,
          included: plan ? plan.included.some((row) => row.public_id === item.public_id) : false,
          score: item.priority_score,
        },
      })),
    };
    const source = map.getSource("src-plan") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(collection);
      return;
    }
    map.addSource("src-plan", { type: "geojson", data: collection });
    map.addLayer({
      id: "plan-circles",
      type: "circle",
      source: "src-plan",
      paint: {
        "circle-radius": ["+", 6, ["*", ["get", "score"], 0.08]],
        "circle-color": ["case", ["get", "included"], "#16a34a", "#94a3b8"],
        "circle-stroke-width": 1,
        "circle-stroke-color": "#0f172a",
      },
    });
    map.on("click", "plan-circles", (event) => {
      const publicId = event.features?.[0]?.properties?.public_id;
      const found = (plan ? [...plan.included, ...plan.deferred] : items).find((row) => row.public_id === publicId);
      if (found) setSelected(found);
    });
  }, [items, plan]);

  return (
    <div className="flex h-full min-h-0">
      <aside className="w-80 overflow-auto border-r border-slate-800 p-4 text-sm">
        <p className="text-xs uppercase tracking-wide text-slate-500">City Planner</p>
        <p className="mt-2 text-xs text-amber-300">
          Costs are indicative lab placeholders in BDT. They are not official Paurashava, LGED, or PWD rates.
        </p>
        <label className="mt-3 block text-xs">
          Scenario budget (BDT)
          <input
            className="mt-1 w-full rounded bg-slate-900 p-2"
            value={budget}
            onChange={(event) => setBudget(event.target.value)}
          />
        </label>
        <button className="mt-3 w-full rounded bg-slate-800 py-2" onClick={() => void generate()}>
          Draft interventions
        </button>
        <button className="mt-2 w-full rounded bg-sky-700 py-2" onClick={() => void runCompare()}>
          Compare budget packs
        </button>
        {message ? <p className="mt-2 text-xs text-emerald-400">{message}</p> : null}
        <p className="mt-4 font-semibold">Placeholder unit rates</p>
        <ul className="mt-2 space-y-2">
          {rates.map((row) => (
            <li key={row.id} className="rounded border border-slate-800 p-2">
              <p className="text-xs">
                {row.category} · {row.action_code} / {row.unit}
              </p>
              <input
                className="mt-1 w-full rounded bg-slate-900 p-1"
                defaultValue={row.amount_bdt}
                onBlur={(event) => void saveRate(row.id, event.target.value)}
              />
              <p className="text-[11px] text-slate-500">{row.is_demo ? "Demo rate" : ""} · {row.notes}</p>
            </li>
          ))}
        </ul>
      </aside>
      <main ref={mapNode} className="min-w-0 flex-1" />
      <aside className="w-[26rem] overflow-auto border-l border-slate-800 p-4 text-sm">
        {plan ? (
          <div className="space-y-3">
            <div className="flex gap-1">
              {compare?.plans.map((row) => (
                <button
                  key={row.method}
                  className={`rounded px-2 py-1 text-xs ${method === row.method ? "bg-sky-800" : "bg-slate-800"}`}
                  onClick={() => setMethod(row.method)}
                >
                  {row.method.replace("greedy_", "")}
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-400">{plan.notes}</p>
            <p>
              Spent {money(plan.spent_bdt)} of {money(plan.budget_bdt)} · {plan.included_count} in ·{" "}
              {plan.deferred_count} deferred
            </p>
            <p className="text-xs text-slate-500">Green = packed under this scenario. Grey = deferred. Not an approved project.</p>
            <h2 className="font-semibold">Included</h2>
            {plan.included.map((item) => (
              <button
                key={item.public_id}
                className="block w-full rounded border border-slate-800 p-2 text-left"
                onClick={() => setSelected(item)}
              >
                <p className="font-mono text-xs">{item.public_id}</p>
                <p>
                  {item.category} · score {item.priority_score} · {money(item.cost.total_mid_bdt)}
                </p>
              </button>
            ))}
            <h2 className="font-semibold">Deferred</h2>
            {plan.deferred.map((item) => (
              <button
                key={item.public_id}
                className="block w-full rounded border border-slate-800 p-2 text-left text-slate-400"
                onClick={() => setSelected(item)}
              >
                <p className="font-mono text-xs">{item.public_id}</p>
                <p>
                  {item.category} · {money(item.cost.total_mid_bdt)}
                </p>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-slate-400">Draft interventions, then compare packs under a scenario budget.</p>
        )}
        {selected ? (
          <div className="mt-4 space-y-1 border-t border-slate-800 pt-3 text-xs">
            <h2 className="font-mono text-sm text-slate-100">{selected.public_id}</h2>
            <p>
              {selected.action_code} · {selected.quantity} {selected.unit} · score {selected.priority_score}
            </p>
            <p>
              Indicative {money(selected.cost.total_low_bdt)} – {money(selected.cost.total_high_bdt)} (mid{" "}
              {money(selected.cost.total_mid_bdt)})
            </p>
            <p>
              Labour {money(selected.cost.labour_bdt)} · materials {money(selected.cost.materials_bdt)} · equipment{" "}
              {money(selected.cost.equipment_bdt)} · contingency {money(selected.cost.contingency_bdt)}
            </p>
            <p className="text-slate-400">{selected.assumptions}</p>
          </div>
        ) : null}
        {compare ? (
          <ul className="mt-4 list-disc pl-4 text-[11px] text-slate-500">
            {compare.limitations.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
      </aside>
    </div>
  );
}
