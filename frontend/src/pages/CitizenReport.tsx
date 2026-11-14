import { FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import maplibregl from "maplibre-gl";
import { createMap, onStyleReady, webglAvailable } from "../map";
import { addBuildings3D, set3D } from "../map3d";
import { addRoadLabels, searchPlaces, searchRoads, type PlaceHit } from "../placeSearch";

type Meta = {
  categories: Record<string, { en: string; bn: string }>;
  severities: string[];
};

type Created = {
  tracking_id: string;
  status: string;
};

const CENTER: [number, number] = [91.099, 22.869];

export default function CitizenReport() {
  const mapNode = useRef<HTMLDivElement | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const [lang, setLang] = useState<"en" | "bn">("en");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [lat, setLat] = useState(CENTER[1]);
  const [lng, setLng] = useState(CENTER[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const placeRef = useRef<HTMLInputElement | null>(null);
  const justChose = useRef(false);
  const [view3d, setView3d] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PlaceHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchNote, setSearchNote] = useState("");
  const [moved, setMoved] = useState(false);

  useEffect(() => {
    fetch("/api/reports/meta")
      .then((response) => response.json())
      .then(setMeta)
      .catch(() => setError("Could not load form options."));
  }, []);

  useEffect(() => {
    if (!mapNode.current) {
      return;
    }
    const map = createMap(mapNode.current);
    map.setZoom(14);
    if (!webglAvailable()) {
      return () => map.remove();
    }
    const marker = new maplibregl.Marker({ color: "#dc2626", draggable: true })
      .setLngLat(CENTER)
      .addTo(map);
    marker.on("dragend", () => {
      const pos = marker.getLngLat();
      setLng(pos.lng);
      setLat(pos.lat);
      setMoved(true);
    });
    map.on("click", (event) => {
      marker.setLngLat(event.lngLat);
      setLng(event.lngLat.lng);
      setLat(event.lngLat.lat);
      setMoved(true);
    });
    markerRef.current = marker;
    mapRef.current = map;
    // Road names help people recognise where they are; a failure here must not break reporting.
    onStyleReady(map, () => void addRoadLabels(map).catch(() => undefined));
    return () => {
      marker.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  const t = (en: string, bn: string) => (lang === "bn" ? bn : en);

  async function useGps() {
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const next: [number, number] = [pos.coords.longitude, pos.coords.latitude];
        setLng(next[0]);
        setLat(next[1]);
        markerRef.current?.setLngLat(next);
        mapRef.current?.flyTo({ center: next, zoom: 17 });
        setMoved(true);
      },
      () => setError(t("Location permission was denied.", "অবস্থান অনুমতি দেওয়া হয়নি।")),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  }

  // Road names from our own data suggest instantly while typing.
  useEffect(() => {
    let current = true;
    if (justChose.current) {
      justChose.current = false; // the query was set by picking a result, so do not suggest again
      return;
    }
    if (query.trim().length < 2) {
      setHits([]);
      return;
    }
    searchRoads(query)
      .then((roads) => current && setHits((prev) => [...roads, ...prev.filter((h) => h.kind === "place")]))
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [query]);

  async function runSearch() {
    if (query.trim().length < 2) return;
    setSearching(true);
    setSearchNote("");
    try {
      const [roads, places] = await Promise.all([searchRoads(query).catch(() => [] as PlaceHit[]), searchPlaces(query).catch(() => null)]);
      setHits([...roads, ...(places ?? [])]);
      if (places === null) setSearchNote(t("Online place search is unavailable; showing road names only.", "অনলাইন স্থান খোঁজা এখন পাওয়া যাচ্ছে না; শুধু রাস্তার নাম দেখানো হচ্ছে।"));
      else if (!roads.length && !places.length) setSearchNote(t("Nothing found. Try a road name, market, school or mosque, or tap the map.", "কিছু পাওয়া যায়নি। রাস্তা, বাজার, স্কুল বা মসজিদের নাম লিখুন, অথবা মানচিত্রে ট্যাপ করুন।"));
    } finally {
      setSearching(false);
    }
  }

  function choose(hit: PlaceHit) {
    const next: [number, number] = [hit.lon, hit.lat];
    markerRef.current?.setLngLat(next);
    mapRef.current?.flyTo({ center: next, zoom: 17, essential: true });
    setLng(hit.lon);
    setLat(hit.lat);
    setMoved(true);
    setHits([]);
    justChose.current = true;
    setQuery(hit.label);
    // Help fill the required place box, without overwriting what the person already typed.
    if (placeRef.current && !placeRef.current.value.trim()) {
      placeRef.current.value = hit.kind === "place" && hit.sub ? `${hit.label}, ${hit.sub.split(",")[0]}` : hit.label;
    }
  }

  async function toggle3d(on: boolean) {
    const map = mapRef.current;
    if (!map) return;
    setView3d(on);
    if (on) {
      try {
        await addBuildings3D(map);
      } catch {
        setSearchNote(t("Buildings could not be loaded; the 3D view shows roads only.", "ভবন লোড করা যায়নি; ৩ডি ভিউতে শুধু রাস্তা দেখানো হচ্ছে।"));
      }
    }
    set3D(map, on, []);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Marking the map is optional: a known landmark typed in the place box is placed by the server.
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    form.set("latitude", String(lat));
    form.set("longitude", String(lng));
    form.set("language", lang);
    form.set("pin_set", String(moved));
    try {
      const response = await fetch("/api/reports", { method: "POST", body: form });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.detail ?? t("Could not submit.", "জমা দেওয়া যায়নি।"));
      }
      setCreated(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <div className="mx-auto max-w-lg p-6">
        <h1 className="text-xl font-semibold">{t("Report received", "রিপোর্ট গৃহীত হয়েছে")}</h1>
        <p className="mt-2 text-slate-300">
          {t("This is a citizen report, not a verified issue.", "এটি নাগরিক রিপোর্ট, যাচাইকৃত সমস্যা নয়।")}
        </p>
        <p className="mt-4 text-lg font-mono text-emerald-400">{created.tracking_id}</p>
        <p className="mt-1 text-sm text-slate-400">
          {t("Save this ID to check status later.", "পরে অবস্থা দেখতে এই আইডিটি রাখুন।")}
        </p>
        <Link className="mt-6 inline-block text-sky-400" to={`/track/${created.tracking_id}`}>
          {t("Track this report", "এই রিপোর্ট ট্র্যাক করুন")}
        </Link>
      </div>
    );
  }

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_auto] overflow-y-auto lg:grid-cols-2 lg:grid-rows-1 lg:overflow-hidden">
      <form className="space-y-3 p-5 lg:overflow-auto" onSubmit={onSubmit}>
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">{t("Report a city problem", "শহরের সমস্যা জানান")}</h1>
          <button
            type="button"
            className="text-xs text-sky-400"
            onClick={() => setLang(lang === "en" ? "bn" : "en")}
          >
            {lang === "en" ? "বাংলা" : "English"}
          </button>
        </div>
        <p className="text-xs text-slate-400">
          {t(
            "Your submission stays a report until an officer verifies it.",
            "অফিসার যাচাই করার আগে এটি শুধু রিপোর্ট হিসেবে থাকবে।",
          )}
        </p>
        <label className="block text-sm">
          {t("Category", "ধরন")}
          <select name="category" required className="mt-1 w-full rounded bg-slate-900 p-2">
            {meta &&
              Object.entries(meta.categories).map(([id, labels]) => (
                <option key={id} value={id}>
                  {labels[lang]}
                </option>
              ))}
          </select>
        </label>
        <label className="block text-sm">
          {t("Severity", "তীব্রতা")}
          <select name="severity" required className="mt-1 w-full rounded bg-slate-900 p-2">
            {(meta?.severities ?? ["medium"]).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          {t("Description", "বিবরণ")}
          <textarea name="description" required minLength={8} rows={4} className="mt-1 w-full rounded bg-slate-900 p-2" />
        </label>
        <label className="block text-sm">
          {t("Place or landmark (required)", "জায়গা বা পরিচিত স্থান (আবশ্যক)")}
          <input
            name="location_text"
            ref={placeRef}
            required
            maxLength={200}
            placeholder={t("e.g. near Shonapur Zero Point, in front of the market", "যেমন: সোনাপুর জিরো পয়েন্টের কাছে, বাজারের সামনে")}
            className="mt-1 w-full rounded bg-slate-900 p-2"
          />
        </label>
        <label className="block text-sm">
          {t("Your name (optional)", "আপনার নাম (ঐচ্ছিক)")}
          <input name="reporter_name" className="mt-1 w-full rounded bg-slate-900 p-2" />
        </label>
        <label className="block text-sm">
          {t("Photos (required: JPEG/PNG/WebP, 1 to 3)", "ছবি (আবশ্যক: JPEG/PNG/WebP, ১ থেকে ৩টি)")}
          <input name="files" type="file" required accept="image/jpeg,image/png,image/webp" multiple className="mt-1 w-full text-sm" />
        </label>
        <div className="flex items-center justify-between text-sm">
          <span>
            GPS: {lat.toFixed(5)}, {lng.toFixed(5)}
          </span>
          <button type="button" className="text-sky-400" onClick={() => void useGps()}>
            {t("Use my location", "আমার অবস্থান ব্যবহার করুন")}
          </button>
        </div>
        {error ? <p className="text-sm text-amber-400">{error}</p> : null}
        <p className="text-xs text-slate-500">
          {t(
            "Your photo is stored for municipal review. Staff may use automated tools, including third-party AI services, to help assess it. Please avoid photographing faces or number plates.",
            "আপনার ছবি পৌরসভার পর্যালোচনার জন্য সংরক্ষিত থাকবে। কর্মীরা এটি যাচাইয়ে স্বয়ংক্রিয় টুল, এমনকি তৃতীয়-পক্ষের এআই সেবাও ব্যবহার করতে পারেন। অনুগ্রহ করে মুখ বা গাড়ির নম্বর প্লেটের ছবি তোলা এড়িয়ে চলুন।",
          )}
        </p>
        <button disabled={busy} className="w-full rounded bg-sky-700 py-2 font-medium disabled:opacity-50">
          {busy ? t("Submitting…", "জমা হচ্ছে…") : t("Submit report", "রিপোর্ট জমা দিন")}
        </button>
      </form>
      <div className="relative order-first h-[280px] border-b border-slate-800 lg:order-none lg:h-auto lg:min-h-[320px] lg:border-b-0 lg:border-l">
        <div ref={mapNode} className="absolute inset-0" style={{ position: "absolute", inset: 0 }} />
        <div className="absolute left-3 right-3 top-3 z-10 max-w-md space-y-1.5">
          <form
            className="flex gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              void runSearch();
            }}
            role="search"
          >
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("Search a road, market, school, mosque…", "রাস্তা, বাজার, স্কুল, মসজিদ খুঁজুন…")}
              aria-label={t("Search for a place", "স্থান খুঁজুন")}
              className="min-w-0 flex-1 rounded-md border border-slate-600 bg-slate-950/90 px-3 py-2 text-sm shadow"
            />
            <button type="submit" disabled={searching} className="rounded-md bg-sky-600 px-3 text-sm font-medium text-white shadow disabled:opacity-50">
              {searching ? "…" : t("Search", "খুঁজুন")}
            </button>
          </form>
          {hits.length ? (
            <ul className="max-h-64 overflow-auto rounded-md border border-slate-700 bg-slate-950/95 text-sm shadow">
              {hits.map((h, i) => (
                <li key={`${h.kind}-${h.label}-${i}`}>
                  <button type="button" onClick={() => choose(h)} className="block w-full px-3 py-2 text-left hover:bg-slate-800">
                    <span className="font-medium text-slate-100">{h.label}</span>
                    {h.sub ? <span className="block truncate text-[11px] text-slate-400">{h.sub}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {searchNote ? <p className="rounded-md bg-slate-950/90 px-3 py-1.5 text-[11px] text-amber-300">{searchNote}</p> : null}
          <p className="pointer-events-none inline-block rounded-md bg-slate-950/85 px-3 py-1.5 text-[11px] text-slate-100 shadow">
            {t("Search, or tap the map / drag the red pin to mark where the problem is.", "খুঁজুন, অথবা সমস্যার জায়গা চিহ্নিত করতে মানচিত্রে ট্যাপ করুন বা লাল পিন টেনে আনুন।")}
          </p>
        </div>
        <div className="absolute bottom-8 right-3 z-10 flex gap-1 rounded-lg border border-slate-700 bg-slate-950/90 p-0.5 shadow">
          {[false, true].map((on) => (
            <button
              key={String(on)}
              type="button"
              onClick={() => void toggle3d(on)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${view3d === on ? "bg-sky-500 text-slate-950" : "text-slate-300 hover:text-white"}`}
            >
              {on ? "3D" : "2D"}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
