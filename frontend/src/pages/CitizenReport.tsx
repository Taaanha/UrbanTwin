import { FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import maplibregl from "maplibre-gl";
import { createMap, webglAvailable } from "../map";

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
    });
    map.on("click", (event) => {
      marker.setLngLat(event.lngLat);
      setLng(event.lngLat.lng);
      setLat(event.lngLat.lat);
    });
    markerRef.current = marker;
    return () => {
      marker.remove();
      map.remove();
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
      },
      () => setError(t("Location permission was denied.", "অবস্থান অনুমতি দেওয়া হয়নি।")),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lat === CENTER[1] && lng === CENTER[0]) {
      setError(t("Please tap the map (or use your location) to mark where the problem is. The pin has not been moved yet.", "সমস্যার জায়গাটি মানচিত্রে ট্যাপ করে বা আপনার অবস্থান ব্যবহার করে চিহ্নিত করুন। পিন এখনো সরানো হয়নি।"));
      return;
    }
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    form.set("latitude", String(lat));
    form.set("longitude", String(lng));
    form.set("language", lang);
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
          {t("Your name (optional)", "আপনার নাম (ঐচ্ছিক)")}
          <input name="reporter_name" className="mt-1 w-full rounded bg-slate-900 p-2" />
        </label>
        <label className="block text-sm">
          {t("Photos (JPEG/PNG/WebP, max 3)", "ছবি (JPEG/PNG/WebP, সর্বোচ্চ ৩টি)")}
          <input name="files" type="file" accept="image/jpeg,image/png,image/webp" multiple className="mt-1 w-full text-sm" />
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
        <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-md bg-slate-950/85 px-3 py-2 text-xs text-slate-100 shadow">
          {t("Tap the map (or drag the red pin) to mark where the problem is.", "সমস্যার জায়গা চিহ্নিত করতে মানচিত্রে ট্যাপ করুন বা লাল পিন টেনে আনুন।")}
        </div>
      </div>
    </div>
  );
}
